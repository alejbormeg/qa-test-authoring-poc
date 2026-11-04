"""Recorre el flujo completo sin UI y comprueba el resultado (requiere `make up` o los servicios arrancados).

1. Sube el DFF del carrito, espera la extracción y aprueba los casos sin avisos (Gate 1).
2. Espera la generación y ejecución; aparta los que no estén en verde y aprueba la revisión (Gate 2).
3. Aprueba y completa la PR en Azure Repos como qa.lead.
4. Confirma el registro (Gate 3) y comprueba en Azure que los Test Cases están en la suite con su automatización.

Uso: uv run python scripts/demo_e2e.py [ruta/al/DFF.docx]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qa_assistant import store  # noqa: E402
from qa_assistant.config import settings  # noqa: E402
from qa_assistant.domain.models import CaseStatus, RunState  # noqa: E402
from qa_assistant.pipeline import service  # noqa: E402

USER = "qa.analista"
DFF = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sample_data/dff/DFF_Carrito_cupones_v2.4.docx"


def wait(run_id: int, *states: RunState, timeout: int = 900) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        run = store.get_run(run_id)
        if run.state in states and not service.is_busy(run_id):
            return
        if run.state == RunState.ERROR:
            raise SystemExit(f"La ejecución falló en {run.failed_phase}: {run.error}")
        time.sleep(1)
    raise SystemExit(f"Timeout esperando {states}")


def step(msg: str) -> None:
    print(f"\n=== {msg}")


def main() -> None:
    api = service.azure()
    name = DFF.name.lower()
    feature_id = 104 if "checkout" in name else 105 if "cliente" in name else 103
    feature = next(f for f in api.features() if f["id"] == feature_id)
    plan = next(p for p in api.plans() if p["id"] == 20)

    step(f"Alta de la ejecución con {DFF.name} → Feature #{feature['id']}")
    run = service.create_run(DFF, DFF.name, feature, plan, None, "v2.4 · " + feature["fields"]["System.Title"], USER)
    wait(run.id, RunState.EXTRAIDO)
    for c in store.cases(run.id):
        print(f"  {c.ext_id:16} {c.status:10} {c.title}  {'⚠ ' + '; '.join(c.warnings) if c.warnings else ''}")
        if c.status == CaseStatus.PENDIENTE:
            service.set_case_status(c.id, CaseStatus.DESCARTADO if c.warnings else CaseStatus.APROBADO, USER)

    step("GATE 1 · aprobar casos")
    service.approve_cases(run.id, USER)
    wait(run.id, RunState.EN_REVISION)
    for c in store.cases(run.id):
        if c.status != CaseStatus.APROBADO:
            continue
        print(f"  {c.ext_id:16} {c.result:9} nuevos={c.components_new} reutilizados={len(c.components_reused)}")
        if c.result != "passed":
            print("    " + c.result_message.replace("\n", "\n    ")[:600])
            service.exclude_case(c.id, USER)
    print("  Componentes nuevos:", [f"{x['pagina']}.{x['nombre']}" for x in store.get_run(run.id).new_components])

    step("GATE 2 · aprobar revisión y abrir PR")
    service.approve_review(run.id, USER)
    wait(run.id, RunState.PR_ABIERTA)
    run = store.get_run(run.id)
    print(f"  PR !{run.pr_id}")

    step("qa.lead aprueba y completa la PR en Azure Repos")
    base = f"{settings.azure_url}/_apis/git/repositories/{settings.azure_repo}/pullrequests/{run.pr_id}"
    auth = ("", settings.azure_pat)
    httpx.put(f"{base}/reviewers/qa.lead", json={"vote": 10, "displayName": "qa.lead"}, auth=auth,
              params={"api-version": "7.1"}, headers={"X-QA-User": "qa.lead"}).raise_for_status()
    httpx.patch(base, json={"status": "completed"}, auth=auth, params={"api-version": "7.1"},
                headers={"X-QA-User": "qa.lead"}).raise_for_status()
    service.check_pr(run.id)
    wait(run.id, RunState.MERGEADO)

    step("GATE 3 · confirmar registro")
    for item in service.registration_preview(run.id):
        print(f"  {item['title']} → {item['test']}")
    service.confirm_registration(run.id, USER)
    wait(run.id, RunState.REGISTRADO)

    step("Comprobación en Azure DevOps")
    run = store.get_run(run.id)
    in_suite = set(api.suite_cases(run.plan_id, run.suite_id))
    ok = True
    for c in store.cases(run.id):
        if c.status != CaseStatus.APROBADO:
            continue
        wi = api.work_item(c.azure_id)
        f = wi["fields"]
        linked = any(r["rel"] == "Microsoft.VSTS.Common.TestedBy-Reverse" and r["url"].endswith(f"/{run.feature_id}")
                     for r in wi.get("relations", []))
        good = c.azure_id in in_suite and linked and f["Microsoft.VSTS.TCM.AutomationStatus"] == "Automated"
        ok &= good
        print(f"  {'✔' if good else '✘'} #{c.azure_id} {f['System.Title']} · {f['Microsoft.VSTS.TCM.AutomatedTestName']}")
    print(f"\nUso de IA: {run.usage or 'simulada, sin coste'}")
    print("\nRESULTADO:", "OK" if ok else "FALLOS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
