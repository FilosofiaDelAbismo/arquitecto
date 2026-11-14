// Tests de assets/cookies.js (consentimiento) y de la regla «sin consentimiento
// no hay eventos» de assets/crea-tu-cancion-medicion.js
//   node --test tools/test_cookies_consent.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const C = require('../assets/cookies.js');
const M = require('../assets/crea-tu-cancion-medicion.js');

const DAY = 24 * 60 * 60 * 1000;
const NOW = Date.parse('2026-11-14T12:00:00Z');
const rec = (choice, ts, v = 3) => JSON.stringify({ choice, ts: new Date(ts).toISOString(), v });

test('elección válida: accepted y rejected', () => {
  assert.strictEqual(C.parseRecord(rec('accepted', NOW - DAY), NOW).choice, 'accepted');
  assert.strictEqual(C.parseRecord(rec('rejected', NOW - DAY), NOW).choice, 'rejected');
});

test('caduca a los 12 meses: se vuelve a preguntar', () => {
  assert.ok(C.parseRecord(rec('accepted', NOW - 364 * DAY), NOW));
  assert.strictEqual(C.parseRecord(rec('accepted', NOW - 366 * DAY), NOW), null);
  assert.strictEqual(C.parseRecord(rec('rejected', NOW - 366 * DAY), NOW), null);
  assert.strictEqual(C.MAX_AGE_MS, 365 * DAY);
});

test('el «Entendido» del aviso anterior (v2, choice seen) NO cuenta como elección', () => {
  assert.strictEqual(C.parseRecord(JSON.stringify({ choice: 'seen', ts: new Date(NOW).toISOString(), v: 2 }), NOW), null);
  assert.strictEqual(C.parseRecord(rec('accepted', NOW, 2), NOW), null);
});

test('datos rotos, vacíos, elección desconocida o fecha futura → sin elección', () => {
  for (const raw of [null, '', '{', '"x"', '[]', rec('maybe', NOW), rec('accepted', NOW + 3 * DAY),
                     JSON.stringify({ choice: 'accepted', ts: 'ayer', v: 3 })]) {
    assert.strictEqual(C.parseRecord(raw, NOW), null, String(raw));
  }
});

test('dominios donde borrar _fbp/_fbc', () => {
  const d = C.cookieDomains('www.arquitectodigital.io');
  for (const x of ['', 'www.arquitectodigital.io', 'arquitectodigital.io', '.arquitectodigital.io']) assert.ok(d.includes(x), x);
  assert.deepStrictEqual(C.cookieDomains('127.0.0.1'), ['', '127.0.0.1']);
});

function win(consent, withFbq = true) {
  const calls = [];
  const w = { ADCookies: { hasConsent: () => consent } };
  if (withFbq) w.fbq = (...a) => calls.push(a);
  w.calls = calls;
  return w;
}

test('canTrack: solo con consentimiento Y fbq cargado', () => {
  assert.strictEqual(M.canTrack(win(true)), true);
  assert.strictEqual(M.canTrack(win(false)), false);
  assert.strictEqual(M.canTrack(win(true, false)), false);
  assert.strictEqual(M.canTrack({ fbq() {} }), false);            // sin cookies.js → nada
  assert.strictEqual(M.canTrack({ fbq() {}, ADCookies: { hasConsent() { throw new Error('x'); } } }), false);
  assert.strictEqual(M.canTrack(null), false);
});
