/* Medición de Crea tu Canción (14-11-2026, sin píxel de Meta).
 *
 * - Solo Plausible (autoalojado, sin cookies): usa window.plausible, que define
 *   el script.js que ya carga la página. Si no está (bloqueado), no pasa nada.
 * - NO guarda nada en el navegador: ni cookies, ni localStorage, ni
 *   sessionStorage.
 * - UTM: al pulsar «Comprar» lee los utm_* de la URL ACTUAL de la página y los
 *   añade al Payment Link (utm_* y client_reference_id). Si ya no están en la
 *   URL (la persona ha navegado), se pierden: aceptado.
 * - Eventos (con los utm_* de la URL como propiedades, si los hay):
 *     «Cancion Comprar»: al pulsar «Comprar mi canción» con la casilla legal.
 *     «Cancion Canje»:   al canjear bien un código de pago cs_live_/cs_test_
 *                        (los REGALO-… no cuentan).
 *   Antes de salir de la página se espera a que Plausible confirme el envío,
 *   como mucho WAIT_MS.
 */
(function (root) {
  'use strict';

  var UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  var WAIT_MS = 400;
  var EV_COMPRAR = 'Cancion Comprar';
  var EV_CANJE = 'Cancion Canje';

  function isPaidCode(code) {
    return typeof code === 'string' && /^cs_(live|test)_[A-Za-z0-9]+$/.test(code);
  }

  /* utm_* de una query string → objeto, o null si no hay ninguno. */
  function pickUtm(search) {
    var qs = new URLSearchParams(search || '');
    var out = {};
    var any = false;
    UTM_KEYS.forEach(function (k) {
      var v = qs.get(k);
      if (v) { out[k] = v.slice(0, 100); any = true; }
    });
    return any ? out : null;
  }

  /* client_reference_id de Stripe: solo [A-Za-z0-9_-] y máximo 200. */
  function refId(utm) {
    if (!utm) return '';
    var parts = UTM_KEYS.map(function (k) {
      return (utm[k] || '').replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 38);
    });
    return ('u_' + parts.join('__')).slice(0, 200);
  }

  /* URL del Payment Link con los UTM añadidos (sin tocar los que ya traiga). */
  function buildPayUrl(base, utm) {
    if (!utm) return base;
    var u = new URL(base);
    UTM_KEYS.forEach(function (k) {
      if (utm[k] && !u.searchParams.has(k)) u.searchParams.set(k, utm[k]);
    });
    if (!u.searchParams.has('client_reference_id')) {
      u.searchParams.set('client_reference_id', refId(utm));
    }
    return u.toString();
  }

  /* Envía un evento a Plausible y llama a `done` UNA vez: cuando Plausible
     confirma, o a los WAIT_MS si no contesta, o al momento si no hay Plausible. */
  function track(w, name, utm, done) {
    var called = false;
    function finish() { if (!called) { called = true; if (done) done(); } }
    var p = w && w.plausible;
    if (typeof p !== 'function') { finish(); return false; }
    var opts = { callback: finish };
    if (utm) opts.props = utm;
    try { p(name, opts); } catch (e) { finish(); return false; }
    if (done) setTimeout(finish, WAIT_MS);
    return true;
  }

  var api = {
    isPaidCode: isPaidCode, pickUtm: pickUtm, refId: refId, buildPayUrl: buildPayUrl,
    track: track, EV_COMPRAR: EV_COMPRAR, EV_CANJE: EV_CANJE, WAIT_MS: WAIT_MS,
    /* Lo llama el canje de la página tras un ok: true. Si el código es de pago,
       envía «Cancion Canje» y luego llama a `go`; devuelve true. Si no (regalo),
       devuelve false y la página navega por su cuenta. */
    onRedeemOk: function (code, go) {
      if (!isPaidCode(code)) return false;
      track(root, EV_CANJE, pickUtm(root.location && root.location.search), go);
      return true;
    }
  };

  if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
  if (!root || !root.document) return;
  root.ADCancionMedicion = api;

  function init() {
    var doc = root.document;
    var pago = doc.getElementById('btn-pago');
    var legal = doc.getElementById('cc-legal');
    if (!pago) return;
    var base = pago.getAttribute('href');
    pago.addEventListener('click', function (e) {
      if (e.defaultPrevented || (legal && !legal.checked)) return;  // el otro manejador ya lo frena
      var utm = pickUtm(root.location.search);
      var href = buildPayUrl(base, utm);
      pago.setAttribute('href', href);
      // Ctrl/Cmd/Mayús-clic o clic central: nueva pestaña; no hace falta esperar.
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) {
        track(root, EV_COMPRAR, utm, null);
        return;
      }
      e.preventDefault();
      track(root, EV_COMPRAR, utm, function () { root.location.href = href; });
    });
  }

  if (root.document.readyState === 'loading') {
    root.document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
