"""Alta de una ejecución: documento y destino en Azure DevOps (Feature, Test Plan y suite)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from nicegui import events, run, ui

from ..adapters.azure_devops import AzureError
from ..config import ROOT
from ..pipeline import service
from .theme import current_user, frame

SAMPLES = ROOT / "sample_data" / "dff"
NEW_SUITE = "__nueva__"


@ui.page("/nueva")
async def new_run() -> None:
    frame("new")
    state: dict = {"file": None, "name": None}

    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-5"):
        ui.label("Nueva ejecución").classes("text-2xl font-bold")
        ui.label("Sube el documento funcional y di dónde deben quedar los casos en Azure DevOps. El asistente "
                 "extraerá los casos y te los enseñará antes de escribir ningún test.").classes("text-slate-600")

        with ui.element("div").classes("card p-5 w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.badge("1", color="indigo").classes("rounded-full")
                ui.label("Documento funcional (DFF)").classes("text-lg font-semibold")
            chosen = ui.label("Ningún documento seleccionado").classes("text-sm text-slate-500 mt-1")

            def pick(path: Path, name: str) -> None:
                state.update(file=path, name=name)
                chosen.set_text(f"📄 {name}")
                chosen.classes(replace="text-sm text-indigo-700 font-medium mt-1")
                m = re.search(r"v?(\d+\.\d+)", name)
                if m and suite_name.value in ("", "v2.4"):
                    suite_name.value = f"v{m.group(1)}"
                if "carrito" in name.lower():
                    feature.value = feature.value or 103
                elif "checkout" in name.lower():
                    feature.value = feature.value or 104
                elif "cliente" in name.lower():
                    feature.value = feature.value or 105

            async def on_upload(e: events.UploadEventArguments) -> None:
                tmp = Path(tempfile.mkdtemp()) / e.file.name
                await e.file.save(tmp)
                pick(tmp, e.file.name)

            with ui.row().classes("w-full gap-4 mt-3 items-start no-wrap"):
                ui.upload(label="Arrastra aquí el .docx", auto_upload=True, on_upload=on_upload, max_files=1).props(
                    'accept=".docx,.md,.txt" flat bordered color=indigo').classes("flex-1")
                with ui.column().classes("flex-1 gap-2"):
                    ui.label("…o usa un DFF de ejemplo").classes("text-sm text-slate-500")
                    for f in sorted(SAMPLES.glob("*.docx")):
                        ui.button(f.name, icon="description", on_click=lambda f=f: pick(f, f.name)).props(
                            "outline no-caps align=left").classes("w-full")

        with ui.element("div").classes("card p-5 w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.badge("2", color="indigo").classes("rounded-full")
                ui.label("Destino en Azure DevOps").classes("text-lg font-semibold")
            status = ui.label("Cargando Features y Test Plans…").classes("text-sm text-slate-500")
            with ui.grid(columns=2).classes("w-full gap-4 mt-2"):
                feature = ui.select({}, label="Feature (los casos se crean dentro de ella)").props("outlined")
                plan = ui.select({}, label="Test Plan").props("outlined")
                suite = ui.select({}, label="Agrupación (suite) por versión o funcionalidad").props("outlined")
                suite_name = ui.input("Nombre de la suite nueva", value="v2.4").props("outlined")
            suite_name.bind_visibility_from(suite, "value", backward=lambda v: v == NEW_SUITE)

        data: dict = {"features": {}, "plans": {}, "suites": {}}
        try:
            api = service.azure()
            feats = await run.io_bound(api.features)
            plans = await run.io_bound(api.plans)
            data["features"] = {f["id"]: f for f in feats}
            data["plans"] = {p["id"]: p for p in plans}
            feature.set_options({f["id"]: f"#{f['id']} · {f['fields']['System.Title']}" for f in feats})
            plan.set_options({p["id"]: f"#{p['id']} · {p['name']}" for p in plans})
            status.set_text(f"Conectado a Azure DevOps: {len(feats)} Features y {len(plans)} Test Plans")
            if state["name"]:
                pick(state["file"], state["name"])
        except AzureError as e:
            status.set_text(f"⚠️ No se puede consultar Azure DevOps: {e}")
            status.classes(replace="text-sm text-red-700")

        async def load_suites() -> None:
            if not plan.value:
                return
            suites = await run.io_bound(service.azure().suites, plan.value)
            data["suites"] = {s["id"]: s for s in suites if s.get("parentSuite")}
            opts = {sid: f"📁 {s['name']} ({s.get('testCaseCount', 0)} casos)" for sid, s in data["suites"].items()}
            opts[NEW_SUITE] = "➕ Crear una suite nueva…"
            suite.set_options(opts, value=NEW_SUITE)

        plan.on_value_change(load_suites)
        if 20 in data["plans"]:
            plan.value = 20

        async def create() -> None:
            if not state["file"]:
                ui.notify("Elige un documento", type="warning")
                return
            if not feature.value or not plan.value or not suite.value:
                ui.notify("Completa el destino en Azure DevOps", type="warning")
                return
            if suite.value == NEW_SUITE and not suite_name.value.strip():
                ui.notify("Pon nombre a la suite nueva", type="warning")
                return
            s = None if suite.value == NEW_SUITE else data["suites"][suite.value]
            r = await run.io_bound(service.create_run, Path(state["file"]), state["name"],
                                   data["features"][feature.value], data["plans"][plan.value], s,
                                   suite_name.value if s is None else None, current_user())
            ui.navigate.to(f"/run/{r.id}")

        with ui.row().classes("w-full justify-end"):
            ui.button("Crear ejecución y extraer casos", icon="auto_awesome", on_click=create).props(
                "unelevated no-caps size=lg")
