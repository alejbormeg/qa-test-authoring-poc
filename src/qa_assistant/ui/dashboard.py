"""Dashboard de medición: lo que irá al informe de cierre (tiempos, calidad, reutilización y coste)."""

from __future__ import annotations

from nicegui import ui

from .. import store
from ..domain.models import STATE_LABELS, RunState
from . import metrics
from .theme import INK, SERIES, STATUS, fmt_minutes, frame, kpi

AXIS = {"axisLine": {"lineStyle": {"color": INK["grid"]}}, "axisTick": {"show": False},
        "axisLabel": {"color": INK["secondary"], "fontSize": 11}, "splitLine": {"lineStyle": {"color": INK["grid"]}}}
BASE = {"textStyle": {"fontFamily": "system-ui, -apple-system, Segoe UI, sans-serif", "color": INK["primary"]},
        "legend": {"top": 0, "left": 0, "icon": "roundRect", "itemWidth": 10, "itemHeight": 10,
                   "textStyle": {"color": INK["secondary"]}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow", "shadowStyle": {"opacity": 0.06}},
                    "backgroundColor": "#ffffff", "borderColor": INK["grid"], "textStyle": {"color": INK["primary"]}}}


def _bar(color: str, horizontal: bool = False) -> dict:
    radius = [0, 4, 4, 0] if horizontal else [4, 4, 0, 0]
    return {"type": "bar", "barMaxWidth": 18, "itemStyle": {"color": color, "borderRadius": radius,
                                                            "borderColor": INK["surface"], "borderWidth": 1}}


def chart_card(title: str, subtitle: str, options: dict, height: str = "300px") -> None:
    with ui.element("div").classes("card p-4 flex-1 min-w-[420px]"):
        ui.label(title).classes("font-semibold")
        ui.label(subtitle).classes("text-xs text-slate-500 mb-2")
        ui.echart(options).classes("w-full").style(f"height:{height}")


@ui.page("/dashboard")
def dashboard() -> None:
    frame("dashboard")

    @ui.refreshable
    def content() -> None:
        m = metrics.compute()
        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-5"):
            with ui.row().classes("items-end w-full"):
                with ui.column().classes("gap-0 flex-1"):
                    ui.label("Medición").classes("text-2xl font-bold")
                    ui.label("Datos medidos en cada ejecución: alimentan el informe de cierre de la iniciativa.") \
                        .classes("text-slate-600")
                base = ui.number("Línea base: minutos por caso a mano", value=m["baseline"], min=1, step=5,
                                 format="%.0f").props("outlined dense").classes("w-72")

                def save_base() -> None:
                    store.set_setting("baseline_minutes_per_case", str(int(base.value or 45)))
                    content.refresh()

                ui.button("Aplicar", on_click=save_base).props("flat no-caps")

            with ui.row().classes("w-full gap-4"):
                kpi("Tests registrados", str(m["registered_cases"]), "verified",
                    f"{m['registered_runs']} ejecuciones completas", color="positive")
                kpi("Ahorro estimado", m["saved_hours"], "schedule", m["saved_hint"], color="indigo")
                kpi("En verde a la primera", m["first_green_pct"], "bolt", f"{m['final_green_pct']} tras autocorrección",
                    color="amber-8")
                kpi("Aceptados sin cambios", m["accepted_unchanged_pct"], "thumb_up", "QA no editó el código generado",
                    color="teal")
                kpi("Coste de IA por test", f"{m['cost_per_case']:.3f} USD" if m["cost_per_case"] else "—",
                    "payments", f"{m['tokens']:,} tokens en total".replace(",", ".") if m["tokens"] else "IA simulada")

            phases = [(label, kind, m["phase_avg"][key]) for key, label, kind in metrics.PHASES]
            labels = [p[0] for p in phases][::-1]
            auto = [round(v, 2) if (k == "auto" and v is not None) else None for _, k, v in phases][::-1]
            human = [round(v, 2) if (k == "human" and v is not None) else None for _, k, v in phases][::-1]
            with ui.row().classes("w-full gap-4"):
                chart_card(
                    "Minutos de media por fase",
                    "Azul: lo hace el asistente. Naranja: tiempo de QA en cada aprobación (incluye esperas).",
                    {**BASE, "grid": {"left": 210, "right": 30, "top": 34, "bottom": 24},
                     "xAxis": {"type": "value", "name": "min", "nameTextStyle": {"color": INK["muted"]}, **AXIS},
                     "yAxis": {"type": "category", "data": labels, **AXIS, "splitLine": {"show": False}},
                     "series": [{**_bar(SERIES["auto"], True), "name": "Asistente", "stack": "t", "data": auto},
                                {**_bar(SERIES["human"], True), "name": "QA", "stack": "t", "data": human}]},
                    height="320px")
                with ui.element("div").classes("card p-4 w-[380px]"):
                    ui.label("Una ejecución de principio a fin").classes("font-semibold")
                    ui.label("Suma de las ejecuciones registradas").classes("text-xs text-slate-500 mb-3")
                    for label, value, color in [("Trabajo del asistente", fmt_minutes(m["auto_minutes"]), SERIES["auto"]),
                                                ("Tiempo de QA en el asistente", fmt_minutes(m["human_minutes"]),
                                                 SERIES["human"]),
                                                ("Mismo trabajo a mano (línea base)", fmt_minutes(m["manual_minutes"]),
                                                 INK["muted"])]:
                        with ui.row().classes("items-center gap-3 w-full py-2 border-b border-slate-100 no-wrap"):
                            ui.element("div").style(f"width:10px;height:10px;border-radius:3px;background:{color}")
                            ui.label(label).classes("flex-1 text-sm text-slate-700")
                            ui.label(value).classes("font-semibold")
                    ui.label("La línea base es una estimación que introduce el equipo; el resto es medido.") \
                        .classes("text-xs text-slate-500 mt-3")

            outcome_cats = ["A la primera", "Tras autocorrección"]
            with ui.row().classes("w-full gap-4"):
                chart_card(
                    "Resultado de los tests generados",
                    f"{m['approved']} tests ejecutados contra la web. La autocorrección solo actúa con la IA real.",
                    {**BASE, "grid": {"left": 130, "right": 30, "top": 34, "bottom": 24},
                     "xAxis": {"type": "value", "minInterval": 1, **AXIS},
                     "yAxis": {"type": "category", "data": outcome_cats, "inverse": True, **AXIS, "splitLine": {"show": False}},
                     "series": [{**_bar(STATUS["good"], True), "name": "✓ En verde", "stack": "o",
                                 "data": [m["first"]["passed"], m["final"]["passed"]]},
                                {**_bar(STATUS["critical"], True), "name": "✗ Falla", "stack": "o",
                                 "data": [m["first"]["failed"], m["final"]["failed"]]},
                                {**_bar(STATUS["serious"], True), "name": "⚠ No compila", "stack": "o",
                                 "data": [m["first"]["not_built"], m["final"]["not_built"]]}]},
                    height="220px")
                runs = m["per_run"]
                chart_card(
                    "Reutilización de mapeos por ejecución",
                    f"Componentes ya mapeados que se reutilizan frente a mapeos nuevos propuestos "
                    f"({m['new_components']} en total).",
                    {**BASE, "grid": {"left": 40, "right": 20, "top": 34, "bottom": 28},
                     "xAxis": {"type": "category", "data": [r["run"] for r in runs], **AXIS,
                               "splitLine": {"show": False}},
                     "yAxis": {"type": "value", "minInterval": 1, **AXIS},
                     "series": [{**_bar(SERIES["auto"]), "name": "Reutilizados", "data": [r["reused"] for r in runs]},
                                {**_bar(SERIES["human"]), "name": "Nuevos", "data": [r["new"] for r in runs]}]},
                    height="220px")

            with ui.element("div").classes("card p-4 w-full"):
                ui.label("Detalle por ejecución").classes("font-semibold mb-2")
                ui.table(columns=[{"name": "run", "label": "Ejecución", "field": "run", "align": "left"},
                                  {"name": "state", "label": "Estado", "field": "state", "align": "left"},
                                  {"name": "cases", "label": "Tests", "field": "cases"},
                                  {"name": "reused", "label": "Reutilizados", "field": "reused"},
                                  {"name": "new", "label": "Nuevos", "field": "new"},
                                  {"name": "ai", "label": "IA", "field": "ai"},
                                  {"name": "cost", "label": "Coste (USD)", "field": "cost"}],
                         rows=[{**r, "state": STATE_LABELS[RunState(r["state"])], "ai": "Claude" if r["ai"] == "claude" else "Simulada",
                                "cost": f"{r['cost']:.3f}" if r["ai"] == "claude" else "—"} for r in runs]) \
                    .props("flat dense").classes("w-full")

    content()
