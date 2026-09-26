#!/usr/bin/env python3
"""Rellena los huecos de parciales en las páginas HTML del sitio.

Una página declara un hueco así:

    <!-- PARTIAL:footer -->
    ...lo que haya aquí se REEMPLAZA con partials/footer.html...
    <!-- /PARTIAL:footer -->

Con extras (se insertan en el <!-- SLOT:extra --> del parcial):

    <!-- PARTIAL:footer +footer-home-extra -->
    ...
    <!-- /PARTIAL:footer -->

Garantías:
  - Solo se reescribe lo que hay ENTRE los marcadores. El resto del fichero
    se comprueba byte a byte antes de escribir; si difiriera, no se escribe.
  - Idempotente: una segunda pasada no cambia nada.
  - Las páginas sin marcadores se ignoran.
  - Cualquier error en una página (marcador sin cerrar, anidado, parcial
    inexistente) deja esa página intacta y hace que el script salga con 1.

Uso:
    python3 tools/sync_partials.py --dry-run      # enseña el diff, no escribe
    python3 tools/sync_partials.py                # escribe
    python3 tools/sync_partials.py --check        # sale 1 si algo está desincronizado
    python3 tools/sync_partials.py index.html ... # limita a esas páginas
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTIALS_DIR = ROOT / "partials"
SKIP_DIRS = {".git", "partials", "tools", "node_modules"}

NAME = r"[a-z0-9][a-z0-9-]*"
OPEN_RE = re.compile(rf"<!-- PARTIAL:({NAME})((?:\s+\+{NAME})*)\s*-->")
CLOSE_RE = re.compile(rf"<!-- /PARTIAL:({NAME}) -->")
ANY_MARKER_RE = re.compile(rf"<!-- /?PARTIAL:{NAME}")
SLOT = "<!-- SLOT:extra -->"


class SyncError(Exception):
    pass


def load_partial(name: str) -> str:
    path = PARTIALS_DIR / f"{name}.html"
    if not path.is_file():
        raise SyncError(f"parcial inexistente: partials/{name}.html")
    text = path.read_text(encoding="utf-8")
    if ANY_MARKER_RE.search(text):
        raise SyncError(f"partials/{name}.html contiene marcadores PARTIAL (anidado no permitido)")
    return text.rstrip("\n")


def render(name: str, extras: list[str]) -> str:
    body = load_partial(name)
    if SLOT in body:
        fill = "\n".join(load_partial(e) for e in extras)
        # La línea del SLOT desaparece entera si no hay extras.
        body = re.sub(rf"[ \t]*{re.escape(SLOT)}\n?",
                      (fill + "\n") if fill else "", body, count=1)
    elif extras:
        raise SyncError(f"partials/{name}.html no tiene {SLOT} y se pidieron extras {extras}")
    return body


def find_blocks(text: str) -> list[tuple[int, int, str, list[str]]]:
    """Devuelve (inicio_contenido, fin_contenido, nombre, extras) por bloque."""
    blocks = []
    pos = 0
    while True:
        m_open = OPEN_RE.search(text, pos)
        stray_close = CLOSE_RE.search(text, pos)
        if m_open is None:
            if stray_close is not None:
                raise SyncError(f"cierre /PARTIAL:{stray_close.group(1)} sin apertura")
            return blocks
        if stray_close is not None and stray_close.start() < m_open.start():
            raise SyncError(f"cierre /PARTIAL:{stray_close.group(1)} sin apertura")
        name = m_open.group(1)
        extras = re.findall(rf"\+({NAME})", m_open.group(2))
        m_close = CLOSE_RE.search(text, m_open.end())
        if m_close is None:
            raise SyncError(f"PARTIAL:{name} sin cierre")
        if m_close.group(1) != name:
            raise SyncError(f"PARTIAL:{name} cerrado con /PARTIAL:{m_close.group(1)}")
        inner_open = OPEN_RE.search(text, m_open.end(), m_close.start())
        if inner_open is not None:
            raise SyncError(f"PARTIAL:{inner_open.group(1)} anidado dentro de PARTIAL:{name}")
        blocks.append((m_open.end(), m_close.start(), name, extras))
        pos = m_close.end()


def sync_text(text: str) -> str:
    blocks = find_blocks(text)
    if not blocks:
        return text
    out, last = [], 0
    for start, end, name, extras in blocks:
        out.append(text[last:start])
        out.append("\n" + render(name, extras) + "\n")
        last = end
    out.append(text[last:])
    new = "".join(out)
    if _outside(text, blocks) != _outside(new, find_blocks(new)):
        raise SyncError("el contenido fuera de los marcadores cambiaría (abortado)")
    return new


def _outside(text: str, blocks) -> list[str]:
    parts, last = [], 0
    for start, end, _, _ in blocks:
        parts.append(text[last:start])
        last = end
    parts.append(text[last:])
    return parts


def iter_pages(args_paths: list[str]):
    if args_paths:
        for p in args_paths:
            yield (ROOT / p).resolve()
        return
    for path in sorted(ROOT.rglob("*.html")):
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            yield path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", help="páginas concretas (relativas a la raíz)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="enseña el diff sin escribir")
    mode.add_argument("--check", action="store_true", help="sale 1 si hay algo desincronizado")
    args = ap.parse_args()

    changed, errors, with_markers = [], [], 0
    for path in iter_pages(args.paths):
        rel = path.relative_to(ROOT)
        try:
            old = path.read_text(encoding="utf-8")
            if not OPEN_RE.search(old) and not CLOSE_RE.search(old):
                continue
            with_markers += 1
            new = sync_text(old)
        except (SyncError, OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: {exc}")
            continue
        if new == old:
            continue
        changed.append(str(rel))
        if args.dry_run:
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=f"a/{rel}", tofile=f"b/{rel}"))
        elif not args.check:
            path.write_text(new, encoding="utf-8")

    verb = "cambiarían" if (args.dry_run or args.check) else "actualizadas"
    print(f"\n[sync_partials] páginas con marcadores: {with_markers} · {verb}: {len(changed)}"
          f" · errores: {len(errors)}", file=sys.stderr)
    for rel in changed:
        print(f"  ~ {rel}", file=sys.stderr)
    for err in errors:
        print(f"  ✗ {err}", file=sys.stderr)
    if errors or (args.check and changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
