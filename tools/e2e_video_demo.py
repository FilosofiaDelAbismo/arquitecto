#!/usr/bin/env python3
"""E2E LOCAL del vídeo demo de Crea tu Canción (14-11-2026, vídeo sin datos personales).

Sirve el repo en local y, emulando iPhone 13 y Pixel 7, comprueba en crea-tu-cancion.html que el vídeo:
  · apunta a assets/video/crea-tu-cancion.mp4?v=… (rompe la caché del CDN) y el fichero que llega es el del disco;
  · título, aria-label y JSON-LD dicen «Demostración en 40 segundos» (nada de «1 minuto»);
    (estas, con el Chromium de Playwright y su emulación de dispositivo)
  · carga (loadeddata, readyState ≥ 2, sin error) con 1080×1920 y ~40 s;
  · se reproduce (silenciado, currentTime avanza ≥ 1 s).
    (estas dos, con el Firefox de Playwright: el Chromium de Playwright no trae H.264/AAC. Firefox no tiene
     emulación de dispositivo, así que se usa el viewport, la densidad, el táctil y el user-agent del móvil)
Requiere: python3 -m playwright install firefox
No sale nada a la red: todo lo que no sea el servidor local se corta.

    python3 tools/e2e_video_demo.py
"""
from __future__ import annotations

import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "assets/video/crea-tu-cancion.mp4"
TITULO = "Demostración en 40 segundos"
FAILS: list[str] = []


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


def main() -> int:
    srv, port = serve()
    base = f"http://127.0.0.1:{port}"
    tam = VIDEO.stat().st_size
    with sync_playwright() as p:
        br = p.chromium.launch()
        ff = p.firefox.launch()
        for dev_name in ("iPhone 13", "Pixel 7"):
            print(f"\n════ {dev_name} ════")
            dev = {k: v for k, v in p.devices[dev_name].items() if k != "default_browser_type"}
            ctx = br.new_context(**dev)
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            pg = ctx.new_page()
            pg.goto(f"{base}/crea-tu-cancion.html", wait_until="load")
            src = pg.get_attribute("#demo-cancion", "src") or ""
            check(src.startswith("assets/video/crea-tu-cancion.mp4?v="), f"src con ?v= ({src})")
            h2 = pg.evaluate("() => document.getElementById('demo-cancion').closest('div').parentElement.querySelector('h2').textContent.trim()")
            check(h2 == TITULO, f"título «{h2}»")
            check(pg.get_attribute("#demo-cancion", "aria-label") == TITULO, "aria-label")
            ld = pg.evaluate("() => [...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s => s.textContent).join('\\n')")
            check(f'"name": "{TITULO}"' in ld and "1 minuto" not in pg.content(), "JSON-LD con el título nuevo y sin «1 minuto» en la página")
            r = pg.request.get(f"{base}/{src}")
            check(r.ok and len(r.body()) == tam, f"el servidor entrega el fichero del disco ({len(r.body())} = {tam} bytes)")
            ctx.close()

            # Carga y reproducción en Firefox (H.264/AAC), con el tamaño de pantalla y el user-agent del móvil
            d = p.devices[dev_name]
            fctx = ff.new_context(viewport=d["viewport"], screen=d.get("screen", d["viewport"]),
                                  device_scale_factor=d["device_scale_factor"], has_touch=d["has_touch"],
                                  user_agent=d["user_agent"])
            fctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            recibidos: list[tuple[str, int, int]] = []
            fctx.on("response", lambda r: recibidos.append((r.url, r.status, int(r.headers.get("content-length", "-1"))))
                    if "crea-tu-cancion.mp4" in r.url else None)
            pg = fctx.new_page()
            pg.goto(f"{base}/crea-tu-cancion.html", wait_until="load")
            emu = pg.evaluate("() => ({w: innerWidth, h: innerHeight, dpr: devicePixelRatio, ua: navigator.userAgent})")
            print(f"    Firefox: {emu['w']}×{emu['h']} @{emu['dpr']}x · UA {emu['ua'][:60]}…")
            check(emu["w"] == d["viewport"]["width"] and emu["ua"] == d["user_agent"],
                  f"Firefox con el viewport y el user-agent de {dev_name}")
            st = pg.evaluate("""() => new Promise(res => {
                const v = document.getElementById('demo-cancion');
                const fin = () => res({rs: v.readyState, d: v.duration, w: v.videoWidth, h: v.videoHeight, err: v.error && v.error.code});
                if (v.readyState >= 2) return fin();
                v.preload = 'auto'; v.addEventListener('loadeddata', fin, {once: true});
                v.addEventListener('error', fin, {once: true}); v.load();
                setTimeout(fin, 15000);
            })""")
            print("    estado:", st)
            check(st["err"] is None, f"sin error de vídeo ({st['err']})")
            check(st["rs"] >= 2, f"carga: readyState ≥ 2 ({st['rs']})")
            check(st["w"] == 1080 and st["h"] == 1920, f"resolución 1080×1920 ({st['w']}×{st['h']})")
            check(39 <= (st["d"] or 0) <= 41, f"duración ~40 s ({st['d']})")
            pl = pg.evaluate("""async () => {
                const v = document.getElementById('demo-cancion');
                v.muted = true; v.currentTime = 0;
                try { await v.play(); } catch (e) { return {err: String(e)}; }
                const t0 = v.currentTime;
                await new Promise(r => setTimeout(r, 2500));
                return {t0, t1: v.currentTime, paused: v.paused};
            }""")
            print("    reproducción:", pl)
            check("err" not in pl and pl["t1"] - pl["t0"] >= 1.0, f"se reproduce: avanza {pl.get('t1', 0) - pl.get('t0', 0):.2f} s")
            check(any(s in (200, 206) for _, s, _ in recibidos), f"el navegador pidió el vídeo ({[(u.split('/')[-1], s) for u, s, _ in recibidos]})")
            fctx.close()
        br.close()
        ff.close()
    srv.shutdown()
    print("\nRESULTADO:", "OK" if not FAILS else f"{len(FAILS)} FALLOS")
    for f in FAILS:
        print("  ✖", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
