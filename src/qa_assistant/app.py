"""Punto de entrada del asistente de QA (NiceGUI sobre FastAPI)."""

from __future__ import annotations

import os

from nicegui import ui

from .config import settings
from .ui import dashboard, home, new_run, run_page  # noqa: F401 - registran las páginas


def main() -> None:
    ui.run(host="127.0.0.1", port=settings.app_port, title="Asistente de QA", favicon="🧪", language="es",
           storage_secret=os.environ.get("QA_STORAGE_SECRET", "poc-local-secret"), reload=False, show=False,
           show_welcome_message=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
