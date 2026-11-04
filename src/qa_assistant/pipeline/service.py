"""Orquestación del flujo con humano en el bucle.

subido → extrayendo → extraido [GATE 1: QA aprueba casos] → generando → en_revision [GATE 2: QA aprueba código
y se abre la PR] → pr_abierta (QA aprueba y completa la PR en Azure Repos) → mergeado [GATE 3: QA confirma el
registro] → registrando → registrado

Las fases automáticas corren en hilos; cada transición queda en la base de datos, de modo que un fallo deja la
ejecución en `error` con la fase que falló y se puede reintentar sin perder ni duplicar casos.
"""

from __future__ import annotations

import re
import shutil
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from ..adapters import dotnet_runner
from ..adapters import git as gitops
from ..adapters.azure_devops import AzureAuthError, AzureDevOps
from ..adapters.dff import read_blocks, to_text
from ..adapters.dom_inspector import DomInspector
from ..adapters.workspace import LOCK, Workspace, class_name, fqn, method_name, render_test_file, test_file
from ..config import settings
from ..domain.models import CaseDraft, CaseStatus, Run, RunState
from ..llm.claude import make_llm
from ..llm.schemas import CaseInput
from .. import store
from .toolbox import CaseFile, Toolbox


class GateError(RuntimeError):
    """Se intenta avanzar sin la decisión humana o en un estado que no corresponde."""


def azure(run_id: int | None = None, user: str = "Asistente QA") -> AzureDevOps:
    return AzureDevOps(user=user, on_retry=(lambda msg: store.log(run_id, "⚠️ " + msg, "warn")) if run_id else None)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ======================================================================== hilos

_threads: dict[int, threading.Thread] = {}


def _spawn(run_id: int, phase: str, label: str, fn: Callable[[], None]) -> None:
    def target() -> None:
        store.update_run(run_id, busy=label, error=None, failed_phase=None)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - cualquier fallo queda registrado en la ejecución
            msg = str(e) if isinstance(e, (AzureAuthError, GateError, RuntimeError)) else f"{type(e).__name__}: {e}"
            store.log(run_id, f"❌ {msg}", "error")
            store.log(run_id, traceback.format_exc()[-1500:], "debug")
            store.update_run(run_id, state=RunState.ERROR, error=msg, failed_phase=phase)
        finally:
            store.update_run(run_id, busy=None)

    t = threading.Thread(target=target, name=f"run-{run_id}-{phase}", daemon=True)
    _threads[run_id] = t
    t.start()


def is_busy(run_id: int) -> bool:
    t = _threads.get(run_id)
    return bool(t and t.is_alive())


def _require(run: Run, *states: RunState) -> None:
    if run.state not in states:
        raise GateError(f"La ejecución está en «{run.state}»; esta acción requiere {', '.join(states)}")
    if is_busy(run.id):
        raise GateError("La ejecución está ocupada; espera a que termine la fase en curso")


# ======================================================================== 1. alta y extracción

def create_run(dff_file: Path, dff_name: str, feature: dict, plan: dict, suite: dict | None, new_suite: str | None,
               user: str) -> Run:
    settings.uploads.mkdir(parents=True, exist_ok=True)
    run = store.add(Run(created_by=user, dff_name=dff_name, dff_path="", ai_mode=settings.ai_mode,
                        feature_id=feature["id"], feature_title=feature["fields"]["System.Title"],
                        plan_id=plan["id"], plan_name=plan["name"],
                        suite_id=suite["id"] if suite else None,
                        suite_name=suite["name"] if suite else (new_suite or "").strip(),
                        test_class=class_name(feature["fields"]["System.Title"])))
    dest = settings.uploads / f"run-{run.id}-{dff_name}"
    shutil.copy(dff_file, dest)
    store.update_run(run.id, dff_path=str(dest), branch=f"qa-assistant/run-{run.id}-{run.test_class.lower()}")
    store.decide(run.id, user, "Sube el DFF", f"{dff_name} → Feature #{feature['id']}, plan «{plan['name']}», "
                                             f"suite «{suite['name'] if suite else new_suite}»"
                                             + ("" if suite else " (nueva)"))
    start_extraction(run.id)
    return store.get_run(run.id)


def start_extraction(run_id: int) -> None:
    store.update_run(run_id, state=RunState.EXTRAYENDO)
    _spawn(run_id, "extraccion", "Leyendo el documento y extrayendo casos", lambda: _extract(run_id))


def _extract(run_id: int) -> None:
    run = store.get_run(run_id)
    store.mark(run_id, "extraccion", "start")
    llm = make_llm()
    blocks = read_blocks(Path(run.dff_path))
    text = to_text(blocks)
    store.log(run_id, f"📄 Documento leído: {len(blocks)} bloques, {len(text):,} caracteres")
    store.log(run_id, f"🤖 Extrayendo casos con {'Claude · ' + settings.claude_model if llm.name == 'claude' else 'la IA simulada'}")
    result, usage = llm.extract(text, blocks, run.dff_name)
    store.add_usage(run_id, usage)

    existing = azure(run_id).test_cases()
    store.log(run_id, f"🔎 Comparando con {len(existing)} casos que ya existen en Azure DevOps")
    by_title = {_norm(w["fields"]["System.Title"]): w for w in existing}
    for pos, c in enumerate(result.casos):
        warnings = list(c.avisos)
        dup = None
        for w in existing:
            title = w["fields"]["System.Title"]
            if c.id and c.id.lower() in title.lower() or _norm(c.titulo) in by_title:
                dup = w
                break
        status = CaseStatus.PENDIENTE
        if dup:
            warnings.insert(0, f"Ya existe en Azure DevOps como #{dup['id']} «{dup['fields']['System.Title']}»")
            status = CaseStatus.DESCARTADO
        store.add(CaseDraft(run_id=run_id, position=pos, ext_id=c.id, title=c.titulo, preconditions=c.precondiciones,
                            steps=[p.model_dump() for p in c.pasos], data=c.datos, expected=c.resultado_esperado,
                            warnings=warnings, duplicate_of=dup["id"] if dup else None, status=status,
                            method_name=method_name(c.id, c.titulo)))
    meta = {"funcionalidad": result.funcionalidad, "feature_ref": result.feature_ref, "version": result.version}
    notes = list(result.avisos_generales)
    if result.feature_ref and str(run.feature_id) not in result.feature_ref:
        notes.append(f"El documento indica la Feature {result.feature_ref}, pero se eligió la #{run.feature_id}")
    store.update_run(run_id, dff_meta=meta, notes=notes, state=RunState.EXTRAIDO)
    store.mark(run_id, "extraccion", "end")
    store.mark(run_id, "revision_casos", "start")
    with_w = sum(1 for c in store.cases(run_id) if c.warnings)
    store.log(run_id, f"✅ {len(result.casos)} casos extraídos ({with_w} con avisos). Esperando la revisión de QA")


# ======================================================================== GATE 1

def edit_case(case_id: int, user: str, **fields) -> CaseDraft:
    case = store.get_case(case_id)
    run = store.get_run(case.run_id)
    if run.state not in (RunState.EXTRAIDO, RunState.EN_REVISION):
        raise GateError("Los casos solo se editan durante la revisión")
    if "title" in fields or "ext_id" in fields:
        fields["method_name"] = method_name(fields.get("ext_id", case.ext_id), fields.get("title", case.title))
    updated = store.update_case(case_id, edited_by_human=True, **fields)
    store.decide(run.id, user, f"Edita el caso {updated.ext_id}", ", ".join(k for k in fields if k != "method_name"))
    return updated


def set_case_status(case_id: int, status: CaseStatus, user: str) -> None:
    case = store.get_case(case_id)
    run = store.get_run(case.run_id)
    if run.state not in (RunState.EXTRAIDO, RunState.EN_REVISION):
        raise GateError("Solo se puede cambiar durante la revisión")
    store.update_case(case_id, status=status)
    verb = {"aprobado": "Aprueba", "descartado": "Descarta", "pendiente": "Deja pendiente"}[status]
    store.decide(run.id, user, f"{verb} el caso {case.ext_id}")


def approve_cases(run_id: int, user: str) -> None:
    run = store.get_run(run_id)
    _require(run, RunState.EXTRAIDO)
    cases = store.cases(run_id)
    pending = [c.ext_id for c in cases if c.status == CaseStatus.PENDIENTE]
    if pending:
        raise GateError(f"Quedan casos sin decidir: {', '.join(pending)}")
    approved = [c for c in cases if c.status == CaseStatus.APROBADO]
    if not approved:
        raise GateError("No hay ningún caso aprobado")
    store.mark(run_id, "revision_casos", "end")
    store.decide(run_id, user, "GATE 1 · Aprueba los casos para automatizar",
                 f"{len(approved)} aprobados, {len(cases) - len(approved)} descartados")
    start_generation(run_id)


# ======================================================================== 2. generación y ejecución

def start_generation(run_id: int) -> None:
    store.update_run(run_id, state=RunState.GENERANDO)
    _spawn(run_id, "generacion", "Generando y ejecutando los tests", lambda: _generate(run_id))


def _case_input(c: CaseDraft) -> CaseInput:
    return CaseInput(c.ext_id, c.title, c.preconditions, c.steps, c.data, c.expected, c.method_name)


def _toolbox(run: Run, ws: Workspace, dom: DomInspector) -> Toolbox:
    tb = Toolbox(ws, dom, run.test_class, run.feature_id, lambda m: store.log(run.id, m))
    for comp in run.new_components:
        tb.pending[(comp["pagina"], comp["nombre"])] = dict(comp)
    return tb


def _materialize(run: Run, ws: Workspace, cases: list[CaseDraft]) -> None:
    """Reconstruye la rama de la ejecución: origin/main + mapeos nuevos + un fichero por caso."""
    ws.prepare(run.branch)
    ws.add_components(run.new_components)
    for c in cases:
        if c.code:
            ws.write(c.file_path, render_test_file(run.test_class, c.method_name, run.feature_id, c.ext_id, c.title,
                                                   c.code))


def _generate(run_id: int) -> None:
    run = store.get_run(run_id)
    store.mark(run_id, "generacion", "start")
    llm = make_llm()
    cases = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO]
    with LOCK, DomInspector() as dom:
        ws = Workspace()
        store.log(run_id, f"📦 Preparando el repositorio {settings.azure_repo} en la rama {run.branch}")
        ws.prepare(run.branch)
        tb = _toolbox(run, ws, dom)
        store.log(run_id, f"🗺️ Contexto: {sum(len(tb.mapping(p)) for p in tb.pages())} componentes mapeados en "
                          f"{len(tb.pages())} páginas, {len(ws.list('Pages/*.cs'))} page objects")
        for c in cases:
            store.log(run_id, f"🤖 {c.ext_id}: generando el test {run.test_class}.{c.method_name}")
            gen, usage = llm.generate(_case_input(c), tb)
            store.add_usage(run_id, usage)
            reused, new = tb.classify(gen.body)
            store.update_case(c.id, file_path=test_file(run.test_class, c.ext_id), ai_code=gen.body,
                              first_ai_code=gen.body, code=gen.body, ai_notes=gen.notes, unresolved=gen.unresolved,
                              components_reused=reused, components_new=new, attempts=1,
                              result=None if gen.compiled else "not_built",
                              result_message="" if gen.compiled else "\n".join(gen.unresolved))
            store.update_run(run_id, new_components=list(tb.pending.values()))
            state = "compila" if gen.compiled else "NO compila"
            store.log(run_id, f"   {c.ext_id}: {state} · reutiliza {len(reused)} componentes, {len(new)} nuevos",
                      "info" if gen.compiled else "warn")

        _execute(run_id, ws, first=True)

        # Autocorrección: los que fallan vuelven a la IA con el error real (solo tiene sentido con IA real)
        for attempt in range(2, settings.max_fix_attempts + 2):
            failing = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO and c.result == "failed"
                       and not c.unresolved]
            if not failing or llm.name != "claude":
                break
            for c in failing:
                store.log(run_id, f"🔁 {c.ext_id}: intento {attempt}, corrigiendo con el error de la ejecución")
                gen, usage = llm.generate(_case_input(c), tb, feedback=c.result_message, previous=c.code)
                store.add_usage(run_id, usage)
                reused, new = tb.classify(gen.body)
                store.update_case(c.id, ai_code=gen.body, code=gen.body, ai_notes=gen.notes, attempts=attempt,
                                  components_reused=reused, components_new=new, unresolved=gen.unresolved)
                store.update_run(run_id, new_components=list(tb.pending.values()))
            _materialize(store.get_run(run_id), ws, [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO])
            _execute(run_id, ws, first=False)

    store.mark(run_id, "generacion", "end")
    store.mark(run_id, "revision_codigo", "start")
    cs = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO]
    ok = sum(1 for c in cs if c.result == "passed")
    store.update_run(run_id, state=RunState.EN_REVISION)
    store.log(run_id, f"🧪 {ok}/{len(cs)} tests en verde. Esperando la revisión del código por QA")


def _execute(run_id: int, ws: Workspace, first: bool) -> None:
    run = store.get_run(run_id)
    cases = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO and c.code]
    store.log(run_id, "🔨 Compilando la solución (dotnet build)")
    build = dotnet_runner.build(ws.root)
    if not build.ok:
        # Aísla los casos que no compilan para que no arrastren al resto
        broken = [c for c in cases if dotnet_runner.errors_for(build, c.file_path)]
        for c in broken:
            store.update_case(c.id, result="not_built",
                              result_message="\n".join(dotnet_runner.errors_for(build, c.file_path)),
                              **({"first_result": "not_built"} if first else {}))
            ws.path(c.file_path).unlink(missing_ok=True)
            store.log(run_id, f"   ⛔ {c.ext_id} no compila: se aparta de la ejecución", "warn")
        cases = [c for c in cases if c not in broken]
        build = dotnet_runner.build(ws.root) if broken else build
        if not build.ok:
            for c in cases:
                store.update_case(c.id, result="not_built", result_message="\n".join(build.errors[:5]),
                                  **({"first_result": "not_built"} if first else {}))
            store.log(run_id, f"❌ La solución no compila: {len(build.errors)} errores", "error")
            return
        if not cases:
            return
    names = {fqn(run.test_class, c.method_name): c for c in cases}
    store.log(run_id, f"▶️ Ejecutando {len(names)} tests con Playwright (dotnet test) contra {settings.demo_site_url}")
    results = dotnet_runner.run_tests(ws.root, list(names), settings.results / f"run-{run_id}")
    seen = set()
    for r in results:
        c = names.get(r.name)
        if not c:
            continue
        seen.add(r.name)
        outcome = "passed" if r.outcome == "Passed" else "failed"
        store.update_case(c.id, result=outcome, result_message=r.message, duration_ms=r.duration_ms,
                          **({"first_result": outcome} if first else {}))
        icon = "🟢" if outcome == "passed" else "🔴"
        store.log(run_id, f"   {icon} {c.ext_id} {r.outcome} ({r.duration_ms} ms)"
                          + (f": {r.message.splitlines()[0][:160]}" if r.message else ""),
                  "info" if outcome == "passed" else "warn")
    for name, c in names.items():
        if name not in seen:
            store.update_case(c.id, result="failed", result_message="El test no se ha ejecutado (no aparece en el TRX)")


# ======================================================================== GATE 2

def save_code(case_id: int, code: str, user: str) -> None:
    case = store.get_case(case_id)
    run = store.get_run(case.run_id)
    _require(run, RunState.EN_REVISION)
    if code == case.code:
        return
    store.update_case(case_id, code=code, result=None, result_message="Editado por QA: vuelve a ejecutar los tests",
                      unresolved=[])
    store.decide(run.id, user, f"Edita el código de {case.ext_id}")


def rerun(run_id: int, user: str) -> None:
    run = store.get_run(run_id)
    _require(run, RunState.EN_REVISION)
    store.decide(run_id, user, "Vuelve a ejecutar los tests")

    def job() -> None:
        with LOCK:
            ws = Workspace()
            _materialize(store.get_run(run_id), ws, [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO])
            _execute(run_id, ws, first=False)

    _spawn(run_id, "ejecucion", "Ejecutando los tests", job)


def exclude_case(case_id: int, user: str) -> None:
    case = store.get_case(case_id)
    run = store.get_run(case.run_id)
    _require(run, RunState.EN_REVISION)
    store.update_case(case_id, status=CaseStatus.DESCARTADO)
    store.decide(run.id, user, f"Saca de la PR el caso {case.ext_id}")


def approve_review(run_id: int, user: str) -> None:
    run = store.get_run(run_id)
    _require(run, RunState.EN_REVISION)
    cases = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO]
    if not cases:
        raise GateError("No queda ningún caso en la PR")
    not_green = [c.ext_id for c in cases if c.result != "passed"]
    if not_green:
        raise GateError(f"Hay tests que no están en verde: {', '.join(not_green)}. Corrígelos o sácalos de la PR")
    store.mark(run_id, "revision_codigo", "end")
    store.decide(run_id, user, "GATE 2 · Aprueba el código y abre la pull request", f"{len(cases)} tests")
    _spawn(run_id, "pr", "Publicando la rama y abriendo la PR", lambda: _open_pr(run_id, user))


def _pr_description(run: Run, cases: list[CaseDraft]) -> str:
    lines = [f"Tests automatizados a partir de `{run.dff_name}` para la Feature #{run.feature_id} "
             f"«{run.feature_title}».", "", "| Caso | Test | Resultado | Componentes nuevos |", "|---|---|---|---|"]
    for c in cases:
        lines.append(f"| {c.ext_id} · {c.title} | `{run.test_class}.{c.method_name}` | 🟢 {c.duration_ms} ms | "
                     f"{', '.join(c.components_new) or '—'} |")
    if run.new_components:
        lines += ["", "**Mapeos añadidos**", ""]
        lines += [f"- `{x['pagina']}.{x['nombre']}` → `{x['selector']}` ({x['descripcion']})" for x in run.new_components]
    lines += ["", f"Generado con {'Claude (' + settings.claude_model + ')' if run.ai_mode == 'claude' else 'la IA simulada'}"
                  f" y revisado por QA en el asistente (ejecución #{run.id})."]
    return "\n".join(lines)


def _open_pr(run_id: int, user: str) -> None:
    run = store.get_run(run_id)
    cases = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO]
    with LOCK:
        ws = Workspace()
        _materialize(run, ws, cases)
        sha = ws.commit_and_push(run.branch, f"Tests E2E de {run.feature_title}: {', '.join(c.ext_id for c in cases)}\n\n"
                                             f"Generados por el asistente de QA (ejecución #{run.id}) y revisados por {user}.")
    store.log(run_id, f"⬆️ Rama {run.branch} publicada ({sha[:8]})")
    pr = azure(run_id, user).create_pr(settings.azure_repo, run.branch,
                                       f"[QA] Tests de {run.feature_title} ({len(cases)} casos)",
                                       _pr_description(run, cases))
    store.update_run(run_id, pr_id=pr["pullRequestId"], pr_status=pr["status"], state=RunState.PR_ABIERTA)
    store.mark(run_id, "pr", "start")
    store.log(run_id, f"🔀 PR !{pr['pullRequestId']} abierta en Azure Repos. Esperando aprobación y merge")


def check_pr(run_id: int) -> str:
    run = store.get_run(run_id)
    if run.state != RunState.PR_ABIERTA or not run.pr_id:
        return run.pr_status
    pr = azure(run_id).pr(settings.azure_repo, run.pr_id)
    votes = [{"reviewer": r["displayName"], "vote": r["vote"]} for r in pr.get("reviewers", [])]
    if pr["status"] != run.pr_status or votes != run.pr_votes:
        store.update_run(run_id, pr_status=pr["status"], pr_votes=votes)
        for v in votes:
            if v not in run.pr_votes:
                store.log(run_id, f"🗳️ {v['reviewer']} vota {v['vote']:+d} en la PR !{run.pr_id}")
    if pr["status"] == "completed":
        store.mark(run_id, "pr", "end")
        _verify_merge(run_id)
        store.update_run(run_id, state=RunState.MERGEADO)
        store.mark(run_id, "registro_confirmacion", "start")
        store.log(run_id, "✅ PR completada: los tests están en main. Revisa el registro propuesto en Azure Test Plans")
    elif pr["status"] == "abandoned":
        store.update_run(run_id, state=RunState.DESCARTADO)
        store.log(run_id, "🗑️ La PR se ha abandonado: la ejecución queda descartada", "warn")
    return pr["status"]


def _verify_merge(run_id: int) -> None:
    run = store.get_run(run_id)
    for c in store.cases(run_id):
        if c.status != CaseStatus.APROBADO:
            continue
        merged = gitops.show(settings.remote_repo, "main", c.file_path)
        if merged is None:
            store.log(run_id, f"⚠️ {c.file_path} no aparece en main tras el merge", "warn")
        elif merged != render_test_file(run.test_class, c.method_name, run.feature_id, c.ext_id, c.title, c.code):
            store.log(run_id, f"ℹ️ {c.ext_id}: el fichero en main difiere de lo revisado en el asistente")


# ======================================================================== GATE 3 y registro

def registration_preview(run_id: int) -> list[dict]:
    run = store.get_run(run_id)
    out = []
    for c in store.cases(run_id):
        if c.status != CaseStatus.APROBADO:
            continue
        out.append({"case_id": c.id, "ext_id": c.ext_id, "title": f"{c.ext_id} · {c.title}",
                    "steps": _steps(c), "test": fqn(run.test_class, c.method_name), "azure_id": c.azure_id,
                    "tags": _tags(run)})
    return out


def _steps(c: CaseDraft) -> list[tuple[str, str]]:
    steps = [(s["accion"], s.get("esperado", "")) for s in c.steps]
    if steps and c.expected and not any(e for _, e in steps):
        steps[-1] = (steps[-1][0], c.expected.replace("\n", "; "))
    return steps


def _tags(run: Run) -> str:
    version = (run.dff_meta or {}).get("version")
    return "; ".join(["qa-assistant", "automatizado"] + ([f"v{version}"] if version else []))


def confirm_registration(run_id: int, user: str) -> None:
    run = store.get_run(run_id)
    _require(run, RunState.MERGEADO)
    store.mark(run_id, "registro_confirmacion", "end")
    store.decide(run_id, user, "GATE 3 · Confirma el registro en Azure Test Plans",
                 f"Feature #{run.feature_id}, plan «{run.plan_name}», suite «{run.suite_name}»")
    start_registration(run_id, user)


def start_registration(run_id: int, user: str = "Asistente QA") -> None:
    store.update_run(run_id, state=RunState.REGISTRANDO)
    _spawn(run_id, "registro", "Registrando en Azure DevOps", lambda: _register(run_id, user))


def _register(run_id: int, user: str) -> None:
    from mocks.azure_devops.store import steps_xml, new_automation_id  # formato idéntico al de Azure

    run = store.get_run(run_id)
    store.mark(run_id, "registro", "start")
    api = azure(run_id, user)
    suite_id = run.suite_id
    if suite_id is None:
        root = next(p for p in api.plans() if p["id"] == run.plan_id)["rootSuite"]["id"]
        existing = next((s for s in api.suites(run.plan_id) if s["name"] == run.suite_name), None)
        suite = existing or api.create_suite(run.plan_id, run.suite_name, root)
        suite_id = suite["id"]
        store.update_run(run_id, suite_id=suite_id)
        store.log(run_id, f"📁 Suite «{run.suite_name}» {'reutilizada' if existing else 'creada'} (#{suite_id})")
    for item in registration_preview(run_id):
        if item["azure_id"]:
            store.log(run_id, f"   {item['ext_id']} ya estaba registrado como #{item['azure_id']}: se reutiliza")
            continue
        wi = api.create_test_case({
            "System.Title": item["title"],
            "System.State": "Ready",
            "System.AreaPath": "QA-Web\\Tienda web",
            "System.Tags": item["tags"],
            "Microsoft.VSTS.TCM.Steps": steps_xml(item["steps"]),
            "Microsoft.VSTS.TCM.AutomatedTestName": item["test"],
            "Microsoft.VSTS.TCM.AutomatedTestStorage": settings.test_assembly,
            "Microsoft.VSTS.TCM.AutomatedTestType": "xUnit",
            "Microsoft.VSTS.TCM.AutomatedTestId": new_automation_id(),
            "Microsoft.VSTS.TCM.AutomationStatus": "Automated",
        }, run.feature_id)
        store.update_case(item["case_id"], azure_id=wi["id"])
        store.log(run_id, f"   🧾 {item['ext_id']} → Test Case #{wi['id']} enlazado a la Feature #{run.feature_id}")
    ids = [c.azure_id for c in store.cases(run_id) if c.status == CaseStatus.APROBADO and c.azure_id]
    already = set(api.suite_cases(run.plan_id, suite_id))
    todo = [i for i in ids if i not in already]
    if todo:
        api.add_to_suite(run.plan_id, suite_id, todo)
    store.log(run_id, f"📋 {len(ids)} casos en la suite «{run.suite_name}» del plan «{run.plan_name}»")
    store.mark(run_id, "registro", "end")
    store.update_run(run_id, state=RunState.REGISTRADO)
    store.log(run_id, "🏁 Registro completado")


# ======================================================================== reintentos

def retry(run_id: int, user: str) -> None:
    run = store.get_run(run_id)
    _require(run, RunState.ERROR)
    store.decide(run_id, user, "Reintenta la fase que falló", run.failed_phase or "")
    phase = run.failed_phase
    if phase == "extraccion":
        for c in store.cases(run_id):
            with store.session() as s:
                s.delete(s.get(CaseDraft, c.id))
                s.commit()
        start_extraction(run_id)
    elif phase in ("generacion", "ejecucion"):
        start_generation(run_id)
    elif phase == "pr":
        store.update_run(run_id, state=RunState.EN_REVISION)
        approve_review(run_id, user)
    elif phase == "registro":
        start_registration(run_id, user)
    else:
        raise GateError(f"No se sabe reintentar la fase «{phase}»")


def discard(run_id: int, user: str) -> None:
    store.decide(run_id, user, "Descarta la ejecución")
    store.update_run(run_id, state=RunState.DESCARTADO)
