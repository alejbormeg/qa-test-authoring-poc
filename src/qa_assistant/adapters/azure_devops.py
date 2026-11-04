"""Cliente REST de Azure DevOps (api-version 7.1).

Funciona igual contra el simulador y contra dev.azure.com: solo cambian AZURE_BASE_URL y AZURE_PAT.
Reintenta los 5xx y los errores de red con espera exponencial; un 401 no se reintenta.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any

import httpx

from ..config import settings

API = "7.1"
TESTED_BY_REVERSE = "Microsoft.VSTS.Common.TestedBy-Reverse"


class AzureError(RuntimeError):
    pass


class AzureAuthError(AzureError):
    pass


class AzureDevOps:
    def __init__(self, base_url: str | None = None, pat: str | None = None, user: str = "Asistente QA",
                 on_retry: Callable[[str], None] | None = None, retries: int = 4) -> None:
        self.base = (base_url or settings.azure_url).rstrip("/")
        token = base64.b64encode(f":{pat or settings.azure_pat}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "X-QA-User": user, "Accept": "application/json"}
        self.on_retry = on_retry or (lambda _msg: None)
        self.retries = retries

    # ------------------------------------------------------------ transporte

    def _request(self, method: str, path: str, *, json: Any = None, params: dict | None = None,
                 content_type: str = "application/json") -> Any:
        url = f"{self.base}/_apis/{path}"
        params = {"api-version": API, **(params or {})}
        delay = 0.5
        for attempt in range(self.retries + 1):
            try:
                resp = httpx.request(method, url, json=json, params=params, timeout=30,
                                     headers={**self.headers, "Content-Type": content_type})
            except httpx.TransportError as e:
                if attempt == self.retries:
                    raise AzureError(f"Azure DevOps no responde ({e.__class__.__name__})") from e
                self.on_retry(f"Azure DevOps no responde; reintento {attempt + 1} en {delay:.1f}s")
            else:
                if resp.status_code == 401:
                    raise AzureAuthError("Azure DevOps rechaza el PAT (401): renueva el token y reintenta")
                if resp.status_code >= 500 or resp.status_code == 429:
                    if attempt == self.retries:
                        raise AzureError(f"Azure DevOps devuelve {resp.status_code} tras {attempt + 1} intentos")
                    self.on_retry(f"Azure DevOps devuelve {resp.status_code}; reintento {attempt + 1} en {delay:.1f}s")
                elif resp.status_code >= 400:
                    raise AzureError(f"{method} {path}: {resp.status_code} {resp.text[:300]}")
                else:
                    return resp.json() if resp.content else None
            time.sleep(delay)
            delay = min(delay * 2, 8)
        raise AzureError("No se pudo completar la llamada")

    # ------------------------------------------------------------ work items

    def work_item(self, wid: int) -> dict:
        return self._request("GET", f"wit/workitems/{wid}", params={"$expand": "relations"})

    def work_items_by_type(self, wtype: str) -> list[dict]:
        q = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project "
                      f"AND [System.WorkItemType] = '{wtype}' ORDER BY [System.Id]"}
        ids = [w["id"] for w in self._request("POST", "wit/wiql", json=q)["workItems"]]
        if not ids:
            return []
        out: list[dict] = []
        for i in range(0, len(ids), 200):
            chunk = ",".join(str(x) for x in ids[i:i + 200])
            out += self._request("GET", "wit/workitems", params={"ids": chunk, "$expand": "relations"})["value"]
        return out

    def features(self) -> list[dict]:
        return self.work_items_by_type("Feature")

    def test_cases(self) -> list[dict]:
        return self.work_items_by_type("Test Case")

    def create_test_case(self, fields: dict[str, Any], feature_id: int) -> dict:
        ops = [{"op": "add", "path": f"/fields/{k}", "value": v} for k, v in fields.items()]
        ops.append({"op": "add", "path": "/relations/-", "value": {
            "rel": TESTED_BY_REVERSE, "url": f"{self.base}/_apis/wit/workItems/{feature_id}",
            "attributes": {"comment": "Creado por el asistente de QA"}}})
        return self._request("POST", "wit/workitems/$Test Case", json=ops, content_type="application/json-patch+json")

    # ------------------------------------------------------------ test plans

    def plans(self) -> list[dict]:
        return self._request("GET", "testplan/plans")["value"]

    def suites(self, plan_id: int) -> list[dict]:
        return self._request("GET", f"testplan/Plans/{plan_id}/suites")["value"]

    def create_suite(self, plan_id: int, name: str, parent_id: int) -> dict:
        return self._request("POST", f"testplan/Plans/{plan_id}/suites",
                             json={"name": name, "suiteType": "staticTestSuite", "parentSuite": {"id": parent_id}})

    def suite_cases(self, plan_id: int, suite_id: int) -> list[int]:
        res = self._request("GET", f"testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase")["value"]
        return [x["workItem"]["id"] for x in res]

    def add_to_suite(self, plan_id: int, suite_id: int, ids: list[int]) -> None:
        self._request("POST", f"testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase",
                      json=[{"workItem": {"id": i}} for i in ids])

    # ------------------------------------------------------------ pull requests

    def create_pr(self, repo: str, branch: str, title: str, description: str) -> dict:
        return self._request("POST", f"git/repositories/{repo}/pullrequests", json={
            "sourceRefName": f"refs/heads/{branch}", "targetRefName": "refs/heads/main",
            "title": title, "description": description})

    def pr(self, repo: str, pr_id: int) -> dict:
        return self._request("GET", f"git/repositories/{repo}/pullrequests/{pr_id}")


def html_link(wid: int) -> str:
    return f"{settings.azure_console_url}/?wi={wid}"
