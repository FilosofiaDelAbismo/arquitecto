#!/usr/bin/env python3
"""Test GEO de la web (local, sin red). 2026-11-07.

Comprueba en los ficheros del repo:
  1. Portada: <title>, meta description, og:site_name; JSON-LD válido con
     WebSite «Arquitecto Digital» y ProfessionalService con todos los campos;
     dirección SOLO localidad/provincia/país (sin calle, CP ni NIF).
  2. Enlace a la ficha de Google en contacto y en el pie de TODAS las páginas
     con pie común, en pestaña nueva y rel="noopener".
  3. Páginas legales: noindex y fuera del sitemap.
  4. Ninguna página fuera de las legales con la calle o el NIF.
  5. llms.txt / llms-full.txt: servicios, zonas, horario, contacto, ficha;
     sin Reforma SEO ni auditoría gratis; «sin versión impresa» intacta.
  6. og:site_name = «Arquitecto Digital» en todas las páginas que lo llevan.

Uso:
  python3 tools/test_geo_web.py            # rama: admite el marcador de la ficha
  python3 tools/test_geo_web.py --publicar # exige el enlace real de la ficha
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARCA = "__ENLACE_FICHA_GOOGLE__"
FICHA_RE = re.compile(r"^https://(g\.page|maps\.app\.goo\.gl|goo\.gl/maps|share\.google|www\.google\.com/maps|maps\.google\.com|g\.co/kgs|business\.google\.com)/[^\s\"'<>]+$")
REDES = ["https://www.instagram.com/arquitecto.digital/",
         "https://www.facebook.com/profile.php?id=61575581849782",
         "https://www.linkedin.com/in/daniel-arquitecto-digital-b08696411/"]
CIUDADES = {"El Puerto de Santa María", "Cádiz", "Jerez de la Frontera", "Chiclana de la Frontera"}
LEGALES = ["aviso-legal", "privacidad", "cookies", "condiciones", "audio-libro-condiciones",
           "autoblog-condiciones", "chatbot-condiciones", "crea-tu-cancion-condiciones",
           "girobot-condiciones", "sistemas-condiciones", "webs-condiciones", "cenit-condiciones",
           "cenit-uso", "cenit-privacidad", "cenit-pioneros-bases", "privacidad-pinterest",
           "cenit/legal/privacidad", "cenit/legal/terminos"]
# Páginas no legales que llevan un aviso de privacidad con la dirección postal
# (noindex, nofollow, fuera del sitemap). Se informan, no se tocan.
CON_AVISO_PRIVACIDAD = {"cenit/p-1e09b29040534a0b.html"}
CALLE_NIF = re.compile(r"C/\s*Chile|Calle\s+Chile|45326983", re.I)

fallos: list[str] = []
publicar = "--publicar" in sys.argv


def falla(msg: str) -> None:
    fallos.append(msg)


def leer(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def tracked_html() -> list[str]:
    out = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "*.html"], text=True)
    return [f for f in out.split() if not f.startswith(("partials/", "tools/")) and ".bak" not in f]


def ficha_ok(url: str) -> bool:
    if url == MARCA:
        return not publicar
    return bool(FICHA_RE.match(url))


# 1. Portada ───────────────────────────────────────────────────────────
idx = leer("index.html")
m = re.search(r"<title>([^<]*)</title>", idx)
titulo = m.group(1) if m else ""
for palabra in ("Arquitecto Digital", "Diseño web", "chatbots", "IA", "El Puerto", "Cádiz"):
    if palabra not in titulo:
        falla(f"portada: el <title> no dice «{palabra}»: {titulo!r}")
if len(titulo) > 70:
    falla(f"portada: <title> de {len(titulo)} caracteres (> 70)")
m = re.search(r'<meta name="description" content="([^"]*)"', idx)
desc = m.group(1) if m else ""
for palabra in ("Diseño web", "chatbots", "El Puerto de Santa María", "Cádiz"):
    if palabra not in desc:
        falla(f"portada: la description no dice «{palabra}»")
if not 70 <= len(desc) <= 160:
    falla(f"portada: description de {len(desc)} caracteres (fuera de 70-160)")
if re.search(r"\b(obras?|reformas?)\b", titulo + " " + desc, re.I):
    falla("portada: title/description mencionan obras/reformas")

bloques = re.findall(r'<script type="application/ld\+json">(.*?)</script>', idx, re.S)
items: list[dict] = []
for b in bloques:
    try:
        d = json.loads(b)
    except json.JSONDecodeError as e:
        falla(f"portada: JSON-LD inválido: {e}")
        continue
    items += d.get("@graph", [d]) if isinstance(d, dict) else d
    if CALLE_NIF.search(b) or re.search(r'"(streetAddress|postalCode|taxID|vatID)"', b):
        falla("portada: el JSON-LD lleva calle, CP o NIF")


def tipos(it: dict) -> set:
    t = it.get("@type", [])
    return set(t if isinstance(t, list) else [t])


web = [i for i in items if "WebSite" in tipos(i)]
neg = [i for i in items if tipos(i) & {"ProfessionalService", "LocalBusiness"}]
if len(web) != 1 or web[0].get("name") != "Arquitecto Digital":
    falla(f"portada: WebSite.name debe ser «Arquitecto Digital» (hay {[w.get('name') for w in web]})")
if len(neg) != 1:
    falla(f"portada: debe haber 1 ProfessionalService/LocalBusiness (hay {len(neg)})")
else:
    n = neg[0]
    for campo in ("name", "description", "telephone", "email", "url", "logo", "areaServed",
                  "openingHoursSpecification", "sameAs", "knowsAbout", "address"):
        if not n.get(campo):
            falla(f"portada: ProfessionalService sin «{campo}»")
    if n.get("name") != "Arquitecto Digital":
        falla("portada: ProfessionalService.name ≠ Arquitecto Digital")
    for k in ("diseño web", "chatbots con ia", "blogs automáticos con ia", "sistemas de ia a medida", "cursos de ia"):
        if k not in n.get("description", "").lower():
            falla(f"portada: description del negocio sin «{k}»")
    if n.get("telephone") != "+34 743 08 86 55" or n.get("email") != "daniel@arquitectodigital.io":
        falla("portada: teléfono o email del negocio no coinciden con la ficha")
    if n.get("url") != "https://arquitectodigital.io/":
        falla("portada: url del negocio")
    ad = n.get("address", {})
    if ad != {"@type": "PostalAddress", "addressLocality": "El Puerto de Santa María",
              "addressRegion": "Cádiz", "addressCountry": "ES"}:
        falla(f"portada: address debe ser SOLO localidad/provincia/país: {ad}")
    ciudades = {a.get("name") for a in n.get("areaServed", []) if isinstance(a, dict)}
    if ciudades != CIUDADES:
        falla(f"portada: areaServed {sorted(ciudades)} ≠ {sorted(CIUDADES)}")
    horas = sorted((h.get("opens"), h.get("closes"), tuple(h.get("dayOfWeek", [])))
                   for h in n.get("openingHoursSpecification", []))
    lv = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    if horas != [("11:00", "15:00", lv), ("17:00", "21:00", lv)]:
        falla(f"portada: openingHoursSpecification no es L-V 11-15 y 17-21: {horas}")
    same = n.get("sameAs", [])
    for r in REDES:
        if r not in same:
            falla(f"portada: sameAs sin {r}")
    fichas = [u for u in same if u == MARCA or FICHA_RE.match(u)]
    if len(fichas) != 1 or not ficha_ok(fichas[0]):
        falla(f"portada: sameAs sin enlace válido a la ficha de Google ({fichas})")
if CALLE_NIF.search(idx):
    falla("portada: aparece la calle o el NIF")

# 2. Enlace a la ficha (contacto + pie) ──────────────────────────────────
A_FICHA = re.compile(r'<a href="([^"]+)" target="_blank" rel="noopener"[^>]*>Ver Arquitecto Digital en Google</a>')
contacto = idx[idx.find('<section id="contacto"'):idx.find("</section>", idx.find('<section id="contacto"'))]
if not any(ficha_ok(u) for u in A_FICHA.findall(contacto)):
    falla("portada: falta el enlace a la ficha en la zona de contacto")
paginas = tracked_html()
con_pie = [f for f in paginas if "<!-- PARTIAL:footer" in leer(f)]
sin = [f for f in con_pie if not any(ficha_ok(u) for u in
       A_FICHA.findall(leer(f)[leer(f).find("<!-- PARTIAL:footer"):]))]
if sin:
    falla(f"pie: {len(sin)} páginas sin enlace a la ficha: {sin[:5]}")
quedan_marcas = [f for f in paginas + ["llms.txt", "llms-full.txt"] if MARCA in leer(f)]
if publicar and quedan_marcas:
    falla(f"queda el marcador {MARCA} en {len(quedan_marcas)} ficheros: pon el enlace real de la ficha")

# 3. Legales: noindex y fuera del sitemap ───────────────────────────────
sitemap = leer("sitemap.xml")
for lg in LEGALES:
    t = leer(lg + ".html")
    m = re.search(r'<meta name="robots" content="([^"]*)"', t)
    if not m or "noindex" not in m.group(1).replace(" ", "").split(","):
        falla(f"legal {lg}.html sin noindex")
    if f"/{lg}.html<" in sitemap:
        falla(f"legal {lg}.html está en el sitemap")

# 4. Calle/NIF fuera de las legales ────────────────────────────────────
legal_set = {lg + ".html" for lg in LEGALES} | CON_AVISO_PRIVACIDAD
for f in paginas + ["llms.txt", "llms-full.txt", "robots.txt"]:
    if f not in legal_set and CALLE_NIF.search(leer(f)):
        falla(f"{f}: lleva la calle o el NIF y no es página legal")

# 5. llms ───────────────────────────────────────────────────────────────
for fn in ("llms.txt", "llms-full.txt"):
    t = leer(fn)
    for k in ("Chatbot", "Sprint", "41", "954", "2.650", "250", "529", "849", "158", "84",
              "79,99", "149,99", "299,99", "15", "29,99", "GiroBot", "1.200", "Junior IA", "Senior IA",
              "daniel@arquitectodigital.io", "743 08 86 55", "11:00 a 15:00", "17:00 a 21:00",
              "Jerez de la Frontera", "Chiclana de la Frontera", "Ficha de Google"):
        if k not in t:
            falla(f"{fn}: falta «{k}»")
    if re.search(r"reforma\s*seo|auditor[ií]a[^.\n]{0,40}grat|grat[^.\n]{0,40}auditor", t, re.I):
        falla(f"{fn}: menciona Reforma SEO o auditoría gratis")
if "la entrega de Audio a Libro es 100% digital, sin versión impresa" not in leer("llms-full.txt"):
    falla("llms-full.txt: ha cambiado la línea «sin versión impresa»")

# 6. og:site_name ───────────────────────────────────────────────────────
for f in paginas:
    for v in re.findall(r'og:site_name"\s+content="([^"]*)"', leer(f)):
        if v != "Arquitecto Digital":
            falla(f"{f}: og:site_name = {v!r}")

print(f"· portada: title {len(titulo)} car. · description {len(desc)} car. · {len(bloques)} bloques JSON-LD")
print(f"· pie común en {len(con_pie)} páginas · {len(LEGALES)} legales · marcador de ficha en "
      f"{len(quedan_marcas)} ficheros ({'NO admitido' if publicar else 'admitido en la rama'})")
if fallos:
    print(f"❌ {len(fallos)} fallo(s):")
    for x in fallos:
        print("   -", x)
    sys.exit(1)
print("✅ GEO web OK")
