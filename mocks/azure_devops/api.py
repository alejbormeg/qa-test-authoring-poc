"""Subconjunto de la REST API de Azure DevOps 7.1 que usa el asistente.

Mismas rutas, payloads JSON Patch y formas de respuesta que el servicio real, para que el cliente del
asistente funcione igual contra dev.azure.com cambiando solo la URL base y el PAT.
"""

from __future__ import annotations

import base64
import re
from typing import Any

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import store

router = APIRouter(prefix="/{org}/{project}/_apis")

TESTED_BY_REVERSE = "Microsoft.VSTS.Common.TestedBy-Reverse"


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def azure_like(request: Request, call_next):
        path = request.scope["path"]
        if "/_apis/" in path:
            head, tail = path.split("/_apis/", 1)
            request.scope["path"] = f"{head}/_apis/{tail.lower()}"
            auth = request.headers.get("authorization", "")
            if not auth.lower().startswith("basic ") or not _pat(auth):
                return JSONResponse({"message": "TF400813: El usuario no está autorizado."}, status_code=401)
            faults = store.load()["faults"]
            if faults["mode"] and faults["remaining"] > 0:
                faults["remaining"] -= 1
                mode = faults["mode"]
                if faults["remaining"] == 0:
                    faults["mode"] = None
                store.event("fallo", f"Fallo simulado {mode} en {request.method} /_apis/{tail}")
                store.save()
                if mode == "401":
                    return JSONResponse({"message": "TF400813: El token de acceso personal ha caducado."}, status_code=401)
                return JSONResponse({"message": "Service Unavailable (simulado)"}, status_code=503,
                                    headers={"Retry-After": "1"})
        return await call_next(request)

    app.include_router(router)


def _pat(auth: str) -> str:
    try:
        return base64.b64decode(auth.split(" ", 1)[1]).decode().split(":", 1)[-1]
    except Exception:
        return ""


def _user(request: Request) -> str:
    return request.headers.get("x-qa-user") or "Asistente QA"


def _wi(item: dict) -> dict:
    return {**item, "url": store.wi_url(item["id"]),
            "_links": {"html": {"href": f"{store.base_url()}/_workitems/edit/{item['id']}"}}}


# ---------------------------------------------------------------- work items

@router.post("/wit/workitems/{wtype}")
def create_work_item(wtype: str, request: Request, ops: list[dict[str, Any]] = Body(...)) -> dict:
    wtype = wtype.lstrip("$")
    names = {"test case": "Test Case", "feature": "Feature"}
    if wtype not in names:
        raise HTTPException(400, f"Tipo de work item no soportado en el simulador: {wtype}")
    fields, relations = _apply_ops(ops)
    return _wi(store.create_work_item(names[wtype], fields, relations, by=_user(request)))


@router.get("/wit/workitems/{wid}")
def get_work_item(wid: int) -> dict:
    item = store.get_work_item(wid)
    if not item:
        raise HTTPException(404, f"TF401232: El work item {wid} no existe.")
    return _wi(item)


@router.get("/wit/workitems")
def get_work_items(ids: str) -> dict:
    items = [store.get_work_item(int(i)) for i in ids.split(",") if i.strip()]
    found = [_wi(i) for i in items if i]
    return {"count": len(found), "value": found}


@router.patch("/wit/workitems/{wid}")
def update_work_item(wid: int, ops: list[dict[str, Any]] = Body(...)) -> dict:
    fields, relations = _apply_ops(ops)
    item = store.update_work_item(wid, fields, relations)
    if not item:
        raise HTTPException(404, f"TF401232: El work item {wid} no existe.")
    return _wi(item)


@router.post("/wit/wiql")
def wiql(body: dict = Body(...)) -> dict:
    query = body.get("query", "")
    m = re.search(r"\[System\.WorkItemType\]\s*=\s*'([^']+)'", query, re.I)
    items = store.work_items(m.group(1) if m else None)
    return {"queryType": "flat", "asOf": store.now(),
            "workItems": [{"id": w["id"], "url": store.wi_url(w["id"])} for w in items]}


def _apply_ops(ops: list[dict[str, Any]]) -> tuple[dict, list]:
    fields: dict[str, Any] = {}
    relations: list[dict] = []
    for op in ops:
        path = op.get("path", "")
        if op.get("op") not in ("add", "replace"):
            raise HTTPException(400, f"Operación JSON Patch no soportada: {op.get('op')}")
        if path.startswith("/fields/"):
            fields[path.removeprefix("/fields/")] = op.get("value")
        elif path == "/relations/-":
            relations.append(op["value"])
        else:
            raise HTTPException(400, f"Ruta JSON Patch no soportada: {path}")
    return fields, relations


# ---------------------------------------------------------------- test plans

@router.get("/testplan/plans")
def list_plans() -> dict:
    p = store.plans()
    return {"count": len(p), "value": p}


@router.get("/testplan/plans/{plan_id}")
def get_plan(plan_id: int) -> dict:
    for p in store.plans():
        if p["id"] == plan_id:
            return p
    raise HTTPException(404, "Test plan no encontrado")


def _suite(s: dict) -> dict:
    out = {k: v for k, v in s.items() if k not in ("testCaseIds", "parentSuiteId", "planId")}
    out["plan"] = {"id": s["planId"]}
    out["parentSuite"] = {"id": s["parentSuiteId"]} if s["parentSuiteId"] else None
    out["hasChildren"] = any(c["parentSuiteId"] == s["id"] for c in store.suites(s["planId"]))
    out["testCaseCount"] = len(s["testCaseIds"])
    return out


@router.get("/testplan/plans/{plan_id}/suites")
def list_suites(plan_id: int) -> dict:
    s = [_suite(x) for x in store.suites(plan_id)]
    return {"count": len(s), "value": s}


@router.post("/testplan/plans/{plan_id}/suites")
def create_suite(plan_id: int, body: dict = Body(...)) -> dict:
    parent = (body.get("parentSuite") or {}).get("id")
    if parent is None:
        raise HTTPException(400, "parentSuite.id es obligatorio")
    return _suite(store.create_suite(plan_id, body["name"], parent, body.get("suiteType", "staticTestSuite")))


@router.get("/testplan/plans/{plan_id}/suites/{suite_id}/testcase")
def list_suite_cases(plan_id: int, suite_id: int) -> dict:
    s = store.get_suite(suite_id)
    if not s:
        raise HTTPException(404, "Suite no encontrada")
    value = [{"workItem": {"id": i, "name": (store.get_work_item(i) or {}).get("fields", {}).get("System.Title")},
              "pointAssignments": []} for i in s["testCaseIds"]]
    return {"count": len(value), "value": value}


@router.post("/testplan/plans/{plan_id}/suites/{suite_id}/testcase")
def add_suite_cases(plan_id: int, suite_id: int, body: list[dict] = Body(...)) -> dict:
    ids = [int(x["workItem"]["id"]) for x in body]
    try:
        store.add_test_cases(suite_id, ids)
    except KeyError:
        raise HTTPException(404, "Suite no encontrada") from None
    return list_suite_cases(plan_id, suite_id)


# ---------------------------------------------------------------- git / pull requests

@router.get("/git/repositories/{repo}/pullrequests")
def list_prs(repo: str, request: Request) -> dict:
    status = request.query_params.get("searchcriteria.status") or request.query_params.get("searchCriteria.status")
    prs = store.list_prs(status or "active")
    return {"count": len(prs), "value": prs}


@router.post("/git/repositories/{repo}/pullrequests")
def create_pr(repo: str, request: Request, body: dict = Body(...)) -> dict:
    return store.create_pr(body["sourceRefName"], body.get("targetRefName", "refs/heads/main"), body["title"],
                           body.get("description", ""), _user(request))


@router.get("/git/repositories/{repo}/pullrequests/{pid}")
def get_pr(repo: str, pid: int) -> dict:
    pr = store.get_pr(pid)
    if not pr:
        raise HTTPException(404, "Pull request no encontrada")
    return pr


@router.patch("/git/repositories/{repo}/pullrequests/{pid}")
def update_pr(repo: str, pid: int, request: Request, body: dict = Body(...)) -> dict:
    status = body.get("status")
    if status == "completed":
        try:
            return store.complete_pr(pid, _user(request))
        except PermissionError as e:
            raise HTTPException(409, str(e)) from None
    if status == "abandoned":
        return store.abandon_pr(pid, _user(request))
    raise HTTPException(400, "Solo se admite status=completed|abandoned")


@router.put("/git/repositories/{repo}/pullrequests/{pid}/reviewers/{reviewer}")
def put_reviewer(repo: str, pid: int, reviewer: str, body: dict = Body(...)) -> dict:
    return store.vote(pid, body.get("displayName", reviewer), int(body.get("vote", 0)))
