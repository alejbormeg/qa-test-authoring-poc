"""IA simulada y determinista: sirve para enseñar el flujo sin clave de API.

- Extracción: entiende casos en tabla (ID | Título | ... | Pasos | ... | Resultado esperado) y casos en prosa
  («Caso TC-X: título», «Pasos:», lista numerada, «Resultado esperado: ...»).
- Generación: traduce pasos escritos con un vocabulario controlado («Abrir la página X», «Introducir "v" en el
  campo Y», «Pulsar el botón Z», «Se muestra W», «W contiene "t"»...) a C# reutilizando los mapeos; si un
  componente no está mapeado, lo busca en el DOM real y lo propone. Lo que no entiende queda marcado.
"""

from __future__ import annotations

import re
import unicodedata

from ..adapters.dff import Block
from ..pipeline.toolbox import CaseFile, Toolbox
from .schemas import CaseInput, CasoExtraido, Extraccion, Generation, Paso, Usage

STOP = {"el", "la", "los", "las", "de", "del", "en", "un", "una", "al", "a", "y", "con", "se", "que", "su", "sus",
        "lo", "para", "por", "pagina", "boton", "campo", "enlace", "selector", "texto"}
TYPE_HINTS = {"campo": {"input", "select"}, "boton": {"button"}, "enlace": {"link"}, "selector": {"select"},
              "desplegable": {"select"}, "mensaje": {"text"}, "aviso": {"text"}, "texto": {"text"}}
VERBS = ("abrir", "ir a", "introducir", "escribir", "pulsar", "hacer clic", "seleccionar", "anadir el producto",
         "iniciar sesion", "se muestra", "no se muestra", "la url", "contiene", "muestra")


def norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def tokens(text: str, drop: set[str] = frozenset()) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", norm(text)):
        if w in STOP or w in drop:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


def cs(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ====================================================================== extracción

def _lines(text: str) -> list[str]:
    return [re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", ln).strip() for ln in text.splitlines() if ln.strip()]


def _warnings(case: CasoExtraido) -> list[str]:
    warns = []
    if not case.resultado_esperado.strip():
        warns.append("Falta el resultado esperado: no se puede comprobar nada")
    if not case.pasos:
        warns.append("El caso no tiene pasos")
    for p in case.pasos:
        if '"' not in p.accion and not any(v in norm(p.accion) for v in VERBS):
            warns.append(f"Paso poco concreto: «{p.accion}». Detalla la acción y los datos")
    m = re.search(r"contrase[nñ]a:?\s*([^\s,.;]+)", case.datos, re.I)
    steps_text = " ".join(p.accion for p in case.pasos)
    used = re.search(r'contrase[nñ]a\s+"([^"]+)"', steps_text, re.I)
    if m and used and m.group(1) != used.group(1):
        warns.append(f"Dato contradictorio: los datos de prueba indican la contraseña «{m.group(1)}» "
                     f"pero los pasos usan «{used.group(1)}»")
    for line in _lines(case.resultado_esperado):
        if '"' not in line and not any(v in norm(line) for v in ("se muestra", "no se muestra")):
            warns.append(f"Resultado esperado poco verificable: «{line}»")
    return warns


def _meta(blocks: list[Block]) -> dict[str, str]:
    for b in blocks:
        if b.kind == "table" and b.rows and len(b.rows[0]) == 2:
            return {r[0]: r[1] for r in b.rows if len(r) == 2}
    return {}


def _from_tables(blocks: list[Block]) -> list[CasoExtraido]:
    out = []
    for b in blocks:
        if b.kind != "table" or not b.rows:
            continue
        head = [norm(c) for c in b.rows[0]]
        if not any("paso" in h for h in head) or not any(h == "id" for h in head):
            continue
        col = lambda name: next((i for i, h in enumerate(head) if name in h), None)  # noqa: E731
        ci, ct, cp, cs_, cd, ce = (col("id"), col("titulo"), col("precondicion"), col("paso"), col("dato"),
                                   col("resultado"))
        for row in b.rows[1:]:
            get = lambda i: row[i].strip() if i is not None and i < len(row) else ""  # noqa: E731
            if not get(ci):
                continue
            expected = get(ce)
            pasos = [Paso(accion=s, esperado="") for s in _lines(get(cs_))]
            out.append(CasoExtraido(id=get(ci), titulo=get(ct), precondiciones=get(cp), pasos=pasos,
                                    datos=get(cd), resultado_esperado=expected, avisos=[]))
    return out


def _from_prose(blocks: list[Block]) -> list[CasoExtraido]:
    out: list[CasoExtraido] = []
    cur: dict | None = None
    mode = ""
    for b in blocks:
        if b.kind != "p":
            continue
        m = re.match(r"^Caso\s+([A-Z][\w-]+)\s*[:.-]\s*(.+)$", b.text)
        if m:
            cur = {"id": m.group(1), "titulo": m.group(2), "pre": "", "pasos": [], "datos": "", "esperado": ""}
            out.append(cur)  # type: ignore[arg-type]
            mode = ""
            continue
        if cur is None:
            continue
        low = norm(b.text)
        if low.startswith("precondicion"):
            cur["pre"] = b.text.split(":", 1)[-1].strip()
        elif low.startswith("datos"):
            cur["datos"] = b.text.split(":", 1)[-1].strip()
        elif low.startswith("pasos"):
            mode = "pasos"
        elif low.startswith("resultado esperado"):
            cur["esperado"] = b.text.split(":", 1)[-1].strip()
            mode = ""
        elif mode == "pasos" and "list" in b.style.lower():
            cur["pasos"].append(b.text)
    return [CasoExtraido(id=c["id"], titulo=c["titulo"], precondiciones=c["pre"],
                         pasos=[Paso(accion=p, esperado="") for p in c["pasos"]], datos=c["datos"],
                         resultado_esperado=c["esperado"], avisos=[]) for c in out]  # type: ignore[index]


class MockLlm:
    name = "mock"

    def extract(self, text: str, blocks: list[Block], dff_name: str) -> tuple[Extraccion, Usage]:
        meta = _meta(blocks)
        casos = _from_tables(blocks) or _from_prose(blocks)
        for c in casos:
            c.avisos = _warnings(c)
            expected = _lines(c.resultado_esperado)
            if c.pasos and expected:
                c.pasos[-1].esperado = "; ".join(expected)
        general = [] if casos else ["No se ha encontrado ningún caso con el formato esperado"]
        feature = next((v for k, v in meta.items() if "feature" in norm(k)), "")
        return Extraccion(funcionalidad=meta.get("Funcionalidad", dff_name), feature_ref=feature,
                          version=meta.get("Versión", ""), casos=casos, avisos_generales=general), {}

    # ================================================================== generación

    def generate(self, case: CaseInput, tb: Toolbox, feedback: str | None = None,
                 previous: str | None = None) -> tuple[Generation, Usage]:
        gen = _Generator(case, tb)
        body = gen.run()
        ok, errors = tb.write_case(CaseFile(case.ext_id, case.title, case.method_name), body)
        notes = ("Generado con el vocabulario controlado del simulador: cada paso se ha traducido a un componente "
                 "mapeado o a una acción de un page object existente.")
        if gen.unresolved:
            notes += " Hay pasos que el simulador no sabe automatizar: necesitan revisión de QA."
        if not ok:
            gen.unresolved += errors
        return Generation(body=body, notes=notes, unresolved=gen.unresolved, compiled=ok), {}


class _Generator:
    def __init__(self, case: CaseInput, tb: Toolbox) -> None:
        self.case = case
        self.tb = tb
        self.pages: list[str] = []
        self.lines: list[str] = []
        self.unresolved: list[str] = []

    # ---------------------------------------------------------------- resolución de componentes

    def resolve(self, phrase: str) -> str | None:
        hint: set[str] = set()
        for w, kinds in TYPE_HINTS.items():
            if re.search(rf"\b{w}\b", norm(phrase)):
                hint |= kinds
        context = [p for p in self.pages if p in self.tb.routes] or list(self.tb.routes)
        want = tokens(phrase, drop=set(context[:1]))
        if not want:
            return None
        best, best_score = None, 0
        order = context + ["cabecera"] + [p for p in self.tb.pages() if p not in context and p != "cabecera"]
        for rank, page in enumerate(order):
            if rank > len(context):  # fuera del contexto solo si no hay nada mejor
                break
            for name, entry in self.tb.mapping(page).items():
                score = 2 * len(want & tokens(name.replace("_", " "))) + len(want & tokens(entry["descripcion"]))
                if score and hint:
                    score += 1 if entry["tipo"] in hint else -2
                if score > best_score:
                    best, best_score = f"{page}.{name}", score
        # Un elemento del DOM sin mapear solo gana si encaja claramente mejor que lo ya mapeado
        el, dom_score = self._dom_candidate(context[0], want, hint)
        if el is not None and dom_score >= 2 and dom_score > best_score:
            return self._propose(context[0], el)
        return best

    def _dom_candidate(self, page: str, want: set[str], hint: set[str]) -> tuple[dict | None, int]:
        prefix = page + "-"
        best, best_score = None, 0
        for el in self.tb.inspect(page):
            if el["mapeado_como"]:
                continue
            name_tokens = tokens(el["testid"].removeprefix(prefix).replace("-", " "))
            score = 2 * len(want & name_tokens) + len(want & tokens(f"{el['aria']} {el['label']} {el['placeholder']}"))
            if score and hint:
                score += 1 if el["tipo"] in hint else -2
            if score > best_score:
                best, best_score = el, score
        return best, best_score

    def _propose(self, page: str, best: dict) -> str | None:
        prefix = page + "-"
        name = re.sub(r"[^a-z0-9]+", "_", best["testid"].removeprefix(prefix)).strip("_")
        res = self.tb.propose(page, name, best["selector"], best["tipo"], _describe(best), self.case.ext_id)
        if res.startswith("Error"):
            return None
        m = re.search(r'"([a-z0-9_]+\.[a-z0-9_]+)"', res)
        return m.group(1) if m else f"{page}.{name}"

    # ---------------------------------------------------------------- traducción

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def comp(self, phrase: str, original: str) -> str | None:
        ref = self.resolve(phrase)
        if not ref:
            self.unresolved.append(f"No encuentro el componente «{phrase.strip()}» (paso: «{original}»)")
            self.emit(f"// PENDIENTE: no se encuentra el componente «{phrase.strip()}»")
        return ref

    def step(self, text: str) -> None:
        t = text.strip().rstrip(".")
        n = norm(t)
        q = re.findall(r'"([^"]*)"', t)
        if m := re.match(r"(abrir|ir a) (la )?pagina (de )?(\w+)", n):
            page = m.group(4)
            if page in self.tb.routes:
                self.pages = [page]
                self.emit(f"await GoToAsync(Page, {cs(page)});")
                return
        if m := re.match(r"(abrir|ir a)( la ficha del| el)? producto (\d+)", n):
            self.pages = ["producto"]
            self.emit(f'await GoToAsync(Page, "producto", "?id={m.group(3)}");')
            return
        if m := re.match(r"(abrir|ir|volver)( a| al)?( el| la| mi)? (perfil|carrito|checkout|catalogo|login)\b", n):
            self.pages = [m.group(4)]
            self.emit(f"await GoToAsync(Page, {cs(m.group(4))});")
            return
        if m := re.match(r"anadir el producto (\d+)(?: x ?(\d+))? al carrito", n):
            qty = f", cantidad: {m.group(2)}" if m.group(2) else ""
            self.pages = ["producto"]
            self.emit(f"await new CarritoPage(Page).AnadirProductoAsync(productoId: {m.group(1)}{qty});")
            return
        if n.startswith("iniciar sesion") and len(q) >= 2:
            self.pages = ["perfil", "login"]
            self.emit(f"await new LoginPage(Page).LoginAsync({cs(q[0])}, {cs(q[1])});")
            return
        if (n.startswith("introducir") or n.startswith("escribir")) and q:
            target = re.split(r'"\s+en\s+', t, maxsplit=1)[-1]
            if ref := self.comp(target, text):
                self.emit(f"await Component(Page, {cs(ref)}).FillAsync({cs(q[0])});")
            return
        if n.startswith("seleccionar") and q:
            target = re.split(r'"\s+en\s+', t, maxsplit=1)[-1]
            if ref := self.comp(target, text):
                self.emit(f"await Component(Page, {cs(ref)}).SelectOptionAsync({cs(q[0])});")
            return
        if n.startswith("pulsar") or n.startswith("hacer clic"):
            target = re.sub(r"^(pulsar|hacer clic( en)?)\s+", "", t, flags=re.I)
            if ref := self.comp(target, text):
                self.emit(f"await Component(Page, {cs(ref)}).ClickAsync();")
            return
        self.unresolved.append(f"Paso no automatizable sin más detalle: «{text}»")
        self.emit(f"// PENDIENTE: «{text}»")
        self.emit(f"throw new NotImplementedException({cs('Paso pendiente de detallar: ' + text)});")

    def check(self, text: str) -> None:
        t = text.strip().rstrip(".")
        n = norm(t)
        q = re.findall(r'"([^"]*)"', t)
        if n.startswith("la url contiene") and q:
            route = next((p for p, r in self.tb.routes.items() if r == q[0] and r != "/"), None)
            if route:
                self.pages = [route]
            self.emit(f"await Expect(Page).ToHaveURLAsync(new Regex(Regex.Escape({cs(q[0])})));")
            return
        if m := re.match(r"(no )?se muestra (.+)$", t, re.I):
            if ref := self.comp(m.group(2), text):
                assertion = "ToBeHiddenAsync" if m.group(1) else "ToBeVisibleAsync"
                self.emit(f"await Expect(Component(Page, {cs(ref)})).{assertion}();")
            return
        if m := re.match(r'(.+?)\s+(contiene|muestra)\s+"([^"]*)"', t, re.I):
            if ref := self.comp(m.group(1), text):
                self.emit(f"await Expect(Component(Page, {cs(ref)})).ToContainTextAsync({cs(m.group(3))});")
            return
        self.unresolved.append(f"Comprobación no automatizable: «{text}»")
        self.emit(f"// PENDIENTE de comprobar: «{text}»")
        self.emit(f"throw new NotImplementedException({cs('Comprobación pendiente: ' + text)});")

    def run(self) -> str:
        self.emit("// Preparación y pasos")
        for i, s in enumerate(self.case.steps, start=1):
            self.emit(f"// {i}. {s['accion']}")
            self.step(s["accion"])
        expected = _lines(self.case.expected)
        self.emit("")
        self.emit("// Resultado esperado")
        if not expected:
            self.unresolved.append("El caso no tiene resultado esperado: el test no comprueba nada")
            self.emit("// PENDIENTE: el documento no indica el resultado esperado")
            self.emit('throw new NotImplementedException("Falta el resultado esperado del caso");')
        for e in expected:
            self.emit(f"// {e}")
            self.check(e)
        return "\n".join(self.lines)


def _describe(el: dict) -> str:
    what = {"input": "Campo", "select": "Selector", "button": "Botón", "link": "Enlace", "list": "Lista"}.get(
        el["tipo"], "Texto")
    name = el["label"] or el["aria"] or el["placeholder"] or el["text"] or el["testid"].split("-", 1)[-1].replace("-", " ")
    return f"{what} {name}"
