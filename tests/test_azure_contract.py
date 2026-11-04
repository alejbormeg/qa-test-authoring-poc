"""Contrato del cliente de Azure DevOps contra el simulador (mismas rutas y payloads que el servicio real)."""

from __future__ import annotations

import httpx
import pytest

from mocks.azure_devops import store as az
from mocks.azure_devops.console import parse_steps
from qa_assistant.adapters.azure_devops import AzureAuthError, AzureDevOps


def test_features_and_existing_cases(fresh_azure):
    api = AzureDevOps()
    assert {f["id"] for f in api.features()} == {101, 102, 103, 104, 105}
    cases = api.test_cases()
    assert len(cases) == 5
    assert all(c["fields"]["Microsoft.VSTS.TCM.AutomationStatus"] == "Automated" for c in cases)


def test_create_test_case_linked_to_feature_and_suite(fresh_azure):
    api = AzureDevOps()
    steps = [("Abrir la página carrito", ""), ("Pulsar <Tramitar>", "Se muestra el login & el aviso")]
    wi = api.create_test_case({"System.Title": "TC-X · Prueba", "Microsoft.VSTS.TCM.Steps": az.steps_xml(steps),
                               "Microsoft.VSTS.TCM.AutomatedTestName": "QaWeb.Tests.Generated.XTests.TC_X",
                               "Microsoft.VSTS.TCM.AutomationStatus": "Automated"}, feature_id=103)
    got = api.work_item(wi["id"])
    assert got["fields"]["System.WorkItemType"] == "Test Case"
    assert any(r["rel"] == "Microsoft.VSTS.Common.TestedBy-Reverse" and r["url"].endswith("/103")
               for r in got["relations"])
    assert parse_steps(got["fields"]["Microsoft.VSTS.TCM.Steps"]) == steps

    plan = next(p for p in api.plans() if p["id"] == 20)
    suite = api.create_suite(20, "v9.9", plan["rootSuite"]["id"])
    api.add_to_suite(20, suite["id"], [wi["id"]])
    api.add_to_suite(20, suite["id"], [wi["id"]])  # idempotente
    assert api.suite_cases(20, suite["id"]) == [wi["id"]]


def test_retries_on_503_and_reports(fresh_azure):
    msgs: list[str] = []
    az.load()["faults"].update(mode="503", remaining=2)
    api = AzureDevOps(on_retry=msgs.append)
    assert len(api.plans()) == 2
    assert len(msgs) == 2 and "503" in msgs[0]


def test_expired_pat_is_not_retried(fresh_azure):
    az.load()["faults"].update(mode="401", remaining=1)
    with pytest.raises(AzureAuthError):
        AzureDevOps(retries=3).plans()
    assert az.load()["faults"]["mode"] is None


def test_requests_without_pat_are_rejected(fresh_azure):
    r = httpx.get(f"{fresh_azure.azure_url}/_apis/testplan/plans")
    assert r.status_code == 401


def test_pr_requires_approval_before_merge(fresh_azure):
    from qa_assistant.adapters import git as gitops
    from qa_assistant.adapters.workspace import Workspace

    ws = Workspace(fresh_azure.data_dir / "ws-pr-test")
    ws.prepare("feature/x")
    ws.write("Tests/Generated/X/TC_X.cs", "// test\n")
    ws.commit_and_push("feature/x", "test")
    api = AzureDevOps()
    pr = api.create_pr(fresh_azure.azure_repo, "feature/x", "Prueba", "desc")
    base = f"{fresh_azure.azure_url}/_apis/git/repositories/{fresh_azure.azure_repo}/pullrequests/{pr['pullRequestId']}"
    auth = ("", "pat")
    assert httpx.patch(base, json={"status": "completed"}, auth=auth).status_code == 409
    httpx.put(f"{base}/reviewers/qa.lead", json={"vote": 10}, auth=auth).raise_for_status()
    httpx.patch(base, json={"status": "completed"}, auth=auth).raise_for_status()
    assert api.pr(fresh_azure.azure_repo, pr["pullRequestId"])["status"] == "completed"
    assert gitops.show(fresh_azure.remote_repo, "main", "Tests/Generated/X/TC_X.cs") == "// test\n"
