#!/usr/bin/env python3
"""E2E LOCAL: sitio sin píxel de Meta + aviso de cookies COMPACTO + medición de
Crea tu Canción con Plausible (14-11-2026).

Aviso compacto: franja en el flujo bajo la cabecera («Esta web no usa
cookies.» + «Más info» + «Entendido»). Se mide su alto, que no tape nada
(elementFromPoint en el H1, el vídeo y «Comprar»; y en las 92 páginas, ningún
texto ni elemento bajo la franja), el vídeo en la primera pantalla, «Entendido»,
recarga, «Ver el aviso de cookies», 0 cookies y el CLS (también con red y CPU
lentas). ResizeObserver: el alto del aviso no cambia en toda la carga (normal,
red 4G lenta + CPU ×4 y sin fuentes web) y su CLS propio es < 0,001. En las 15
legales y contratar.html, elementFromPoint en la primera línea del título, con
y sin aviso: empieza bajo la cabecera fija (y bajo el aviso si está).

Sirve el repo en local (dominio de pega → 127.0.0.1) y emula iPhone 13,
Pixel 7 y un escritorio de 1366×768. window.plausible se SIMULA (el script.js real se sustituye por uno
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
ALTOS: list[tuple] = []
ALTOS_TODAS: list[tuple] = []
VIDEO: list[tuple] = []
CLS: list[tuple] = []
RO: list[tuple] = []        # (dispositivo, página, modo, altos distintos vistos por ResizeObserver, CLS propio del aviso)
TITULOS: list[tuple] = []   # (dispositivo, con/sin aviso, páginas OK, total)
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

# CLS: suma de layout-shift sin interacción reciente (como la métrica de Google),
# con el nodo que se movió en cada salto.
CLS_INIT = """
window.__cls = 0; window.__clsAviso = 0; window.__shifts = [];
try {
  new PerformanceObserver(function (l) {
    l.getEntries().forEach(function (e) {
      if (e.hadRecentInput) return;
      window.__cls += e.value;
      /* CLS PROPIO del aviso: misma fórmula que Chrome (fracción de impacto ×
         fracción de distancia) pero SOLO con los nodos del aviso de cada salto. */
      var vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight, rs = [], dmax = 0;
      (e.sources || []).forEach(function (s) {
        var n = s.node, el = n && (n.nodeType === 1 ? n : n.parentElement);
        if (!(el && el.closest && el.closest('#aviso-cookies'))) return;
        [s.previousRect, s.currentRect].forEach(function (r) {
          var x0 = Math.max(0, r.x), y0 = Math.max(0, r.y), x1 = Math.min(vw, r.x + r.width), y1 = Math.min(vh, r.y + r.height);
          if (x1 > x0 && y1 > y0) rs.push([x0, y0, x1, y1]);
        });
        dmax = Math.max(dmax, Math.abs(s.currentRect.x - s.previousRect.x), Math.abs(s.currentRect.y - s.previousRect.y));
      });
      var area = 0;   /* área de la unión de rectángulos (rejilla de 1 px: son pocos y pequeños) */
      if (rs.length) {
        var X0 = Math.min.apply(null, rs.map(function (r) { return Math.floor(r[0]); })), X1 = Math.max.apply(null, rs.map(function (r) { return Math.ceil(r[2]); }));
        var Y0 = Math.min.apply(null, rs.map(function (r) { return Math.floor(r[1]); })), Y1 = Math.max.apply(null, rs.map(function (r) { return Math.ceil(r[3]); }));
        for (var y = Y0; y < Y1; y++) for (var x = X0; x < X1; x++)
          if (rs.some(function (r) { return x + .5 > r[0] && x + .5 < r[2] && y + .5 > r[1] && y + .5 < r[3]; })) area++;
      }
      window.__clsAviso = (window.__clsAviso || 0) + (area / (vw * vh)) * (dmax / Math.max(vw, vh));
      window.__shifts.push({v: e.value, src: (e.sources || []).map(function (s) {
        var n = s.node; var el = n && (n.nodeType === 1 ? n : n.parentElement);
        return n ? ((el && el.closest && el.closest('#aviso-cookies') ? 'aviso-cookies>' : '') + n.nodeName + (n.id ? '#' + n.id : '') + (n.className && n.className.baseVal === undefined ? '.' + n.className : '')) : '?'; })});
    });
  }).observe({type: 'layout-shift', buffered: true});
} catch (e) {}
/* ResizeObserver en el aviso desde que entra en el DOM: todos los altos que
   tiene durante la carga (fuentes, red lenta…). Alto 0 = oculto. */
window.__avisoH = [];
try {
  var __mo = new MutationObserver(function () {
    var b = document.getElementById('aviso-cookies');
    if (!b) return;
    __mo.disconnect();
    new ResizeObserver(function (es) { es.forEach(function (e) {
      var h = e.borderBoxSize && e.borderBoxSize[0] ? e.borderBoxSize[0].blockSize : e.target.getBoundingClientRect().height;
      window.__avisoH.push({h: Math.round(h * 10) / 10, t: Math.round(performance.now())});
    }); }).observe(b);
  });
  __mo.observe(document, {childList: true, subtree: true});
} catch (e) {}
"""
# Las 15 legales (main.legal) y contratar.html (section.section-content): lo
# primero tras la cabecera común.
SEL16 = "#aviso-cookies + script + main.legal, #aviso-cookies + script + section.section-content"

AVISO = "#aviso-cookies"
AVISO_ON = "#aviso-cookies:not([hidden])"
DESKTOP = "Escritorio 1366×768"
MAX_ALTO_MOVIL = 70   # objetivo (máximo absoluto 90)
LEGALES16 = ["audio-libro-condiciones.html", "autoblog-condiciones.html", "aviso-legal.html", "cenit-condiciones.html",
             "cenit-pioneros-bases.html", "cenit-privacidad.html", "cenit-uso.html", "chatbot-condiciones.html",
             "condiciones.html", "contratar.html", "cookies.html", "crea-tu-cancion-condiciones.html",
             "girobot-condiciones.html", "privacidad.html", "sistemas-condiciones.html", "webs-condiciones.html"]


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


def covered_by(pg, sel: str) -> str | None:
    """Con el elemento en pantalla, ¿qué hay encima en 3 puntos? None = nada (se puede pulsar/ver)."""
    return pg.evaluate("""(sel) => {
        const t = document.querySelector(sel); const b = t.getBoundingClientRect();
        const pts = [[.5,.5],[.15,.5],[.85,.5]].map(([x,y]) => document.elementFromPoint(b.left + b.width*x, b.top + b.height*y));
        const ok = e => e && (t.contains(e) || e.contains(t) || (sel === '#demo-cancion' && e.closest('div') === t.parentElement));
        const bad = pts.find(e => !ok(e));
        return bad === undefined ? null : (bad ? (bad.closest('#aviso-cookies') ? 'aviso de cookies'
               : bad.tagName + '#' + bad.id + '.' + bad.className) : 'nada');
    }""", sel)


def overlap_banner(pg) -> list[str]:
    """Todo lo visible (texto, imágenes, vídeo, botones, enlaces, campos) que cae
    debajo de la franja del aviso. Vacío = el aviso no tapa nada."""
    return pg.evaluate("""() => {
        const bn = document.getElementById('aviso-cookies');
        if (!bn || bn.hidden) return ['(aviso no visible)'];
        const B = bn.getBoundingClientRect();
        const hit = r => r.width > 0 && r.height > 0 && r.bottom > B.top + 0.5 && r.top < B.bottom - 0.5 && r.right > B.left && r.left < B.right;
        const skip = el => !el || bn.contains(el) || el.closest('header') || ['fixed', 'sticky'].includes(getComputedStyle(el).position)
                            || [...(function* (e) { while (e) { yield e; e = e.parentElement; } })(el)].some(e => getComputedStyle(e).position === 'fixed');
        const out = [];
        const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let n; (n = w.nextNode());) {
          if (!n.textContent.trim() || skip(n.parentElement)) continue;
          const cs = getComputedStyle(n.parentElement);
          if (cs.visibility === 'hidden' || cs.display === 'none') continue;
          const rg = document.createRange(); rg.selectNodeContents(n);
          if ([...rg.getClientRects()].some(hit)) out.push('texto «' + n.textContent.trim().slice(0, 40) + '»');
        }
        for (const el of document.body.querySelectorAll('img,video,iframe,svg,button,input,select,textarea,a,canvas')) {
          if (skip(el)) continue;
          if (hit(el.getBoundingClientRect())) out.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''));
        }
        return out.slice(0, 5);
    }""")


def aviso_estable(pg, dev_name: str, pagina: str, modo: str) -> None:
    """Alto del aviso constante en TODA la carga (ResizeObserver) y CLS propio < 0,001."""
    hs = [x["h"] for x in pg.evaluate("window.__avisoH") if x["h"] > 0]
    propio = pg.evaluate("window.__clsAviso")
    distintos = sorted(set(hs))
    RO.append((dev_name, pagina, modo, distintos, round(propio, 5)))
    fin = rect(pg, AVISO)["height"]
    check(bool(hs) and max(hs) - min(hs) <= 0.5 and abs(hs[-1] - fin) <= 0.5,
          f"{pagina} ({modo}): el alto del aviso no cambia durante la carga (ResizeObserver: {distintos} px, {len(hs)} medidas)")
    check(propio < 0.001, f"{pagina} ({modo}): CLS propio del aviso < 0,001 ({propio:.5f})")


def titulo_libre(pg) -> list[str]:
    """Legales y contratar: el título (y lo primero del contenido) empieza bajo la
    cabecera fija y, si está, bajo el aviso; elementFromPoint en su PRIMERA línea."""
    return pg.evaluate("""(sel) => {
        const c = document.querySelector(sel);
        if (!c) return ['(no hay main.legal / section.section-content tras la cabecera)'];
        const hb = document.querySelector('header').getBoundingClientRect().bottom;
        const av = document.getElementById('aviso-cookies');
        const tope = av && !av.hidden ? Math.max(hb, av.getBoundingClientRect().bottom) : hb;
        const out = [];
        for (const t of [...new Set([c.firstElementChild, c.querySelector('h1')])].filter(Boolean)) {
          const r = t.getBoundingClientRect();
          const nom = t.tagName + (t.id ? '#' + t.id : '');
          if (r.top < tope - 0.5) out.push(`${nom} empieza en ${r.top.toFixed(1)} y lo de arriba acaba en ${tope.toFixed(1)}`);
          const rg = document.createRange(); rg.selectNodeContents(t);
          const l = [...rg.getClientRects()].filter(x => x.width > 0 && x.height > 0)[0] || r;
          for (const fx of [.05, .5, .95]) {
            const e = document.elementFromPoint(l.left + l.width * fx, l.top + l.height / 2);
            if (!e || !(t === e || t.contains(e)))
              out.push(`${nom}: 1.ª línea tapada por ${e ? (e.closest('#aviso-cookies') ? 'el aviso' : e.closest('header') ? 'la cabecera' : e.tagName) : 'nada'}`);
          }
        }
        return out;
    }""", SEL16)


def rect(pg, sel: str):
    return pg.evaluate(f"() => {{ const e = document.querySelector({json.dumps(sel)}); "
                       "return e ? e.getBoundingClientRect().toJSON() : null; }")


def device_run(p, dev_name: str, base: str, capturas: Path | None, todas: list[str], con_aviso: set[str]) -> None:
    if dev_name == DESKTOP:
        dev = {"viewport": {"width": 1366, "height": 768}, "device_scale_factor": 1, "is_mobile": False, "has_touch": False}
    else:
        dev = {k: v for k, v in p.devices[dev_name].items() if k != "default_browser_type"}
    br = p.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
    page_url = f"{base}/crea-tu-cancion.html"
    tag = {"iPhone 13": "iphone13", "Pixel 7": "pixel7"}.get(dev_name, "escritorio1366")

    def fresh(**kw):
        ctx = br.new_context(**dev)
        net = Net(**kw)
        ctx.route("**/*", net.route)
        ctx.expose_function("__plRec", net.rec)
        ctx.add_init_script(PLAUSIBLE_STUB)
        ctx.add_init_script(CLS_INIT)
        return ctx, net

    print(f"\n════ {dev_name} ({dev['viewport']['width']}×{dev['viewport']['height']}) ════")

    # ── 1) Primera visita: aviso compacto ──────────────────────────────
    for pagina in ("crea-tu-cancion.html", "index.html"):
        print(f"1) Primera visita: {pagina}")
        ctx, net = fresh()
        pg = ctx.new_page()
        pg.goto(f"{base}/{pagina}")
        pg.wait_for_selector(AVISO_ON)
        pg.wait_for_timeout(1500)   # deja montar la burbuja del chat y cargar fuentes
        txt = " ".join(pg.inner_text(AVISO).split())
        check(txt == "Esta web no usa cookies. Más info Entendido", f"texto: «Esta web no usa cookies. Más info» + «Entendido» ({txt!r})")
        check(pg.get_attribute(f"{AVISO} a", "href") == "/cookies.html", "«Más info» lleva a /cookies.html")
        btns = pg.eval_on_selector_all(f"{AVISO} button", "bs => bs.map(b => b.textContent.trim())")
        check(btns == ["Entendido"], f"un solo botón «Entendido» ({btns})")
        check(ctx.cookies() == [], f"antes: sin cookies ({[c['name'] for c in ctx.cookies()]})")
        check(pg.evaluate("typeof window.fbq") == "undefined", "window.fbq no existe")
        vh = pg.evaluate("innerHeight")
        bn, cab, h1 = rect(pg, AVISO), rect(pg, "header"), rect(pg, "h1")
        bt = rect(pg, f"{AVISO} button")
        lineas = pg.evaluate("() => { const p = document.querySelector('#aviso-cookies p'); "
                             "return Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(p).lineHeight)); }")
        fila = pg.evaluate("() => { const p = document.querySelector('#aviso-cookies p').getBoundingClientRect(), "
                           "b = document.querySelector('#aviso-cookies button').getBoundingClientRect(); return Math.abs((p.top+p.bottom)/2 - (b.top+b.bottom)/2) < 4; }")
        ALTOS.append((dev_name, pagina, round(bn["height"], 1), lineas, round(100 * bn["height"] / vh, 1), vh))
        print(f"     aviso: {bn['height']:.1f} px de alto = {100 * bn['height'] / vh:.1f} % de la pantalla ({vh} px); texto en {lineas} línea(s)")
        if dev_name == DESKTOP:
            check(lineas == 1 and fila, f"PC: una sola línea (texto y botón en la misma fila) ({lineas} líneas)")
        else:
            check(lineas <= 2, f"móvil: como mucho dos líneas ({lineas})")
            check(bn["height"] <= MAX_ALTO_MOVIL, f"móvil: alto ≤ {MAX_ALTO_MOVIL} px ({bn['height']:.1f})")
        check(bt["height"] >= 44, f"botón «Entendido» ≥ 44 px de alto ({bt['height']:.1f})")
        check(abs(bn["top"] - cab["bottom"]) <= 1, f"justo debajo de la cabecera (aviso {bn['top']:.1f} / cabecera {cab['bottom']:.1f})")
        check(pg.evaluate("getComputedStyle(document.getElementById('aviso-cookies')).position") == "relative",
              "en el flujo de la página (position: relative, ni fixed ni sticky)")
        check(h1 is not None and h1["top"] >= bn["bottom"] - 0.5, f"orden: cabecera → aviso → título (H1 en {h1 and round(h1['top'])}, aviso acaba en {bn['bottom']:.0f})")
        who = covered_by(pg, "h1")
        check(who is None, f"el H1 no está tapado (elementFromPoint){'' if who is None else ': lo tapa ' + who}")
        if pagina == "crea-tu-cancion.html":
            v = rect(pg, "#demo-cancion")
            check(v["top"] >= bn["bottom"], "orden: … título → vídeo")
            vis = max(0.0, min(v["bottom"], vh) - v["top"])
            print(f"     vídeo: de {v['top']:.0f} a {v['bottom']:.0f} px; en la primera pantalla se ven {vis:.0f} px ({100 * vis / v['height']:.0f} %)")
            VIDEO.append((dev_name, round(v["top"]), round(v["bottom"]), vh, round(100 * vis / v["height"])))
            if dev_name != DESKTOP:
                check(vis / v["height"] >= 0.5, f"vídeo visible en la primera pantalla con el aviso puesto (≥ 50 %: {100 * vis / v['height']:.0f} %)")
            who = covered_by(pg, "#demo-cancion")
            check(who is None, f"el vídeo no está tapado (elementFromPoint){'' if who is None else ': lo tapa ' + who}")
        ov = overlap_banner(pg)
        check(ov == [], f"nada visible debajo de la franja ({ov})")
        pg.wait_for_timeout(500)
        cls = pg.evaluate("window.__cls"); sh = pg.evaluate("window.__shifts")
        CLS.append((dev_name, pagina, "normal", round(cls, 4)))
        print(f"     CLS al cargar: {cls:.4f} {sh if sh else ''}")
        check(cls < 0.1, f"CLS < 0,1 ({cls:.4f})")
        aviso_estable(pg, dev_name, pagina, "normal")
        if capturas:
            f = capturas / f"{tag}_{pagina[:-5]}_1_con_aviso.png"
            pg.screenshot(path=str(f)); print("     captura:", f)
        if pagina == "crea-tu-cancion.html":
            who = covered_by(pg, "#btn-pago") if pg.evaluate(
                "() => document.getElementById('btn-pago').scrollIntoView({block: 'center'})") is None else "?"
            check(who is None, f"«Comprar» se puede pulsar sin cerrar el aviso (elementFromPoint){'' if who is None else ': lo tapa ' + who}")
            r_b = pg.evaluate("() => { const a = document.getElementById('aviso-cookies').getBoundingClientRect(), "
                              "c = document.getElementById('btn-pago').getBoundingClientRect(); return c.top >= a.bottom; }")
            check(r_b, "«Comprar» está por debajo de la franja en la página (no se cruzan nunca)")
            st = storage(pg)
            check(st["ls"] == {} and st["ss"] == {} and st["ck"] == "", f"bajar no guarda nada ni cuenta como «Entendido» ({st})")
            pg.evaluate("() => window.scrollTo(0, 0)"); pg.wait_for_timeout(200)
        h1_antes = rect(pg, "h1")["top"]
        pg.click(f"{AVISO} button[data-close]")
        pg.wait_for_timeout(300)
        check(pg.locator(AVISO_ON).count() == 0, "con «Entendido» desaparece")
        sube = h1_antes - rect(pg, "h1")["top"]
        check(abs(sube - bn["height"]) <= 1, f"y el contenido sube justo el alto del aviso ({sube:.1f} px)")
        check(ctx.cookies() == [], f"después: sin cookies ({[c['name'] for c in ctx.cookies()]})")
        st = storage(pg)
        rec = json.loads(st["ls"].get("ad_cookie_consent", "null") or "null")
        check(list(st["ls"]) == ["ad_cookie_consent"] and st["ss"] == {} and st["ck"] == "",
              f"solo queda ad_cookie_consent en localStorage ({st})")
        check(isinstance(rec, dict) and rec.get("choice") == "seen" and rec.get("v") == 2, f"mismo formato que antes: choice «seen», v 2 ({rec})")
        if capturas:
            f = capturas / f"{tag}_{pagina[:-5]}_2_tras_entendido.png"
            pg.screenshot(path=str(f)); print("     captura:", f)
        pg.reload(); pg.wait_for_timeout(800)
        check(pg.locator(AVISO_ON).count() == 0, "al recargar no vuelve a salir")
        cls, sh = pg.evaluate("window.__cls"), pg.evaluate("window.__shifts")
        CLS.append((dev_name, pagina, "recarga sin aviso", round(cls, 4)))
        check(not any("aviso-cookies" in str(x) for x in sh) and cls < 0.1, f"recarga sin aviso: CLS {cls:.4f}, nada del aviso ({sh})")
        # «Ver el aviso de cookies» del pie: vuelve a salir arriba, en su sitio.
        pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)"); pg.wait_for_timeout(200)
        pg.locator("footer a", has_text="Ver el aviso de cookies").first.click()
        pg.wait_for_timeout(300)
        check(pg.locator(AVISO_ON).count() == 1, "«Ver el aviso de cookies» lo vuelve a mostrar")
        bn2, cab2 = rect(pg, AVISO), rect(pg, "header")
        check(pg.evaluate("scrollY") == 0 and abs(bn2["top"] - cab2["bottom"]) <= 1, "en el mismo sitio, arriba (y sube para que se vea)")
        check(pg.evaluate("localStorage.getItem('ad_cookie_consent')") is None, "se borra la elección")
        check(ctx.cookies() == [], "sin cookies")
        pg.click(f"{AVISO} button[data-close]"); pg.wait_for_timeout(200)
        pg.reload(); pg.wait_for_timeout(500)
        check(pg.locator(AVISO_ON).count() == 0, "«Entendido» otra vez: y no vuelve al recargar")
        check(net.meta == [], f"ninguna petición a Meta ({net.meta[:3]})")
        ctx.close()

    # ── 1b) Quien ya pulsó «Entendido» con el aviso anterior no lo vuelve a ver
    ctx, net = fresh()
    ctx.add_init_script("localStorage.setItem('ad_cookie_consent', JSON.stringify({choice: 'seen', ts: '2026-11-01T10:00:00.000Z', v: 2}))")
    pg = ctx.new_page(); pg.goto(page_url); pg.wait_for_timeout(500)
    check(pg.locator(AVISO_ON).count() == 0, "con la elección guardada por el aviso anterior (v2) no sale")
    ctx.close()

    # ── 1c) Carga lenta y sin fuentes web: el aviso no cambia de alto ───
    #   · red 4G lenta + CPU ×4 (llegada desde el anuncio en un móvil normal)
    #   · fuentes web bloqueadas (solo las de reserva, más anchas: era lo que
    #     partía el aviso en 2 filas en iPhone)
    for modo in ("red 4G lenta + CPU ×4", "sin fuentes web"):
        for pagina in ("crea-tu-cancion.html", "index.html"):
            ctx, net = fresh()
            if modo == "sin fuentes web":
                ctx.route("**/*", lambda r: r.abort() if r.request.resource_type == "font" else r.fallback())
            pg = ctx.new_page()
            if modo.startswith("red"):
                cdp = ctx.new_cdp_session(pg)
                cdp.send("Network.enable")
                cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                         "downloadThroughput": 1.6e6 / 8, "uploadThroughput": 750e3 / 8})
                cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            pg.goto(f"{base}/{pagina}", wait_until="load", timeout=60000)
            pg.wait_for_timeout(1500)
            cls = pg.evaluate("window.__cls"); sh = pg.evaluate("window.__shifts")
            CLS.append((dev_name, pagina, modo, round(cls, 4)))
            print(f"1c) {pagina} ({modo}): CLS {cls:.4f} {sh if sh else ''}")
            check(cls < 0.1, f"{pagina} ({modo}): CLS < 0,1 ({cls:.4f})")
            aviso_estable(pg, dev_name, pagina, modo)
            ctx.close()
    # Mismo alto en todos los modos (normal, lenta, sin fuentes) en este dispositivo.
    hs = sorted({h for d, _, _, ds, _ in RO if d == dev_name for h in ds})
    check(len(hs) == 1, f"mismo alto del aviso con y sin fuentes web y con red lenta ({hs} px)")

    # ── 2) Comprar con UTM en la URL ────────────────────────────────────
    print("2) Llegada con ?" + UTM_Q)
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?" + UTM_Q)
    pg.wait_for_selector(AVISO_ON)
    pg.click(f"{AVISO} button[data-close]")
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
    pg.goto(page_url); pg.click(f"{AVISO} button[data-close]")
    pg.click("#btn-pago", force=True); pg.wait_for_timeout(700)
    check(net.stripe == [] and net.pl == [], f"no va a Stripe ni manda evento ({net.stripe}, {net.pl})")
    ctx.close()

    # ── 4) Canje ─────────────────────────────────────────────────────────
    print("4) Canje")
    ctx, net = fresh()
    pg = ctx.new_page()
    pg.goto(page_url + "?" + UTM_Q); pg.click(f"{AVISO} button[data-close]")
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
        malas, sin_aviso, tapa, altos, p16 = [], [], [], [], []
        for path in todas:
            pg.goto(f"{base}/{path}", wait_until="load")
            for _ in range(3):   # alguna página redirige al cargar: se mira la de destino
                try:
                    if pg.evaluate("typeof window.fbq !== 'undefined' || typeof window._fbq !== 'undefined'"):
                        malas.append(path)
                    if pg.evaluate("(s) => !!document.querySelector(s)", SEL16):
                        p16.append(path)
                    if path in con_aviso:
                        if pg.locator(AVISO_ON).count() != 1:
                            sin_aviso.append(path)
                        else:
                            altos.append(rect(pg, AVISO)["height"])
                            ov = overlap_banner(pg)
                            if ov:
                                tapa.append(f"{path}: {ov}")
                    break
                except Exception:
                    pg.wait_for_load_state("load")
        check(malas == [], f"window.fbq no existe en ninguna ({malas})")
        check(len(altos) == len(con_aviso) == 92 and sin_aviso == [], f"el aviso sale en las {len(con_aviso)} páginas con cookies.js ({sin_aviso})")
        if altos:
            print(f"     alto del aviso en las {len(altos)} páginas: {min(altos):.1f}–{max(altos):.1f} px")
            ALTOS_TODAS.append((dev_name, len(altos), round(min(altos), 1), round(max(altos), 1)))
        check(tapa == [], f"en ninguna página tapa texto ni elementos ({tapa[:5]})")
        check(net.meta == [], f"ninguna petición a Meta ({net.meta[:3]})")
        check(ctx.cookies() == [], "sin cookies tras recorrerlas todas")
        check(sorted(p16) == sorted(LEGALES16), f"main.legal / section.section-content justo tras la cabecera: las 16 previstas ({sorted(set(p16) ^ set(LEGALES16))})")
        ctx.close()

    # ── 7) Legales y contratar: el título empieza bajo la cabecera (y el aviso)
    print(f"7) {len(LEGALES16)} páginas (15 legales + contratar.html): título libre, con y sin aviso")
    for con in (True, False):
        ctx, net = fresh(widget_real=False)
        if not con:
            ctx.add_init_script("localStorage.setItem('ad_cookie_consent', JSON.stringify({choice: 'seen', ts: '2026-11-14T10:00:00.000Z', v: 2}))")
        pg = ctx.new_page()
        malas = []
        for path in LEGALES16:
            pg.goto(f"{base}/{path}", wait_until="load")
            pg.wait_for_timeout(150)
            if (pg.locator(AVISO_ON).count() == 1) != con:
                malas.append(f"{path}: aviso {'no ' if con else ''}visible")
                continue
            if pg.evaluate("scrollY") != 0:
                malas.append(f"{path}: no empieza arriba"); continue
            r = titulo_libre(pg)
            if r:
                malas.append(f"{path}: {r}")
            if capturas and path == "aviso-legal.html":
                f = capturas / f"{tag}_aviso-legal_{'1_con' if con else '2_sin'}_aviso.png"
                pg.screenshot(path=str(f)); print("     captura:", f)
        modo = "con aviso" if con else "sin aviso"
        TITULOS.append((dev_name, modo, len(LEGALES16) - len(malas), len(LEGALES16)))
        check(malas == [], f"{modo}: título y primera línea bajo la cabecera{' y el aviso' if con else ''} en las {len(LEGALES16)} (elementFromPoint) ({malas[:4]})")
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
    con_aviso = {f for f in todas if "assets/cookies.js" in (ROOT / f).read_text(encoding="utf-8", errors="replace")}
    srv, port = serve()
    base = f"http://{HOST}:{port}"
    with sync_playwright() as p:
        for dev in ("iPhone 13", "Pixel 7", DESKTOP):
            device_run(p, dev, base, a.capturas, todas, con_aviso)
    srv.shutdown()
    print("\n════ Resumen del aviso ════")
    for d, pag, h, l, pct, vh in ALTOS:
        print(f"  alto  {d:<22} {pag:<22} {h:>5} px · {l} línea(s) · {pct} % de {vh} px")
    for d, n, lo, hi in ALTOS_TODAS:
        print(f"  alto  {d:<22} {n} páginas: {lo}–{hi} px")
    for d, t, b, vh, pct in VIDEO:
        print(f"  vídeo {d:<22} de {t} a {b} px, pantalla {vh} px → {pct} % visible en la primera pantalla")
    for d, pag, modo, c in CLS:
        print(f"  CLS   {d:<22} {pag:<22} {modo:<22} {c}")
    for d, pag, modo, hs, pr in RO:
        print(f"  RO    {d:<22} {pag:<22} {modo:<22} altos vistos {hs} px · CLS propio del aviso {pr}")
    for d, modo, ok, n in TITULOS:
        print(f"  título {d:<21} {modo:<10} {ok}/{n} páginas con el título libre")
    print()
    print("RESULTADO:", "OK" if not FAILS else f"{len(FAILS)} FALLOS")
    for f in FAILS:
        print("  ✖", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
