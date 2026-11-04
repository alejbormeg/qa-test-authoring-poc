"""Inicio: qué espera una decisión de QA, indicadores y todas las ejecuciones."""

from __future__ import annotations

from nicegui import ui

from .. import store
from ..domain.models import STATE_COLORS, STATE_LABELS, WAITING_HUMAN, CaseStatus, RunState
from . import metrics
from .theme import USERS, frame, kpi, local_time, state_badge

NEXT_ACTION = {
    RunState.EXTRAIDO: ("Revisar los casos extraídos", "fact_check"),
    RunState.EN_REVISION: ("Revisar el código y los resultados", "code"),
    RunState.PR_ABIERTA: ("Aprobar y completar la pull request", "merge"),
    RunState.MERGEADO: ("Confirmar el registro en Azure", "inventory"),
}


@ui.page("/")
def home() -> None:
    frame("home")

    @ui.refreshable
    def content() -> None:
        runs = store.runs()
        m = metrics.compute()
        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-5"):
            with ui.element("div").classes("hero rounded-2xl p-6 w-full"):
                with ui.row().classes("items-center w-full gap-6"):
                    with ui.column().classes("gap-1 flex-1"):
                        ui.label("Del documento funcional al test registrado, con QA al mando").classes(
                            "text-2xl font-bold text-slate-900")
                        ui.label("El asistente lee el DFF, escribe los tests en C# con Playwright reutilizando "
                                 "vuestros mapeos, los ejecuta y prepara la pull request y el registro en Azure "
                                 "Test Plans. Nada avanza sin la aprobación de una persona de QA.").classes(
                            "text-slate-600 max-w-3xl")
                    ui.button("Nueva ejecución", icon="upload_file", on_click=lambda: ui.navigate.to("/nueva")).props(
                        "unelevated no-caps size=lg")
                with ui.row().classes("gap-2 mt-4 flex-wrap"):
                    for i, (label, icon, gate) in enumerate([("DFF", "description", False),
                                                             ("Casos", "fact_check", True),
                                                             ("Tests C#", "code", False), ("Revisión y PR", "merge", True),
                                                             ("Registro en Azure", "inventory", True)]):
                        if i:
                            ui.icon("chevron_right", color="grey-5")
                        with ui.row().classes("items-center gap-1 rounded-full px-3 py-1 "
                                              + ("bg-amber-50 text-amber-800" if gate else "bg-slate-100 text-slate-700")):
                            ui.icon(icon, size="16px")
                            ui.label(label).classes("text-sm")
                            if gate:
                                ui.icon("person", size="14px").tooltip("Requiere aprobación de QA")

            with ui.row().classes("w-full gap-4"):
                kpi("Ejecuciones", str(m["runs"]), "list_alt", f"{m['registered_runs']} registradas en Azure")
                kpi("Tests registrados", str(m["registered_cases"]), "verified", f"de {m['extracted']} casos extraídos",
                    color="positive")
                kpi("En verde a la primera", m["first_green_pct"], "bolt", "tests generados que pasan sin tocar",
                    color="amber-8")
                kpi("Aceptados sin cambios", m["accepted_unchanged_pct"], "thumb_up", "QA no editó el código",
                    color="teal")
                kpi("Ahorro estimado", m["saved_hours"], "schedule", m["saved_hint"], color="indigo")

            waiting = [r for r in runs if r.state in WAITING_HUMAN]
            if waiting:
                ui.label("Pendiente de tu decisión").classes("text-lg font-semibold mt-1")
                with ui.row().classes("w-full gap-3"):
                    for r in waiting:
                        action, icon = NEXT_ACTION[RunState(r.state)]
                        with ui.element("div").classes("card p-4 w-[360px] cursor-pointer hover:shadow-md").on(
                                "click", lambda rid=r.id: ui.navigate.to(f"/run/{rid}")):
                            with ui.row().classes("items-center gap-3 no-wrap"):
                                ui.icon(icon, color="amber-8", size="28px")
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(action).classes("font-semibold")
                                    ui.label(f"#{r.id} · {r.dff_name}").classes("text-sm text-slate-500 truncate")
                                    ui.label(f"Feature #{r.feature_id} {r.feature_title}").classes(
                                        "text-xs text-slate-500 truncate")

            ui.label("Ejecuciones").classes("text-lg font-semibold mt-1")
            rows = []
            for r in runs:
                cs = store.cases(r.id)
                approved = [c for c in cs if c.status == CaseStatus.APROBADO]
                rows.append({"id": r.id, "dff": r.dff_name, "feature": f"#{r.feature_id} {r.feature_title}",
                             "state": r.state, "busy": r.busy or "",
                             "state_label": STATE_LABELS[RunState(r.state)], "state_color": STATE_COLORS[RunState(r.state)], "casos": f"{len(approved)}/{len(cs)}",
                             "verdes": sum(1 for c in approved if c.result == "passed"),
                             "por": USERS.get(r.created_by, r.created_by).split(" · ")[0],
                             "fecha": local_time(r.created_at), "ia": "Claude" if r.ai_mode == "claude" else "Simulada"})
            if not rows:
                with ui.element("div").classes("card p-10 w-full text-center"):
                    ui.icon("inbox", size="48px", color="grey-5")
                    ui.label("Todavía no hay ejecuciones. Sube un DFF para empezar.").classes("text-slate-500")
                return
            table = ui.table(columns=[
                {"name": "id", "label": "#", "field": "id", "align": "left", "sortable": True},
                {"name": "dff", "label": "Documento", "field": "dff", "align": "left"},
                {"name": "feature", "label": "Feature", "field": "feature", "align": "left"},
                {"name": "state", "label": "Estado", "field": "state", "align": "left"},
                {"name": "casos", "label": "Casos aprobados", "field": "casos"},
                {"name": "verdes", "label": "En verde", "field": "verdes"},
                {"name": "ia", "label": "IA", "field": "ia"},
                {"name": "por", "label": "Creada por", "field": "por", "align": "left"},
                {"name": "fecha", "label": "Fecha", "field": "fecha"},
            ], rows=rows, row_key="id").classes("w-full card").props("flat")
            table.add_slot("body-cell-state", r"""
                <q-td :props="props">
                  <q-badge :color="props.row.busy ? 'blue-grey' : props.row.state_color" class="q-px-sm q-py-xs">
                    <q-spinner v-if="props.row.busy" size="12px" class="q-mr-xs"/>{{ props.row.state_label }}
                  </q-badge>
                </q-td>""")
            table.on("rowClick", lambda e: ui.navigate.to(f"/run/{e.args[1]['id']}"))
            table.classes("cursor-pointer")

    content()
    seen = {"v": None}

    def tick() -> None:
        v = tuple((r.id, r.version) for r in store.runs())
        if v != seen["v"]:
            if seen["v"] is not None:
                content.refresh()
            seen["v"] = v

    ui.timer(2.0, tick)


__all__ = ["home", "state_badge"]
