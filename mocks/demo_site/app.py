"""Web bajo prueba: una tienda demo sencilla con data-testid en sus componentes.

Sirve páginas estáticas; el estado (sesión, carrito, pedidos) vive en localStorage del navegador,
así cada test de Playwright empieza con una tienda limpia.
"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from qa_assistant.config import settings

STATIC = Path(__file__).parent / "static"
PAGES = {
    "/": "catalogo.html",
    "/login": "login.html",
    "/producto": "producto.html",
    "/carrito": "carrito.html",
    "/checkout": "checkout.html",
    "/perfil": "perfil.html",
}

app = FastAPI(title="Tienda demo (web bajo prueba)")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _page(name: str):
    return lambda: FileResponse(STATIC / name, headers={"Cache-Control": "no-store"})


for route, file in PAGES.items():
    app.add_api_route(route, _page(file), methods=["GET"], include_in_schema=False)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=settings.demo_site_port, log_level="warning")


if __name__ == "__main__":
    main()
