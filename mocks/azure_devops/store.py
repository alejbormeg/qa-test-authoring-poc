"""Estado del Azure DevOps simulado: work items, test plans, suites y pull requests.

Se guarda en un JSON (`.data/azure-mock.json`) para sobrevivir a reinicios. Todo el acceso pasa por un
lock porque la API y la consola comparten el mismo proceso.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import UTC, datetime
from html import escape
from typing import Any

from qa_assistant.adapters import git as gitops
from qa_assistant.config import settings

_lock = threading.RLock()
_state: dict[str, Any] | None = None

REPO_ID = "5b1f6a62-6f2e-4b7d-9a43-2f5f0c0a7e11"
FEATURE_STATE = "Active"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty() -> dict[str, Any]:
    return {
        "next_id": 300,
        "next_pr": 40,
        "work_items": {},
        "plans": {},
        "suites": {},
        "pull_requests": {},
        "faults": {"mode": None, "remaining": 0},
        "events": [],
    }


def load() -> dict[str, Any]:
    global _state
    with _lock:
        if _state is None:
            f = settings.azure_state_file
            _state = json.loads(f.read_text(encoding="utf-8")) if f.exists() else _empty()
        return _state


def save() -> None:
    with _lock:
        settings.azure_state_file.write_text(json.dumps(load(), ensure_ascii=False, indent=1), encoding="utf-8")


def reset(state: dict[str, Any] | None = None) -> None:
    global _state
    with _lock:
        _state = state or _empty()
        save()


def event(kind: str, text: str) -> None:
    with _lock:
        evs = load()["events"]
        evs.insert(0, {"at": now(), "kind": kind, "text": text})
        del evs[200:]


def base_url() -> str:
    return settings.azure_url


# ---------------------------------------------------------------- work items

def wi_url(wid: int) -> str:
    return f"{base_url()}/_apis/wit/workItems/{wid}"


def create_work_item(wtype: str, fields: dict[str, Any], relations: list[dict] | None = None, *, wid: int | None = None,
                     by: str = "Asistente QA") -> dict:
    with _lock:
        st = load()
        if wid is None:
            wid = st["next_id"]
            st["next_id"] += 1
        f = {
            "System.Id": wid,
            "System.WorkItemType": wtype,
            "System.TeamProject": settings.azure_project,
            "System.State": "Design" if wtype == "Test Case" else FEATURE_STATE,
            "System.CreatedDate": now(),
            "System.CreatedBy": by,
            "System.ChangedDate": now(),
            **fields,
        }
        item = {"id": wid, "rev": 1, "fields": f, "relations": relations or []}
        st["work_items"][str(wid)] = item
        event("workitem", f"{wtype} #{wid} creado: {f.get('System.Title', '')}")
        save()
        return item


def get_work_item(wid: int) -> dict | None:
    with _lock:
        return copy.deepcopy(load()["work_items"].get(str(wid)))


def update_work_item(wid: int, fields: dict[str, Any], add_relations: list[dict] | None = None) -> dict | None:
    with _lock:
        item = load()["work_items"].get(str(wid))
        if item is None:
            return None
        item["fields"].update(fields)
        item["fields"]["System.ChangedDate"] = now()
        item["relations"].extend(add_relations or [])
        item["rev"] += 1
        event("workitem", f"#{wid} actualizado")
        save()
        return copy.deepcopy(item)


def work_items(wtype: str | None = None) -> list[dict]:
    with _lock:
        items = [copy.deepcopy(w) for w in load()["work_items"].values()]
    if wtype:
        items = [w for w in items if w["fields"]["System.WorkItemType"].lower() == wtype.lower()]
    return sorted(items, key=lambda w: w["id"])


def related_ids(item: dict, rel: str) -> list[int]:
    return [int(r["url"].rstrip("/").rsplit("/", 1)[-1]) for r in item.get("relations", []) if r["rel"] == rel]


def tests_of_feature(feature_id: int) -> list[dict]:
    return [w for w in work_items("Test Case") if feature_id in related_ids(w, "Microsoft.VSTS.Common.TestedBy-Reverse")]


# ---------------------------------------------------------------- test plans

def create_plan(name: str, *, area: str = "QA-Web", iteration: str = "QA-Web", pid: int | None = None) -> dict:
    with _lock:
        st = load()
        if pid is None:
            pid = st["next_id"]
            st["next_id"] += 1
        root = create_suite(pid, name, parent=None, suite_type="staticTestSuite")
        plan = {"id": pid, "name": name, "areaPath": area, "iteration": iteration, "state": "Active",
                "rootSuite": {"id": root["id"], "name": root["name"]}, "updatedDate": now()}
        st["plans"][str(pid)] = plan
        event("plan", f"Test Plan #{pid} creado: {name}")
        save()
        return plan


def create_suite(plan_id: int, name: str, parent: int | None, suite_type: str = "staticTestSuite") -> dict:
    with _lock:
        st = load()
        sid = st["next_id"]
        st["next_id"] += 1
        suite = {"id": sid, "name": name, "planId": plan_id, "parentSuiteId": parent, "suiteType": suite_type,
                 "testCaseIds": [], "lastUpdatedDate": now()}
        st["suites"][str(sid)] = suite
        if parent is not None:
            event("suite", f"Suite #{sid} «{name}» creada en el plan #{plan_id}")
        save()
        return suite


def plans() -> list[dict]:
    with _lock:
        return sorted(copy.deepcopy(list(load()["plans"].values())), key=lambda p: p["id"])


def suites(plan_id: int) -> list[dict]:
    with _lock:
        return sorted([copy.deepcopy(s) for s in load()["suites"].values() if s["planId"] == plan_id], key=lambda s: s["id"])


def get_suite(suite_id: int) -> dict | None:
    with _lock:
        return copy.deepcopy(load()["suites"].get(str(suite_id)))


def add_test_cases(suite_id: int, ids: list[int]) -> list[int]:
    with _lock:
        suite = load()["suites"].get(str(suite_id))
        if suite is None:
            raise KeyError(suite_id)
        added = [i for i in ids if i not in suite["testCaseIds"]]
        suite["testCaseIds"].extend(added)
        suite["lastUpdatedDate"] = now()
        if added:
            event("suite", f"{len(added)} caso(s) añadidos a la suite «{suite['name']}»")
        save()
        return added


# ---------------------------------------------------------------- pull requests

def create_pr(source: str, target: str, title: str, description: str, by: str) -> dict:
    with _lock:
        st = load()
        pid = st["next_pr"]
        st["next_pr"] += 1
        branch = source.removeprefix("refs/heads/")
        pr = {
            "pullRequestId": pid,
            "repository": {"id": REPO_ID, "name": settings.azure_repo},
            "title": title,
            "description": description,
            "sourceRefName": source,
            "targetRefName": target,
            "status": "active",
            "mergeStatus": "succeeded",
            "createdBy": {"displayName": by},
            "creationDate": now(),
            "closedDate": None,
            "reviewers": [],
            "lastMergeSourceCommit": {"commitId": gitops.head(settings.remote_repo, branch)},
            "lastMergeCommit": None,
            "url": f"{base_url()}/_apis/git/repositories/{REPO_ID}/pullRequests/{pid}",
        }
        st["pull_requests"][str(pid)] = pr
        event("pr", f"PR !{pid} abierta: {title}")
        save()
        return copy.deepcopy(pr)


def get_pr(pid: int) -> dict | None:
    with _lock:
        pr = load()["pull_requests"].get(str(pid))
        if pr and pr["status"] == "active":
            branch = pr["sourceRefName"].removeprefix("refs/heads/")
            if gitops.branch_exists(settings.remote_repo, branch):
                pr["lastMergeSourceCommit"] = {"commitId": gitops.head(settings.remote_repo, branch)}
        return copy.deepcopy(pr)


def list_prs(status: str | None = None) -> list[dict]:
    with _lock:
        prs = [copy.deepcopy(p) for p in load()["pull_requests"].values()]
    if status and status != "all":
        prs = [p for p in prs if p["status"] == status]
    return sorted(prs, key=lambda p: -p["pullRequestId"])


def vote(pid: int, reviewer: str, value: int) -> dict:
    with _lock:
        pr = load()["pull_requests"][str(pid)]
        pr["reviewers"] = [r for r in pr["reviewers"] if r["displayName"] != reviewer]
        pr["reviewers"].append({"displayName": reviewer, "id": reviewer, "vote": value, "isRequired": False})
        label = {10: "aprueba", 5: "aprueba con sugerencias", 0: "sin voto", -5: "espera al autor", -10: "rechaza"}[value]
        event("pr", f"{reviewer} {label} la PR !{pid}")
        save()
        return copy.deepcopy(pr)


def complete_pr(pid: int, by: str) -> dict:
    with _lock:
        pr = load()["pull_requests"][str(pid)]
        if pr["status"] != "active":
            return copy.deepcopy(pr)
        if not any(r["vote"] >= 5 for r in pr["reviewers"]):
            raise PermissionError("La política de rama exige al menos una aprobación")
        branch = pr["sourceRefName"].removeprefix("refs/heads/")
        target = pr["targetRefName"].removeprefix("refs/heads/")
        commit = gitops.merge_into(settings.remote_repo, branch,
                                   f"Merged PR {pid}: {pr['title']}", target=target)
        pr.update(status="completed", closedDate=now(), lastMergeCommit={"commitId": commit},
                  closedBy={"displayName": by})
        event("pr", f"PR !{pid} completada por {by} (merge {commit[:8]})")
        save()
        return copy.deepcopy(pr)


def abandon_pr(pid: int, by: str) -> dict:
    with _lock:
        pr = load()["pull_requests"][str(pid)]
        pr.update(status="abandoned", closedDate=now(), closedBy={"displayName": by})
        event("pr", f"PR !{pid} abandonada por {by}")
        save()
        return copy.deepcopy(pr)


# ---------------------------------------------------------------- utilidades

def steps_xml(steps: list[tuple[str, str]]) -> str:
    """Formato de Microsoft.VSTS.TCM.Steps (pasos con acción y resultado esperado)."""
    parts = []
    for i, (action, expected) in enumerate(steps, start=2):
        kind = "ValidateStep" if expected else "ActionStep"
        a = escape(f"<DIV><P>{escape(action)}</P></DIV>")
        e = escape(f"<DIV><P>{escape(expected)}</P></DIV>") if expected else ""
        parts.append(f'<step id="{i}" type="{kind}"><parameterizedString isformatted="true">{a}</parameterizedString>'
                     f'<parameterizedString isformatted="true">{e}</parameterizedString><description/></step>')
    return f'<steps id="0" last="{len(steps) + 1}">{"".join(parts)}</steps>'


def new_automation_id() -> str:
    return str(uuid.uuid4())
