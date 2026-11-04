"""Detalle de una ejecución: pipeline, las tres aprobaciones de QA, código, PR, registro y actividad."""

from __future__ import annotations

import difflib

from nicegui import run as nrun
from nicegui import ui

from .. import store
from ..config import settings
from ..domain.models import CaseDraft, CaseStatus, Run, RunState
from ..pipeline import service
from ..pipeline.service import GateError
from .theme import USERS, current_user, fmt_minutes, frame, local_time, minutes_between, state_badge

PIPE = [
    ("Documento", "description", False, "extraccion"),
    ("Casos", "fact_check", True, "revision_casos"),
    ("Tests C#", "code", False, "generacion"),
    ("Revisión", "rate_review", True, "revision_codigo"),
    ("Pull request", "merge", False, "pr"),
    ("Registro", "inventory", True, "registro_confirmacion"),
    ("Registrado", "verified", False, "registro"),
]
STATE_INDEX = {RunState.EXTRAYENDO: 0, RunState.EXTRAIDO: 1, RunState.GENERANDO: 2, RunState.EN_REVISION: 3,
               RunState.PR_ABIERTA: 4, RunState.MERGEADO: 5, RunState.REGISTRANDO: 6, RunState.REGISTRADO: 7,
               RunState.DESCARTADO: -1}
PHASE_INDEX = {"extraccion": 0, "generacion": 2, "ejecucion": 3, "pr": 3, "registro": 6}
RESULT = {"passed": ("En verde", "positive", "check_circle"), "failed": ("Falla", "negative", "cancel"),
          "not_built": ("No compila", "deep-orange", "build_circle"), None: ("Sin ejecutar", "grey", "schedule")}


def _steps_to_text(steps: list[dict]) -> str:
    return "\n".join(s["accion"] + (f"  =>  {s['esperado']}" if s.get("esperado") else "") for s in steps)


def _text_to_steps(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        accion, _, esperado = line.partition("=>")
        out.append({"accion": accion.strip(), "esperado": esperado.strip()})
    return out


def _diff(a: str, b: str, a_name: str, b_name: str) -> str:
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), a_name, b_name)) or "(sin cambios)"


@ui.page("/run/{run_id}")
def run_page(run_id: int) -> None:
    frame("home")
    if not store.get_run(run_id):
        ui.label("Ejecución no encontrada").classes("p-8 text-lg")
        return
    opened: set[int] = set()

    async def act(fn, *args, ok: str | None = None) -> None:
        try:
            await nrun.io_bound(fn, *args)
            if ok:
                ui.notify(ok, type="positive")
        except GateError as e:
            ui.notify(str(e), type="warning", multi_line=True)
        except Exception as e:  # noqa: BLE001 - se enseña al usuario
            ui.notify(f"Error: {e}", type="negative", multi_line=True)
        refresh_all()

    # ------------------------------------------------------------------ cabecera y pipeline

    @ui.refreshable
    def header() -> None:
        r = store.get_run(run_id)
        with ui.row().classes("w-full items-start gap-4"):
            with ui.column().classes("gap-1 flex-1 min-w-0"):
                ui.link("← Ejecuciones", "/").classes("text-sm text-slate-500 no-underline")
                with ui.row().classes("items-center gap-3"):
                    ui.label(f"#{r.id} · {r.dff_name}").classes("text-2xl font-bold truncate")
                    state_badge(r.state, r.busy)
                meta = r.dff_meta or {}
                ui.label(f"Feature #{r.feature_id} «{r.feature_title}» · Test Plan «{r.plan_name}» · suite "
                         f"«{r.suite_name}»{' (nueva)' if r.suite_id is None and r.state != RunState.REGISTRADO else ''}"
                         + (f" · versión {meta['version']}" if meta.get("version") else "")).classes(
                    "text-slate-600 text-sm")
                ui.label(f"Creada por {USERS.get(r.created_by, r.created_by)} el {local_time(r.created_at)} · IA: "
                         f"{'Claude (' + settings.claude_model + ')' if r.ai_mode == 'claude' else 'simulada'}"
                         f" · rama {r.branch}").classes("text-xs text-slate-500")
            if r.busy:
                with ui.row().classes("items-center gap-2 bg-indigo-50 text-indigo-800 rounded-xl px-4 py-2"):
                    ui.spinner(size="20px")
                    ui.label(r.busy + "…").classes("font-medium")

    @ui.refreshable
    def pipeline() -> None:
        r = store.get_run(run_id)
        idx = STATE_INDEX.get(RunState(r.state), PHASE_INDEX.get(r.failed_phase or "", 0))
        with ui.row().classes("w-full gap-2 no-wrap items-stretch"):
            for i, (label, icon, gate, phase) in enumerate(PIPE):
                t = (r.timings or {}).get(phase, {})
                dur = minutes_between(t.get("start"), t.get("end"))
                cls = "pipe-step flex-1"
                if gate:
                    cls += " gate"
                if r.state == RunState.ERROR and i == idx:
                    cls += " error"
                elif i < idx or r.state == RunState.REGISTRADO:
                    cls += " done"
                elif i == idx:
                    cls += " current"
                with ui.element("div").classes(cls):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        done = i < idx or r.state == RunState.REGISTRADO
                        ui.icon("check_circle" if done else icon,
                                color="positive" if done else ("amber-8" if gate else "indigo"), size="20px")
                        ui.label(label).classes("font-semibold text-sm truncate")
                        if gate:
                            ui.icon("person", size="15px", color="amber-9").tooltip("Aprobación de QA")
                    sub = fmt_minutes(dur) if dur is not None else ("en curso" if i == idx else "")
                    ui.label(sub).classes("text-[11px] text-slate-500")

    # ------------------------------------------------------------------ contenido por estado

    @ui.refreshable
    def main() -> None:
        r = store.get_run(run_id)
        cases = store.cases(run_id)
        st = RunState(r.state)
        if r.busy and st in (RunState.EXTRAYENDO, RunState.REGISTRANDO):
            progress(r, cases)
        elif st == RunState.GENERANDO or (r.busy and st == RunState.EN_REVISION):
            generating(r, cases)
        elif st == RunState.EXTRAIDO:
            gate1(r, cases)
        elif st == RunState.EN_REVISION:
            gate2(r, cases)
        elif st == RunState.PR_ABIERTA:
            pr_view(r)
        elif st == RunState.MERGEADO:
            gate3(r)
        elif st == RunState.REGISTRADO:
            done_view(r, cases)
        elif st == RunState.ERROR:
            error_view(r)
        elif st == RunState.DESCARTADO:
            with ui.element("div").classes("card p-6 w-full"):
                ui.label("Ejecución descartada").classes("text-lg font-semibold")
        else:
            progress(r, cases)

    def progress(r: Run, cases: list[CaseDraft]) -> None:
        with ui.element("div").classes("card p-8 w-full"):
            with ui.row().classes("items-center gap-4"):
                ui.spinner("dots", size="40px", color="indigo")
                with ui.column().classes("gap-0"):
                    ui.label(r.busy or "Trabajando…").classes("text-lg font-semibold")
                    ui.label("Puedes seguir el detalle en la actividad de la derecha.").classes("text-slate-500")
            for _ in range(3):
                ui.skeleton(height="48px").classes("w-full mt-3 rounded-lg")

    def generating(r: Run, cases: list[CaseDraft]) -> None:
        approved = [c for c in cases if c.status == CaseStatus.APROBADO]
        done = sum(1 for c in approved if c.code)
        with ui.element("div").classes("card p-6 w-full"):
            with ui.row().classes("items-center gap-4 w-full"):
                ui.spinner("dots", size="36px", color="indigo")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(r.busy or "Generando").classes("text-lg font-semibold")
                    ui.label(f"{done}/{len(approved)} tests escritos · los selectores nuevos se validan contra la "
                             "web real y cada test se compila antes de seguir").classes("text-slate-500 text-sm")
            ui.linear_progress(value=done / max(len(approved), 1), show_value=False).props("rounded color=indigo").classes(
                "mt-3")
            for c in approved:
                label, color, icon = RESULT[c.result] if c.code else ("Pendiente", "grey", "hourglass_empty")
                if c.code and c.result is None:
                    label, color, icon = ("Escrito, pendiente de ejecutar", "indigo", "edit_note")
                with ui.row().classes("items-center gap-3 w-full py-2 border-b border-slate-100"):
                    ui.icon(icon, color=color)
                    ui.label(c.ext_id).classes("mono text-sm w-36")
                    ui.label(c.title).classes("flex-1")
                    for comp in c.components_new:
                        ui.badge(comp, color="purple").props("outline")
                    ui.badge(label, color=color)

    # ------------------------------------------------------------------ GATE 1

    def gate1(r: Run, cases: list[CaseDraft]) -> None:
        warn = sum(1 for c in cases if c.warnings)
        dups = sum(1 for c in cases if c.duplicate_of)
        pending = sum(1 for c in cases if c.status == CaseStatus.PENDIENTE)
        approved = sum(1 for c in cases if c.status == CaseStatus.APROBADO)
        with ui.element("div").classes("card p-5 w-full border-amber-300 bg-amber-50/40"):
            with ui.row().classes("items-center gap-3 w-full"):
                ui.icon("person", color="amber-8", size="28px")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label("Gate 1 · Revisa los casos extraídos").classes("text-lg font-semibold")
                    ui.label(f"{len(cases)} casos · {warn} con avisos · {dups} ya existen en Azure · "
                             f"{approved} aprobados · {pending} sin decidir. Corrige lo que haga falta: el asistente "
                             "solo automatizará los casos que apruebes.").classes("text-slate-600 text-sm")
                ui.button("Aprobar los que no tienen avisos", icon="done_all", on_click=lambda: approve_clean(cases)) \
                    .props("outline no-caps")
            for note in r.notes or []:
                ui.label(f"⚠️ {note}").classes("text-amber-800 text-sm mt-2")
        for c in cases:
            case_card_gate1(c)
        with ui.row().classes("w-full justify-end gap-3 sticky bottom-0 bg-[#f5f6fa]/95 py-3"):
            ui.button("Descartar ejecución", icon="delete", on_click=lambda: act(service.discard, run_id, current_user())) \
                .props("flat no-caps color=grey-8")
            ui.button(f"Aprobar {approved} casos y generar los tests", icon="play_arrow",
                      on_click=lambda: act(service.approve_cases, run_id, current_user(), ok="Generación en marcha")) \
                .props("unelevated no-caps size=lg").set_enabled(pending == 0 and approved > 0)

    async def approve_clean(cases: list[CaseDraft]) -> None:
        for c in cases:
            if c.status == CaseStatus.PENDIENTE and not c.warnings:
                await nrun.io_bound(service.set_case_status, c.id, CaseStatus.APROBADO, current_user())
        refresh_all()

    def case_card_gate1(c: CaseDraft) -> None:
        with ui.element("div").classes(f"card case-card {c.status} w-full p-4"):
            with ui.row().classes("items-center gap-3 w-full no-wrap"):
                ui.label(c.ext_id).classes("mono text-sm bg-slate-100 rounded px-2 py-0.5")
                ui.label(c.title).classes("font-semibold flex-1 min-w-0 truncate")
                if c.edited_by_human:
                    ui.badge("editado por QA", color="indigo").props("outline")
                ui.toggle({"aprobado": "Aprobar", "descartado": "Descartar", "pendiente": "Pendiente"}, value=c.status,
                          on_change=lambda e, cid=c.id: act(service.set_case_status, cid, CaseStatus(e.value),
                                                            current_user())).props("no-caps dense unelevated "
                                                                                   "toggle-color=indigo")
            for w in c.warnings:
                with ui.row().classes("items-start gap-2 mt-2 no-wrap"):
                    ui.icon("warning", color="amber-8", size="18px")
                    ui.label(w).classes("text-sm text-amber-900")
            with ui.expansion("Pasos, datos y resultado esperado", value=c.id in opened,
                              on_value_change=lambda e, cid=c.id: opened.add(cid) if e.value else opened.discard(cid)) \
                    .classes("w-full mt-1 text-sm").props("dense"):
                title = ui.input("Título", value=c.title).props("outlined dense").classes("w-full")
                pre = ui.input("Precondiciones", value=c.preconditions).props("outlined dense").classes("w-full")
                steps = ui.textarea("Pasos (uno por línea; «acción  =>  esperado» si el paso tiene su propio "
                                    "resultado)", value=_steps_to_text(c.steps)).props("outlined autogrow").classes(
                    "w-full mono")
                with ui.row().classes("w-full gap-3 no-wrap"):
                    data = ui.textarea("Datos de prueba", value=c.data).props("outlined autogrow").classes("flex-1")
                    expected = ui.textarea("Resultado esperado (una comprobación por línea)", value=c.expected).props(
                        "outlined autogrow").classes("flex-1")
                async def save(cid=c.id) -> None:
                    user = current_user()
                    await act(lambda: service.edit_case(cid, user, title=title.value, preconditions=pre.value,
                                                        steps=_text_to_steps(steps.value), data=data.value,
                                                        expected=expected.value), ok="Caso actualizado")

                ui.button("Guardar cambios", icon="save", on_click=save).props("unelevated no-caps dense")

    # ------------------------------------------------------------------ GATE 2

    def gate2(r: Run, cases: list[CaseDraft]) -> None:
        approved = [c for c in cases if c.status == CaseStatus.APROBADO]
        green = sum(1 for c in approved if c.result == "passed")
        reused = sorted({x for c in approved for x in c.components_reused})
        with ui.element("div").classes("card p-5 w-full border-amber-300 bg-amber-50/40"):
            with ui.row().classes("items-center gap-3 w-full"):
                ui.icon("person", color="amber-8", size="28px")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label("Gate 2 · Revisa el código y los resultados").classes("text-lg font-semibold")
                    ui.label(f"{green}/{len(approved)} tests en verde contra {settings.demo_site_url} · "
                             f"{len(reused)} componentes reutilizados · {len(r.new_components)} mapeos nuevos. Puedes "
                             "editar el código, volver a ejecutar o sacar un caso de la PR.").classes(
                        "text-slate-600 text-sm")
                cost = (r.usage or {}).get("cost_usd")
                if cost:
                    ui.badge(f"IA: {cost:.3f} USD", color="indigo").props("outline")
        if r.new_components:
            with ui.element("div").classes("card p-4 w-full"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("extension", color="purple")
                    ui.label("Mapeos nuevos que irán en la PR").classes("font-semibold")
                    ui.label("· selectores tomados del DOM real y validados antes de aceptarlos").classes(
                        "text-sm text-slate-500")
                ui.table(columns=[{"name": "ref", "label": "Componente", "field": "ref", "align": "left"},
                                  {"name": "selector", "label": "Selector", "field": "selector", "align": "left"},
                                  {"name": "tipo", "label": "Tipo", "field": "tipo"},
                                  {"name": "descripcion", "label": "Descripción", "field": "descripcion", "align": "left"},
                                  {"name": "casos", "label": "Casos", "field": "casos", "align": "left"}],
                         rows=[{"ref": f"{x['pagina']}.{x['nombre']}", "selector": x["selector"], "tipo": x["tipo"],
                                "descripcion": x["descripcion"], "casos": ", ".join(x.get("casos", []))}
                               for x in r.new_components]).props("flat dense").classes("w-full mono text-xs")
        for c in approved:
            case_card_gate2(r, c)
        excluded = [c for c in cases if c.status == CaseStatus.DESCARTADO]
        if excluded:
            ui.label("Fuera de la PR: " + ", ".join(f"{c.ext_id}" for c in excluded)).classes("text-sm text-slate-500")
        with ui.row().classes("w-full justify-end gap-3 sticky bottom-0 bg-[#f5f6fa]/95 py-3"):
            ui.button("Volver a ejecutar los tests", icon="replay",
                      on_click=lambda: act(service.rerun, run_id, current_user())).props("outline no-caps")
            ui.button(f"Aprobar y abrir la pull request ({green}/{len(approved)} en verde)", icon="merge",
                      on_click=lambda: act(service.approve_review, run_id, current_user(), ok="Abriendo la PR")) \
                .props("unelevated no-caps size=lg").set_enabled(bool(approved) and green == len(approved))

    def case_card_gate2(r: Run, c: CaseDraft) -> None:
        label, color, icon = RESULT[c.result]
        with ui.element("div").classes(f"card case-card {'aprobado' if c.result == 'passed' else 'pendiente'} w-full p-4"):
            with ui.row().classes("items-center gap-3 w-full no-wrap"):
                ui.icon(icon, color=color, size="24px")
                ui.label(c.ext_id).classes("mono text-sm bg-slate-100 rounded px-2 py-0.5")
                ui.label(c.title).classes("font-semibold flex-1 min-w-0 truncate")
                if c.attempts > 1:
                    ui.badge(f"{c.attempts} intentos", color="indigo").props("outline").tooltip(
                        "La IA corrigió el test con el error de la ejecución")
                if c.code.strip() != c.ai_code.strip():
                    ui.badge("editado por QA", color="indigo")
                for comp in c.components_new:
                    ui.badge(comp, color="purple").props("outline").tooltip("Componente nuevo")
                ui.badge(f"{len(c.components_reused)} reutilizados", color="teal").props("outline").tooltip(
                    ", ".join(c.components_reused) or "—")
                ui.badge(f"{label}" + (f" · {c.duration_ms} ms" if c.result == "passed" else ""), color=color)
            if c.result in ("failed", "not_built") and c.result_message:
                ui.code(c.result_message[:2500], language="text").classes("w-full mt-2 text-xs border-red-200")
            for u in c.unresolved:
                with ui.row().classes("items-start gap-2 mt-1 no-wrap"):
                    ui.icon("warning", color="amber-8", size="18px")
                    ui.label(u).classes("text-sm text-amber-900")
            with ui.expansion("Código, cambios y notas de la IA", value=c.id in opened or c.result != "passed",
                              on_value_change=lambda e, cid=c.id: opened.add(cid) if e.value else opened.discard(cid)) \
                    .classes("w-full mt-1 text-sm").props("dense"):
                ui.label(f"{c.file_path} · {settings.test_namespace}.Generated.{r.test_class}.{c.method_name}()").classes(
                    "mono text-xs text-slate-500")
                with ui.tabs().props("dense no-caps align=left").classes("text-slate-700") as tabs:
                    t_code = ui.tab("Código")
                    t_qa = ui.tab("Cambios de QA")
                    t_fix = ui.tab("Autocorrección") if c.attempts > 1 else None
                    t_notes = ui.tab("Notas de la IA")
                with ui.tab_panels(tabs, value=t_code).classes("w-full bg-transparent"):
                    with ui.tab_panel(t_code).classes("p-0 pt-2"):
                        editor = ui.codemirror(c.code, language="C#", theme="githubLight").classes("w-full")
                        with ui.row().classes("gap-2 mt-2"):
                            ui.button("Guardar cambios", icon="save",
                                      on_click=lambda cid=c.id: act(service.save_code, cid, editor.value, current_user(),
                                                                    ok="Código guardado: vuelve a ejecutar los tests")) \
                                .props("unelevated no-caps dense")
                            ui.button("Sacar de la PR", icon="remove_circle_outline",
                                      on_click=lambda cid=c.id: act(service.exclude_case, cid, current_user())) \
                                .props("flat no-caps dense color=grey-8")
                    with ui.tab_panel(t_qa).classes("p-0 pt-2"):
                        ui.code(_diff(c.ai_code, c.code, "generado por la IA", "revisado por QA"), language="diff") \
                            .classes("w-full")
                    if t_fix:
                        with ui.tab_panel(t_fix).classes("p-0 pt-2"):
                            ui.code(_diff(c.first_ai_code, c.ai_code, "intento 1", f"intento {c.attempts}"),
                                    language="diff").classes("w-full")
                    with ui.tab_panel(t_notes).classes("p-0 pt-2"):
                        ui.markdown(c.ai_notes or "_Sin notas_").classes("text-sm")

    # ------------------------------------------------------------------ PR

    def pr_view(r: Run) -> None:
        with ui.element("div").classes("card p-6 w-full"):
            with ui.row().classes("items-center gap-4 w-full"):
                ui.icon("merge", color="indigo", size="40px")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(f"Pull request !{r.pr_id} abierta en Azure Repos").classes("text-lg font-semibold")
                    ui.label(f"{r.branch} → main · {settings.azure_repo}").classes("mono text-sm text-slate-500")
                ui.button("Revisar la PR en Azure Repos", icon="open_in_new",
                          on_click=lambda: ui.navigate.to(f"{settings.azure_console_url}/pr/{r.pr_id}", new_tab=True)) \
                    .props("unelevated no-caps")
            ui.separator().classes("my-4")
            ui.label("La revisión y el merge se hacen en Azure Repos, como cualquier otro cambio del equipo. En cuanto "
                     "un revisor apruebe y complete la PR, el asistente lo detecta y te propone el registro en Azure "
                     "Test Plans.").classes("text-slate-600")
            with ui.row().classes("items-center gap-2 mt-3"):
                ui.label("Votos:").classes("text-sm text-slate-500")
                if not r.pr_votes:
                    ui.label("ninguno todavía").classes("text-sm")
                for v in r.pr_votes:
                    ok = v["vote"] >= 5
                    ui.badge(f"{v['reviewer']}: {'aprueba' if ok else 'rechaza' if v['vote'] <= -10 else 'espera'}",
                             color="positive" if ok else "negative")
                ui.space()
                ui.button("Comprobar ahora", icon="sync", on_click=lambda: act(service.check_pr, run_id)).props(
                    "flat no-caps")

    # ------------------------------------------------------------------ GATE 3

    def gate3(r: Run) -> None:
        preview = service.registration_preview(run_id)
        with ui.element("div").classes("card p-5 w-full border-amber-300 bg-amber-50/40"):
            with ui.row().classes("items-center gap-3 w-full"):
                ui.icon("person", color="amber-8", size="28px")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label("Gate 3 · Confirma dónde se registran los casos").classes("text-lg font-semibold")
                    ui.label("La PR ya está en main. Esto es lo que se va a crear en Azure DevOps:").classes(
                        "text-slate-600 text-sm")
            with ui.row().classes("gap-6 mt-3"):
                for label, value, icon in [("Feature", f"#{r.feature_id} {r.feature_title}", "emoji_events"),
                                           ("Test Plan", r.plan_name, "science"),
                                           ("Suite", r.suite_name + (" (se crea)" if r.suite_id is None else ""),
                                            "folder")]:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(icon, color="indigo")
                        ui.label(f"{label}:").classes("text-slate-500 text-sm")
                        ui.label(value).classes("font-semibold text-sm")
        for item in preview:
            with ui.element("div").classes("card p-4 w-full"):
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.icon("science", color="teal")
                    ui.label(item["title"]).classes("font-semibold flex-1")
                    ui.badge("Test Case nuevo" if not item["azure_id"] else f"#{item['azure_id']}",
                             color="teal").props("outline")
                ui.label(f"AutomatedTestName = {item['test']} · {settings.test_assembly} · xUnit").classes(
                    "mono text-xs text-slate-600 mt-1")
                ui.label(f"Etiquetas: {item['tags']}").classes("text-xs text-slate-500")
                ui.table(columns=[{"name": "n", "label": "#", "field": "n"},
                                  {"name": "a", "label": "Acción", "field": "a", "align": "left"},
                                  {"name": "e", "label": "Resultado esperado", "field": "e", "align": "left"}],
                         rows=[{"n": i + 1, "a": a, "e": e} for i, (a, e) in enumerate(item["steps"])]) \
                    .props("flat dense wrap-cells").classes("w-full mt-2 text-xs")
        with ui.row().classes("w-full justify-end gap-3 sticky bottom-0 bg-[#f5f6fa]/95 py-3"):
            ui.button(f"Confirmar el registro de {len(preview)} Test Cases", icon="inventory",
                      on_click=lambda: act(service.confirm_registration, run_id, current_user(),
                                           ok="Registrando en Azure DevOps")).props("unelevated no-caps size=lg")

    # ------------------------------------------------------------------ final y error

    def done_view(r: Run, cases: list[CaseDraft]) -> None:
        reg = [c for c in cases if c.azure_id]
        total = minutes_between(r.created_at.isoformat() if r.created_at else None,
                                (r.timings or {}).get("registro", {}).get("end"))
        human = sum(minutes_between(t.get("start"), t.get("end")) or 0 for k, t in (r.timings or {}).items()
                    if k in ("revision_casos", "revision_codigo", "pr", "registro_confirmacion"))
        with ui.element("div").classes("card p-6 w-full border-green-300 bg-green-50/50"):
            with ui.row().classes("items-center gap-4"):
                ui.icon("verified", color="positive", size="44px")
                with ui.column().classes("gap-0"):
                    ui.label(f"{len(reg)} Test Cases automatizados y registrados").classes("text-xl font-bold")
                    ui.label(f"Suite «{r.suite_name}» del plan «{r.plan_name}», enlazados a la Feature #{r.feature_id}. "
                             f"El código está en main (PR !{r.pr_id}).").classes("text-slate-600")
            with ui.row().classes("gap-8 mt-4"):
                for label, value in [("Tiempo total", fmt_minutes(total)), ("Tiempo de QA (incluye esperas)",
                                                                           fmt_minutes(human)),
                                     ("Coste de IA", f"{(r.usage or {}).get('cost_usd', 0):.3f} USD"
                                      if r.ai_mode == "claude" else "simulada")]:
                    with ui.column().classes("gap-0"):
                        ui.label(label).classes("text-xs text-slate-500")
                        ui.label(value).classes("text-lg font-semibold")
        for c in reg:
            with ui.row().classes("card p-3 w-full items-center gap-3"):
                ui.icon("science", color="teal")
                ui.label(f"#{c.azure_id}").classes("mono text-slate-500")
                ui.label(f"{c.ext_id} · {c.title}").classes("flex-1")
                ui.label(f"{r.test_class}.{c.method_name}").classes("mono text-xs text-slate-500")
                ui.badge("Automated", color="positive")
        ui.button("Ver en Azure Test Plans", icon="open_in_new",
                  on_click=lambda: ui.navigate.to(f"{settings.azure_console_url}/plans", new_tab=True)).props(
            "outline no-caps")

    def error_view(r: Run) -> None:
        with ui.element("div").classes("card p-6 w-full border-red-300 bg-red-50/50"):
            with ui.row().classes("items-center gap-4 w-full"):
                ui.icon("error", color="negative", size="40px")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(f"Ha fallado la fase «{r.failed_phase}»").classes("text-lg font-semibold")
                    ui.label(r.error or "").classes("text-red-800")
                    ui.label("No se ha perdido nada: lo ya hecho está guardado y el reintento continúa donde se "
                             "quedó.").classes("text-sm text-slate-600 mt-1")
            with ui.row().classes("gap-3 mt-4"):
                ui.button("Reintentar", icon="replay", on_click=lambda: act(service.retry, run_id, current_user())) \
                    .props("unelevated no-caps")
                ui.button("Descartar", icon="delete", on_click=lambda: act(service.discard, run_id, current_user())) \
                    .props("flat no-caps color=grey-8")

    # ------------------------------------------------------------------ actividad y decisiones

    @ui.refreshable
    def side() -> None:
        with ui.element("div").classes("card w-full p-0 overflow-hidden"):
            with ui.tabs().props("dense no-caps align=justify").classes("w-full border-b border-slate-100") as tabs:
                t_log = ui.tab("Actividad", icon="terminal")
                t_dec = ui.tab("Decisiones de QA", icon="how_to_reg")
            with ui.tab_panels(tabs, value=side_tab["v"] or t_log,
                               on_change=lambda e: side_tab.update(v=e.value)).classes("w-full"):
                with ui.tab_panel(t_log).classes("p-0"):
                    with ui.scroll_area().classes("h-[640px] w-full bg-slate-50") as area:
                        with ui.column().classes("gap-0 p-3"):
                            for e in store.logs(run_id):
                                if e.level == "debug":
                                    continue
                                with ui.row().classes("gap-2 no-wrap items-start"):
                                    ui.label(local_time(e.at, "%H:%M:%S")).classes("logline text-slate-400 shrink-0")
                                    ui.label(e.text).classes(f"logline {e.level} flex-1 min-w-0")
                    area.scroll_to(percent=1.0)
                with ui.tab_panel(t_dec).classes("p-3"):
                    decs = store.decisions(run_id)
                    if not decs:
                        ui.label("Sin decisiones todavía").classes("text-slate-500 text-sm")
                    with ui.timeline(side="right").classes("w-full"):
                        for d in decs:
                            ui.timeline_entry(d.detail, title=d.action,
                                              subtitle=f"{USERS.get(d.user, d.user)} · {local_time(d.at, '%d/%m %H:%M:%S')}",
                                              icon="gavel" if "GATE" in d.action else "person",
                                              color="amber-8" if "GATE" in d.action else "indigo")

    side_tab: dict = {"v": None}

    # ------------------------------------------------------------------ layout y refresco

    with ui.column().classes("w-full max-w-[1500px] mx-auto p-6 gap-4"):
        header()
        pipeline()
        with ui.row().classes("w-full gap-5 items-start no-wrap"):
            with ui.column().classes("flex-1 min-w-0 gap-3"):
                main()
            with ui.column().classes("w-[440px] shrink-0 sticky top-20"):
                side()

    def content_key() -> tuple:
        r = store.get_run(run_id)
        cs = store.cases(run_id)
        return (r.state, r.busy, r.pr_status, len(r.pr_votes or []), len(r.new_components or []),
                tuple((c.id, c.status, c.result, c.attempts, c.azure_id, hash(c.code), hash(c.title),
                       hash(tuple(c.warnings)), bool(c.code)) for c in cs))

    seen = {"v": store.get_run(run_id).version, "k": content_key(), "poll": 0}

    def refresh_all() -> None:
        seen["v"] = store.get_run(run_id).version
        seen["k"] = content_key()
        header.refresh()
        pipeline.refresh()
        main.refresh()
        side.refresh()

    async def tick() -> None:
        r = store.get_run(run_id)
        if r.state == RunState.PR_ABIERTA and not r.busy:
            seen["poll"] += 1
            if seen["poll"] % 3 == 0:
                try:
                    await nrun.io_bound(service.check_pr, run_id)
                except Exception:  # noqa: BLE001 - se reintenta en el siguiente tick
                    pass
                r = store.get_run(run_id)
        if r.version != seen["v"]:
            seen["v"] = r.version
            side.refresh()
            key = content_key()
            if key != seen["k"]:
                seen["k"] = key
                header.refresh()
                pipeline.refresh()
                main.refresh()

    ui.timer(1.0, tick)
