"""Marco común de la UI: cabecera, navegación, usuario activo y piezas visuales reutilizables."""

from __future__ import annotations

from datetime import UTC, datetime

from nicegui import app, ui

from ..config import settings
from ..domain.models import STATE_COLORS, STATE_LABELS, RunState

USERS = {"qa.analista": "Marta Ruiz · Analista QA", "qa.lead": "Jorge Peña · QA Lead"}

# Paleta de datos (guía dataviz): slots categóricos validados y paleta de estado reservada
SERIES = {"auto": "#2a78d6", "human": "#eb6834"}
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#8a8984", "grid": "#e6e5e0", "surface": "#fcfcfb"}

CSS = """
body { background: #f5f6fa; }
.q-header { backdrop-filter: blur(6px); }
.brand-dot { width: 30px; height: 30px; border-radius: 9px;
  background: linear-gradient(135deg, #4f46e5 0%, #0ea5e9 100%); display:flex; align-items:center; justify-content:center; }
.hero { background: radial-gradient(1200px 300px at 10% -40%, #c7d2fe 0%, transparent 60%),
  radial-gradient(900px 300px at 100% 0%, #bae6fd 0%, transparent 60%), #ffffff; border: 1px solid #e5e7eb; }
.card { background: #fff; border: 1px solid #e7e8ee; border-radius: 14px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.kpi-value { font-size: 30px; font-weight: 750; letter-spacing: -0.02em; line-height: 1.1; color: #0b0b0b; }
.kpi-label { font-size: 12.5px; color: #52514e; }
.muted { color: #6b7280; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.pipe-step { border-radius: 12px; padding: 10px 12px; border: 1px solid #e5e7eb; background: #fff; min-width: 0; }
.pipe-step.done { border-color: #c7e9cf; background: #f3fbf5; }
.pipe-step.current { border-color: #818cf8; background: #eef2ff; box-shadow: 0 0 0 3px rgba(129,140,248,.18); }
.pipe-step.gate.current { border-color: #f59e0b; background: #fffbeb; box-shadow: 0 0 0 3px rgba(245,158,11,.18); }
.pipe-step.error { border-color: #fca5a5; background: #fef2f2; }
.logline { word-break: break-word; min-width: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.55; white-space: pre-wrap; }
.logline.warn { color: #b45309; } .logline.error { color: #b91c1c; } .logline.human { color: #4338ca; font-weight: 600; }
.logline.debug { display: none; }
.case-card { border-left: 4px solid #e5e7eb; }
.case-card.aprobado { border-left-color: #16a34a; } .case-card.descartado { border-left-color: #9ca3af; opacity: .78; }
.case-card.pendiente { border-left-color: #f59e0b; }
.q-expansion-item__container > .q-item { padding: 8px 12px; }
.nicegui-code { font-size: 12px; }
.cm-editor { font-size: 12.5px; border-radius: 8px; border: 1px solid #e5e7eb; }
"""


def current_user() -> str:
    try:
        return app.storage.user.get("user", "qa.analista")
    except Exception:  # noqa: BLE001 - fuera de una petición
        return "qa.analista"


def frame(active: str) -> None:
    ui.colors(primary="#4f46e5", secondary="#0f766e", accent="#0ea5e9", positive="#15803d", negative="#b91c1c",
              warning="#d97706", info="#2563eb")
    ui.add_css(CSS)
    ui.query(".nicegui-content").classes("p-0")
    with ui.header().classes("bg-white/90 text-slate-900 border-b border-slate-200 px-6 py-2 items-center gap-3 no-wrap"):
        with ui.row().classes("items-center gap-3 cursor-pointer").on("click", lambda: ui.navigate.to("/")):
            with ui.element("div").classes("brand-dot"):
                ui.icon("auto_awesome", color="white", size="18px")
            with ui.column().classes("gap-0"):
                ui.label("Asistente de QA").classes("text-base font-bold leading-tight")
                ui.label("DFF → tests Playwright → Azure DevOps").classes("text-[11px] text-slate-500 leading-tight")
        ui.space()
        for key, label, icon, target in [("home", "Ejecuciones", "list_alt", "/"), ("new", "Nueva", "add_circle", "/nueva"),
                                         ("dashboard", "Dashboard", "insights", "/dashboard")]:
            btn = ui.button(label, icon=icon, on_click=lambda t=target: ui.navigate.to(t)).props("flat no-caps dense")
            btn.classes("px-3")
            btn.classes("text-indigo-700 bg-indigo-50" if key == active else "text-slate-600")
        ui.separator().props("vertical")
        ui.button("Azure DevOps", icon="open_in_new",
                  on_click=lambda: ui.navigate.to(settings.azure_console_url, new_tab=True)).props("flat no-caps dense").classes(
            "text-slate-600").tooltip("Consola del Azure DevOps simulado")
        ui.button("Web", icon="open_in_new",
                  on_click=lambda: ui.navigate.to(settings.demo_site_url, new_tab=True)).props("flat no-caps dense").classes(
            "text-slate-600").tooltip("Web bajo prueba (tienda demo)")
        ai = "Claude · " + settings.claude_model if settings.ai_mode == "claude" else "IA simulada"
        ui.badge(ai, color="indigo" if settings.ai_mode == "claude" else "grey-7").props("outline").classes("py-1")

        def change(e) -> None:
            app.storage.user["user"] = e.value
            ui.notify(f"Ahora trabajas como {USERS[e.value]}")

        ui.select(USERS, value=current_user(), on_change=change).props("dense outlined options-dense").classes(
            "w-52 shrink-0").tooltip("Usuario que firma las decisiones")


def state_badge(state: str, busy: str | None = None) -> None:
    st = RunState(state)
    with ui.badge(color=STATE_COLORS[st]).classes("px-2 py-1 text-[12px]"):
        if busy:
            ui.spinner(size="12px", color="white").classes("mr-1")
        ui.label(STATE_LABELS[st])


def kpi(label: str, value: str, icon: str, hint: str = "", color: str = "indigo") -> None:
    with ui.element("div").classes("card p-4 flex-1 min-w-[180px]"):
        with ui.row().classes("items-center justify-between w-full no-wrap"):
            ui.label(label).classes("kpi-label")
            ui.icon(icon, color=color, size="20px")
        ui.label(value).classes("kpi-value mt-1")
        if hint:
            ui.label(hint).classes("text-[12px] text-slate-500 mt-1")


def local_time(dt: datetime | str | None, fmt: str = "%d/%m %H:%M") -> str:
    if dt is None:
        return "—"
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime(fmt)


def minutes_between(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    da, db = datetime.fromisoformat(a), datetime.fromisoformat(b)
    return max((db - da).total_seconds() / 60, 0)


def fmt_minutes(m: float | None) -> str:
    if m is None:
        return "—"
    if m < 1:
        return f"{m * 60:.0f} s"
    if m < 90:
        return f"{m:.1f} min"
    return f"{m / 60:.1f} h"
