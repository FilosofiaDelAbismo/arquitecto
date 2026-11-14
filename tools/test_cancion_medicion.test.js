// Tests de assets/crea-tu-cancion-medicion.js y del sitio sin píxel de Meta
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

test('aviso de cookies: el anterior («Sin cookies» + «Entendido»), sin Aceptar/Rechazar', () => {
  const js = fs.readFileSync(path.join(ROOT, 'assets', 'cookies.js'), 'utf8');
  assert.ok(js.includes('<strong>Sin cookies.</strong> Este sitio no instala cookies.'));
  assert.ok(js.includes('>Entendido</button>'));
  assert.ok(!/>Aceptar<|>Rechazar<|fbevents|AD_META/.test(js));
  assert.strictEqual((js.match(/<button/g) || []).length, 1);
});

/* cookies.js = el de 7f9ac27^ + UN bloque marcado (observador de «Comprar»). */
const OBS_RE = /  \/\* >>> observador «Comprar»[\s\S]*?\/\* <<< observador «Comprar» \*\/\n\n/g;
const gitShow = f => execFileSync('git', ['show', `7f9ac27^:${f}`], { cwd: ROOT, encoding: 'utf8' });

test('aviso de cookies: TEXTO y ESTILO idénticos a 7f9ac27^; la única diferencia es el bloque del observador', () => {
  const js = fs.readFileSync(path.join(ROOT, 'assets', 'cookies.js'), 'utf8');
  const old = gitShow('assets/cookies.js');
  // Un solo bloque y, quitándolo, el fichero es byte a byte el de 7f9ac27^.
  assert.strictEqual((js.match(OBS_RE) || []).length, 1, 'debe haber exactamente un bloque del observador');
  assert.strictEqual(js.replace(OBS_RE, ''), old, 'fuera del bloque del observador, cookies.js debe ser idéntico al de 7f9ac27^');
  // TEXTO: la función build() (texto y botón del aviso) es la misma.
  const build = s => s.match(/function build\(\) \{[\s\S]*?\n  \}\n/)[0];
  assert.strictEqual(build(js), build(old), 'el texto del aviso cambió');
  // ESTILO: todas las reglas .cookie-* de styles.css son las de 7f9ac27^.
  const rules = s => (s.match(/[^{}]*\.cookie-[^{}]*\{[^{}]*\}/g) || []).map(r => r.trim());
  const css = fs.readFileSync(path.join(ROOT, 'assets', 'styles.css'), 'utf8');
  assert.ok(rules(css).length >= 10);
  assert.deepStrictEqual(rules(css), rules(gitShow('assets/styles.css')), 'el estilo del aviso cambió');
});

test('observador de «Comprar»: solo actúa con #btn-pago, solo oculta/muestra, no guarda nada', () => {
  const blk = fs.readFileSync(path.join(ROOT, 'assets', 'cookies.js'), 'utf8').match(OBS_RE)[0]
    .replace(/\/\*[\s\S]*?\*\//g, '');
  assert.ok(blk.includes("document.getElementById('btn-pago')") && /if \(!buy \|\|/.test(blk), 'sin #btn-pago no hace nada');
  assert.ok(blk.includes('IntersectionObserver'));
  assert.ok(blk.includes("b.style.display = onScreen ? 'none' : ''"));
  assert.ok(!/localStorage|sessionStorage|document\.cookie|indexedDB|save\(|STORAGE_KEY|innerHTML|textContent|classList|className|\.remove\(/.test(blk),
    'el observador no puede guardar, cerrar ni tocar texto/clases del aviso');
  const withBtn = execFileSync('git', ['ls-files', '*.html'], { cwd: ROOT, encoding: 'utf8' }).split('\n').filter(Boolean)
    .filter(f => fs.readFileSync(path.join(ROOT, f), 'utf8').includes('id="btn-pago"'));
  assert.deepStrictEqual(withBtn, ['crea-tu-cancion.html']);
});

test('pie: «Ver el aviso de cookies» en todas las páginas, ninguna con «Configurar cookies»', () => {
  const files = execFileSync('git', ['ls-files', '*.html'], { cwd: ROOT, encoding: 'utf8' }).split('\n').filter(Boolean);
  const link = 'return false;">Ver el aviso de cookies</a></li>';
  const withLink = files.filter(f => fs.readFileSync(path.join(ROOT, f), 'utf8').includes(link));
  assert.strictEqual(withLink.length, 93);
  assert.deepStrictEqual(files.filter(f => fs.readFileSync(path.join(ROOT, f), 'utf8').includes('Configurar cookies')), []);
});
