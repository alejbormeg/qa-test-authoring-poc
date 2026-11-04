"""IA real con Claude (API de Anthropic).

- Extracción: salida estructurada validada con Pydantic (`messages.parse`).
- Generación: agente con herramientas (`tool_runner`) sobre el repositorio de tests y el DOM real; el
  contexto del repositorio va en el system prompt con caché para no pagarlo en cada caso.
"""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
from anthropic import beta_tool

from ..adapters.dff import Block
from ..config import settings
from ..pipeline.toolbox import CaseFile, Toolbox
from .schemas import CaseInput, Extraccion, Generation, Usage

PROMPTS = Path(__file__).parent / "prompts"
# USD por millón de tokens (precios públicos de Claude Opus 5.5); configurable si se cambia de modelo
PRICES = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _usage(u) -> Usage:
    if u is None:
        return {}
    data = {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "calls": 1,
    }
    data["cost_usd"] = (data["input_tokens"] * PRICES["input"] + data["output_tokens"] * PRICES["output"]
                        + data["cache_read_tokens"] * PRICES["cache_read"]
                        + data["cache_write_tokens"] * PRICES["cache_write"]) / 1_000_000
    return data


def _merge(a: Usage, b: Usage) -> Usage:
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


class ClaudeLlm:
    name = "claude"

    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.model = settings.claude_model

    # ------------------------------------------------------------------ extracción

    def extract(self, text: str, blocks: list[Block], dff_name: str) -> tuple[Extraccion, Usage]:
        system = (PROMPTS / "extraccion.md").read_text(encoding="utf-8")
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=32000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"<documento nombre=\"{dff_name}\">\n{text}\n</documento>"}],
            output_format=Extraccion,
            output_config={"effort": "medium"},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("El modelo ha rechazado procesar el documento")
        if resp.parsed_output is None:
            raise RuntimeError(f"Respuesta sin datos estructurados (stop_reason={resp.stop_reason})")
        return resp.parsed_output, _usage(resp.usage)

    # ------------------------------------------------------------------ generación

    def _repo_context(self, tb: Toolbox) -> str:
        parts = [f"### README.md\n{tb.read_file('README.md')}",
                 f"### Mappings/_rutas.json\n{tb.read_file('Mappings/_rutas.json')}"]
        for page in tb.pages():
            parts.append(f"### Mappings/{page}.json\n{json.dumps(tb.mapping(page), ensure_ascii=False, indent=1)}")
        for f in tb.list_files():
            if f.endswith(".cs"):
                parts.append(f"### {f}\n```csharp\n{tb.read_file(f)}\n```")
        return "\n\n".join(parts)

    def generate(self, case: CaseInput, tb: Toolbox, feedback: str | None = None,
                 previous: str | None = None) -> tuple[Generation, Usage]:
        state: dict = {"body": previous or "", "ok": False, "errors": []}
        cf = CaseFile(case.ext_id, case.title, case.method_name)

        @beta_tool
        def leer_fichero(ruta: str) -> str:
            """Lee un fichero del repositorio de tests (Mappings/, Pages/, Support/, Tests/ o README.md).

            Args:
                ruta: Ruta relativa a la raíz del repositorio, p. ej. Pages/LoginPage.cs.
            """
            return tb.read_file(ruta)

        @beta_tool
        def inspeccionar_pagina(pagina: str, query: str = "") -> str:
            """Devuelve los elementos con data-testid del DOM real de una página de la web, indicando cuáles
            están ya mapeados y con qué nombre. Úsalo antes de proponer un componente nuevo.

            Args:
                pagina: Nombre de la página según Mappings/_rutas.json (p. ej. carrito).
                query: Query string opcional, p. ej. ?id=2.
            """
            try:
                return json.dumps(tb.inspect(pagina, query), ensure_ascii=False)
            except KeyError as e:
                return f"Error: {e}"

        @beta_tool
        def proponer_componente(pagina: str, nombre: str, selector: str, tipo: str, descripcion: str) -> str:
            """Añade al mapeo de la página un componente que todavía no está mapeado. El selector debe salir de
            inspeccionar_pagina; se valida contra el DOM real y se rechaza si no existe.

            Args:
                pagina: Página a la que pertenece el componente (p. ej. carrito).
                nombre: Nombre en snake_case, en español y descriptivo (p. ej. cupon_mensaje).
                selector: Selector CSS por data-testid, p. ej. [data-testid=carrito-cupon-mensaje].
                tipo: input, select, button, link, text o list.
                descripcion: Descripción breve en español, como en el resto del mapeo.
            """
            return tb.propose(pagina, nombre, selector, tipo, descripcion, case.ext_id)

        @beta_tool
        def escribir_test(cuerpo: str) -> str:
            """Escribe el cuerpo del método de test del caso (solo las sentencias, sin la firma ni la clase),
            lo compila con dotnet build y devuelve el resultado. Repite hasta que compile.

            Args:
                cuerpo: Sentencias C# del método. Usa Component(Page, "pagina.componente"), GoToAsync, los page
                    objects existentes y Expect(...) de Playwright. Comenta cada bloque con el paso del caso.
            """
            ok, errors = tb.write_case(cf, cuerpo)
            state.update(body=cuerpo, ok=ok, errors=errors)
            if ok:
                return "Compila correctamente. Si el caso está completo, termina con un resumen breve."
            return "No compila o no cumple las convenciones:\n" + "\n".join(errors[:12])

        system = [
            {"type": "text", "text": (PROMPTS / "generacion.md").read_text(encoding="utf-8")},
            {"type": "text", "text": "## Repositorio de tests (estado actual)\n\n" + self._repo_context(tb),
             "cache_control": {"type": "ephemeral"}},
        ]
        steps = "\n".join(f"{i}. {s['accion']}" + (f"  → esperado: {s['esperado']}" if s.get("esperado") else "")
                          for i, s in enumerate(case.steps, start=1))
        prompt = (f"Automatiza este caso de prueba.\n\nID: {case.ext_id}\nTítulo: {case.title}\n"
                  f"Precondiciones: {case.preconditions or '—'}\nDatos de prueba: {case.data or '—'}\n"
                  f"Pasos:\n{steps}\nResultado esperado:\n{case.expected or '(no indicado)'}\n\n"
                  f"El método se llamará {case.method_name} en la clase parcial {tb.test_class}.")
        if feedback:
            prompt += (f"\n\nYa existe una versión que compila pero FALLA al ejecutarse contra la web. Código "
                       f"actual:\n```csharp\n{previous}\n```\nError de la ejecución:\n```\n{feedback}\n```\n"
                       "Inspecciona la página si hace falta, corrige el test y vuelve a escribirlo. No cambies el "
                       "resultado esperado del caso para que pase: si la web no cumple el caso, déjalo y explícalo.")

        usage: Usage = {}
        params = dict(model=self.model, max_tokens=32000, system=system, max_iterations=24,
                      tools=[leer_fichero, inspeccionar_pagina, proponer_componente, escribir_test],
                      messages=[{"role": "user", "content": prompt}], output_config={"effort": "high"})
        if settings.claude_fallbacks:
            params.update(betas=[FALLBACK_BETA], fallbacks="default")
        final_text = ""
        try:
            runner = self.client.beta.messages.tool_runner(**params)
            for message in runner:
                usage = _merge(usage, _usage(message.usage))
                final_text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text") or final_text
        except anthropic.BadRequestError as e:
            if settings.claude_fallbacks and "fallback" in str(e).lower():
                params.pop("betas"), params.pop("fallbacks")
                runner = self.client.beta.messages.tool_runner(**params)
                for message in runner:
                    usage = _merge(usage, _usage(message.usage))
                    final_text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text") or final_text
            else:
                raise
        unresolved = [] if state["ok"] else (state["errors"] or ["El agente no llegó a escribir un test que compile"])
        return Generation(body=state["body"], notes=final_text.strip(), unresolved=unresolved,
                          compiled=state["ok"]), usage


def make_llm():
    if settings.ai_mode == "claude":
        return ClaudeLlm()
    from .mock import MockLlm

    return MockLlm()
