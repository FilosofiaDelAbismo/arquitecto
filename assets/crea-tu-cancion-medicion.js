/* Medición del anuncio de Crea tu Canción (14-11-2026).
 *
 * - NO carga el píxel de Meta ni añade cookies: solo usa window.fbq si la
 *   página ya lo ha cargado. Si fbq no existe (bloqueado), no hace nada.
 * - Consentimiento (14-11-2026): ningún evento sale sin «Aceptar» en el aviso
 *   de cookies (window.ADCookies.hasConsent()). Sin consentimiento no se envía
 *   nada ni se encola, y tampoco se marca la compra como enviada.
 * - InitiateCheckout: al pulsar «Comprar mi canción» con la casilla legal
 *   marcada. Una vez por carga de página.
 * - Purchase (value 15, currency EUR): UNA vez por pago, identificado por su
 *   código de Stripe (cs_live_… / cs_test_…). Se dispara:
 *     a) al volver de Stripe con ?session_id=cs_… (solo si el Payment Link
 *        redirige aquí; hoy NO lo hace), o
 *     b) al canjear correctamente un código de pago cs_… en esta página.
 *   Los códigos de regalo (REGALO-…) no son compras y no lo disparan.
 *   Sin duplicados: marca en localStorage["ad_purchase_<cs>"] y además
 *   eventID = <cs>, que Meta usa para deduplicar.
 * - UTM: guarda los utm_* con los que se entra (sessionStorage, primer toque
 *   de la sesión) y los pasa al Payment Link al pulsar pagar, como utm_* y
 *   client_reference_id. Son parámetros de URL que Stripe admite; no cambia
 *   nada de la configuración de Stripe.
 */
(function (root) {
  'use strict';

  var UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  var UTM_STORE = 'ad_cancion_utm';
  var PRICE = 15;
  var CURRENCY = 'EUR';

  function isPaidCode(code) {
    return typeof code === 'string' && /^cs_(live|test)_[A-Za-z0-9]+$/.test(code);
  }

  function purchaseKey(code) { return 'ad_purchase_' + code; }

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

  function safeGet(storage, key) {
    try { return storage ? storage.getItem(key) : null; } catch (e) { return null; }
  }
  function safeSet(storage, key, val) {
    try { if (storage) storage.setItem(key, val); } catch (e) { /* modo privado */ }
  }

  /* ¿Se puede enviar a Meta? Solo con consentimiento vigente y fbq cargado. */
  function canTrack(w) {
    if (!w || typeof w.fbq !== 'function') return false;
    var c = w.ADCookies;
    try { return !!(c && typeof c.hasConsent === 'function' && c.hasConsent()); }
    catch (e) { return false; }
  }

  /* Purchase una sola vez por código de pago. Devuelve true si lo ha enviado. */
  function trackPurchase(fbq, storage, code) {
    if (!isPaidCode(code) || typeof fbq !== 'function') return false;
    if (safeGet(storage, purchaseKey(code))) return false;
    fbq('track', 'Purchase',
        { value: PRICE, currency: CURRENCY, content_name: 'Crea tu canción' },
        { eventID: code });
    safeSet(storage, purchaseKey(code), new Date().toISOString());
    return true;
  }

  /* UTM de primer toque de la sesión: los de la URL si no había guardados. */
  function rememberUtm(storage, search) {
    var prev = safeGet(storage, UTM_STORE);
    if (prev) { try { return JSON.parse(prev); } catch (e) { /* sigue */ } }
    var utm = pickUtm(search);
    if (utm) safeSet(storage, UTM_STORE, JSON.stringify(utm));
    return utm;
  }

  var api = {
    isPaidCode: isPaidCode, pickUtm: pickUtm, refId: refId,
    buildPayUrl: buildPayUrl, trackPurchase: trackPurchase,
    rememberUtm: rememberUtm, canTrack: canTrack, PRICE: PRICE, CURRENCY: CURRENCY,
    /* Lo llama el canje de la página tras un ok: true. */
    onRedeemOk: function (code) {
      var ls = null;
      if (!canTrack(root)) return false;
      try { ls = root.localStorage; } catch (e) { ls = null; }
      return trackPurchase(root.fbq, ls, code);
    }
  };

  if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
  if (!root || !root.document) return;
  root.ADCancionMedicion = api;

  function init() {
    var doc = root.document;
    var ls = null, ss = null;
    try { ls = root.localStorage; } catch (e) { ls = null; }
    try { ss = root.sessionStorage; } catch (e) { ss = null; }

    var utm = rememberUtm(ss, root.location.search);

    // a) Vuelta de Stripe con ?session_id=cs_…
    var sid = new URLSearchParams(root.location.search).get('session_id');
    if (sid && canTrack(root)) trackPurchase(root.fbq, ls, sid);

    var pago = doc.getElementById('btn-pago');
    var legal = doc.getElementById('cc-legal');
    if (!pago) return;
    var base = pago.getAttribute('href');
    var initiated = false;
    pago.addEventListener('click', function () {
      if (legal && !legal.checked) return;   // el otro manejador ya lo frena
      pago.setAttribute('href', buildPayUrl(base, utm));
      if (!initiated && canTrack(root)) {
        root.fbq('track', 'InitiateCheckout', { value: PRICE, currency: CURRENCY });
        initiated = true;
      }
    });
  }

  if (root.document.readyState === 'loading') {
    root.document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
