"""Indicadores para el inicio y el dashboard, calculados con lo medido en cada ejecución."""

from __future__ import annotations

from statistics import mean

from .. import store
from ..domain.models import CaseStatus, RunState
from .theme import minutes_between

# (clave de timings, etiqueta, tipo): "auto" lo hace el asistente, "human" es tiempo de QA (incluye esperas)
PHASES = [
    ("extraccion", "Extracción de casos", "auto"),
    ("revision_casos", "Revisión de casos (Gate 1)", "human"),
    ("generacion", "Generación y ejecución", "auto"),
    ("revision_codigo", "Revisión del código (Gate 2)", "human"),
    ("pr", "Aprobación y merge de la PR", "human"),
    ("registro_confirmacion", "Confirmación del registro (Gate 3)", "human"),
    ("registro", "Registro en Azure", "auto"),
]


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f} %" if b else "—"


def compute() -> dict:
    runs = store.runs()
    cases = store.all_cases()
    approved = [c for c in cases if c.status == CaseStatus.APROBADO and c.first_result]
    registered = [c for c in cases if c.azure_id]
    baseline = float(store.get_setting("baseline_minutes_per_case") or 45)

    phase_minutes: dict[str, list[float]] = {k: [] for k, _, _ in PHASES}
    human_minutes = 0.0
    for r in runs:
        for key, _, kind in PHASES:
            t = (r.timings or {}).get(key, {})
            m = minutes_between(t.get("start"), t.get("end"))
            if m is not None:
                phase_minutes[key].append(m)
                if kind == "human" and r.state == RunState.REGISTRADO:
                    human_minutes += m
    auto_registered = 0.0
    for r in runs:
        if r.state == RunState.REGISTRADO:
            for key, _, kind in PHASES:
                if kind == "auto":
                    t = (r.timings or {}).get(key, {})
                    auto_registered += minutes_between(t.get("start"), t.get("end")) or 0

    manual = len(registered) * baseline
    saved = manual - human_minutes
    first = {"passed": 0, "failed": 0, "not_built": 0}
    final = {"passed": 0, "failed": 0, "not_built": 0}
    for c in approved:
        first[c.first_result] = first.get(c.first_result, 0) + 1
        final[c.result or "not_built"] = final.get(c.result or "not_built", 0) + 1

    cost = sum((r.usage or {}).get("cost_usd", 0) for r in runs)
    tokens = sum((r.usage or {}).get("input_tokens", 0) + (r.usage or {}).get("output_tokens", 0) for r in runs)
    per_run = []
    for r in runs:
        cs = [c for c in cases if c.run_id == r.id and c.status == CaseStatus.APROBADO]
        reused = {x for c in cs for x in c.components_reused}
        per_run.append({"run": f"#{r.id}", "reused": len(reused), "new": len(r.new_components or []),
                        "cases": len(cs), "cost": (r.usage or {}).get("cost_usd", 0), "state": r.state,
                        "ai": r.ai_mode})
    accepted_unchanged = sum(1 for c in registered if c.code.strip() == c.ai_code.strip())
    return {
        "runs": len(runs),
        "registered_runs": sum(1 for r in runs if r.state == RunState.REGISTRADO),
        "extracted": len(cases),
        "registered_cases": len(registered),
        "first_green_pct": pct(first["passed"], len(approved)),
        "final_green_pct": pct(final["passed"], len(approved)),
        "accepted_unchanged_pct": pct(accepted_unchanged, len(registered)),
        "saved_hours": f"{saved / 60:.1f} h" if registered else "—",
        "saved_hint": f"vs {baseline:.0f} min/caso a mano (línea base)" if registered else "cuando haya tests registrados",
        "baseline": baseline,
        "human_minutes": human_minutes,
        "auto_minutes": auto_registered,
        "manual_minutes": manual,
        "phase_avg": {k: (mean(v) if v else None) for k, v in phase_minutes.items()},
        "first": first,
        "final": final,
        "approved": len(approved),
        "cost": cost,
        "tokens": tokens,
        "cost_per_case": cost / len(registered) if registered else None,
        "per_run": list(reversed(per_run)),
        "new_components": sum(len(r.new_components or []) for r in runs),
    }
