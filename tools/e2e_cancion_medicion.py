#!/usr/bin/env python3
"""E2E LOCAL: sitio sin píxel de Meta + aviso de cookies anterior + medición de
Crea tu Canción con Plausible (14-11-2026).

Sirve el repo en local (dominio de pega → 127.0.0.1) y emula iPhone 13 y
Pixel 7. window.plausible se SIMULA (el script.js real se sustituye por uno
vacío) y cada llamada se registra aquí. Se interceptan la API de canje y
Stripe: no sale nada a Plausible, a Stripe ni a la API real. Cualquier
petición a Meta se registra como fallo y se corta.

    python3 tools/e2e_cancion_medicion.py [--capturas DIR] [--sin-todas]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HOST = "arquitectodigital.test"
FAILS: list[str] = []
UTM_Q = "utm_source=meta&utm_campaign=cancion_nov"
STRIPE = "https://buy.stripe.com/dRm9ATedzg67etcfvybEA0E"

# window.plausible simulado: registra (nombre, props) y llama al callback
# cuando el registro ha llegado (como hace el script real al recibir el 202).
PLAUSIBLE_STUB = """
window.plausible = function (name, opts) {
  var cb = opts && opts.callback;
  var p = window.__plRec ? window.__plRec(name, JSON.stringify((opts && opts.props) || null)) : Promise.resolve();
  p.then(function () { if (cb) cb({status: 202}); });
};
"""


def check(cond: bool, msg: str) -> None:
    print(("  ✔ " if cond else "  ✖ ") + msg)
    if not cond:
        FAILS.append(msg)


def serve() -> tuple[socketserver.TCPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


class Net:
    def __init__(self, widget_real: bool = True, ligero: bool = False) -> None:
        self.meta: list[str] = []
        self.stripe: list[str] = []
        self.pl: list[tuple[str, dict | None]] = []
        self.widget_real = widget_real
        self.ligero = ligero

    def rec(self, name: str, props: str) -> None:
        self.pl.append((name, json.loads(props)))

    def route(self, r) -> None:
        u = r.request.url
        h = urlparse(u).hostname or ""
        if "facebook" in h or h.endswith("fbcdn.net"):
            self.meta.append(u)
            return r.abort()
        if h == "analytics.arquitectodigital.io":
            return r.fulfill(status=200, content_type="application/javascript", body="")
        if h == "api.arquitectodigital.io" and u.endswith("/webhook/music/redeem"):
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "token": "tok_test"}))
        if h == "api.arquitectodigital.io" and "/music/create" in u:
            return r.fulfill(status=200, content_type="text/html", body="<p>create stub</p>")
        if h == "api.arquitectodigital.io" and (r.request.method != "GET" or not self.widget_real):
            return r.fulfill(status=200, content_type="application/javascript", body="")
        if h == "buy.stripe.com":
            self.stripe.append(u)
            return r.fulfill(status=200, content_type="text/html", body="<p>stripe stub</p>")
        if self.ligero and r.request.resource_type in ("image", "media", "font"):
            return r.abort()
        return r.continue_()


def storage(pg) -> dict:
    return pg.evaluate("() => ({ls: {...localStorage}, ss: {...sessionStorage}, ck: document.cookie})")


def buy_clickable(pg) -> str | None:
    """Pone «Comprar» en pantalla como lo haría el usuario y mira qué hay encima."""
    pg.evaluate("() => document.getElementById('btn-pago').scrollIntoView({block: 'center'})")
    pg.wait_for_timeout(300)
    return pg.evaluate("""() => {
        const b = document.getElementById('btn-pago').getBoundingClientRect();
        const pts = [[.5,.5],[.15,.5],[.85,.5]].map(([x,y]) => document.elementFromPoint(b.left + b.width*x, b.top + b.height*y));
        const bad = pts.find(e => !e || !e.closest('#btn-pago'));
        return bad === undefined ? null : (bad ? (bad.closest('.cookie-banner') ? 'aviso de cookies'
               : bad.tagName + '#' + bad.id + '.' + bad.className) : 'nada');
    }""")


def rect(pg, sel: str):
    return pg.evaluate(f"() => {{ const e = document.querySelector({json.dumps(sel)}); "
                       "return e ? e.getBoundingClientRect().toJSON() : null; }")


def device_run(p, dev_name: str, base: str, capturas: Path | None, todas: list[str]) -> None:
    dev = {k: v for k, v in p.devices[dev_name].items() if k != "default_browser_type"}
    br = p.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
    page_url = f"{base}/crea-tu-cancion.html"
    tag = dev_name.replace(" ", "_")

    def fresh(**kw):
        ctx = br.new_context(**dev)
        net = Net(**kw)
        ctx.route("**/*", net.route)
        ctx.expose_function("__plRec", net.rec)
        ctx.add_init_script(PLAUSIBLE_STUB)
        return ctx, net

    print(f"\n════ {dev_name} ({dev['viewport']['width']}×{dev['viewport']['height']}) ════")

    # ── 1) Primera visita: aviso anterior ───────────────────────────────
    print("1) Primera visita")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url)
    pg.wait_for_selector(".cookie-banner.is-visible")
    pg.wait_for_timeout(1500)   # deja montar la burbuja del chat
    txt = pg.inner_text(".cookie-banner")
    check(txt.startswith("Sin cookies. Este sitio no instala cookies."), "aviso anterior: «Sin cookies. Este sitio no instala cookies…»")
    btns = pg.eval_on_selector_all(".cookie-banner button", "bs => bs.map(b => b.textContent.trim())")
    check(btns == ["Entendido"], f"un solo botón «Entendido» ({btns})")
    check(ctx.cookies() == [], f"antes: sin cookies ({[c['name'] for c in ctx.cookies()]})")
    check(pg.evaluate("typeof window.fbq") == "undefined", "window.fbq no existe")
    vh = pg.evaluate("innerHeight")
    bn = rect(pg, ".cookie-banner")
    print(f"     aviso: {round(bn['height'])} px de alto = {round(100 * bn['height'] / vh)} % de la pantalla ({vh} px)")
    if capturas:
        f = capturas / f"{tag}_01_primera_pantalla_aviso.png"
        pg.screenshot(path=str(f)); print("     captura:", f)
    check(pg.is_visible(".cookie-banner"), "primera pantalla: el aviso se ve")
    who = buy_clickable(pg)
    check(who is None, f"«Comprar» se puede pulsar sin cerrar el aviso (elementFromPoint){'' if who is None else ': lo tapa ' + who}")
    check(not pg.is_visible(".cookie-banner"), "con «Comprar» en pantalla el aviso no se ve")
    st = storage(pg)
    check(st["ls"] == {} and st["ss"] == {} and st["ck"] == "", f"ocultarlo no guarda nada ni cuenta como «Entendido» ({st})")
    if capturas:
        f = capturas / f"{tag}_02_zona_comprar_sin_aviso.png"
        pg.screenshot(path=str(f)); print("     captura:", f)
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(400)
    check(pg.is_visible(".cookie-banner") and pg.locator(".cookie-banner button[data-close]").is_visible(),
          "al volver arriba el aviso reaparece con «Entendido»")
    if capturas:
        f = capturas / f"{tag}_03_vuelta_arriba_aviso.png"
        pg.screenshot(path=str(f)); print("     captura:", f)
    pg.click(".cookie-banner button[data-close]")
    pg.wait_for_timeout(500)
    check(pg.locator(".cookie-banner").count() == 0, "con «Entendido» desaparece")
    check(ctx.cookies() == [], f"después: sin cookies ({[c['name'] for c in ctx.cookies()]})")
    st = storage(pg)
    check(list(st["ls"]) == ["ad_cookie_consent"] and st["ss"] == {} and st["ck"] == "",
          f"solo queda ad_cookie_consent en localStorage ({st})")
    pg.reload(); pg.wait_for_timeout(800)
    check(pg.locator(".cookie-banner").count() == 0, "al recargar no vuelve a salir")
    check(net.meta == [], f"ninguna petición a Meta ({net.meta[:3]})")
    ctx.close()

    # ── 1b) Página sin «Comprar»: el aviso se comporta como siempre ────
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(f"{base}/index.html")
    pg.wait_for_selector(".cookie-banner.is-visible")
    pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    pg.wait_for_timeout(400)
    check(pg.is_visible(".cookie-banner") and pg.evaluate("document.querySelector('.cookie-banner').style.display") == "",
          "index.html (sin «Comprar»): el aviso sigue visible al bajar del todo, sin tocar")
    ctx.close()

    # ── 2) Comprar con UTM en la URL ────────────────────────────────────
    print("2) Llegada con ?" + UTM_Q)
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?" + UTM_Q)
    pg.wait_for_selector(".cookie-banner.is-visible")
    pg.click(".cookie-banner button[data-close]")
    st0 = storage(pg)
    pg.check("#cc-legal")
    pg.click("#btn-pago")
    pg.wait_for_url("**/buy.stripe.com/**", timeout=5000)
    check(len(net.stripe) == 1, f"se llega a Stripe ({len(net.stripe)} peticiones)")
    q = parse_qs(urlparse(net.stripe[0]).query) if net.stripe else {}
    print("     enlace:", net.stripe[0] if net.stripe else None)
    check(q.get("utm_source") == ["meta"] and q.get("utm_campaign") == ["cancion_nov"], "el enlace lleva utm_source y utm_campaign")
    check(q.get("client_reference_id") == ["u_meta____cancion_nov____"], f"y client_reference_id ({q.get('client_reference_id')})")
    check(net.pl == [("Cancion Comprar", {"utm_source": "meta", "utm_campaign": "cancion_nov"})],
          f"Plausible: «Cancion Comprar» con props UTM ({net.pl})")
    pg.goto(page_url); pg.wait_for_timeout(300)
    st1 = storage(pg)
    blob = json.dumps([st0, st1])
    check("utm" not in blob and "meta" not in blob.replace("ad_cookie_consent", ""),
          f"ni localStorage ni sessionStorage guardan UTM ({st1})")
    check(st1["ss"] == {}, "sessionStorage vacío")
    # Ha navegado: sin UTM en la URL, el siguiente enlace sale limpio.
    net.stripe.clear(); net.pl.clear()
    pg.check("#cc-legal"); pg.click("#btn-pago")
    pg.wait_for_url("**/buy.stripe.com/**", timeout=5000)
    check(net.stripe == [STRIPE], f"tras navegar sin UTM: el enlace va limpio ({net.stripe})")
    check(net.pl == [("Cancion Comprar", None)], f"y el evento sale sin props ({net.pl})")
    check(net.meta == [], "ninguna petición a Meta")
    ctx.close()

    # ── 3) Sin casilla legal: ni evento ni Stripe ───────────────────────
    print("3) Sin marcar la casilla")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url); pg.click(".cookie-banner button[data-close]")
    pg.click("#btn-pago", force=True); pg.wait_for_timeout(700)
    check(net.stripe == [] and net.pl == [], f"no va a Stripe ni manda evento ({net.stripe}, {net.pl})")
    ctx.close()

    # ── 4) Canje ─────────────────────────────────────────────────────────
    print("4) Canje")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?" + UTM_Q); pg.click(".cookie-banner button[data-close]")
    pg.fill("#music-codigo", "cs_test_CANJE22"); pg.fill("#music-email", "test@example.com")
    pg.click("#music-form button[type=submit]")
    pg.wait_for_url("**/music/create**", timeout=5000)
    check(net.pl == [("Cancion Canje", {"utm_source": "meta", "utm_campaign": "cancion_nov"})],
          f"código cs_test_: «Cancion Canje» y pasa a crear ({net.pl})")
    net.pl.clear()
    pg.goto(page_url)
    pg.fill("#music-codigo", "REGALO-ABCD-EFGH"); pg.fill("#music-email", "test@example.com")
    pg.click("#music-form button[type=submit]")
    pg.wait_for_url("**/music/create**", timeout=5000)
    check(net.pl == [], f"código REGALO-: sin evento, y pasa a crear ({net.pl})")
    pg.goto(page_url); pg.wait_for_timeout(300)
    st = storage(pg)
    check(list(st["ls"]) == ["ad_cookie_consent"] and st["ss"] == {}, f"el canje no guarda nada ({st})")
    check(net.meta == [], "ninguna petición a Meta")
    ctx.close()

    # ── 5) Textos de la Fase A que se quedan ────────────────────────────
    print("5) Precio y plazo")
    ctx, net = fresh()
    pg = ctx.new_page(); pg.goto(page_url)
    body = pg.inner_text("main") if pg.locator("main").count() else pg.inner_text("body")
    check(pg.locator("s").count() == 0, "sin precio tachado")
    check("15 € · pago único · IVA incluido" in body, "«15 € · pago único · IVA incluido»")
    check(body.count("en unos 10 minutos") >= 2, f"«en unos 10 minutos» en el hero y en el paso 4 ({body.count('en unos 10 minutos')})")
    ctx.close()

    # ── 6) window.fbq en todas las páginas ──────────────────────────────
    if todas:
        print(f"6) {len(todas)} páginas: sin window.fbq ni peticiones a Meta")
        ctx, net = fresh(widget_real=False, ligero=True)
        pg = ctx.new_page()
        malas = []
        for path in todas:
            pg.goto(f"{base}/{path}", wait_until="load")
            for _ in range(3):   # alguna página redirige al cargar: se mira la de destino
                try:
                    if pg.evaluate("typeof window.fbq !== 'undefined' || typeof window._fbq !== 'undefined'"):
                        malas.append(path)
                    break
                except Exception:
                    pg.wait_for_load_state("load")
        check(malas == [], f"window.fbq no existe en ninguna ({malas})")
        check(net.meta == [], f"ninguna petición a Meta ({net.meta[:3]})")
        check(ctx.cookies() == [], "sin cookies tras recorrerlas todas")
        ctx.close()
    br.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capturas", type=Path, default=None)
    ap.add_argument("--sin-todas", action="store_true", help="no recorrer todas las páginas")
    a = ap.parse_args()
    if a.capturas:
        a.capturas.mkdir(parents=True, exist_ok=True)
    todas = [] if a.sin_todas else [
        f for f in subprocess.run(["git", "ls-files", "*.html"], cwd=ROOT, capture_output=True,
                                  text=True, check=True).stdout.split()
        if not f.startswith("partials/")]
    srv, port = serve()
    base = f"http://{HOST}:{port}"
    with sync_playwright() as p:
        for dev in ("iPhone 13", "Pixel 7"):
            device_run(p, dev, base, a.capturas, todas)
    srv.shutdown()
    print()
    print("RESULTADO:", "OK" if not FAILS else f"{len(FAILS)} FALLOS")
    for f in FAILS:
        print("  ✖", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
