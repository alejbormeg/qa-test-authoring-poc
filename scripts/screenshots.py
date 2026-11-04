"""Capturas de las pantallas del asistente y de la consola de Azure DevOps simulada.

Uso: uv run python scripts/screenshots.py [carpeta] [ruta ...]
     (por defecto docs/capturas y las pantallas principales; los servicios deben estar arrancados)
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qa_assistant.config import settings  # noqa: E402

APP = f"http://localhost:{settings.app_port}"
DEFAULT = [
    ("01-inicio", f"{APP}/"),
    ("02-nueva", f"{APP}/nueva"),
    ("03-dashboard", f"{APP}/dashboard"),
    ("10-azure-boards", f"{settings.azure_console_url}/"),
    ("11-azure-plans", f"{settings.azure_console_url}/plans"),
    ("12-azure-prs", f"{settings.azure_console_url}/prs"),
]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "capturas"
    out.mkdir(parents=True, exist_ok=True)
    targets = DEFAULT
    if len(sys.argv) > 2:
        targets = [(Path(u).name or "pagina", u if u.startswith("http") else APP + u) for u in sys.argv[2:]]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="es-ES")
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        for name, url in targets:
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
            print(f"{name}: {url}" + (f"  ERRORES JS: {errors}" if errors else ""))
            errors.clear()
        browser.close()


if __name__ == "__main__":
    main()
