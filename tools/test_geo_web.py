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
  7. Decisiones del 07-11: banner de Cénit debajo del H1 y del párrafo principal;
     sin «Cénit · Cénit» en los <title>; newsletter apagada (noindex, fuera del
     sitemap, sin enlaces a la página de alta en ninguna página salvo la
     redirección newsletter.html, formulario sin envío); GiroBot con sus 4
     módulos (chatbot, clips 9:16, publicador en TikTok y alertas con voz) en
     portada, girobot, portfolio y llms, y en girobot.html las alertas en directo
     y el lector de voz del chat en los 3 planes.
  8. Flecos del 07-11: solo España (ni UE/Europa/LATAM como ámbito ni «fuera de
     España… caso por caso» fuera de legales y posts); GiroBot «todo en uno» (sin
     3-en-1 / tres en uno / tres servicios distintos fuera de los posts); ningún
     «200 clips» (UNLIMITED = hasta 50 clips/día en el plan, la oferta JSON-LD y
     llms-full); portada con priceRange «€€» y postalCode 11500 (sigue prohibido
     streetAddress, la calle y el NIF).
  9. Dudas del 07-11 (respuestas de Daniel): el SSL va incluido en el precio de la
     web (nada de «SSL va en el mantenimiento»; FAQ visible y JSON-LD y llms-full lo
     incluyen); Audio a Libro sí reescribe en prosa literaria (nada de «no
     reescribimos» / «se limita a transcribir» donde se describe); Audio a Libro
     solo para particulares (hero, JSON-LD Service, llms; sin empresas, autónomos,
     «Profesionales que dictan» ni lead magnet); Cénit sin licencia vitalicia (ni
     «vitalicia», «de por vida» ni «lifetime» fuera de legales, posts incluidos) y
     con «licencia de 1 año» y «sin suscripción ni renovación automática».
 10. Cierre del 07-11: Audio a Libro por plan (manda ramas/audio_book/config.py
     PLAN_REFINEMENT_STYLE): los TRES planes reescriben; Ebook estilo neutro, Libro
     prosa literaria, Libro Premium prosa literaria cuidada (tarjetas, ofertas JSON-LD,
     llms.txt, llms-full y el post del 28-08, que ya no dice «no se reescribe» ni «el
     tratamiento es el mismo»). Mantenimiento web (250 €/año) = dominio, servidor,
     mantenimiento y RGPD; el SSL en el precio de la web, no en el mantenimiento.

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
TITULO = "Arquitecto Digital · Webs, chatbots e IA en El Puerto de Santa María"
if titulo != TITULO:
    falla(f"portada: <title> {titulo!r} ≠ {TITULO!r}")
m = re.search(r'<meta property="og:title" content="([^"]*)"', idx)
if not m or m.group(1) != TITULO:
    falla(f"portada: og:title ≠ <title> ({m.group(1) if m else None!r})")
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
    if CALLE_NIF.search(b) or re.search(r'"(streetAddress|taxID|vatID)"', b):
        falla("portada: el JSON-LD lleva calle o NIF")


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
              "postalCode": "11500", "addressRegion": "Cádiz", "addressCountry": "ES"}:
        falla(f"portada: address debe ser SOLO localidad, CP 11500, provincia y país: {ad}")
    if n.get("priceRange") != "€€":
        falla(f"portada: ProfessionalService.priceRange debe ser «€€» ({n.get('priceRange')!r})")
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

# 7. Decisiones del 07-11 ───────────────────────────────────────────────
h1, sub, ban = idx.find("<h1"), idx.find('class="hero-sub"'), idx.find('class="cenit-banner')
if not (0 <= h1 < sub < ban):
    falla("portada: el banner de Cénit no está debajo del H1 y del párrafo principal")
for f in paginas:
    t = leer(f)
    if "<!-- PARTIAL:cenit-badge" in t and not (0 <= t.find("<h1") < t.find("<!-- PARTIAL:cenit-badge")):
        falla(f"{f}: el banner de Cénit va antes del H1")
    m = re.search(r"<title>([^<]*)</title>", t)
    if m and re.search(r"Cénit · (App Cénit · )?Cénit ·|App Cénit · Cénit ·", m.group(1)):
        falla(f"{f}: <title> con Cénit repetido: {m.group(1)!r}")
nl = leer("newsletter-signup.html")
m = re.search(r'<meta name="robots" content="([^"]*)"', nl)
if not m or "noindex" not in m.group(1):
    falla("newsletter-signup.html sin noindex")
if "/newsletter-signup.html<" in sitemap:
    falla("newsletter-signup.html está en el sitemap")
if "ALTAS_ABIERTAS = false" not in nl or 'class="form-submit" disabled' not in nl:
    falla("newsletter-signup.html: el formulario no está apagado")
if "newsletter-signup" in idx or 'id="newsletter"' in idx:
    falla("portada: sigue enlazando la newsletter o tiene la sección [07]")
if "newsletter-signup" in leer("partials/footer.html"):
    falla("pie: sigue enlazando la newsletter")
A_ALTA = re.compile(r'href="[^"]*newsletter-signup\.html')
con_alta = [f for f in paginas if f not in ("newsletter.html", "newsletter-signup.html")
            and A_ALTA.search(leer(f))]
if con_alta:
    falla(f"siguen enlazando la página de alta de la newsletter: {con_alta}")
# GiroBot: los 4 módulos en cada sitio donde se describe
MODULOS = {"chatbot": re.compile(r"chatbot", re.I),
           "clips 9:16": re.compile(r"9:16|1080×1920", re.I),
           "publicador en TikTok": re.compile(r"publicador automático[^.]{0,60}TikTok", re.I),
           "alertas con voz": re.compile(r"alertas (con voz|en directo)", re.I)}
def bloque_girobot(f: str) -> str:
    t = leer(f)
    if f == "index.html":
        i = t.find('aria-label="Ver detalles de GiroBot'); return t[i:t.find('class="service-cta"', i)]
    if f == "portfolio.html":
        i = t.find('aria-label="Ver GiroBot'); return t[i:t.find("</p>", i)]
    if f == "llms.txt":
        return next(l for l in t.splitlines() if l.startswith("- [GiroBot"))
    if f == "llms-full.txt":
        i = t.find("## GiroBot"); return t[i:t.find("\n## ", i + 5)]
    return t
for f in ["index.html", "portfolio.html", "llms.txt", "llms-full.txt", "girobot.html"]:
    b = bloque_girobot(f)
    falta = [m for m, rx in MODULOS.items() if not rx.search(b)]
    if falta:
        falla(f"{f}: GiroBot sin {falta}")
gb = leer("girobot.html")
planes = re.findall(r'<ul class="gb-feats">(.*?)</ul>', gb, re.S)
for linea in ["Alertas en directo (subs, bits, raids, follows)", "Lector de voz del chat incluido (activable)",
              "Publicador automático en TikTok (opcional)"]:
    if len(planes) != 3 or not all(linea in pl for pl in planes):
        falla(f"girobot.html: «{linea}» no está en los 3 planes")
app = [d for bl in re.findall(r'<script type="application/ld\+json">(.*?)</script>', gb, re.S)
       for d in [json.loads(bl)] if isinstance(d, dict) and d.get("@type") == "SoftwareApplication"]
if len(app) != 1:
    falla(f"girobot.html: {len(app)} bloques JSON-LD SoftwareApplication (se espera 1)")
for d in app:
    txt = json.dumps(d, ensure_ascii=False)
    falta = [m for m, rx in MODULOS.items() if not rx.search(txt)]
    if falta:
        falla(f"girobot.html JSON-LD SoftwareApplication sin {falta}")

# 8. Flecos del 07-11 ───────────────────────────────────────────────────
# a) Solo España: ni UE/Europa/LATAM como ámbito de servicio ni «fuera de España… caso por caso»,
#    en ninguna página no legal ni en llms*. Fuera: el texto legal (RGPD, transferencias) y los posts del blog
#    (artículos con fecha; hablan del RGPD en la UE/LATAM, no del ámbito del servicio).
AMBITO = re.compile(
    r"\b(para|en|a|desde España para|clientes de|clientes en)\s+(toda\s+)?(la\s+)?"
    r"(UE|Uni[oó]n Europea|Europa|LATAM|Latinoam[eé]rica|Am[eé]rica Latina|Hispanoam[eé]rica)\b"
    r"|\b(trabaj\w+|atiend\w+|ofrec\w+|vend\w+|disponible)\b[^.\n<]{0,40}\b(internacional\w*|fuera de Espa[ñn]a)\b"
    r"|fuera de Espa[ñn]a[^.\n<]{0,120}(caso por caso|lo vemos)|¿El tuyo está fuera\?", re.I)
for f in paginas + ["llms.txt", "llms-full.txt"]:
    if f in legal_set or f.startswith("blog/"):
        continue
    for m in AMBITO.finditer(leer(f)):
        falla(f"{f}: ámbito fuera de España: «{m.group(0)}»")
# b) GiroBot «todo en uno»: sin 3-en-1 / tres en uno / tres servicios distintos fuera de los posts,
#    ni «tres herramientas» en lo que describe GiroBot (se ignoran los enlaces a los posts, que llevan su título).
TRES = re.compile(r"3[- ]en[- ]1|tres[- ]en[- ]uno|tres servicios distintos", re.I)
for f in paginas + ["llms.txt", "llms-full.txt"]:
    if f.startswith("blog/") or f in legal_set:
        continue
    for m in TRES.finditer(leer(f)):
        falla(f"{f}: «{m.group(0)}» (GiroBot es «todo en uno»)")
for f in ["index.html", "portfolio.html", "llms.txt", "llms-full.txt", "girobot.html"]:
    b = re.sub(r'<a href="/blog/[^"]*"[^>]*>[^<]*</a>', "", bloque_girobot(f))
    if re.search(r"tres herramientas|incluye tres", b, re.I):
        falla(f"{f}: GiroBot descrito como «tres herramientas»")
# c) UNLIMITED = hasta 50 clips/día (ramas/twitch/tiers.py)
for f in paginas + ["llms.txt", "llms-full.txt"]:
    if re.search(r"\b200\s*clips", leer(f), re.I):
        falla(f"{f}: dice «200 clips» (UNLIMITED = 50 clips/día)")
if len(planes) == 3 and "hasta 50 clips/día" not in planes[2]:
    falla("girobot.html: el plan UNLIMITED no dice «hasta 50 clips/día»")
of_unl = [o for d in app for o in d.get("offers", []) if "UNLIMITED" in o.get("name", "")]
if len(of_unl) != 1 or "hasta 50 clips/día" not in of_unl[0].get("description", ""):
    falla("girobot.html JSON-LD: la oferta UNLIMITED no dice «hasta 50 clips/día»")
if "hasta 50 clips/día en UNLIMITED" not in leer("llms-full.txt"):
    falla("llms-full.txt: falta «hasta 50 clips/día en UNLIMITED»")

# 9. Dudas del 07-11 (respuestas de Daniel) ─────────────────────────────
# Mismo alcance que la sección 8: páginas no legales y llms*; los posts del blog se excluyen
# (artículos con fecha; el de Audio a Libro del 28-08 se vigila en la sección 10).
no_legal = [f for f in paginas + ["llms.txt", "llms-full.txt"] if f not in legal_set and not f.startswith("blog/")]
# a) Webs: el certificado SSL va INCLUIDO en el precio de la web (no «en el mantenimiento»).
SSL_MANT = re.compile(r"SSL\s+(va|van)\s+en\s+el\s+mantenimiento", re.I)
for f in no_legal:
    for m in SSL_MANT.finditer(leer(f)):
        falla(f"{f}: «{m.group(0)}» (el SSL va incluido en el precio de la web)")
w = leer("webs.html")
faq_precio = re.findall(r"¿Qué incluye y qué no incluye el precio\?.{0,400}?Incluye ([^.]*)\.", w, re.S)
if len(faq_precio) != 2 or not all("certificado SSL" in x for x in faq_precio):
    falla("webs.html: la FAQ «¿Qué incluye… el precio?» (visible y JSON-LD) no incluye el certificado SSL")
if not re.search(r"Incluye: diseño, desarrollo, deploy, conexión de dominio,\s+certificado SSL", w):
    falla("webs.html: «Qué incluye y qué no» ya no dice certificado SSL")
if "Incluye diseño, desarrollo, deploy, conexión de dominio, certificado SSL" not in leer("llms-full.txt"):
    falla("llms-full.txt: el precio de la web ya no incluye el certificado SSL")
# b) Audio a Libro SÍ reescribe en prosa literaria: nada que diga lo contrario.
NO_REESCRIBE = re.compile(r"no (se )?reescrib\w*|se limita a transcribir|convertido a texto y volcado|"
                          r"sin reescribir (tu|el) contenido", re.I)
for f in no_legal:
    t = leer(f)
    if f not in ("audio-libro.html", "llms.txt", "llms-full.txt", "index.html", "portfolio.html"):
        continue   # solo donde se describe Audio a Libro (en index «Sin reescribir.» es de sistemas)
    if f == "index.html":
        i = t.find("Convierte tus audios, podcasts"); t = t[max(0, i - 800):i + 800]
    for m in NO_REESCRIBE.finditer(t):
        falla(f"{f}: «{m.group(0)}» (Audio a Libro sí reescribe en prosa literaria)")
if "Prosa literaria" not in leer("audio-libro.html") or "prosa literaria" not in leer("llms-full.txt"):
    falla("audio-libro.html / llms-full.txt: ya no dicen «prosa literaria»")
# c) Audio a Libro es SOLO para particulares.
a = leer("audio-libro.html")
srv = json.loads(re.search(r'<script type="application/ld\+json">\s*(\{\s*"@context"[^<]*?"@type": "Service".*?)</script>',
                           a, re.S).group(1))
if "Solo para particulares" not in srv.get("description", ""):
    falla("audio-libro.html JSON-LD Service: la description no dice «Solo para particulares»")
hero = a[a.find('class="page-hero"'):a.find("</section>", a.find('class="page-hero"'))]
if "Solo para particulares" not in hero:
    falla("audio-libro.html: el hero no dice «Solo para particulares»")
AUDIO_EMPRESA = re.compile(r"empresas?\b|autónomos?\b|Profesionales que dictan|lead magnet|\bpymes?\b", re.I)
cuerpo = re.sub(r"<!-- PARTIAL:(header|footer) -->.*?<!-- /PARTIAL:\1 -->", "", a, flags=re.S)
for m in AUDIO_EMPRESA.finditer(cuerpo):
    falla(f"audio-libro.html: «{m.group(0)}» (Audio a Libro es solo para particulares)")
lf = leer("llms-full.txt")
sec_audio = lf[lf.find("## Audio → Libro"):lf.find("\n## ", lf.find("## Audio → Libro") + 5)]
if "Solo para particulares" not in sec_audio:
    falla("llms-full.txt: la sección de Audio → Libro no dice «Solo para particulares»")
for m in AUDIO_EMPRESA.finditer(sec_audio):
    falla(f"llms-full.txt (Audio → Libro): «{m.group(0)}» (solo para particulares)")
l1 = [x for x in leer("llms.txt").splitlines() if "audio-libro.html" in x]
if len(l1) != 1 or "Para particulares" not in l1[0]:
    falla("llms.txt: la línea de Audio → Libro no dice «Para particulares»")
# e) Cénit: NO hay licencia vitalicia. Versión gratis + Cénit Pro, 1 año de uso, 29,99 €, sin renovación automática.
VITALICIA = re.compile(r"vitalici\w*|de por vida|lifetime", re.I)
for f in no_legal + [p for p in paginas if p.startswith("blog/")]:
    for m in VITALICIA.finditer(leer(f)):
        falla(f"{f}: «{m.group(0)}» (Cénit no tiene licencia vitalicia)")
c = leer("cenit/index.html")
for need in ["Cénit Pro · licencia de 1 año, pago único", "29,99€", "sin suscripción ni renovación automática"]:
    if need not in c:
        falla(f"cenit/index.html: falta «{need}»")
for need in ["Cénit Pro · licencia de 1 año, pago único: 29,99 €", "sin suscripción ni renovación automática"]:
    if need not in lf:
        falla(f"llms-full.txt: falta «{need}»")

# 10. Cierre del 07-11 ───────────────────────────────────────────────────
# a) Audio a Libro por plan: los 3 reescriben; neutral / literary / literary_plus (config.py).
ESTILO = {"Ebook": "estilo neutro", "Libro": "prosa literaria", "Libro Premium": "prosa literaria cuidada"}
tarjetas = dict(re.findall(r'<h3 class="service-title">([^<]+)</h3>(.*?)</ul>', a, re.S))
ofertas = {o.get("name"): o.get("description", "") for o in srv.get("offers", [])}
lineas_lf = {m.group(1): m.group(0) for m in re.finditer(r"^- (Ebook|Libro|Libro Premium): .*$", sec_audio, re.M)}
for plan, estilo in ESTILO.items():
    for donde, txt in (("audio-libro.html tarjeta", tarjetas.get(plan, "")),
                       ("audio-libro.html JSON-LD oferta", ofertas.get(plan, "")),
                       ("llms-full.txt", lineas_lf.get(plan, ""))):
        low = txt.lower()
        if estilo not in low:
            falla(f"{donde} «{plan}»: no dice «{estilo}»")
        if plan == "Ebook" and "prosa literaria" in low:
            falla(f"{donde} «Ebook»: dice «prosa literaria» (el Ebook es estilo neutro)")
        if plan == "Libro" and "cuidada" in low:
            falla(f"{donde} «Libro»: dice «cuidada» (eso es Libro Premium)")
        if plan != "Ebook" and "neutro" in low:
            falla(f"{donde} «{plan}»: dice «neutro» (solo el Ebook)")
que_es = a[a.find("[01] Qué es"):a.find("</section>", a.find("[01] Qué es"))]
if "Los tres planes lo reescriben" not in que_es or "neutro en Ebook" not in que_es:
    falla("audio-libro.html [01] Qué es: no dice que los tres planes reescriben ni el estilo de cada uno")
if "Los tres planes reescriben lo que cuentas" not in sec_audio:
    falla("llms-full.txt (Audio → Libro): no dice «Los tres planes reescriben lo que cuentas»")
if len(l1) != 1 or not all(k in l1[0] for k in ("Los tres planes reescriben", "Ebook en estilo neutro",
                                                "Libro en prosa literaria", "Libro Premium en prosa literaria cuidada")):
    falla("llms.txt: la línea de Audio → Libro no dice que los tres planes reescriben ni el estilo de cada uno")
POST_AL = "blog/audio-a-libro-lo-que-el-servicio-no-20260828.html"
MISMO_TRATO = re.compile(r"tratamiento del audio es (el mismo|idéntico)|única diferencia entre (el plan )?Libro y "
                         r"(el plan )?Libro Premium|mejor procesada|no compra mejor tratamiento|"
                         r"con ambición literaria, no", re.I)
for f in no_legal + [POST_AL]:
    for m in MISMO_TRATO.finditer(leer(f)):
        falla(f"{f}: «{m.group(0)}» (cada plan tiene su estilo de prosa)")
pa = leer(POST_AL)
for m in NO_REESCRIBE.finditer(pa):
    falla(f"{POST_AL}: «{m.group(0)}» (Audio a Libro sí reescribe)")
faq_pa = re.findall(r"¿El libro se edita o se corrige\?.{0,200}?(Se reescribe en prosa[^<\"]*)", pa, re.S)
if len(faq_pa) != 2 or not all(all(e in x for e in ESTILO.values()) for x in faq_pa):
    falla(f"{POST_AL}: la FAQ «¿El libro se edita…?» (visible y JSON-LD) no da el estilo de los tres planes")
# b) Mantenimiento web (250 €/año) = dominio, servidor, mantenimiento y RGPD. El SSL, en el precio de la web.
MANT = "dominio, servidor, mantenimiento y RGPD"
SSL_PRECIO = "el SSL va incluido en el precio de la web, no en el mantenimiento"
MANT_SSL = re.compile(r"Hosting \+ dominio \+ SSL|hosting,? dominio y SSL|"
                      r"mantenimiento[^.;\n]{0,80}\b(cubre|incluye)\b[^.;\n]{0,60}\bSSL\b", re.I)
for f in no_legal:
    for m in MANT_SSL.finditer(leer(f)):
        falla(f"{f}: «{m.group(0)}» (el SSL va en el precio de la web, no en el mantenimiento)")
mw = re.search(r'<h3 class="service-title">Mantenimiento anual</h3>(.*?)</ul>', w, re.S)
if not mw or "<li>Dominio, servidor, mantenimiento y RGPD</li>" not in mw.group(1) or "SSL" in mw.group(1):
    falla("webs.html: la tarjeta del mantenimiento no dice «Dominio, servidor, mantenimiento y RGPD» (o lleva SSL)")
w2 = leer("webs.html")
if w2.count(f"incluye {MANT}; {SSL_PRECIO}") != 2:
    falla("webs.html: la FAQ del precio (visible y JSON-LD) no dice qué incluye el mantenimiento y dónde va el SSL")
cm = re.search(r"mantenimiento: \{(.*?)\}", leer("contratar.html"), re.S)
if not cm or '"Dominio, servidor, mantenimiento y RGPD"' not in cm.group(1) or "SSL" in cm.group(1):
    falla("contratar.html: el mantenimiento no incluye «Dominio, servidor, mantenimiento y RGPD» (o lleva SSL)")
lw = [x for x in leer("llms.txt").splitlines() if "webs.html" in x]
if len(lw) != 1 or f"incluye {MANT}" not in lw[0] or SSL_PRECIO not in lw[0]:
    falla("llms.txt: la línea de webs no dice qué incluye el mantenimiento y dónde va el SSL")
if f"incluye {MANT}; {SSL_PRECIO}" not in lf:
    falla("llms-full.txt: no dice qué incluye el mantenimiento y dónde va el SSL")

print(f"· portada: title {len(titulo)} car. · description {len(desc)} car. · {len(bloques)} bloques JSON-LD")
print(f"· pie común en {len(con_pie)} páginas · {len(LEGALES)} legales · marcador de ficha en "
      f"{len(quedan_marcas)} ficheros ({'NO admitido' if publicar else 'admitido en la rama'})")
if fallos:
    print(f"❌ {len(fallos)} fallo(s):")
    for x in fallos:
        print("   -", x)
    sys.exit(1)
print("✅ GEO web OK")
