"""El adaptador de Claude construye bien las peticiones (sin llamar a la API: cliente falso)."""

from __future__ import annotations

from types import SimpleNamespace

from qa_assistant.llm import claude
from qa_assistant.llm.schemas import CaseInput, Extraccion


class FakeToolbox:
    test_class = "CarritoTests"

    def read_file(self, rel):
        return "{}" if rel.endswith(".json") else "# README"

    def pages(self):
        return ["carrito"]

    def mapping(self, page):
        return {"total": {"selector": "[data-testid=carrito-total]", "tipo": "text", "descripcion": "Total"}}

    def list_files(self):
        return ["Pages/LoginPage.cs"]

    def write_case(self, case, body):
        return True, []


def _usage():
    return SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=5000,
                           cache_creation_input_tokens=0)


def test_generation_request_and_tool_loop(monkeypatch):
    captured = {}

    def tool_runner(**params):
        captured.update(params)
        tools = {t.name: t for t in params["tools"]}
        assert tools["escribir_test"].call({"cuerpo": "await GoToAsync(Page, \"carrito\");"}).startswith("Compila")
        return iter([SimpleNamespace(usage=_usage(), content=[SimpleNamespace(type="text", text="Resumen")])])

    llm = claude.ClaudeLlm.__new__(claude.ClaudeLlm)
    llm.model = "claude-opus-5-5"
    llm.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner)))
    case = CaseInput("TC-1", "Caso", "", [{"accion": "Abrir la página carrito", "esperado": ""}], "", "Se muestra x",
                     "TC_1_Caso")
    gen, usage = llm.generate(case, FakeToolbox())
    assert gen.compiled and gen.notes == "Resumen" and "GoToAsync" in gen.body
    assert {t.name for t in captured["tools"]} == {"leer_fichero", "inspeccionar_pagina", "proponer_componente",
                                                   "escribir_test"}
    assert captured["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert captured["output_config"] == {"effort": "high"}
    assert usage["calls"] == 1 and usage["cost_usd"] > 0


def test_extraction_uses_structured_output():
    captured = {}

    def parse(**params):
        captured.update(params)
        return SimpleNamespace(stop_reason="end_turn", usage=_usage(),
                               parsed_output=Extraccion(funcionalidad="X", feature_ref="", version="", casos=[],
                                                        avisos_generales=[]))

    llm = claude.ClaudeLlm.__new__(claude.ClaudeLlm)
    llm.model = "claude-opus-5-5"
    llm.client = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    result, _ = llm.extract("texto", [], "doc.docx")
    assert captured["output_format"] is Extraccion
    assert result.funcionalidad == "X"
