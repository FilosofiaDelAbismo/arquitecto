// Tests de assets/crea-tu-cancion-medicion.js · node --test tools/test_cancion_medicion.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const M = require('../assets/crea-tu-cancion-medicion.js');

function memStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), _m: m };
}
function fakeFbq() { const calls = []; const f = (...a) => calls.push(a); f.calls = calls; return f; }

const CS = 'cs_live_a1B2c3D4e5';

test('solo los códigos de pago cs_ cuentan como compra', () => {
  assert.ok(M.isPaidCode(CS));
  assert.ok(M.isPaidCode('cs_test_XYZ123'));
  assert.ok(!M.isPaidCode('REGALO-ABCD-EFGH'));
  assert.ok(!M.isPaidCode('cs_live_<script>'));
  assert.ok(!M.isPaidCode(''));
  assert.ok(!M.isPaidCode(null));
});

test('Purchase: value 15, EUR, eventID = código, y UNA sola vez', () => {
  const fbq = fakeFbq(); const ls = memStorage();
  assert.strictEqual(M.trackPurchase(fbq, ls, CS), true);
  assert.strictEqual(M.trackPurchase(fbq, ls, CS), false);  // recarga
  assert.strictEqual(fbq.calls.length, 1);
  const [cmd, ev, data, opts] = fbq.calls[0];
  assert.strictEqual(cmd, 'track'); assert.strictEqual(ev, 'Purchase');
  assert.strictEqual(data.value, 15); assert.strictEqual(data.currency, 'EUR');
  assert.deepStrictEqual(opts, { eventID: CS });
});

test('Purchase: otro pago distinto sí cuenta', () => {
  const fbq = fakeFbq(); const ls = memStorage();
  M.trackPurchase(fbq, ls, CS); M.trackPurchase(fbq, ls, 'cs_live_OTRO999');
  assert.strictEqual(fbq.calls.length, 2);
});

test('Purchase: regalo o sin píxel → nada, y no marca', () => {
  const fbq = fakeFbq(); const ls = memStorage();
  assert.strictEqual(M.trackPurchase(fbq, ls, 'REGALO-ABCD-EFGH'), false);
  assert.strictEqual(M.trackPurchase(undefined, ls, CS), false);
  assert.strictEqual(ls._m.size, 0);
  assert.strictEqual(fbq.calls.length, 0);
});

test('Purchase: localStorage bloqueado no rompe (Meta deduplica por eventID)', () => {
  const fbq = fakeFbq();
  const broken = { getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); } };
  assert.strictEqual(M.trackPurchase(fbq, broken, CS), true);
  assert.deepStrictEqual(fbq.calls[0][3], { eventID: CS });
});

test('UTM: se recogen, se guardan con primer toque y no se pisan', () => {
  const ss = memStorage();
  const a = M.rememberUtm(ss, '?utm_source=facebook&utm_medium=paid&utm_campaign=cancion_A&x=1');
  assert.deepStrictEqual(a, { utm_source: 'facebook', utm_medium: 'paid', utm_campaign: 'cancion_A' });
  const b = M.rememberUtm(ss, '?utm_source=otro');
  assert.deepStrictEqual(b, a);
  assert.strictEqual(M.rememberUtm(memStorage(), '?foo=1'), null);
});

test('Payment Link: añade utm_* y client_reference_id válido para Stripe', () => {
  const base = 'https://buy.stripe.com/dRm9ATedzg67etcfvybEA0E';
  const utm = { utm_source: 'facebook', utm_medium: 'paid social', utm_campaign: 'canción A/B', utm_content: 'vídeo_C' };
  const u = new URL(M.buildPayUrl(base, utm));
  assert.strictEqual(u.origin + u.pathname, base);
  assert.strictEqual(u.searchParams.get('utm_source'), 'facebook');
  assert.strictEqual(u.searchParams.get('utm_campaign'), 'canción A/B');
  const ref = u.searchParams.get('client_reference_id');
  assert.match(ref, /^[A-Za-z0-9_-]{1,200}$/);
  assert.ok(ref.includes('facebook'));
  assert.strictEqual(M.buildPayUrl(base, null), base);  // sin UTM, link intacto
});

test('client_reference_id nunca pasa de 200 caracteres', () => {
  const long = 'x'.repeat(500);
  const r = M.refId({ utm_source: long, utm_medium: long, utm_campaign: long, utm_content: long, utm_term: long });
  assert.ok(r.length <= 200);
  assert.match(r, /^[A-Za-z0-9_-]+$/);
});

test('página: sin precio tachado ni «precio de lanzamiento»; plazo de 10 min; JSON-LD válido', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'crea-tu-cancion.html'), 'utf8');
  assert.ok(!/25\s*(€|&euro;|EUR)/.test(html), 'queda un 25 €');
  assert.ok(!/precio de lanzamiento/i.test(html));
  assert.ok(!/<s[\s>]/.test(html) && !/precio-antes/.test(html), 'queda un tachado');
  assert.ok(/15 €<\/strong> · pago único/.test(html));
  assert.ok((html.match(/en unos 10 minutos/g) || []).length >= 1);
  assert.ok(!/en 2 minutos|al instante/i.test(html));
  for (const m of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)) JSON.parse(m[1]);
  assert.ok(html.includes('assets/crea-tu-cancion-medicion.js'));
  // 14-11-2026: el píxel ya no se carga en la página; solo se declara el ID y
  // assets/cookies.js lo carga tras «Aceptar».
  assert.ok(html.includes("window.AD_META_PIXEL_ID = '1722843912288989'"));
  assert.ok(!/fbevents\.js|fbq\(|facebook\.com\/tr/.test(html.replace(/<!--[\s\S]*?-->/g, '')),
            'la página carga el píxel por su cuenta');
  assert.ok(html.indexOf('assets/cookies.js') < html.indexOf('assets/crea-tu-cancion-medicion.js'),
            'cookies.js debe ir antes que la medición');
});
