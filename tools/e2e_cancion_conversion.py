#!/usr/bin/env python3
"""E2E LOCAL del arreglo de conversión de Crea tu Canción (17-11-2026).

Sirve el repo en local y, en Chromium, con 4 pantallas:
  · navegador interno de Facebook en Android (412×760, user-agent con FBAN/FBAV),
  · Pixel 7, · iPhone 13, · escritorio 1366×768,
y con la franja de cookies puesta (primera visita), comprueba:
  1. SIN scroll se ven el título, el subtítulo, el precio, el botón «Crear mi
     canción · 15 €», la casilla legal y el enlace «▶ Ver cómo funciona (40 s)»;
     «Hablemos» no aparece en la primera pantalla; el vídeo empieza debajo.
  2. Sin la casilla: el botón no va a Stripe, avisa y lleva el foco a la casilla;
     solo sale «Cancion CTA» (arriba).
  3. Con la casilla: UN toque en el botón → Stripe con los utm_*; Plausible
     recibe «Cancion CTA» (posicion arriba) y «Cancion Comprar» con los utm_*.
  4. El botón de debajo del vídeo baja al bloque de pago y este queda ENTERO en
     pantalla (bajo la cabecera fija); «Cancion CTA» con posicion abajo.
  5. «▶ Ver cómo funciona» baja al vídeo.
  6. Vuelta de Stripe (?session_id=cs_…): código relleno y el formulario a la vista.
  7. Ningún error en la consola ni excepción de la página.
Y en Firefox (el Chromium de Playwright no trae H.264), con la pantalla y el
user-agent de Facebook en Android: el vídeo se reproduce al pulsar play y sale
«Cancion Video» con los utm_*.

window.plausible se SIMULA y se registra cada llamada; Stripe, la API y el
widget se interceptan. No sale nada a la red.

    python3 tools/e2e_cancion_conversion.py [--capturas DIR]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FAILS: list[str] = []
UTM_Q = "utm_source=meta&utm_medium=paid&utm_campaign=cancion_nov&utm_content=video_a"
UTM = {"utm_source": "meta", "utm_medium": "paid", "utm_campaign": "cancion_nov", "utm_content": "video_a"}
STRIPE = "https://buy.stripe.com/dRm9ATedzg67etcfvybEA0E"
FB_UA = ("Mozilla/5.0 (Linux; Android 13; SM-A536B Build/TP1A.220624.014; wv) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.163 Mobile Safari/537.36 "
         "[FB_IAB/FB4A;FBAN/FB4A;FBAV/442.0.0.33.113;]")
FB = "Facebook Android (FBAN/FBAV)"
DESKTOP = "Escritorio 1366×768"

PLAUSIBLE_STUB = """
window.plausible = function (name, opts) {
  var cb = opts && opts.callback;
  var p = window.__plRec ? window.__plRec(name, JSON.stringify((opts && opts.props) || null)) : Promise.resolve();
  p.then(function () { if (cb) cb({status: 202}); });
};
"""


def check(ok: bool, msg: str) -> None:
    print(("  ✔ " if ok else "  ✖ ") + msg)
    if not ok:
        FAILS.append(msg)


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


class Net:
    def __init__(self, base: str) -> None:
        self.base = base
        self.pl: list[tuple[str, dict | None]] = []
        self.stripe: list[str] = []

    def rec(self, name: str, props: str) -> None:
        self.pl.append((name, json.loads(props)))

    def route(self, r) -> None:
        u = r.request.url
        h = urlparse(u).hostname or ""
        if u.startswith(self.base):
            return r.continue_()
        if h == "buy.stripe.com":
            self.stripe.append(u)
            return r.fulfill(status=200, content_type="text/html", body="<p>stripe stub</p>")
        if h in ("analytics.arquitectodigital.io", "api.arquitectodigital.io"):
            return r.fulfill(status=200, content_type="application/javascript", body="")
        if h in ("fonts.googleapis.com",):
            return r.fulfill(status=200, content_type="text/css", body="")
        return r.abort()


def devices(p) -> dict:
    strip = lambda d: {k: v for k, v in d.items() if k != "default_browser_type"}
    return {
        FB: dict(viewport={"width": 412, "height": 760}, screen={"width": 412, "height": 915},
                 device_scale_factor=2.625, is_mobile=True, has_touch=True, user_agent=FB_UA),
        "Pixel 7": strip(p.devices["Pixel 7"]),
        "iPhone 13": strip(p.devices["iPhone 13"]),
        DESKTOP: dict(viewport={"width": 1366, "height": 768}),
    }


def fresh(br, dev: dict, base: str):
    ctx = br.new_context(**dev)
    net = Net(base)
    ctx.route("**/*", net.route)
    ctx.expose_function("__plRec", net.rec)
    ctx.add_init_script(PLAUSIBLE_STUB)
    return ctx, net


def rect(pg, sel: str):
    return pg.evaluate("(s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().toJSON() : null; }", sel)


def visible_sin_scroll(pg, sel: str) -> bool:
    """Entero dentro de la pantalla, por debajo de la cabecera fija y sin nada encima."""
    return pg.evaluate("""(s) => {
        const e = document.querySelector(s); if (!e) return false;
        const r = e.getBoundingClientRect(), hb = document.querySelector('header').getBoundingClientRect().bottom;
        if (r.top < hb - 0.5 || r.bottom > innerHeight + 0.5 || r.width === 0) return false;
        const p = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 10));
        return !!p && (e === p || e.contains(p) || p.contains(e));
    }""", sel)


def run_device(p, br, name: str, dev: dict, base: str, capturas: Path | None) -> None:
    url = f"{base}/crea-tu-cancion.html"
    tag = {FB: "fb_android", "Pixel 7": "pixel7", "iPhone 13": "iphone13"}.get(name, "escritorio")
    print(f"\n════ {name} ({dev['viewport']['width']}×{dev['viewport']['height']}) ════")
    ctx, net = fresh(br, dev, base)
    errores: list[str] = []
    pg = ctx.new_page()
    pg.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
    pg.goto(f"{url}?{UTM_Q}", wait_until="load")
    pg.wait_for_selector("#aviso-cookies:not([hidden])")
    pg.wait_for_timeout(400)
    if name == FB:
        check("FBAN/" in pg.evaluate("navigator.userAgent") and "FBAV/" in pg.evaluate("navigator.userAgent"), "user-agent con FBAN/FBAV")
    check(pg.evaluate("scrollY") == 0, "empieza arriba")
    for sel, nom in (("h1", "título"), (".cancion-sub", "subtítulo"), (".cancion-precio", "precio"),
                     ("#btn-pago", "botón «Crear mi canción · 15 €»"), (".consent-compacta", "casilla legal"),
                     (".ver-video", "enlace «▶ Ver cómo funciona (40 s)»")):
        check(visible_sin_scroll(pg, sel), f"sin scroll se ve: {nom} (acaba en {rect(pg, sel)['bottom']:.0f} de {pg.evaluate('innerHeight')} px)")
    check(pg.inner_text("h1").strip() == "Regala una canción con SU nombre", f"título del anuncio ({pg.inner_text('h1')!r})")
    check(pg.inner_text(".cancion-precio").strip() == "15 € · pago único · IVA incluido", "precio «15 € · pago único · IVA incluido»")
    check(pg.inner_text("#btn-pago").strip() == "Crear mi canción · 15 €", "texto del botón")
    hab = pg.evaluate("""() => [...document.querySelectorAll('a,button')].filter(a => /Hablemos/.test(a.textContent))
        .map(a => a.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0 && r.top < innerHeight).length""")
    check(hab == 0, f"«Hablemos» no aparece en la primera pantalla ({hab})")
    check(pg.locator("a", has_text="Hablemos").count() >= 1, "«Hablemos» sigue en la página (enlace discreto al final)")
    v = rect(pg, "#demo-cancion")
    check(v["top"] >= rect(pg, ".ver-video")["bottom"], f"el vídeo va debajo de la primera pantalla (empieza en {v['top']:.0f})")
    check(pg.evaluate("document.getElementById('demo-cancion').paused"), "el vídeo no arranca solo")
    if capturas:
        pg.screenshot(path=str(capturas / f"e2e_{tag}_1_primera_pantalla.png"))

    # 2) Sin casilla
    pg.click("#btn-pago"); pg.wait_for_timeout(500)
    check(net.stripe == [], f"sin casilla no va a Stripe ({net.stripe})")
    check(pg.evaluate("document.activeElement && document.activeElement.id") == "cc-legal", "lleva el foco a la casilla")
    check("Marca la casilla" in pg.inner_text("#cc-msg"), f"avisa ({pg.inner_text('#cc-msg')!r})")
    check(net.pl == [("Cancion CTA", {**UTM, "posicion": "arriba"})], f"solo «Cancion CTA» arriba, con UTM ({net.pl})")
    check(pg.evaluate("scrollY") < 5, "no mueve la página")

    # 4) Botón de abajo → bloque de pago entero
    net.pl.clear()
    pg.evaluate("() => document.getElementById('btn-pago-abajo').scrollIntoView({block: 'center'})"); pg.wait_for_timeout(200)
    pg.click("#btn-pago-abajo"); pg.wait_for_timeout(1200)
    br_ = rect(pg, "#bloque-pago")
    check(visible_sin_scroll(pg, "#bloque-pago"),
          f"el botón de abajo deja el bloque de pago entero en pantalla, bajo la cabecera ({br_['top']:.0f}–{br_['bottom']:.0f} de {pg.evaluate('innerHeight')} px)")
    check(net.pl == [("Cancion CTA", {**UTM, "posicion": "abajo"})], f"«Cancion CTA» abajo, con UTM ({net.pl})")
    if capturas:
        pg.screenshot(path=str(capturas / f"e2e_{tag}_2_bloque_pago.png"))

    # 5) «Ver cómo funciona» → vídeo
    pg.click(".ver-video"); pg.wait_for_timeout(1200)
    vr = rect(pg, "#demo-cancion")
    check(vr["top"] < pg.evaluate("innerHeight") and vr["bottom"] > 0, f"«Ver cómo funciona» baja al vídeo (vídeo en {vr['top']:.0f}–{vr['bottom']:.0f})")
    pg.evaluate("() => window.scrollTo(0, 0)"); pg.wait_for_timeout(200)

    # 3) Con casilla: un toque → Stripe
    net.pl.clear()
    pg.check("#cc-legal")
    pg.click("#btn-pago")
    pg.wait_for_url("**/buy.stripe.com/**", timeout=5000)
    q = parse_qs(urlparse(net.stripe[0]).query) if net.stripe else {}
    check(len(net.stripe) == 1 and net.stripe[0].startswith(STRIPE), f"un toque → Stripe ({net.stripe[:1]})")
    check(all(q.get(k) == [v_] for k, v_ in UTM.items()) and bool(q.get("client_reference_id")), f"el enlace lleva los utm_* y client_reference_id ({q})")
    check(net.pl == [("Cancion CTA", {**UTM, "posicion": "arriba"}), ("Cancion Comprar", UTM)],
          f"«Cancion CTA» arriba + «Cancion Comprar», con UTM ({net.pl})")
    check(errores == [], f"sin errores en la consola ({errores[:3]})")
    ctx.close()

    # 6) Vuelta de Stripe
    ctx, net = fresh(br, dev, base)
    errores = []
    pg = ctx.new_page()
    pg.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
    pg.goto(f"{url}?session_id=cs_test_VUELTA123", wait_until="load"); pg.wait_for_timeout(600)
    check(pg.input_value("#music-codigo") == "cs_test_VUELTA123", "vuelta de Stripe: código relleno")
    check(visible_sin_scroll(pg, "#music-email"), "vuelta de Stripe: el formulario «Ya he pagado» a la vista")
    check(pg.evaluate("document.activeElement && document.activeElement.id") == "music-email", "y el foco en el email")
    check(errores == [], f"sin errores en la consola ({errores[:3]})")
    ctx.close()


def run_firefox(p, base: str) -> None:
    print("\n════ Firefox · vídeo con la pantalla y el user-agent de Facebook en Android ════")
    ff = p.firefox.launch()
    ctx = ff.new_context(viewport={"width": 412, "height": 760}, device_scale_factor=2.625, has_touch=True, user_agent=FB_UA)
    net = Net(base)
    ctx.route("**/*", net.route)
    ctx.expose_function("__plRec", net.rec)
    ctx.add_init_script(PLAUSIBLE_STUB)
    errores: list[str] = []
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errores.append(f"pageerror: {e}"))
    pg.goto(f"{base}/crea-tu-cancion.html?{UTM_Q}", wait_until="load")
    pg.wait_for_timeout(500)
    check(pg.evaluate("document.getElementById('demo-cancion').paused"), "no arranca solo")
    pg.click(".ver-video"); pg.wait_for_timeout(1000)
    r = pg.evaluate("""async () => {
        const v = document.getElementById('demo-cancion');
        v.muted = true;
        try { await v.play(); } catch (e) { return {err: String(e)}; }
        const t0 = v.currentTime; await new Promise(r => setTimeout(r, 2500));
        return {t0, t1: v.currentTime, w: v.videoWidth, h: v.videoHeight, d: v.duration};
    }""")
    print("    reproducción:", r)
    check("err" not in r and r["t1"] - r["t0"] >= 1.0, f"se reproduce (avanza {r.get('t1', 0) - r.get('t0', 0):.2f} s)")
    check(r.get("w") == 1080 and r.get("h") == 1920 and 39 <= (r.get("d") or 0) <= 41, "1080×1920, ~40 s")
    pg.evaluate("() => { const v = document.getElementById('demo-cancion'); v.pause(); return v.play(); }")
    pg.wait_for_timeout(300)
    check(net.pl == [("Cancion Video", UTM)], f"«Cancion Video» una vez, con UTM ({net.pl})")
    check(errores == [], f"sin excepciones ({errores[:3]})")
    ctx.close()
    ff.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capturas", type=Path, default=None)
    a = ap.parse_args()
    if a.capturas:
        a.capturas.mkdir(parents=True, exist_ok=True)
    srv, port = serve()
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as p:
        br = p.chromium.launch()
        for name, dev in devices(p).items():
            run_device(p, br, name, dev, base, a.capturas)
        br.close()
        run_firefox(p, base)
    srv.shutdown()
    print("\nRESULTADO:", "OK" if not FAILS else f"{len(FAILS)} FALLOS")
    for f in FAILS:
        print("  ✖", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
