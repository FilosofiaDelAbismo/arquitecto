#!/usr/bin/env python3
"""Genera sitemap.xml a partir de las páginas HTML versionadas en git.

Entra una página si:
  - está en git (git ls-files) y es .html,
  - no está en tools/ ni partials/ ni empieza por «_» (Jekyll no las sirve),
  - tiene <link rel="canonical"> que apunta a su propia URL,
  - no tiene <meta name="robots"> con noindex,
  - no está en tools/sitemap_pendientes.txt (páginas que decide Daniel cuándo entran).

<lastmod> = fecha del último commit de la historia principal (--first-parent)
que tocó ese fichero, es decir, cuándo cambió su contenido en main; no la
fecha del build. Sin priority ni changefreq (Google los ignora).

Uso (desde la raíz del repo):
    python3 tools/gen_sitemap.py            # escribe sitemap.xml
    python3 tools/gen_sitemap.py --check    # sale 1 si sitemap.xml no está al día
    python3 tools/gen_sitemap.py --stdout   # lo imprime sin escribir
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://arquitectodigital.io"
ROOT = Path(__file__).resolve().parent.parent
PENDIENTES = ROOT / "tools" / "sitemap_pendientes.txt"
EXCLUIR_DIRS = ("tools/", "partials/")

RE_CANON = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]*>', re.I)
RE_ROBOTS = re.compile(r'<meta[^>]+name=["\']robots["\'][^>]*>', re.I)
RE_HREF = re.compile(r'href=["\']([^"\']+)', re.I)
RE_CONTENT = re.compile(r'content=["\']([^"\']+)', re.I)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout


def url_de(path: str) -> str:
    if path == "index.html":
        return SITE + "/"
    if path.endswith("/index.html"):
        return f"{SITE}/{path[:-len('index.html')]}"
    return f"{SITE}/{path}"


def pendientes() -> set[str]:
    if not PENDIENTES.exists():
        return set()
    return {l.strip() for l in PENDIENTES.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("#")}


def entradas() -> list[tuple[str, str]]:
    pend = pendientes()
    out = []
    for path in git("ls-files", "*.html").splitlines():
        if path.startswith(EXCLUIR_DIRS) or any(p.startswith("_") for p in path.split("/")):
            continue
        if path in pend:
            continue
        html = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        m = RE_CANON.search(html)
        canon = RE_HREF.search(m.group(0)).group(1) if m and RE_HREF.search(m.group(0)) else ""
        url = url_de(path)
        if canon != url:
            continue
        m = RE_ROBOTS.search(html)
        if m and RE_CONTENT.search(m.group(0)) and "noindex" in RE_CONTENT.search(m.group(0)).group(1).lower():
            continue
        lastmod = git("log", "-1", "--first-parent", "--format=%cs", "--", path).strip()
        if not lastmod:
            sys.exit(f"ERROR: {path} no tiene commits; haz commit antes de generar el sitemap")
        out.append((url, lastmod))
    # Home primero, después por URL: orden estable para que el diff sea legible.
    out.sort(key=lambda e: (e[0] != SITE + "/", e[0]))
    return out


def render(ents: list[tuple[str, str]]) -> str:
    lineas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, lastmod in ents:
        lineas += ["  <url>", f"    <loc>{escape(url)}</loc>", f"    <lastmod>{lastmod}</lastmod>", "  </url>"]
    lineas.append("</urlset>")
    return "\n".join(lineas) + "\n"


def main() -> int:
    xml = render(entradas())
    destino = ROOT / "sitemap.xml"
    if "--stdout" in sys.argv:
        sys.stdout.write(xml)
        return 0
    if "--check" in sys.argv:
        actual = destino.read_text(encoding="utf-8") if destino.exists() else ""
        if actual != xml:
            print("sitemap.xml NO está al día (ejecuta: python3 tools/gen_sitemap.py)")
            return 1
        print("sitemap.xml al día")
        return 0
    destino.write_text(xml, encoding="utf-8")
    print(f"sitemap.xml escrito: {xml.count('<loc>')} URLs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
