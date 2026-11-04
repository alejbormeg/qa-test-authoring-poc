"""Herramientas que la IA (Claude o el mock) usa sobre el repositorio de tests y la web real.

Garantías que no dependen del modelo:
- Solo lee ficheros del repositorio de tests y solo escribe el fichero del caso y los mapeos.
- Un componente nuevo solo se acepta si su selector existe en el DOM real de la página.
- El código solo se da por bueno si compila y todos los componentes que usa están mapeados.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..adapters import dotnet_runner
from ..adapters.dom_inspector import DomInspector
from ..adapters.workspace import Workspace, render_test_file, test_file

READABLE = ("Mappings/", "Pages/", "Support/", "Tests/", "README.md")
COMPONENT_REF = re.compile(r'Component\(\s*Page\s*,\s*"([a-z0-9_]+)\.([a-z0-9_]+)"\s*\)')
NAME_OK = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


@dataclass
class CaseFile:
    ext_id: str
    title: str
    method: str


@dataclass
class Toolbox:
    ws: Workspace
    dom: DomInspector
    test_class: str
    feature_id: int
    log: Callable[[str], None]
    pending: dict[tuple[str, str], dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.routes = self.ws.routes()
        self.base = self.ws.mappings()

    # ------------------------------------------------------------ lectura

    def mapping(self, page: str) -> dict[str, dict]:
        merged = dict(self.base.get(page, {}))
        for (p, name), comp in self.pending.items():
            if p == page:
                merged[name] = {"selector": comp["selector"], "tipo": comp["tipo"], "descripcion": comp["descripcion"]}
        return merged

    def pages(self) -> list[str]:
        return sorted(set(self.base) | {p for p, _ in self.pending})

    def is_mapped(self, page: str, name: str) -> bool:
        return name in self.mapping(page)

    def is_new(self, page: str, name: str) -> bool:
        return (page, name) in self.pending

    def read_file(self, rel: str) -> str:
        rel = rel.lstrip("./")
        if not rel.startswith(READABLE) or ".." in rel:
            return f"Error: solo se pueden leer ficheros de {', '.join(READABLE)}"
        try:
            if rel.startswith("Mappings/") and rel.endswith(".json") and not rel.endswith("_rutas.json"):
                return json.dumps(self.mapping(rel.removeprefix("Mappings/").removesuffix(".json")),
                                  ensure_ascii=False, indent=1)
            return self.ws.read(rel)
        except FileNotFoundError:
            return f"Error: no existe {rel}. Ficheros disponibles: {', '.join(self.list_files())}"

    def list_files(self) -> list[str]:
        files = []
        for pattern in ("Mappings/*.json", "Pages/*.cs", "Support/*.cs", "Tests/*.cs", "README.md"):
            files += self.ws.list(pattern)
        return files

    def route(self, page: str, query: str = "") -> str:
        if page not in self.routes:
            raise KeyError(f"La página '{page}' no existe. Páginas: {', '.join(self.routes)}")
        return self.routes[page] + query

    def inspect(self, page: str, query: str = "") -> list[dict]:
        """Elementos con data-testid de la página, indicando si ya están mapeados y con qué nombre."""
        by_selector = {v["selector"]: f"{p}.{k}" for p in self.pages() for k, v in self.mapping(p).items()}
        out = []
        for el in self.dom.describe(self.route(page, query)):
            el["mapeado_como"] = by_selector.get(el["selector"], "")
            out.append(el)
        return out

    # ------------------------------------------------------------ escritura

    def propose(self, page: str, name: str, selector: str, tipo: str, descripcion: str, case_id: str) -> str:
        if page not in self.routes:
            return f"Error: la página '{page}' no existe. Páginas: {', '.join(self.routes)}"
        if not NAME_OK.match(name):
            return "Error: el nombre debe ser snake_case en minúsculas (p. ej. cupon_input)"
        if self.is_mapped(page, name):
            existing = self.mapping(page)[name]
            if existing["selector"] == selector:
                return f"Ya existe: usa Component(Page, \"{page}.{name}\")"
            return f"Error: '{page}.{name}' ya existe con otro selector ({existing['selector']}). Elige otro nombre"
        for p in self.pages():
            for k, v in self.mapping(p).items():
                if v["selector"] == selector:
                    return f"Ese selector ya está mapeado como '{p}.{k}': reutilízalo"
        n = self.dom.count(self.route(page), selector)
        if n == 0:
            return (f"Error: el selector {selector} no existe en el DOM de la página '{page}'. "
                    "Inspecciona la página y usa un selector real")
        self.pending[(page, name)] = {"pagina": page, "nombre": name, "selector": selector, "tipo": tipo,
                                      "descripcion": descripcion, "casos": [case_id]}
        self.log(f"🧩 Componente nuevo propuesto: {page}.{name} → {selector} ({n} en el DOM)")
        return f"Componente añadido al mapeo: Component(Page, \"{page}.{name}\")"

    def refs(self, body: str) -> list[tuple[str, str]]:
        return [(m.group(1), m.group(2)) for m in COMPONENT_REF.finditer(body)]

    def write_case(self, case: CaseFile, body: str) -> tuple[bool, list[str]]:
        """Escribe el fichero del caso, actualiza mapeos y compila. Devuelve (ok, errores)."""
        unknown = [f"{p}.{n}" for p, n in self.refs(body) if not self.is_mapped(p, n)]
        if unknown:
            return False, [f"Componentes sin mapear: {', '.join(sorted(set(unknown)))}. Reutiliza uno existente o "
                           "propón uno nuevo con un selector real de la página"]
        if "GotoAsync(" in body and "http" in body:
            return False, ["No navegues con URLs absolutas: usa GoToAsync(Page, \"pagina\")"]
        if re.search(r"Page\.Locator\(|GetByTestId\(|data-testid", body):
            return False, ["No uses selectores directamente en el test: usa Component(Page, \"pagina.componente\")"]
        rel = test_file(self.test_class, case.ext_id)
        self.ws.write(rel, render_test_file(self.test_class, case.method, self.feature_id, case.ext_id, case.title, body))
        self.ws.add_components(list(self.pending.values()))
        result = dotnet_runner.build(self.ws.root)
        errors = dotnet_runner.errors_for(result, rel)
        if not result.ok and not errors:
            errors = result.errors[:5] or ["La compilación falla por un motivo ajeno al caso"]
        for (p, n) in self.refs(body):
            if (p, n) in self.pending and case.ext_id not in self.pending[(p, n)]["casos"]:
                self.pending[(p, n)]["casos"].append(case.ext_id)
        return result.ok, errors

    def classify(self, body: str) -> tuple[list[str], list[str]]:
        reused, new = [], []
        for p, n in self.refs(body):
            ref = f"{p}.{n}"
            (new if self.is_new(p, n) else reused).append(ref)
        return sorted(set(reused)), sorted(set(new))
