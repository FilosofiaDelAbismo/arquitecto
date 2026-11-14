// Tests de assets/crea-tu-cancion-medicion.js, del sitio sin píxel de Meta y del aviso de cookies compacto
//   node --test tools/test_cancion_medicion.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const M = require('../assets/crea-tu-cancion-medicion.js');

const ROOT = path.join(__dirname, '..');
const CS = 'cs_live_a1B2c3D4e5';

/* window.plausible simulado: guarda las llamadas; `confirm` decide si llama al callback. */
function fakeWin(confirm = true) {
  const calls = [];
  const w = { plausible(name, opts) { calls.push([name, opts]); if (confirm && opts && opts.callback) opts.callback({ status: 202 }); } };
  w.calls = calls;
  return w;
}

test('solo los códigos de pago cs_ cuentan como canje de compra', () => {
  assert.ok(M.isPaidCode(CS));
  assert.ok(M.isPaidCode('cs_test_XYZ123'));
  assert.ok(!M.isPaidCode('REGALO-ABCD-EFGH'));
  assert.ok(!M.isPaidCode('cs_live_<script>'));
  assert.ok(!M.isPaidCode(''));
  assert.ok(!M.isPaidCode(null));
});

test('nombres de los eventos de Plausible', () => {
  assert.strictEqual(M.EV_COMPRAR, 'Cancion Comprar');
  assert.strictEqual(M.EV_CANJE, 'Cancion Canje');
});

test('track: llama a plausible con el nombre y los UTM como props, y `done` una sola vez', () => {
  const w = fakeWin();
  let n = 0;
  assert.strictEqual(M.track(w, 'Cancion Comprar', { utm_source: 'meta' }, () => n++), true);
  assert.strictEqual(w.calls.length, 1);
  assert.strictEqual(w.calls[0][0], 'Cancion Comprar');
  assert.deepStrictEqual(w.calls[0][1].props, { utm_source: 'meta' });
  assert.strictEqual(n, 1);
});

test('track: sin UTM no manda props', () => {
  const w = fakeWin();
  M.track(w, 'Cancion Comprar', null, null);
  assert.ok(!('props' in w.calls[0][1]));
});

test('track: sin Plausible (bloqueado) no rompe y sigue adelante al momento', () => {
  let n = 0;
  assert.strictEqual(M.track({}, 'Cancion Comprar', null, () => n++), false);
  assert.strictEqual(n, 1);
  assert.strictEqual(M.track({ plausible() { throw new Error('x'); } }, 'X', null, () => n++), false);
  assert.strictEqual(n, 2);
});

test('track: si Plausible no contesta, sigue adelante a los WAIT_MS', async () => {
  const w = fakeWin(false);
  let n = 0;
  M.track(w, 'Cancion Comprar', null, () => n++);
  assert.strictEqual(n, 0);
  await new Promise(r => setTimeout(r, M.WAIT_MS + 50));
  assert.strictEqual(n, 1);
});

test('UTM: se leen de la query string y nada más', () => {
  assert.deepStrictEqual(M.pickUtm('?utm_source=meta&utm_campaign=cancion_nov&x=1'),
                         { utm_source: 'meta', utm_campaign: 'cancion_nov' });
  assert.strictEqual(M.pickUtm('?foo=1'), null);
  assert.strictEqual(M.pickUtm(''), null);
});

test('Payment Link: añade utm_* y client_reference_id válido para Stripe', () => {
  const base = 'https://buy.stripe.com/dRm9ATedzg67etcfvybEA0E';
  const utm = { utm_source: 'meta', utm_medium: 'paid social', utm_campaign: 'canción A/B', utm_content: 'vídeo_C' };
  const u = new URL(M.buildPayUrl(base, utm));
  assert.strictEqual(u.origin + u.pathname, base);
  assert.strictEqual(u.searchParams.get('utm_source'), 'meta');
  assert.strictEqual(u.searchParams.get('utm_campaign'), 'canción A/B');
  const ref = u.searchParams.get('client_reference_id');
  assert.match(ref, /^[A-Za-z0-9_-]{1,200}$/);
  assert.ok(ref.includes('meta'));
  assert.strictEqual(M.buildPayUrl(base, null), base);  // sin UTM, link intacto
});

test('client_reference_id nunca pasa de 200 caracteres', () => {
  const long = 'x'.repeat(500);
  const r = M.refId({ utm_source: long, utm_medium: long, utm_campaign: long, utm_content: long, utm_term: long });
  assert.ok(r.length <= 200);
  assert.match(r, /^[A-Za-z0-9_-]+$/);
});

test('el script de medición no usa almacenamiento del navegador ni Meta', () => {
  const src = fs.readFileSync(path.join(ROOT, 'assets', 'crea-tu-cancion-medicion.js'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  assert.ok(!/localStorage|sessionStorage|document\.cookie|indexedDB/.test(src));
  assert.ok(!/fbq|facebook|Purchase|InitiateCheckout/.test(src));
});

test('página: sin precio tachado; plazo de 10 min; sin píxel; JSON-LD válido', () => {
  const html = fs.readFileSync(path.join(ROOT, 'crea-tu-cancion.html'), 'utf8');
  assert.ok(!/25\s*(€|&euro;|EUR)/.test(html), 'queda un 25 €');
  assert.ok(!/precio de lanzamiento/i.test(html));
  assert.ok(!/<s[\s>]/.test(html) && !/precio-antes/.test(html), 'queda un tachado');
  assert.ok(/15 €<\/strong> · pago único · IVA incluido/.test(html));
  assert.ok((html.match(/en unos 10 minutos/g) || []).length >= 2, 'hero y paso 4');
  for (const m of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)) JSON.parse(m[1]);
  assert.ok(html.includes('assets/crea-tu-cancion-medicion.js'));
  assert.ok(html.includes('src="https://analytics.arquitectodigital.io/js/script.js"'));
  assert.ok(!/AD_META_PIXEL_ID|<noscript>/.test(html));
});

test('sitio: ningún resto de Meta en HTML/JS/CSS versionados', () => {
  const out = execFileSync('git', ['ls-files', '*.html', '*.js', '*.css', '*.xml', '*.json'], { cwd: ROOT, encoding: 'utf8' })
    .split('\n').filter(f => f && !f.startsWith('tools/'));
  assert.ok(out.length > 90, `solo ${out.length} ficheros`);
  const bad = /fbq|fbevents|facebook\.net|facebook\.com\/tr|1722843912288989|AD_META_PIXEL_ID|_fbp|_fbc/;
  const hits = out.filter(f => bad.test(fs.readFileSync(path.join(ROOT, f), 'utf8')));
  assert.deepStrictEqual(hits, []);
});

/* ── Aviso de cookies compacto (14-11-2026) ─────────────────────────────────
 * Hasta el 14-11-2026 estos tests exigían que el TEXTO y el ESTILO del aviso
 * fueran los de 7f9ac27^ («Sin cookies. Este sitio no instala cookies…» en una
 * caja fija). Eso ya NO aplica: el aviso pasa a ser una franja compacta en el
 * flujo de la página, bajo la cabecera, con el texto nuevo
 *   «Esta web no usa cookies.» + «Más info» (/cookies.html) + «Entendido».
 * Lo que SÍ sigue igual que en 7f9ac27^: la clave y el formato de lo guardado
 * (read/save idénticos), para que quien ya pulsó «Entendido» no lo vuelva a ver.
 * El observador de «Comprar» se quita: el aviso ya no tapa nada. */
const gitShow = f => execFileSync('git', ['show', `7f9ac27^:${f}`], { cwd: ROOT, encoding: 'utf8' });
const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const AVISO_TXT = 'Esta web no usa cookies. Más info';
const pagesWithCookiesJs = () => execFileSync('git', ['ls-files', '*.html'], { cwd: ROOT, encoding: 'utf8' })
  .split('\n').filter(Boolean).filter(f => !f.startsWith('partials/') && /assets\/cookies\.js/.test(read(f)));
const avisoBlock = s => s.match(/<div class="cookie-banner" id="aviso-cookies"[\s\S]*?<\/div>\n<script>[\s\S]*?<\/script>/)[0];

test('aviso de cookies: texto NUEVO «Esta web no usa cookies.» + «Más info» + «Entendido», sin Aceptar/Rechazar', () => {
  const html = avisoBlock(read('partials/header.html'));
  assert.ok(html.includes('<p>Esta web no usa cookies. <a href="/cookies.html">Más info</a></p>'));
  assert.ok(html.includes('<button type="button" data-close="1">Entendido</button>'));
  assert.strictEqual((html.match(/<button/g) || []).length, 1);
  assert.ok(/id="aviso-cookies" role="region" aria-label="Aviso de cookies" hidden>/.test(html), 'sale oculto hasta que el script decide');
  const jsCode = read('assets/cookies.js').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  assert.ok(!/Aceptar|Rechazar|Sin cookies\.|fbevents|AD_META/.test(html + jsCode));
  // El texto vive solo en el parcial: cookies.js no lo duplica.
  assert.ok(!/innerHTML|Esta web no usa cookies/.test(read('assets/cookies.js')));
});

test('aviso de cookies: en las 92 páginas que cargan cookies.js, una sola vez y justo después de la cabecera', () => {
  const pages = pagesWithCookiesJs();
  assert.strictEqual(pages.length, 92);
  const want = avisoBlock(read('partials/header.html'));
  const bad = pages.filter(f => {
    const s = read(f);
    const i = s.indexOf('</header>'), j = s.indexOf(want);
    const between = i >= 0 && j > i ? s.slice(i + '</header>'.length, j) : null;
    return (s.match(/id="aviso-cookies"/g) || []).length !== 1 || (s.match(/<header[\s>]/g) || []).length !== 1
      || between === null || !/^\n(<!--[\s\S]*?-->\n)?$/.test(between);
  });
  assert.deepStrictEqual(bad, []);
  // Y el parcial está sincronizado (lo mismo que comprobará sync_partials --check).
  execFileSync('python3', [path.join(ROOT, 'tools', 'sync_partials.py'), '--check'], { cwd: ROOT, stdio: 'pipe' });
});

test('aviso de cookies: misma clave y formato que antes (read/save idénticos a 7f9ac27^)', () => {
  const js = read('assets/cookies.js');
  const old = gitShow('assets/cookies.js');
  const fn = (s, name) => s.match(new RegExp(`  function ${name}\\(\\) \\{[\\s\\S]*?\\n  \\}\\n`))[0];
  assert.strictEqual(fn(js, 'read'), fn(old, 'read'));
  assert.strictEqual(fn(js, 'save'), fn(old, 'save'));
  assert.ok(js.includes("var STORAGE_KEY = 'ad_cookie_consent';") && js.includes('var CONSENT_VERSION = 2;'));
  const inline = avisoBlock(read('partials/header.html')).match(/<script>([\s\S]*?)<\/script>/)[1];
  assert.ok(inline.includes("localStorage.getItem('ad_cookie_consent')") && inline.includes('r.v===2'),
    'el script en línea del parcial usa la misma clave y versión que cookies.js');
});

/* El script en línea del parcial, ejecutado con un DOM mínimo simulado. */
function runInline(stored, { throws = false, fixed = true } = {}) {
  const vm = require('node:vm');
  const code = avisoBlock(read('partials/header.html')).match(/<script>([\s\S]*?)<\/script>/)[1];
  const header = { tagName: 'HEADER', getBoundingClientRect: () => ({ height: 69.4 }) };
  const props = {};
  const b = { hidden: true, previousElementSibling: header };
  const documentElement = { style: { setProperty: (k, v) => { props[k] = v; } } };
  const ls = { getItem: k => { if (throws) throw new Error('bloqueado'); return k === 'ad_cookie_consent' ? stored : null; } };
  vm.runInNewContext(code, {
    document: { getElementById: id => (id === 'aviso-cookies' ? b : null), documentElement },
    localStorage: ls, getComputedStyle: () => ({ position: fixed ? 'fixed' : 'static' }), JSON,
  });
  return { hidden: b.hidden, cab: props['--ad-cab'] };
}

test('script en línea: enseña el aviso salvo si ya se pulsó «Entendido» (v2), y lo pone bajo la cabecera fija', () => {
  const ok = JSON.stringify({ choice: 'seen', ts: '2026-11-14T10:00:00.000Z', v: 2 });
  // --ad-cab se pone SIEMPRE (también sin aviso): baja el contenido de las legales y contratar.
  assert.deepStrictEqual(runInline(ok), { hidden: true, cab: '69.4px' }, 'ya pulsó «Entendido»: no sale, pero --ad-cab sí');
  assert.deepStrictEqual(runInline(null), { hidden: false, cab: '69.4px' }, 'primera visita: sale');
  assert.strictEqual(runInline(JSON.stringify({ choice: 'seen', v: 1 })).hidden, false, 'versión antigua: sale');
  assert.strictEqual(runInline('{roto').hidden, false, 'dato roto: sale');
  assert.strictEqual(runInline('5').hidden, false, 'dato que no es objeto: sale');
  assert.strictEqual(runInline(null, { throws: true }).hidden, false, 'localStorage bloqueado: sale');
  assert.strictEqual(runInline(null, { fixed: false }).cab, '0px', 'cabecera no fija: sin desplazamiento');
});

test('aviso de cookies: compacto y en el flujo (no fijo), botón de 44 px, sin observador de «Comprar»', () => {
  const css = read('assets/styles.css');
  const rule = css.match(/\n\.cookie-banner \{[^}]*\}/)[0];
  assert.ok(/position: relative;/.test(rule) && !/position: (fixed|absolute|sticky)/.test(rule), 'el aviso no puede ser fijo ni superpuesto');
  assert.ok(/top: var\(--ad-cab, 0px\);/.test(rule));
  assert.ok(/\.cookie-banner\[hidden\] \{ display: none; \}/.test(css), '[hidden] tiene que ganar al display:flex');
  assert.ok(/\.cookie-banner button \{[^}]*min-height: 44px;/.test(css), 'tamaño táctil mínimo');
  assert.ok(!/\.cookie-banner[^{]*\{[^}]*(animation|transition: (all|transform|height|max-height|margin|top))/.test(css), 'sin animaciones que muevan el contenido');
  // Alto constante: texto y botón SIEMPRE en una fila; el texto cede ancho, el botón no.
  assert.ok(/flex-wrap: nowrap;/.test(rule) && !/flex-wrap: wrap/.test(rule), 'texto y botón en una sola fila');
  assert.ok(!/\.cookie-banner[^{]*\{[^}]*flex-wrap: wrap/.test(css), 'ninguna regla del aviso (tampoco la del móvil) vuelve a wrap');
  assert.ok(/\.cookie-banner p \{[^}]*min-width: 0;/.test(css), 'el texto puede encoger y partir en 2 líneas');
  const btn = css.match(/\n\.cookie-banner button \{[^}]*\}/)[0];
  assert.ok(/flex: none;/.test(btn), 'el botón no encoge ni crece');
  assert.ok(!/min-width/.test(btn), 'sin min-width en el botón (era lo que bajaba el botón a otra fila en iPhone)');
  const js = read('assets/cookies.js');
  assert.ok(!/IntersectionObserver|MutationObserver|btn-pago|style\.display/.test(js), 'el observador de «Comprar» ya no está');
});

test('legales y contratar: el contenido empieza SIEMPRE bajo la cabecera fija (con y sin aviso)', () => {
  const css = read('assets/styles.css');
  const m = css.match(/\n\.cookie-banner \+ script \+ main\.legal,\n\.cookie-banner \+ script \+ section\.section-content \{[^}]*\}/);
  assert.ok(m, 'regla para main.legal y section.section-content justo tras el aviso, SIN :not([hidden])');
  assert.ok(/margin-top: var\(--ad-cab, 88px\) !important;/.test(m[0]));
  // Son exactamente las 15 legales + contratar.html (lo primero tras la cabecera común).
  const hit = pagesWithCookiesJs().filter(f => {
    const s = read(f), i = s.indexOf('<!-- /PARTIAL:header -->');
    const first = s.slice(i + 24).replace(/<!--[\s\S]*?-->/g, '').match(/<([a-z]+)\b[^>]*>/);
    return first && /^<(main class="legal"|section class="section-content")/.test(first[0]); });
  assert.strictEqual(hit.length, 16);
  assert.ok(hit.includes('contratar.html') && hit.includes('cookies.html') && hit.includes('privacidad.html'));
});

test('las 16 páginas (legales + contratar): ningún texto cambia, solo la cabecera común', () => {
  const strip = s => s.replace(/<!-- PARTIAL:header -->[\s\S]*?<!-- \/PARTIAL:header -->/, '');
  const pages = ['audio-libro-condiciones.html', 'autoblog-condiciones.html', 'aviso-legal.html', 'cenit-condiciones.html',
    'cenit-pioneros-bases.html', 'cenit-privacidad.html', 'cenit-uso.html', 'chatbot-condiciones.html', 'condiciones.html',
    'cookies.html', 'crea-tu-cancion-condiciones.html', 'girobot-condiciones.html', 'privacidad.html',
    'sistemas-condiciones.html', 'webs-condiciones.html', 'contratar.html'];
  for (const f of pages) {
    const main = execFileSync('git', ['show', `main:${f}`], { cwd: ROOT, encoding: 'utf8' });
    assert.strictEqual(strip(read(f)), strip(main), `${f} cambió fuera de la cabecera`);
  }
});

test('cookies.html y privacidad.html: llevan el aviso y, fuera de la cabecera común, son idénticas a main', () => {
  const want = avisoBlock(read('partials/header.html'));
  for (const f of ['cookies.html', 'privacidad.html']) assert.ok(read(f).includes(want), `${f} sin el aviso`);
  const strip = s => s.replace(/<!-- PARTIAL:header -->[\s\S]*?<!-- \/PARTIAL:header -->/, '');
  for (const f of ['cookies.html', 'privacidad.html']) {
    const main = execFileSync('git', ['show', `main:${f}`], { cwd: ROOT, encoding: 'utf8' });
    assert.strictEqual(strip(read(f)), strip(main), `${f} cambió fuera de la cabecera`);
  }
});

test('pie: «Ver el aviso de cookies» en todas las páginas, ninguna con «Configurar cookies»', () => {
  const files = execFileSync('git', ['ls-files', '*.html'], { cwd: ROOT, encoding: 'utf8' }).split('\n').filter(Boolean);
  const link = 'return false;">Ver el aviso de cookies</a></li>';
  const withLink = files.filter(f => fs.readFileSync(path.join(ROOT, f), 'utf8').includes(link));
  assert.strictEqual(withLink.length, 93);
  assert.deepStrictEqual(files.filter(f => fs.readFileSync(path.join(ROOT, f), 'utf8').includes('Configurar cookies')), []);
});
