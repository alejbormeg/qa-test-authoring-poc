"""Consola web del Azure DevOps simulado: Boards, Test Plans, pull requests, actividad y fallos."""

from __future__ import annotations

import html
import re

from nicegui import ui

from qa_assistant.adapters import git as gitops
from qa_assistant.config import settings

from . import store

TESTED_BY = "Microsoft.VSTS.Common.TestedBy-Reverse"
REVIEWERS = ["qa.lead", "qa.analista"]
VOTES = {10: ("Aprobada", "positive"), 5: ("Aprobada con sugerencias", "positive"), -5: ("Espera al autor", "warning"),
         -10: ("Rechazada", "negative")}
PR_STATUS = {"active": ("Activa", "primary"), "completed": ("Completada", "positive"), "abandoned": ("Abandonada", "grey")}


def parse_steps(xml: str | None) -> list[tuple[str, str]]:
    if not xml:
        return []
    out = []
    for step in re.findall(r"<step [^>]*>(.*?)</step>", xml, re.S):
        strings = re.findall(r"<parameterizedString[^>]*>(.*?)</parameterizedString>", step, re.S)
        # XML escapado que contiene HTML escapado: se desescapa, se quitan las etiquetas HTML y se desescapa el texto
        clean = [html.unescape(re.sub(r"<[^>]+>", "", html.unescape(s))).strip() for s in strings]
        out.append((clean[0] if clean else "", clean[1] if len(clean) > 1 else ""))
    return out


def frame(active: str) -> None:
    ui.colors(primary="#3b5bdb", secondary="#495057", accent="#0c8599", positive="#2b8a3e", negative="#c92a2a")
    ui.add_css("body{background:#f4f5f7} .q-tab{text-transform:none}")
    with ui.header().classes("bg-slate-800 items-center gap-6 px-6 py-2"):
        ui.icon("hub", size="sm").classes("text-sky-300")
        with ui.column().classes("gap-0"):
            ui.label("DevOps simulado").classes("text-lg font-bold")
            ui.label(f"{settings.azure_org} / {settings.azure_project} · API compatible con Azure DevOps 7.1").classes(
                "text-xs text-slate-300")
        ui.space()
        for key, label, icon, target in [("boards", "Boards", "view_kanban", "/"),
                                         ("plans", "Test Plans", "science", "/plans"),
                                         ("repos", "Pull requests", "merge", "/prs"),
                                         ("activity", "Actividad", "history", "/activity"),
                                         ("faults", "Fallos", "bolt", "/faults")]:
            color = "white" if key == active else "blue-grey-3"
            btn = ui.button(label, icon=icon, on_click=lambda t=target: ui.navigate.to(t)).props(f"flat no-caps color={color}")
            if key == active:
                btn.classes("bg-white/10")
        ui.badge("SIMULADO", color="orange").props("outline")


def case_dialog(wid: int) -> None:
    item = store.get_work_item(wid)
    if not item:
        return
    f = item["fields"]
    with ui.dialog() as dlg, ui.card().classes("w-[760px] max-w-full"):
        with ui.row().classes("items-center w-full"):
            ui.label(f"Test Case #{wid}").classes("text-sm text-slate-500")
            ui.space()
            ui.button(icon="close", on_click=dlg.close).props("flat round dense")
        ui.label(f["System.Title"]).classes("text-xl font-semibold")
        with ui.row().classes("gap-2"):
            ui.badge(f.get("System.State", ""), color="secondary")
            for tag in [t.strip() for t in f.get("System.Tags", "").split(";") if t.strip()]:
                ui.badge(tag, color="accent").props("outline")
        feats = store.related_ids(item, TESTED_BY)
        if feats:
            ui.label("Prueba la Feature: " + ", ".join(
                f"#{x} {store.get_work_item(x)['fields']['System.Title']}" for x in feats)).classes("text-sm")
        rows = [{"n": i + 1, "accion": a, "esperado": e} for i, (a, e) in enumerate(parse_steps(f.get("Microsoft.VSTS.TCM.Steps")))]
        ui.table(columns=[{"name": "n", "label": "#", "field": "n"},
                          {"name": "accion", "label": "Acción", "field": "accion", "align": "left"},
                          {"name": "esperado", "label": "Resultado esperado", "field": "esperado", "align": "left"}],
                 rows=rows).classes("w-full").props("flat bordered dense wrap-cells")
        ui.label("Automatización asociada").classes("font-semibold mt-2")
        status = f.get("Microsoft.VSTS.TCM.AutomationStatus", "Not Automated")
        with ui.grid(columns=2).classes("text-sm gap-x-6 gap-y-1"):
            for label, key in [("Estado", "Microsoft.VSTS.TCM.AutomationStatus"),
                               ("Nombre del test", "Microsoft.VSTS.TCM.AutomatedTestName"),
                               ("Ensamblado", "Microsoft.VSTS.TCM.AutomatedTestStorage"),
                               ("Tipo", "Microsoft.VSTS.TCM.AutomatedTestType"),
                               ("Id de automatización", "Microsoft.VSTS.TCM.AutomatedTestId")]:
                ui.label(label).classes("text-slate-500")
                ui.label(f.get(key) or ("Not Automated" if key.endswith("Status") else "—")).classes(
                    "font-mono" if key != "Microsoft.VSTS.TCM.AutomationStatus" else
                    ("text-positive font-semibold" if status == "Automated" else ""))
        ui.label(f"Creado por {f.get('System.CreatedBy')} · {f.get('System.CreatedDate')}").classes("text-xs text-slate-500")
    dlg.open()


def case_row(item: dict) -> None:
    f = item["fields"]
    automated = f.get("Microsoft.VSTS.TCM.AutomationStatus") == "Automated"
    with ui.row().classes("w-full items-center gap-3 px-3 py-2 hover:bg-slate-50 cursor-pointer rounded") \
            .on("click", lambda w=item["id"]: case_dialog(w)):
        ui.icon("science", color="accent")
        ui.label(f"#{item['id']}").classes("text-slate-500 w-12")
        ui.label(f["System.Title"]).classes("flex-1")
        if "qa-assistant" in f.get("System.Tags", ""):
            ui.badge("asistente QA", color="purple").props("outline")
        ui.badge("Automatizado" if automated else "Manual", color="positive" if automated else "grey")


def watch(render) -> None:
    """Refresca la vista cuando cambia el estado (otro proceso puede escribir vía API)."""
    seen = {"n": None}

    def tick():
        marker = (len(store.load()["events"]), store.load()["events"][0]["at"] if store.load()["events"] else None)
        if marker != seen["n"]:
            seen["n"] = marker
            render.refresh()

    ui.timer(2.0, tick)


def install() -> None:
    @ui.page("/")
    def boards() -> None:
        frame("boards")

        @ui.refreshable
        def render() -> None:
            with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4"):
                ui.label("Features y sus casos de prueba").classes("text-2xl font-semibold")
                for feat in store.work_items("Feature"):
                    tests = store.tests_of_feature(feat["id"])
                    with ui.card().classes("w-full p-0"):
                        with ui.expansion(value=True).classes("w-full") as exp:
                            with exp.add_slot("header"):
                                with ui.row().classes("items-center gap-3 w-full"):
                                    ui.icon("emoji_events", color="purple")
                                    ui.label(f"#{feat['id']}").classes("text-slate-500")
                                    ui.label(feat["fields"]["System.Title"]).classes("font-semibold flex-1")
                                    ui.badge(f"{len(tests)} casos", color="secondary").props("outline")
                            ui.label(feat["fields"].get("System.Description", "")).classes("text-sm text-slate-500 px-3")
                            for t in tests:
                                case_row(t)
                            if not tests:
                                ui.label("Sin casos de prueba").classes("text-sm text-slate-400 px-3 pb-2")

        render()
        watch(render)

    @ui.page("/plans")
    def plans_page() -> None:
        frame("plans")

        @ui.refreshable
        def render() -> None:
            with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4"):
                ui.label("Test Plans").classes("text-2xl font-semibold")
                for plan in store.plans():
                    with ui.card().classes("w-full"):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("science", color="primary", size="md")
                            ui.label(f"#{plan['id']} · {plan['name']}").classes("text-lg font-semibold")
                        for suite in store.suites(plan["id"]):
                            if suite["parentSuiteId"] is None:
                                continue
                            with ui.expansion(value=bool(suite["testCaseIds"])).classes("w-full") as exp:
                                with exp.add_slot("header"):
                                    with ui.row().classes("items-center gap-3 w-full"):
                                        ui.icon("folder", color="amber-8")
                                        ui.label(suite["name"]).classes("flex-1 font-medium")
                                        ui.badge(f"{len(suite['testCaseIds'])}", color="secondary").props("outline")
                                for wid in suite["testCaseIds"]:
                                    item = store.get_work_item(wid)
                                    if item:
                                        case_row(item)

        render()
        watch(render)

    @ui.page("/prs")
    def prs_page() -> None:
        frame("repos")

        @ui.refreshable
        def render() -> None:
            with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-3"):
                ui.label(f"Pull requests · {settings.azure_repo}").classes("text-2xl font-semibold")
                prs = store.list_prs("all")
                if not prs:
                    ui.label("Todavía no hay pull requests").classes("text-slate-500")
                for pr in prs:
                    label, color = PR_STATUS[pr["status"]]
                    with ui.card().classes("w-full cursor-pointer hover:shadow-md").on(
                            "click", lambda p=pr["pullRequestId"]: ui.navigate.to(f"/pr/{p}")):
                        with ui.row().classes("items-center gap-3 w-full"):
                            ui.icon("merge", color=color, size="md")
                            with ui.column().classes("gap-0 flex-1"):
                                ui.label(f"!{pr['pullRequestId']} {pr['title']}").classes("font-semibold")
                                ui.label(f"{pr['createdBy']['displayName']} · "
                                         f"{pr['sourceRefName'].removeprefix('refs/heads/')} → "
                                         f"{pr['targetRefName'].removeprefix('refs/heads/')} · {pr['creationDate']}"
                                         ).classes("text-xs text-slate-500")
                            for r in pr["reviewers"]:
                                vl, vc = VOTES.get(r["vote"], ("Sin voto", "grey"))
                                ui.badge(f"{r['displayName']}: {vl}", color=vc).props("outline")
                            ui.badge(label, color=color)

        render()
        watch(render)

    @ui.page("/pr/{pid}")
    def pr_page(pid: int) -> None:
        frame("repos")

        @ui.refreshable
        def render() -> None:
            pr = store.get_pr(pid)
            if not pr:
                ui.label("PR no encontrada").classes("p-6")
                return
            label, color = PR_STATUS[pr["status"]]
            branch = pr["sourceRefName"].removeprefix("refs/heads/")
            with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-4"):
                ui.link("← Pull requests", "/prs").classes("text-sm")
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.badge(label, color=color).classes("text-sm")
                    ui.label(f"!{pid} {pr['title']}").classes("text-2xl font-semibold flex-1")
                ui.label(f"{pr['createdBy']['displayName']} quiere fusionar {branch} en "
                         f"{pr['targetRefName'].removeprefix('refs/heads/')}").classes("text-slate-600")
                with ui.row().classes("w-full gap-4 items-start no-wrap"):
                    with ui.card().classes("flex-1 min-w-0 overflow-x-auto"):
                        ui.label("Descripción").classes("font-semibold")
                        ui.markdown(pr["description"] or "_Sin descripción_").classes("text-sm w-full")
                    with ui.card().classes("w-80 shrink-0"):
                        ui.label("Revisores").classes("font-semibold")
                        for r in pr["reviewers"]:
                            vl, vc = VOTES.get(r["vote"], ("Sin voto", "grey"))
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("person")
                                ui.label(r["displayName"])
                                ui.badge(vl, color=vc)
                        if not pr["reviewers"]:
                            ui.label("Sin votos todavía").classes("text-sm text-slate-500")
                        if pr["status"] == "active":
                            ui.separator()
                            who = ui.select(REVIEWERS, value=REVIEWERS[0], label="Revisar como").classes("w-full")

                            def act(fn, msg):
                                try:
                                    fn()
                                    ui.notify(msg, type="positive")
                                except Exception as e:  # noqa: BLE001 - se muestra al usuario
                                    ui.notify(str(e), type="negative")
                                render.refresh()

                            with ui.row().classes("gap-2"):
                                ui.button("Aprobar", icon="check", color="positive",
                                          on_click=lambda: act(lambda: store.vote(pid, who.value, 10), "PR aprobada"))
                                ui.button("Rechazar", icon="block", color="negative",
                                          on_click=lambda: act(lambda: store.vote(pid, who.value, -10), "PR rechazada"))
                            ui.button("Completar (merge)", icon="merge", color="primary",
                                      on_click=lambda: act(lambda: store.complete_pr(pid, who.value), "PR completada")
                                      ).classes("w-full")
                            ui.button("Abandonar", icon="delete", on_click=lambda: act(
                                lambda: store.abandon_pr(pid, who.value), "PR abandonada")).props("flat").classes("w-full")
                        elif pr.get("lastMergeCommit"):
                            ui.label(f"Merge {pr['lastMergeCommit']['commitId'][:10]}").classes("font-mono text-sm")
                try:
                    target = pr["targetRefName"].removeprefix("refs/heads/")
                    if pr["status"] == "completed":
                        commit = pr["lastMergeCommit"]["commitId"]
                        diff = gitops.git("diff", f"{commit}^1", commit, git_dir=settings.remote_repo)
                    else:
                        diff = gitops.diff(settings.remote_repo, branch, target)
                except gitops.GitError as e:
                    diff = f"# No se pudo calcular el diff: {e}"
                files = [line[6:] for line in diff.splitlines() if line.startswith("+++ b/")]
                with ui.card().classes("w-full"):
                    ui.label(f"Cambios · {len(files)} fichero(s)").classes("font-semibold")
                    for name in files:
                        ui.label(name).classes("font-mono text-xs text-slate-600")
                    ui.code(diff or "(sin cambios)", language="diff").classes("w-full text-xs")

        render()
        watch(render)

    @ui.page("/activity")
    def activity_page() -> None:
        frame("activity")

        @ui.refreshable
        def render() -> None:
            icons = {"workitem": "description", "plan": "science", "suite": "folder", "pr": "merge",
                     "fallo": "bolt", "seed": "restart_alt"}
            with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
                ui.label("Actividad reciente").classes("text-2xl font-semibold")
                with ui.timeline(side="right").classes("w-full"):
                    for ev in store.load()["events"][:80]:
                        ui.timeline_entry(ev["text"], subtitle=ev["at"], icon=icons.get(ev["kind"], "info"),
                                          color="negative" if ev["kind"] == "fallo" else "primary")

        render()
        watch(render)

    @ui.page("/faults")
    def faults_page() -> None:
        frame("faults")

        @ui.refreshable
        def render() -> None:
            f = store.load()["faults"]
            with ui.column().classes("w-full max-w-3xl mx-auto p-6 gap-4"):
                ui.label("Inyección de fallos").classes("text-2xl font-semibold")
                ui.label("Las próximas llamadas a la API fallarán para comprobar que el asistente reintenta "
                         "y no pierde ningún caso.").classes("text-slate-600")
                with ui.card().classes("w-full"):
                    ui.label("Estado actual: " + (f"{f['mode']} en las próximas {f['remaining']} llamadas"
                                                  if f["mode"] else "sin fallos")).classes("font-semibold")

                    def set_fault(mode, n):
                        f.update(mode=mode, remaining=n)
                        store.event("fallo", f"Fallos configurados: {mode or 'ninguno'} × {n}")
                        store.save()
                        render.refresh()

                    with ui.row().classes("gap-2"):
                        ui.button("503 en 2 llamadas", icon="cloud_off", color="warning", on_click=lambda: set_fault("503", 2))
                        ui.button("503 en 6 llamadas", icon="cloud_off", color="negative", on_click=lambda: set_fault("503", 6))
                        ui.button("PAT caducado (401)", icon="key_off", color="negative", on_click=lambda: set_fault("401", 1))
                        ui.button("Quitar fallos", icon="check", on_click=lambda: set_fault(None, 0)).props("outline")

        render()
        watch(render)
