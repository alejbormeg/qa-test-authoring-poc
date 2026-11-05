"""Graba un vídeo de la demo recorriendo la app de verdad (con la IA que esté configurada).

Requisitos: servicios arrancados (`make up`) sobre un estado limpio (`make seed`), idealmente con una ejecución
ya registrada para que el dashboard tenga datos (ver docs/guion-demo.md, «Preparación»).

Uso: uv run --with imageio-ffmpeg python scripts/record_demo.py [salida.mp4]

Captura los fotogramas con el screencast de Chrome (1920×1080), acelera las esperas largas y codifica en H.264.
Los rótulos, el cursor y los resaltados se pintan dentro de la página con una capa propia.
"""

from __future__ import annotations

import base64
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qa_assistant import store  # noqa: E402
from qa_assistant.config import settings  # noqa: E402
from qa_assistant.domain.models import CaseStatus, RunState  # noqa: E402

APP = f"http://localhost:{settings.app_port}"
CONSOLE = settings.azure_console_url
SITE = settings.demo_site_url
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "video" / "demo-asistente-qa.mp4"
DFF = "DFF_Carrito_cupones_v2.4.docx"
FPS = 30
W, H, SCALE = 1600, 900, 1.2  # viewport CSS × escala = 1920×1080

OVERLAY_JS = r"""
(() => {
  if (window.__demo) return;
  const CSS = `
  #dm-cursor{position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;pointer-events:none;
    filter:drop-shadow(0 2px 3px rgba(0,0,0,.35));will-change:transform;opacity:0;transition:opacity .2s}
  .dm-ripple{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;z-index:2147483646;
    pointer-events:none;background:rgba(99,102,241,.45);border:2px solid rgba(99,102,241,.9);
    animation:dm-rip .55s ease-out forwards}
  @keyframes dm-rip{to{transform:scale(4.2);opacity:0}}
  #dm-caption{position:fixed;left:32px;bottom:30px;max-width:860px;z-index:2147483645;pointer-events:none;
    background:rgba(15,23,42,.92);color:#fff;border-radius:18px;padding:16px 26px 18px 26px;
    box-shadow:0 18px 50px rgba(15,23,42,.35);border-left:6px solid #818cf8;
    font:500 23px/1.35 Inter,"Segoe UI",Roboto,"DejaVu Sans",sans-serif;letter-spacing:-.01em;
    opacity:0;transform:translateY(14px);transition:opacity .35s ease,transform .35s ease}
  #dm-caption.on{opacity:1;transform:none}
  #dm-caption .k{display:block;font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
    color:#a5b4fc;margin-bottom:5px}
  #dm-caption code{font-family:"DejaVu Sans Mono",monospace;font-size:.85em;background:rgba(255,255,255,.12);
    padding:1px 6px;border-radius:6px}
  #dm-spot{position:fixed;z-index:2147483640;pointer-events:none;border-radius:12px;border:3px solid #818cf8;
    box-shadow:0 0 0 9999px rgba(15,23,42,.38),0 0 28px rgba(129,140,248,.9);opacity:0;
    transition:opacity .35s ease,left .35s ease,top .35s ease,width .35s ease,height .35s ease}
  #dm-spot.on{opacity:1}
  #dm-ff{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483646;pointer-events:none;
    background:#4f46e5;color:#fff;border-radius:999px;padding:6px 18px;font:700 18px/1.2 Inter,"DejaVu Sans",sans-serif;
    box-shadow:0 8px 24px rgba(79,70,229,.45);opacity:0;transition:opacity .3s}
  #dm-ff.on{opacity:1}
  #dm-card{position:fixed;inset:0;z-index:2147483644;display:flex;flex-direction:column;align-items:center;
    justify-content:center;gap:22px;color:#fff;text-align:center;padding:60px;opacity:0;transition:opacity .6s ease;
    background:radial-gradient(1200px 600px at 20% 10%,#4338ca 0%,transparent 60%),
               radial-gradient(900px 600px at 90% 90%,#0e7490 0%,transparent 55%),#0f172a;
    font-family:Inter,"Segoe UI",Roboto,"DejaVu Sans",sans-serif}
  #dm-card.on{opacity:1}
  #dm-card .eyebrow{font-size:18px;letter-spacing:.2em;text-transform:uppercase;color:#a5b4fc;font-weight:700}
  #dm-card h1{font-size:62px;line-height:1.08;margin:0;font-weight:800;letter-spacing:-.02em;max-width:1300px}
  #dm-card p{font-size:26px;color:#cbd5e1;margin:0;max-width:1100px;line-height:1.4}
  #dm-card .chips{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin-top:14px}
  #dm-card .chip{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:999px;
    padding:10px 20px;font-size:20px;font-weight:600}
  #dm-card .stats{display:flex;gap:28px;margin-top:10px}
  #dm-card .stat{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:22px;
    padding:22px 30px;min-width:220px}
  #dm-card .stat b{display:block;font-size:52px;font-weight:800;color:#fff}
  #dm-card .stat span{font-size:18px;color:#cbd5e1}
  `;
  const SVG = `<svg viewBox="0 0 28 28" width="28" height="28"><path d="M5 3l17 10.2-7.4 1.6 4.3 8.2-3.4 1.8-4.3-8.3L5 22z"
    fill="#fff" stroke="#111827" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
  const el = (id, tag='div') => {
    let e = document.getElementById(id);
    if (!e) { e = document.createElement(tag); e.id = id; document.documentElement.appendChild(e); }
    return e;
  };
  function install() {
    if (!document.getElementById('dm-style')) {
      const s = document.createElement('style'); s.id = 'dm-style'; s.textContent = CSS;
      document.documentElement.appendChild(s);
    }
    const c = el('dm-cursor'); if (!c.innerHTML) c.innerHTML = SVG;
    el('dm-caption'); el('dm-spot'); el('dm-ff');
  }
  let spotTarget = null;
  function place() {
    const s = document.getElementById('dm-spot');
    if (s && spotTarget && document.contains(spotTarget)) {
      const r = spotTarget.getBoundingClientRect(), p = 8;
      Object.assign(s.style, {left:(r.left-p)+'px', top:(r.top-p)+'px', width:(r.width+2*p)+'px',
                              height:(r.height+2*p)+'px'});
    }
    requestAnimationFrame(place);
  }
  window.__demo = {
    caption(html, kicker) {
      install(); const c = document.getElementById('dm-caption');
      if (!html) { c.classList.remove('on'); return; }
      c.innerHTML = (kicker ? `<span class="k">${kicker}</span>` : '') + html;
      c.classList.add('on');
    },
    spot(node) { install(); spotTarget = node; place(); document.getElementById('dm-spot').classList.toggle('on', !!node); },
    ff(text) { install(); const f = document.getElementById('dm-ff'); f.textContent = text || ''; f.classList.toggle('on', !!text); },
    card(html) {
      install(); let k = document.getElementById('dm-card');
      if (!html) { if (k) { k.classList.remove('on'); setTimeout(() => k.remove(), 650); } return; }
      if (!k) { k = document.createElement('div'); k.id = 'dm-card'; document.documentElement.appendChild(k); }
      k.innerHTML = html; requestAnimationFrame(() => k.classList.add('on'));
    },
  };
  addEventListener('mousemove', e => { install();
    const c = document.getElementById('dm-cursor'); c.style.opacity = 1;
    c.style.transform = `translate(${e.clientX-4}px,${e.clientY-3}px)`; }, true);
  addEventListener('mousedown', e => { const r = document.createElement('div'); r.className = 'dm-ripple';
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.documentElement.appendChild(r);
    setTimeout(() => r.remove(), 600); }, true);
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', install); else install();
})();
"""


class Recorder:
    """Recibe fotogramas del screencast y los vuelca a ffmpeg a FPS constantes, aplicando el factor de velocidad."""

    def __init__(self, page: Page, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        self.ff = subprocess.Popen(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
             "-c:v", "mjpeg", "-i", "-", "-vf", f"scale={int(W * SCALE)}:{int(H * SCALE)}:flags=lanczos,format=yuv420p",
             "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", str(out)],
            stdin=subprocess.PIPE)
        self.speed = 1.0
        self.last: bytes | None = None
        self.last_ts: float | None = None
        self.out_t = 0.0
        self.written = 0
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": int(W * SCALE),
                                                "maxHeight": int(H * SCALE), "everyNthFrame": 1})

    def _advance(self, now: float) -> None:
        if self.last is None or self.last_ts is None:
            return
        self.out_t += max(0.0, now - self.last_ts) / self.speed
        self.last_ts = now
        target = int(self.out_t * FPS)
        while self.written < target:
            self.ff.stdin.write(self.last)
            self.written += 1

    def _frame(self, ev: dict) -> None:
        self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        ts = ev["metadata"].get("timestamp") or time.time()
        if self.last_ts is None:
            self.last_ts = ts
        self._advance(ts)
        self.last = base64.b64decode(ev["data"])

    def set_speed(self, factor: float) -> None:
        self._advance(time.time())
        self.speed = factor

    def close(self) -> None:
        self._advance(time.time())
        self.cdp.send("Page.stopScreencast")
        self.ff.stdin.close()
        self.ff.wait()


class Demo:
    def __init__(self, page: Page, rec: Recorder) -> None:
        self.page, self.rec = page, rec
        self.mouse = (W / 2, H / 2)

    # -------------------------------------------------------------- utilidades de puesta en escena

    def pause(self, seconds: float) -> None:
        self.page.wait_for_timeout(int(seconds * 1000))

    def goto(self, url: str, settle: float = 1.2) -> None:
        self.page.goto(url, wait_until="networkidle")
        self.page.mouse.move(*self.mouse)
        self.pause(settle)

    def say(self, html: str | None, kicker: str | None = None, hold: float = 0.0) -> None:
        self.page.evaluate("([h, k]) => window.__demo.caption(h, k)", [html, kicker])
        if hold:
            self.pause(hold)

    def spot(self, loc: Locator | None, hold: float = 0.0) -> None:
        if loc is None:
            self.page.evaluate("() => window.__demo.spot(null)")
        else:
            loc.scroll_into_view_if_needed()
            loc.evaluate("n => n.scrollIntoView({behavior: 'smooth', block: 'center'})")
            self.pause(0.6)
            loc.evaluate("n => window.__demo.spot(n)")
        if hold:
            self.pause(hold)

    def card(self, html: str | None, hold: float = 0.0) -> None:
        self.page.evaluate("h => window.__demo.card(h)", html)
        if hold:
            self.pause(hold)

    def move_to(self, loc: Locator) -> None:
        loc.evaluate("n => n.scrollIntoView({behavior: 'smooth', block: 'center'})")
        self.pause(0.5)
        box = loc.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=28)
        self.mouse = (x, y)
        self.pause(0.25)

    def click(self, loc: Locator, after: float = 0.8) -> None:
        self.move_to(loc)
        loc.click()
        self.pause(after)

    def fast(self, factor: float | None) -> None:
        self.rec.set_speed(factor or 1.0)
        self.page.evaluate("t => window.__demo.ff(t)", f"⏩  ×{factor:g}" if factor else None)

    def wait_run(self, run_id: int, *states: RunState, timeout: float = 900) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = store.get_run(run_id)
            if r.state in states and not r.busy:
                return
            if r.state == RunState.ERROR:
                raise SystemExit(f"La ejecución #{run_id} falló en {r.failed_phase}: {r.error}")
            self.pause(1.0)
        raise SystemExit(f"Timeout esperando {states}")

    def card_of(self, ext_id: str) -> Locator:
        return self.page.locator(".case-card").filter(has_text=ext_id).first

    def open_section(self, ext_id: str, label: str, inner: str) -> Locator:
        """Abre la expansión de una tarjeta; la página puede refrescarse justo al hacer clic, así que se comprueba."""
        for _ in range(4):
            target = self.card_of(ext_id).locator(inner).first
            if target.count() and target.is_visible():
                return target
            self.click(self.card_of(ext_id).get_by_text(label), after=1.2)
        raise SystemExit(f"No se abre «{label}» en {ext_id}")


def chips(*items: str) -> str:
    return '<div class="chips">' + "".join(f'<span class="chip">{i}</span>' for i in items) + "</div>"


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--hide-scrollbars"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=SCALE, locale="es-ES")
        ctx.add_init_script(OVERLAY_JS)
        page = ctx.new_page()
        page.goto(f"{CONSOLE}/", wait_until="networkidle")
        rec = Recorder(page, OUT)
        d = Demo(page, rec)
        try:
            run(d)
        except Exception:
            page.screenshot(path=str(OUT.with_suffix(".error.png")))
            raise
        finally:
            rec.close()
            browser.close()
    print(f"Vídeo: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {rec.written / FPS:.0f} s)")


def run(d: Demo) -> None:
    page = d.page

    # ---------------------------------------------------------------- portada
    d.card('<div class="eyebrow">Asistente de QA</div>'
           '<h1>Del documento funcional al test automatizado y registrado</h1>'
           '<p>Lee el DFF, escribe los tests en C# con Playwright siguiendo las convenciones del equipo, '
           'abre la pull request y los registra en Azure Test Plans. QA aprueba cada paso.</p>'
           + chips("Playwright .NET · xUnit", "Azure DevOps", "Claude", "QA en el bucle"), hold=6.5)

    # ---------------------------------------------------------------- punto de partida
    d.card(None, hold=0.8)
    d.say("Partimos de Azure DevOps: Features con casos de prueba que el equipo ya automatizó a mano.",
          "Punto de partida", hold=3.5)
    d.spot(page.locator("#app").get_by_text("Carrito y cupones", exact=True).first.locator("xpath=ancestor::div[contains(@class,'q-card')][1]"),
           hold=3.0)
    d.spot(None)
    d.click(page.get_by_role("button", name="Test Plans"), after=1.0)
    d.say("Los casos se agrupan en Test Plans: por funcionalidad en la regresión y por versión en «Release 2.4».",
          "Punto de partida", hold=2.0)
    d.spot(page.locator("#app").get_by_text("Release 2.4").first.locator("xpath=ancestor::div[contains(@class,'q-card')][1]"), hold=3.5)
    d.spot(None)

    d.goto(f"{SITE}/", settle=0.6)
    d.say("La web bajo prueba: una tienda con carrito, cupones y avisos de stock.", "Punto de partida", hold=3.0)
    d.goto(f"{SITE}/producto?id=2", settle=0.6)
    d.say("La web bajo prueba: una tienda con carrito, cupones y avisos de stock.", "Punto de partida", hold=2.5)

    # ---------------------------------------------------------------- nueva ejecución
    d.goto(f"{APP}/")
    d.say("El analista de QA abre el asistente y sube el documento funcional (DFF) de la versión 2.4.",
          "1 · El documento", hold=2.5)
    d.click(page.get_by_role("button", name="Nueva ejecución").first, after=1.5)
    d.click(page.get_by_role("button", name=DFF), after=1.0)
    d.say("Un Word con la tabla de casos, tal como lo escribe el analista. Elige dónde quedarán en Azure: "
          "Feature, Test Plan y una suite nueva para la versión.", "1 · El documento", hold=1.0)
    dest = page.locator("#app").get_by_text("Destino en Azure DevOps").locator("xpath=ancestor::div[contains(@class,'card')][1]")
    d.spot(dest, hold=4.0)
    d.spot(None)
    d.click(page.get_by_role("button", name="Crear ejecución y extraer casos"), after=0.5)
    page.wait_for_url("**/run/*")
    run_id = int(page.url.rstrip("/").split("/")[-1])

    # ---------------------------------------------------------------- extracción
    d.pause(1.0)
    d.say("Claude lee el documento, extrae los casos y los compara con los que ya existen en Azure DevOps.",
          "2 · Extracción", hold=1.0)
    d.fast(6)
    d.wait_run(run_id, RunState.EXTRAIDO)
    d.pause(1.5)
    d.fast(None)

    # ---------------------------------------------------------------- gate 1
    d.say("Primera decisión de QA: revisar los casos antes de escribir una línea de código.", "Gate 1 · QA decide",
          hold=3.0)
    dup = d.card_of("TC-CARRITO-001")
    d.say("TC-CARRITO-001 ya existe en Azure (#205): el asistente lo detecta y lo deja fuera.", "Gate 1 · QA decide")
    d.spot(dup, hold=4.0)
    c2 = d.card_of("TC-CARRITO-002")
    d.say("Y avisa de lo que no cuadra. Aquí, la precondición ya pone el producto en el carrito y el paso 1 lo "
          "vuelve a añadir: con dos unidades, el total esperado no saldría.", "Gate 1 · QA decide")
    d.spot(c2, hold=6.5)
    d.spot(None)

    d.say("QA corrige el caso antes de automatizarlo.", "Gate 1 · QA decide")
    pre = d.open_section("TC-CARRITO-002", "Pasos, datos y resultado esperado", "[aria-label=Precondiciones]")
    d.move_to(pre)
    pre.click()
    pre.press("Control+a")
    pre.press_sequentially("Carrito vacío", delay=70)
    d.pause(0.6)
    d.click(d.card_of("TC-CARRITO-002").get_by_role("button", name="Guardar cambios"), after=1.5)

    d.say("Aprueba los casos que se van a automatizar.", "Gate 1 · QA decide")
    for c in store.cases(run_id):
        if c.status == CaseStatus.PENDIENTE:
            d.click(d.card_of(c.ext_id).get_by_role("button", name="Aprobar"), after=0.9)
    approve = page.get_by_role("button", name="casos y generar los tests")
    d.spot(approve, hold=1.2)
    d.spot(None)
    d.click(approve, after=1.0)

    # ---------------------------------------------------------------- generación
    d.say("Claude genera cada test con herramientas acotadas: lee el repositorio de tests, inspecciona la web real "
          "y compila. Si falta un componente en los mapeos, lo busca en el DOM y lo propone.", "3 · Generación",
          hold=4.0)
    d.fast(8)
    d.wait_run(run_id, RunState.EN_REVISION)
    d.pause(3.0)
    d.fast(None)

    # ---------------------------------------------------------------- gate 2
    r = store.get_run(run_id)
    approved = [c for c in store.cases(run_id) if c.status == CaseStatus.APROBADO]
    green = sum(1 for c in approved if c.result == "passed")
    d.say(f"{green} de {len(approved)} tests en verde contra la web, ejecutados con <code>dotnet test</code>.",
          "Gate 2 · QA revisa el código", hold=3.5)
    if r.new_components:
        maps = page.locator("#app").get_by_text("Mapeos nuevos que irán en la PR").locator("xpath=ancestor::div[contains(@class,'card')][1]")
        d.say("Componentes que no estaban mapeados: el selector sale del DOM real y se valida antes de aceptarlo. "
              "Van a la PR en el mismo formato que los mapeos del equipo.", "Gate 2 · QA revisa el código")
        d.spot(maps, hold=6.0)
        d.spot(None)
    code_case = next((c.ext_id for c in approved if c.ext_id == "TC-CARRITO-002"), approved[0].ext_id)
    editor = d.open_section(code_case, "Código, cambios y notas de la IA", ".cm-editor")
    d.say("Código C# con Playwright y xUnit: reutiliza los page objects y los mapeos, un método por caso con su ID "
          "y sus <code>[Trait]</code>. Sin selectores sueltos.", "Gate 2 · QA revisa el código")
    d.spot(editor, hold=8.0)
    d.spot(None)
    open_pr = page.get_by_role("button", name="Aprobar y abrir la pull request")
    d.say("QA aprueba y el asistente publica la rama y abre la pull request.", "Gate 2 · QA revisa el código")
    d.click(open_pr, after=0.5)
    d.wait_run(run_id, RunState.PR_ABIERTA, timeout=120)
    d.pause(2.5)

    # ---------------------------------------------------------------- PR
    r = store.get_run(run_id)
    d.goto(f"{CONSOLE}/pr/{r.pr_id}")
    d.say("La PR llega a Azure Repos como cualquier otro cambio: descripción con los casos y diff de los tests "
          "y de los mapeos.", "4 · Pull request", hold=4.0)
    page.mouse.wheel(0, 900)
    d.pause(2.5)
    page.mouse.wheel(0, -900)
    d.pause(1.0)
    d.say("La política de rama manda: sin aprobación no se puede completar.", "4 · Pull request")
    d.click(page.get_by_role("button", name="Completar (merge)"), after=2.5)
    d.say("El QA Lead revisa, aprueba y completa el merge.", "4 · Pull request")
    d.click(page.get_by_role("button", name="Aprobar", exact=True), after=1.5)
    d.click(page.get_by_role("button", name="Completar (merge)"), after=2.5)

    # ---------------------------------------------------------------- gate 3
    d.goto(f"{APP}/run/{run_id}", settle=0.5)
    d.say("El asistente detecta el merge y propone el registro en Azure Test Plans.", "Gate 3 · QA confirma",
          hold=0.5)
    d.wait_run(run_id, RunState.MERGEADO, timeout=60)
    d.pause(2.0)
    first = page.locator("#app").get_by_text("AutomatedTestName =").first.locator("xpath=ancestor::div[contains(@class,'card')][1]")
    d.say("Cada caso será un Test Case dentro de la Feature, con sus pasos y la automatización asociada "
          "(<code>AutomatedTestName</code>), en la suite de la versión.", "Gate 3 · QA confirma")
    d.spot(first, hold=6.0)
    d.spot(None)
    d.click(page.get_by_role("button", name="Confirmar el registro"), after=0.5)
    d.wait_run(run_id, RunState.REGISTRADO, timeout=120)
    d.pause(1.5)
    d.say("Registrado. Cada decisión de QA queda auditada: quién y cuándo.", "Gate 3 · QA confirma", hold=2.0)
    d.click(page.get_by_role("tab", name="Decisiones de QA"), after=3.5)

    # ---------------------------------------------------------------- Azure
    r = store.get_run(run_id)
    d.goto(f"{CONSOLE}/plans")
    suite = page.locator("#app").get_by_text(r.suite_name, exact=True).first
    d.say(f"En Azure Test Plans: la suite «{r.suite_name}» con los casos marcados como automatizados.",
          "5 · Azure DevOps")
    d.spot(suite.locator("xpath=ancestor::div[contains(@class,'q-expansion-item')][1]"), hold=4.5)
    d.spot(None)
    case_id = next(c.azure_id for c in store.cases(run_id) if c.azure_id)
    d.click(page.locator("#app").get_by_text(f"#{case_id}", exact=True).first, after=1.0)
    d.say("Pasos del caso, enlace a la Feature y el test automatizado asociado.", "5 · Azure DevOps", hold=5.0)
    page.keyboard.press("Escape")
    d.pause(0.6)

    # ---------------------------------------------------------------- medición
    d.goto(f"{APP}/dashboard", settle=1.5)
    d.say("Y todo se mide: tiempo del asistente frente al de QA, tests en verde a la primera, aceptados sin cambios "
          "y coste de IA por test.", "6 · Medición", hold=6.0)
    page.mouse.wheel(0, 600)
    d.pause(3.0)
    d.say(None)
    d.pause(0.5)

    # ---------------------------------------------------------------- cierre
    r = store.get_run(run_id)
    reg = [c for c in store.cases(run_id) if c.azure_id]
    first_green = sum(1 for c in reg if c.attempts <= 1)
    cost = (r.usage or {}).get("cost_usd") or 0
    cost_txt = f"{cost:.2f} $".replace(".", ",") if cost else "—"
    d.card('<div class="eyebrow">Resultado de esta ejecución</div>'
           '<h1>Del DFF a Azure Test Plans, con QA al mando</h1>'
           '<div class="stats">'
           f'<div class="stat"><b>{len(reg)}</b><span>tests registrados</span></div>'
           f'<div class="stat"><b>{first_green}/{len(reg)}</b><span>en verde a la primera</span></div>'
           f'<div class="stat"><b>{len(r.new_components)}</b><span>mapeos nuevos validados</span></div>'
           f'<div class="stat"><b>{cost_txt}</b><span>coste de IA</span></div>'
           '</div>'
           '<p>Tres decisiones de QA: qué casos, qué código y dónde se registran. El resto lo hace el asistente.</p>',
           hold=8.0)


if __name__ == "__main__":
    main()
