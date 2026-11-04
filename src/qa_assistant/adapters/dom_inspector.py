"""Inspección del DOM real de la web con Playwright: de aquí salen los selectores nuevos (no se inventan)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from playwright.sync_api import Browser, Playwright, sync_playwright

from ..config import settings

COLLECT = """
() => Array.from(document.querySelectorAll('[data-testid]')).map(el => ({
  testid: el.getAttribute('data-testid'),
  tag: el.tagName.toLowerCase(),
  type: el.getAttribute('type') || '',
  role: el.getAttribute('role') || '',
  aria: el.getAttribute('aria-label') || '',
  placeholder: el.getAttribute('placeholder') || '',
  label: (el.id && document.querySelector(`label[for="${el.id}"]`)?.innerText) || '',
  text: (el.innerText || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80),
  visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
}))
"""


@dataclass
class DomElement:
    testid: str
    tag: str
    type: str
    role: str
    aria: str
    placeholder: str
    label: str
    text: str
    visible: bool

    @property
    def selector(self) -> str:
        return f"[data-testid={self.testid}]"

    @property
    def tipo(self) -> str:
        if self.tag == "select":
            return "select"
        if self.tag in ("input", "textarea"):
            return "input"
        if self.tag == "button":
            return "button"
        if self.tag == "a":
            return "link"
        if self.tag in ("ul", "ol", "tbody", "table"):
            return "list"
        return "text"

    @property
    def descripcion(self) -> str:
        what = {"input": "Campo", "select": "Selector", "button": "Botón", "link": "Enlace", "list": "Lista"}.get(
            self.tipo, "Texto")
        name = self.label or self.aria or self.placeholder or self.text or self.testid
        return f"{what} {name}".strip()


class DomInspector:
    """Abre un navegador headless bajo demanda y cachea cada página inspeccionada."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._cache: dict[str, list[DomElement]] = {}

    def __enter__(self) -> DomInspector:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _ensure(self) -> Browser:
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
        return self._browser

    def snapshot(self, route: str) -> list[DomElement]:
        if route not in self._cache:
            page = self._ensure().new_page(locale="es-ES")
            try:
                page.goto(settings.demo_site_url + route, wait_until="load", timeout=15000)
                page.wait_for_timeout(150)
                self._cache[route] = [DomElement(**e) for e in page.evaluate(COLLECT)]
            finally:
                page.close()
        return self._cache[route]

    def count(self, route: str, selector: str) -> int:
        page = self._ensure().new_page()
        try:
            page.goto(settings.demo_site_url + route, wait_until="load", timeout=15000)
            return page.locator(selector).count()
        finally:
            page.close()

    def describe(self, route: str) -> list[dict]:
        return [asdict(e) | {"selector": e.selector, "tipo": e.tipo} for e in self.snapshot(route)]

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._browser = self._pw = None
