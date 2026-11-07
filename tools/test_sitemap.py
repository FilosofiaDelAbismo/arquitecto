#!/usr/bin/env python3
"""Test de sitemap.xml (solo lectura; hace GET a la web publicada).

Comprueba:
  1. XML bien formado, declarado UTF-8 y en UTF-8 válido, namespace 0.9.
  2. Cada <loc> es absoluta https://arquitectodigital.io/…, sin duplicados;
     <lastmod> con formato AAAA-MM-DD y no futura; sin priority/changefreq.
  3. sitemap.xml coincide con lo que genera tools/gen_sitemap.py (no está desfasado).
  4. Ninguna URL de tools/sitemap_pendientes.txt está en el sitemap.
  5. En vivo, cada URL: 200 sin redirección, canonical == loc, sin noindex
     (ni en <meta name="robots"> ni en X-Robots-Tag).
  6. robots.txt publicado tiene «Sitemap: https://arquitectodigital.io/sitemap.xml».

Uso: python3 tools/test_sitemap.py [--sin-red]
Sale 0 si todo pasa, 1 si algo falla.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://arquitectodigital.io"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
fallos: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if not cond:
        fallos.append(msg)


class _NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_op = urllib.request.build_opener(_NoRedir)


def get(url: str) -> tuple[int, dict, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (test_sitemap)"})
    try:
        r = _op.open(req, timeout=20)
        return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), (e.read() or b"").decode("utf-8", "replace")


def check_live(url: str) -> list[str]:
    try:
        code, h, body = get(url + ("&" if "?" in url else "?") + "nocache=1")
    except Exception as e:  # red
        return [f"{url}: error de red {e}"]
    errs = []
    if code != 200:
        errs.append(f"{url}: HTTP {code} {h.get('Location', '')}".rstrip())
        return errs
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*>', body, re.I)
    canon = re.search(r'href=["\']([^"\']+)', m.group(0)).group(1) if m else ""
    if canon != url:
        errs.append(f"{url}: canonical = «{canon}»")
    m = re.search(r'<meta[^>]+name=["\']robots["\'][^>]*>', body, re.I)
    if m and "noindex" in m.group(0).lower():
        errs.append(f"{url}: meta robots noindex")
    if "noindex" in str(h.get("X-Robots-Tag", "")).lower():
        errs.append(f"{url}: X-Robots-Tag noindex")
    return errs


def main() -> int:
    raw = (ROOT / "sitemap.xml").read_bytes()
    # 1
    ok(raw.startswith(b'<?xml version="1.0" encoding="UTF-8"?>'), "falta la declaración XML con encoding UTF-8")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        ok(False, f"no es UTF-8 válido: {e}")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"❌ XML mal formado: {e}")
        return 1
    ok(root.tag == NS + "urlset", f"raíz inesperada {root.tag}")
    # 2
    locs, hoy = [], dt.date.today()
    for u in root.findall(NS + "url"):
        loc = (u.findtext(NS + "loc") or "").strip()
        lm = (u.findtext(NS + "lastmod") or "").strip()
        locs.append(loc)
        ok(loc.startswith(SITE + "/"), f"loc no absoluta https del dominio: {loc}")
        ok(re.fullmatch(r"\d{4}-\d{2}-\d{2}", lm) is not None, f"lastmod raro en {loc}: «{lm}»")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", lm):
            ok(dt.date.fromisoformat(lm) <= hoy, f"lastmod futura en {loc}: {lm}")
        ok(u.find(NS + "priority") is None and u.find(NS + "changefreq") is None, f"priority/changefreq en {loc}")
    ok(len(locs) == len(set(locs)), "hay URLs duplicadas")
    ok(len(locs) <= 50000 and len(raw) <= 50 * 1024 * 1024, "supera los límites de 50.000 URLs / 50 MB")
    print(f"· {len(locs)} URLs en sitemap.xml, {len(raw)} bytes")
    # 3
    gen = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_sitemap.py"), "--stdout"],
                         capture_output=True, text=True, check=True).stdout
    ok(gen == raw.decode("utf-8", "replace"), "sitemap.xml no coincide con tools/gen_sitemap.py (regenéralo)")
    # 4
    pend = ROOT / "tools" / "sitemap_pendientes.txt"
    if pend.exists():
        for l in pend.read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if l and not l.startswith("#"):
                ok(f"{SITE}/{l}" not in locs, f"{l} está en sitemap_pendientes.txt y también en el sitemap")
    # 5 y 6
    if "--sin-red" not in sys.argv:
        with cf.ThreadPoolExecutor(8) as ex:
            for errs in ex.map(check_live, locs):
                fallos.extend(errs)
        code, _, robots = get(SITE + "/robots.txt")
        ok(code == 200 and re.search(r"(?mi)^Sitemap:\s*https://arquitectodigital\.io/sitemap\.xml\s*$", robots) is not None,
           "robots.txt publicado sin «Sitemap: https://arquitectodigital.io/sitemap.xml»")
        print(f"· comprobadas en vivo {len(locs)} URLs + robots.txt")
    else:
        print("· (sin red: no se comprueban 200/canonical/noindex en vivo)")

    if fallos:
        print(f"❌ {len(fallos)} fallo(s):")
        for f in fallos:
            print("   -", f)
        return 1
    print("✅ sitemap OK: XML válido UTF-8, URLs absolutas https sin duplicados, lastmod de git, "
          "sin priority/changefreq, al día con el generador, todas 200 + canonical = loc + indexables, robots.txt con Sitemap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
