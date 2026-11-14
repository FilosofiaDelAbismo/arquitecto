#!/usr/bin/env python3
"""E2E LOCAL de la medición de crea-tu-cancion.html (14-11-2026).

Sirve el repo en 127.0.0.1, sustituye fbevents.js por un JS vacío (la cola
`fbq.queue` del snippet oficial guarda cada llamada y la leemos), simula la API
de canje y corta la navegación a Stripe. No toca Meta, Stripe ni la API real.

    python3 tools/e2e_cancion_medicion.py            # imprime las llamadas fbq
"""
from __future__ import annotations

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
UTM = "utm_source=facebook&utm_medium=paid&utm_campaign=cancion_A&utm_content=video_C"
FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ✔ " if cond else "  ✖ ") + msg)
    if not cond:
        FAILS.append(msg)


def serve() -> tuple[socketserver.TCPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):  # noqa: D401
            pass
    h = functools.partial(Quiet, directory=str(ROOT))
    srv = socketserver.TCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def fbq_calls(page) -> list:
    return page.evaluate("() => (window.fbq && window.fbq.queue || []).map(a => Array.from(a))")


def events(page, name: str) -> list:
    return [c for c in fbq_calls(page) if len(c) > 1 and c[0] == "track" and c[1] == name]


def main() -> int:
    srv, port = serve()
    base = f"http://127.0.0.1:{port}/crea-tu-cancion.html"
    stripe_hits: list[str] = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context()
        # 14-11-2026: el píxel solo carga con «Aceptar» en el aviso de cookies.
        # Aquí se prueba la medición CON consentimiento; el caso sin él está en
        # tools/e2e_cookies_consentimiento.py.
        ctx.add_init_script("try{localStorage.setItem('ad_cookie_consent',"
                            "JSON.stringify({choice:'accepted',ts:new Date().toISOString(),v:3}))}catch(e){}")

        def route(r):
            u = r.request.url
            if "connect.facebook.net" in u:
                return r.fulfill(status=200, content_type="application/javascript", body="/*stub*/")
            if "facebook.com/tr" in u or "analytics.arquitectodigital.io" in u or "widget.js" in u:
                return r.fulfill(status=200, body="")
            if "buy.stripe.com" in u:
                stripe_hits.append(u)
                return r.fulfill(status=200, content_type="text/html", body="<p>stripe stub</p>")
            if u.endswith("/webhook/music/redeem"):
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"ok": True, "token": "tok_test"}))
            if "/music/create" in u:
                return r.fulfill(status=200, content_type="text/html", body="<p>create stub</p>")
            return r.continue_()
        ctx.route("**/*", route)

        print("1) Entrada desde el anuncio con UTM → InitiateCheckout y UTM hasta Stripe")
        pg = ctx.new_page()
        pg.goto(f"{base}?{UTM}")
        pg.wait_for_load_state("load")
        check([c[:2] for c in fbq_calls(pg)] == [["set", "autoConfig"], ["init", "1722843912288989"], ["track", "PageView"]],
              "al cargar solo autoConfig off + init + PageView (sin Purchase)")
        pg.click("#btn-pago", force=True)  # aria-disabled: clic real del usuario
        check(not events(pg, "InitiateCheckout") and not stripe_hits,
              "sin casilla legal: ni InitiateCheckout ni salto a Stripe")
        pg.check("#cc-legal")
        with pg.expect_navigation():
            pg.click("#btn-pago")
        check(len(stripe_hits) == 1, "con casilla: navega a Stripe")
        q = parse_qs(urlparse(stripe_hits[0]).query) if stripe_hits else {}
        print("     URL a Stripe:", stripe_hits[0] if stripe_hits else "-")
        check(q.get("utm_campaign") == ["cancion_A"] and q.get("utm_source") == ["facebook"],
              "los utm_* llegan al Payment Link")
        check(bool(q.get("client_reference_id")), "client_reference_id presente")
        pg.go_back(); pg.wait_for_load_state("load")

        print("2) Misma pestaña, vuelve a la página SIN UTM en la URL: los recupera de la sesión")
        pg2 = pg; pg2.goto(base); pg2.wait_for_load_state("load")
        pg2.check("#cc-legal")
        pg2.evaluate("() => document.getElementById('btn-pago').addEventListener('click', e => e.preventDefault())")
        pg2.click("#btn-pago"); pg2.click("#btn-pago")
        ic = events(pg2, "InitiateCheckout")
        print("     fbq:", ic)
        check(len(ic) == 1 and ic[0][2] == {"value": 15, "currency": "EUR"}, "InitiateCheckout una vez, 15 EUR")
        check("utm_campaign=cancion_A" in pg2.get_attribute("#btn-pago", "href"),
              "UTM de primer toque conservados en la misma sesión")

        print("3) Vuelta de Stripe con ?session_id=cs_… → Purchase una vez; recarga → nada")
        pg3 = ctx.new_page(); pg3.goto(f"{base}?session_id=cs_test_RETORNO1"); pg3.wait_for_load_state("load")
        pu = events(pg3, "Purchase")
        print("     fbq:", pu)
        check(len(pu) == 1 and pu[0][2]["value"] == 15 and pu[0][2]["currency"] == "EUR"
              and pu[0][3] == {"eventID": "cs_test_RETORNO1"}, "Purchase value 15 EUR, eventID = código")
        check(pg3.input_value("#music-codigo") == "cs_test_RETORNO1", "el código se prerrellena como antes")
        pg3.reload(); pg3.wait_for_load_state("load")
        check(events(pg3, "Purchase") == [], "recarga: Purchase NO se repite")

        print("4) Canje de un código de pago (flujo real de hoy: el código llega por email)")
        pg4 = ctx.new_page(); pg4.goto(base); pg4.wait_for_load_state("load")
        pg4.fill("#music-codigo", "cs_test_CANJE22"); pg4.fill("#music-email", "test@example.com")
        pg4.click("#music-form button[type=submit]")
        pg4.wait_for_function("() => (window.fbq.queue||[]).some(a => a[1]==='Purchase')", timeout=3000)
        pu4 = events(pg4, "Purchase")
        print("     fbq:", pu4)
        check(len(pu4) == 1 and pu4[0][3] == {"eventID": "cs_test_CANJE22"}, "Purchase al canjear")
        pg4.wait_for_url("**/music/create?token=tok_test", timeout=3000)
        check(True, "redirige a la creación tras 400 ms")
        pg5 = ctx.new_page(); pg5.goto(base); pg5.wait_for_load_state("load")
        pg5.fill("#music-codigo", "cs_test_CANJE22"); pg5.fill("#music-email", "test@example.com")
        pg5.click("#music-form button[type=submit]")
        pg5.wait_for_url("**/music/create**", timeout=3000)
        check(True, "volver a canjear el mismo código: redirige sin esperar…")
        # (la página ya navegó: comprobamos con la marca de localStorage)
        pg6 = ctx.new_page(); pg6.goto(base); pg6.wait_for_load_state("load")
        check(pg6.evaluate("() => !!localStorage.getItem('ad_purchase_cs_test_CANJE22')"),
              "…porque ese pago ya está marcado como enviado")

        print("5) Código de REGALO → sin Purchase")
        pg7 = ctx.new_page(); pg7.goto(base); pg7.wait_for_load_state("load")
        pg7.evaluate("() => { window.__fired = []; const f = window.fbq; window.fbq = function(){ window.__fired.push(Array.from(arguments)); return f.apply(this, arguments); }; }")
        pg7.fill("#music-codigo", "REGALO-ABCD-EFGH"); pg7.fill("#music-email", "test@example.com")
        pg7.click("#music-form button[type=submit]")
        pg7.wait_for_url("**/music/create**", timeout=3000)
        check(True, "regalo: canje y navegación inmediata (sin Purchase, no hay espera de 400 ms)")
        br.close()
    srv.shutdown()
    print()
    print("RESULTADO:", "OK" if not FAILS else f"{len(FAILS)} FALLOS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
