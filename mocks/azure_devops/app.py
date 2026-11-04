"""Azure DevOps simulado: API REST compatible (subconjunto 7.1) + consola web en /console."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from nicegui import ui

from qa_assistant.config import settings

from . import api, console, seed, store

app = FastAPI(title="Azure DevOps simulado")
api.install(app)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/console")


@app.get("/_mock/health")
def health() -> dict:
    return {"status": "ok", "work_items": len(store.load()["work_items"])}


@app.post("/_mock/faults")
def faults(body: dict) -> dict:
    store.load()["faults"].update(mode=body.get("mode"), remaining=int(body.get("remaining", 0)))
    store.save()
    return store.load()["faults"]


@app.post("/_mock/reset")
def reset() -> dict:
    seed.seed()
    return {"status": "seeded"}


console.install()
ui.run_with(app, mount_path="/console", title="DevOps simulado", favicon="🧪", language="es",
            show_welcome_message=False)


def main() -> None:
    import uvicorn

    if not settings.azure_state_file.exists():
        seed.seed()
    uvicorn.run(app, host="127.0.0.1", port=settings.azure_port, log_level="warning")


if __name__ == "__main__":
    main()
