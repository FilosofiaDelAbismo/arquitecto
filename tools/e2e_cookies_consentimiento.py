#!/usr/bin/env python3
"""E2E LOCAL del aviso de cookies y del bloqueo previo del píxel de Meta (14-11-2026).

Sirve el repo en local y emula iPhone 13 y Pixel 7. Usa el fbevents.js REAL de
Meta (connect.facebook.net, solo lectura) para ver las cookies de verdad, pero
TODAS las peticiones a facebook.com (los eventos /tr) se interceptan aquí y NO
salen. También se interceptan los envíos a Plausible, la API de canje y Stripe.

    python3 tools/e2e_cookies_consentimiento.py [--capturas DIR]
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
HOST = "arquitectodigital.test"   # dominio de pega → 127.0.0.1 (cookies como en producción)
FAILS: list[str] = []
META_LS = ("lastExternalReferrer", "lastExternalReferrerTime", "multiFbc")


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
    """Registro de peticiones de terceros de un contexto."""
    def __init__(self) -> None:
        self.fbevents: list[str] = []
        self.meta_tr: list[str] = []
        self.stripe: list[str] = []

    def clear(self) -> None:
        self.fbevents.clear(); self.meta_tr.clear(); self.stripe.clear()

    def events(self, ev: str) -> list[dict]:
        out = []
        for u in self.meta_tr:
            q = parse_qs(urlparse(u).query)
            if q.get("ev") == [ev]:
                out.append(q)
        return out

    def route(self, r) -> None:
        u = r.request.url
        h = urlparse(u).hostname or ""
        if h == "connect.facebook.net":
            if u.split("?")[0].endswith("fbevents.js"):
                self.fbevents.append(u)
            return r.continue_()
        if h.endswith("facebook.com"):
            self.meta_tr.append(u if r.request.method == "GET" else u + "&" + (r.request.post_data or ""))
            return r.fulfill(status=200, body="")
        if h == "analytics.arquitectodigital.io" and "/api/event" in u:
            return r.fulfill(status=202, body="ok")
        if h == "api.arquitectodigital.io" and u.endswith("/webhook/music/redeem"):
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "token": "tok_test"}))
        if h == "api.arquitectodigital.io" and "/music/create" in u:
            return r.fulfill(status=200, content_type="text/html", body="<p>create stub</p>")
        if h == "api.arquitectodigital.io" and r.request.method != "GET":
            return r.fulfill(status=200, content_type="application/json", body="{}")
        if h == "buy.stripe.com":
            self.stripe.append(u)
            return r.fulfill(status=200, content_type="text/html", body="<p>stripe stub</p>")
        return r.continue_()


def meta_cookies(ctx) -> list[str]:
    return sorted(c["name"] for c in ctx.cookies() if c["name"] in ("_fbp", "_fbc"))


def wait_cookie(pg, ctx, name: str, ms: int = 6000) -> bool:
    for _ in range(ms // 250):
        if name in meta_cookies(ctx):
            return True
        pg.wait_for_timeout(250)
    return False


def rect(pg, sel: str):
    return pg.evaluate(f"() => {{ const e = document.querySelector({json.dumps(sel)}); "
                       "return e ? e.getBoundingClientRect().toJSON() : null; }")


def overlap(a, b) -> bool:
    return bool(a and b and a["left"] < b["right"] and b["left"] < a["right"]
                and a["top"] < b["bottom"] and b["top"] < a["bottom"])


def buy_clickable(pg) -> str | None:
    """Pone «Comprar» en pantalla como lo haría el usuario y mira qué hay encima."""
    pg.evaluate("() => document.getElementById('btn-pago').scrollIntoView({block: 'center'})")
    pg.wait_for_timeout(300)
    return pg.evaluate("""() => {
        const b = document.getElementById('btn-pago').getBoundingClientRect();
        const pts = [[.5,.5],[.15,.5],[.85,.5]].map(([x,y]) => document.elementFromPoint(b.left + b.width*x, b.top + b.height*y));
        const bad = pts.find(e => !e || !e.closest('#btn-pago'));
        return bad === undefined ? null : (bad ? (bad.closest('.cookie-banner') ? 'aviso de cookies' : bad.tagName + '#' + bad.id + '.' + bad.className) : 'nada');
    }""")


def device_run(p, dev_name: str, base: str, capturas: Path | None) -> None:
    dev = p.devices[dev_name]
    # Chromium con emulación del dispositivo (viewport, DPR, UA, táctil) para
    # poder mapear el dominio de pega a 127.0.0.1.
    br = p.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
    dev = {k: v for k, v in dev.items() if k != "default_browser_type"}
    page_url = f"{base}/crea-tu-cancion.html"

    def fresh():
        ctx = br.new_context(**dev)
        net = Net()
        ctx.route("**/*", net.route)
        return ctx, net

    print(f"\n════ {dev_name} ({dev['viewport']['width']}×{dev['viewport']['height']}) ════")

    # ── 1) Sin elegir ────────────────────────────────────────────────────
    print("1) Sin elegir")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?utm_source=facebook&utm_campaign=cancion_A&fbclid=PRUEBA1")
    pg.wait_for_selector(".cookie-banner.is-visible")
    pg.wait_for_timeout(1500)
    vh = pg.evaluate("innerHeight")
    bn = rect(pg, ".cookie-banner")
    check(bn is not None and bn["height"] / vh <= 0.25,
          f"aviso compacto: {bn and round(bn['height'])} px = {bn and round(100 * bn['height'] / vh)} % de la pantalla (máx. 25 %)")
    btns = pg.evaluate("""() => [...document.querySelectorAll('.cookie-banner button')].map(b => {
        const s = getComputedStyle(b), r = b.getBoundingClientRect();
        return {t: b.textContent.trim(), w: Math.round(r.width), h: Math.round(r.height),
                css: [s.backgroundColor, s.color, s.borderColor, s.fontSize, s.fontWeight].join('|')}; })""")
    check([b["t"] for b in btns] == ["Rechazar", "Aceptar"], "botones «Rechazar» y «Aceptar»")
    check(len(btns) == 2 and btns[0]["css"] == btns[1]["css"] and btns[0]["w"] == btns[1]["w"]
          and btns[0]["h"] == btns[1]["h"], f"misma prominencia (tamaño y estilo): {btns}")
    check(pg.evaluate("() => !document.querySelector('.cookie-banner input')"), "sin casillas")
    check(pg.locator(".cookie-banner a[href='/cookies.html']").count() == 1, "enlace a /cookies.html")
    vid = rect(pg, "video")
    check(not overlap(bn, vid), f"no tapa el vídeo (aviso {round(bn['top'])}-{round(bn['bottom'])}, vídeo desde {vid and round(vid['top'])})")
    pg.wait_for_selector("#cbai-root", state="attached", timeout=10000)
    pg.wait_for_timeout(800)
    bub = pg.evaluate("""() => { const r = document.getElementById('cbai-root');
        const kids = [r, ...r.querySelectorAll('*')].filter(e => { const s = getComputedStyle(e);
          const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; });
        return kids.map(e => e.getBoundingClientRect().toJSON()); }""")
    check(bool(bub) and not any(overlap(bn, b) for b in bub), "la burbuja del chat y el aviso no se cruzan")
    if capturas:
        pg.evaluate("() => window.scrollTo(0, 0)"); pg.wait_for_timeout(300)
        f = capturas / f"{dev_name.replace(' ', '_')}_01_aviso_primera_pantalla.png"
        pg.screenshot(path=str(f)); print("     captura:", f)
    check(meta_cookies(ctx) == [], "sin _fbp ni _fbc")
    check(not net.fbevents and not net.meta_tr, "no se pide fbevents.js ni nada a Meta")
    check(pg.evaluate("typeof window.fbq") == "undefined", "window.fbq no existe")
    who = buy_clickable(pg)
    check(who is None, f"«Comprar» se puede pulsar (elementFromPoint){'' if who is None else ': lo tapa ' + who}")
    if capturas:
        f = capturas / f"{dev_name.replace(' ', '_')}_02_boton_comprar_con_aviso.png"
        pg.screenshot(path=str(f)); print("     captura:", f)
    pg.check("#cc-legal")
    pg.evaluate("() => document.getElementById('btn-pago').addEventListener('click', e => e.preventDefault())")
    pg.click("#btn-pago")
    check("utm_campaign=cancion_A" in pg.get_attribute("#btn-pago", "href"), "el pago sigue llevando los UTM a Stripe")
    pg.fill("#music-codigo", "cs_test_SINCONS1"); pg.fill("#music-email", "test@example.com")
    pg.click("#music-form button[type=submit]")
    pg.wait_for_url("**/music/create**", timeout=5000)
    check(not net.meta_tr and not net.fbevents, "pagar y canjear sin consentimiento: nada a Meta (ni InitiateCheckout ni Purchase)")
    pg.goto(page_url); pg.wait_for_timeout(800)
    check(pg.evaluate("() => localStorage.getItem('ad_purchase_cs_test_SINCONS1')") is None,
          "la compra no se marca ni se guarda para enviarla después")
    ctx.close()

    # ── 2) Rechazar ──────────────────────────────────────────────────────
    print("2) Rechazar")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?fbclid=PRUEBA2"); pg.wait_for_selector(".cookie-banner.is-visible")
    pg.click(".cookie-banner button[data-choice=rejected]")
    pg.wait_for_timeout(2000)
    check(pg.locator(".cookie-banner").count() == 0, "el aviso se cierra")
    rec = json.loads(pg.evaluate("() => localStorage.getItem('ad_cookie_consent')") or "{}")
    check(rec.get("choice") == "rejected" and rec.get("v") == 3 and bool(rec.get("ts")), f"elección guardada con fecha: {rec}")
    check(meta_cookies(ctx) == [] and not net.fbevents and not net.meta_tr, "sin _fbp y sin peticiones a Meta")
    pg.reload(); pg.wait_for_timeout(2500)
    check(pg.locator(".cookie-banner").count() == 0, "al recargar no vuelve a preguntar")
    check(meta_cookies(ctx) == [] and not net.fbevents and not net.meta_tr, "al recargar: sigue sin _fbp ni peticiones a Meta")
    ctx.close()

    # ── 3) Aceptar ───────────────────────────────────────────────────────
    print("3) Aceptar")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?fbclid=PRUEBA3"); pg.wait_for_selector(".cookie-banner.is-visible")
    pg.wait_for_timeout(800)
    check(not net.fbevents, "antes de aceptar: nada de Meta")
    pg.click(".cookie-banner button[data-choice=accepted]")
    check(wait_cookie(pg, ctx, "_fbp"), "tras aceptar: se carga el píxel y aparece _fbp")
    check(len(net.fbevents) == 1, "fbevents.js pedido una vez")
    check(len(net.events("PageView")) == 1, "PageView enviado (interceptado)")
    check("_fbc" in meta_cookies(ctx), "_fbc aparece al llegar con fbclid")
    net.clear()
    pg.goto(page_url); pg.wait_for_timeout(300)
    check(pg.locator(".cookie-banner").count() == 0, "visita siguiente: no vuelve a preguntar")
    pg.wait_for_function("() => typeof window.fbq === 'function'", timeout=5000)
    pg.wait_for_timeout(1500)
    check(len(net.fbevents) == 1 and len(net.events("PageView")) == 1, "visita siguiente: el píxel carga al entrar y envía PageView")
    pg.check("#cc-legal")
    pg.evaluate("() => document.getElementById('btn-pago').addEventListener('click', e => e.preventDefault())")
    pg.click("#btn-pago"); pg.click("#btn-pago"); pg.wait_for_timeout(1500)
    ic = net.events("InitiateCheckout")
    check(len(ic) == 1 and ic[0].get("cd[value]") == ["15"] and ic[0].get("cd[currency]") == ["EUR"],
          f"InitiateCheckout una vez, 15 EUR: {[{k: v for k, v in e.items() if k.startswith('cd')} for e in ic]}")
    check(not net.events("SubscribedButtonClick"), "sin eventos automáticos de Meta al pulsar botones")
    pg.fill("#music-codigo", "cs_test_CONCONS1"); pg.fill("#music-email", "test@example.com")
    pg.click("#music-form button[type=submit]")
    pg.wait_for_url("**/music/create**", timeout=5000)
    pu = net.events("Purchase")
    check(len(pu) == 1 and pu[0].get("cd[value]") == ["15"] and pu[0].get("eid") == ["cs_test_CONCONS1"],
          f"Purchase al canjear, 15 EUR, eventID = código: {[{k: v for k, v in e.items() if k.startswith('cd') or k == 'eid'} for e in pu]}")

    # ── 4) Retirar desde «Configurar cookies» ────────────────────────────
    print("4) Retirar desde «Configurar cookies»")
    pg.goto(page_url); pg.wait_for_function("() => typeof window.fbq === 'function'"); pg.wait_for_timeout(1200)
    check("_fbp" in meta_cookies(ctx), "partimos con _fbp")
    link = pg.locator("footer a", has_text="Configurar cookies")
    check(link.count() == 1, "enlace «Configurar cookies» en el pie")
    link.click()
    pg.wait_for_selector(".cookie-banner.is-visible")
    check("aceptadas" in pg.inner_text(".cookie-banner"), "el aviso muestra la elección actual")
    net.clear()
    pg.click(".cookie-banner button[data-choice=rejected]")
    pg.wait_for_timeout(1500)
    check(meta_cookies(ctx) == [], "se borran _fbp y _fbc")
    left = pg.evaluate(f"() => {json.dumps(list(META_LS))}.filter(k => localStorage.getItem(k) !== null)")
    check(left == [], f"se borran los datos de Meta en localStorage {left or ''}")
    pg.check("#cc-legal")
    pg.evaluate("() => document.getElementById('btn-pago').addEventListener('click', e => e.preventDefault())")
    pg.click("#btn-pago"); pg.wait_for_timeout(2500)
    check(not net.meta_tr and meta_cookies(ctx) == [], "en la misma página ya no se envía nada ni vuelve _fbp"
          + (f" → enviado: {[u[:160] for u in net.meta_tr]} cookies: {meta_cookies(ctx)}" if net.meta_tr or meta_cookies(ctx) else ""))
    net.clear()
    pg.reload(); pg.wait_for_timeout(2500)
    check(not net.fbevents and not net.meta_tr and meta_cookies(ctx) == [], "al recargar: el píxel deja de cargar")
    ctx.close()

    # ── 5) Caducidad a los 12 meses ──────────────────────────────────────
    print("5) Aceptación de hace 13 meses")
    ctx, net = fresh()
    ctx.add_init_script("try{localStorage.getItem('ad_cookie_consent')||localStorage.setItem('ad_cookie_consent',"
                        "JSON.stringify({choice:'accepted',ts:new Date(Date.now()-395*864e5).toISOString(),v:3}))}catch(e){}")
    pg = ctx.new_page(); pg.goto(page_url); pg.wait_for_timeout(2000)
    check(pg.locator(".cookie-banner.is-visible").count() == 1, "caducada: vuelve a preguntar")
    check(not net.fbevents and not net.meta_tr, "caducada: el píxel no carga")
    ctx.close()

    # ── 6) Resto del sitio ───────────────────────────────────────────────
    print("6) Otras páginas")
    ctx, net = fresh()
    pg = ctx.new_page()
    for path in ("/index.html", "/blog.html", "/cookies.html", "/privacidad.html", "/utilidades/index.html"):
        pg.goto(base + path); pg.wait_for_timeout(700)
        ok = (pg.locator(".cookie-banner.is-visible").count() == 1
              and pg.locator("footer a", has_text="Configurar cookies").count() == 1)
        check(ok, f"{path}: aviso + «Configurar cookies» en el pie")
    pg.click(".cookie-banner button[data-choice=accepted]"); pg.wait_for_timeout(1500)
    check(not net.fbevents and not net.meta_tr, "aceptar en una página sin píxel no carga nada de Meta")
    if capturas:
        pg.goto(base + "/cookies.html"); pg.wait_for_timeout(500)
        pg.locator("table.tabla-cookies").scroll_into_view_if_needed()
        f = capturas / f"{dev_name.replace(' ', '_')}_03_tabla_cookies.png"
        pg.screenshot(path=str(f)); print("     captura:", f)
    ctx.close()
    br.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capturas", type=Path, default=None)
    a = ap.parse_args()
    if a.capturas:
        a.capturas.mkdir(parents=True, exist_ok=True)
    srv, port = serve()
    base = f"http://{HOST}:{port}"
    with sync_playwright() as p:
        for dev in ("iPhone 13", "Pixel 7"):
            device_run(p, dev, base, a.capturas)
    srv.shutdown()
    print()
    print("RESULTADO:", "OK" if not FAILS else f"{len(FAILS)} FALLOS")
    for f in FAILS:
        print("  ✖", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
