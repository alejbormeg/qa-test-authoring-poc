"""Extracción simulada de los DFF, formato de mapeos, guardas del toolbox y gates del flujo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_assistant.adapters.dff import read_blocks, to_text
from qa_assistant.adapters.workspace import Workspace, format_mapping, method_name
from qa_assistant.llm.mock import MockLlm

DFF = Path(__file__).resolve().parents[1] / "sample_data" / "dff"


def extract(name: str):
    blocks = read_blocks(DFF / name)
    result, usage = MockLlm().extract(to_text(blocks), blocks, name)
    return result


def test_table_dff():
    r = extract("DFF_Carrito_cupones_v2.4.docx")
    assert [c.id for c in r.casos] == [f"TC-CARRITO-00{i}" for i in range(1, 7)]
    assert r.feature_ref == "#103" and r.version == "2.4"
    c2 = r.casos[1]
    assert len(c2.pasos) == 4 and "BIENVENIDA10" in c2.pasos[2].accion
    assert "80,10" in c2.pasos[-1].esperado
    assert not any(c.avisos for c in r.casos)


def test_prose_dff():
    r = extract("DFF_Checkout_v2.4.docx")
    assert [c.id for c in r.casos] == ["TC-CHK-001", "TC-CHK-002", "TC-CHK-003"]
    assert len(r.casos[0].pasos) == 8
    assert r.casos[2].resultado_esperado.startswith('La URL contiene "/login"')


def test_draft_dff_raises_warnings():
    r = extract("DFF_Area_cliente_borrador.docx")
    warnings = {c.id: " ".join(c.avisos) for c in r.casos}
    assert warnings["TC-PERFIL-001"] == ""
    assert "Paso poco concreto" in warnings["TC-PERFIL-002"]
    assert "Falta el resultado esperado" in warnings["TC-PERFIL-003"]
    assert "contradictorio" in warnings["TC-PERFIL-003"]


def test_mapping_format_matches_team_style():
    seed = Path(__file__).resolve().parents[1] / "sample_data/test-repo-seed/Mappings/login.json"
    text = seed.read_text(encoding="utf-8")
    assert format_mapping(json.loads(text)) == text


def test_method_names_are_valid_identifiers():
    assert method_name("TC-CARRITO-002", "Aplicar un cupón válido") == "TC_CARRITO_002_AplicarUnCuponValido"


def test_workspace_refuses_paths_outside_repo(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(PermissionError):
        ws.path("../fuera.txt")


def test_gate1_requires_decision_on_every_case(fresh_azure):
    from qa_assistant import store
    from qa_assistant.domain.models import CaseDraft, CaseStatus, Run, RunState
    from qa_assistant.pipeline import service

    run = store.add(Run(created_by="t", dff_name="x", dff_path="x", ai_mode="mock", feature_id=103,
                        feature_title="Carrito", plan_id=20, plan_name="R", suite_name="s", state=RunState.EXTRAIDO))
    a = store.add(CaseDraft(run_id=run.id, ext_id="A", title="a"))
    store.add(CaseDraft(run_id=run.id, ext_id="B", title="b", status=CaseStatus.DESCARTADO))
    with pytest.raises(service.GateError, match="sin decidir"):
        service.approve_cases(run.id, "t")
    store.update_case(a.id, status=CaseStatus.DESCARTADO)
    with pytest.raises(service.GateError, match="ningún caso aprobado"):
        service.approve_cases(run.id, "t")
    with pytest.raises(service.GateError):
        service.confirm_registration(run.id, "t")   # no se puede saltar al Gate 3
