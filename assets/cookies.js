/* Aviso de consentimiento de cookies para arquitectodigital.io (v3, 14-11-2026)
 *
 * - Primera capa compacta, fija bajo la cabecera (no tapa el vídeo de
 *   Crea tu Canción ni el botón de compra, y la burbuja del chat, abajo a la
 *   derecha, no la cruza). Dos botones iguales: «Rechazar» y «Aceptar».
 *   No hay casillas ni «seguir navegando = aceptar»: sin elección no hay píxel.
 * - Guarda la elección en localStorage["ad_cookie_consent"] =
 *   {choice: "accepted"|"rejected", ts, v}. Caduca a los 12 meses: entonces
 *   se vuelve a preguntar. CONSENT_VERSION: si sube, se pregunta a todos.
 *   v2 = aviso informativo «Sin cookies» (un botón): ya no vale, se pregunta.
 * - Píxel de Meta: una página lo pide declarando window.AD_META_PIXEL_ID antes
 *   de este script. Solo se carga fbevents.js si la elección es «accepted»
 *   (bloqueo previo). Sin elección o con «rejected»: no se carga y se borran
 *   _fbp/_fbc (y las claves de Meta en localStorage) si existieran. Al retirar el consentimiento con la página
 *   abierta: fbq('consent','revoke') y borrado de _fbp/_fbc.
 * - Eventos automáticos del píxel desactivados (autoConfig false): a Meta solo
 *   llegan PageView, InitiateCheckout y Purchase.
 * - Plausible (autoalojado, sin cookies) no depende de esto.
 * - API: window.ADCookies.open()       -> vuelve a mostrar el aviso («Configurar cookies»)
 *        window.ADCookies.reset()      -> alias de open() (enlaces antiguos)
 *        window.ADCookies.choice()     -> "accepted" | "rejected" | null
 *        window.ADCookies.hasConsent() -> true solo si «accepted» y vigente
 *   Evento: window 'ad:consent' con detail {choice}.
 */
(function (root) {
  'use strict';

  var STORAGE_KEY = 'ad_cookie_consent';
  var CONSENT_VERSION = 3;
  var MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000;   // 12 meses
  var META_COOKIES = ['_fbp', '_fbc'];
  /* Lo que fbevents.js escribe en localStorage (comprobado con Playwright). */
  var META_STORAGE = ['lastExternalReferrer', 'lastExternalReferrerTime', 'multiFbc'];

  /* Registro guardado → objeto válido o null (sin elección, versión antigua,
     dato roto o caducado). Pura: la usan los tests. */
  function parseRecord(raw, nowMs) {
    if (!raw) return null;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return null; }
    if (!data || typeof data !== 'object') return null;
    if (data.v !== CONSENT_VERSION) return null;
    if (data.choice !== 'accepted' && data.choice !== 'rejected') return null;
    var ts = Date.parse(data.ts);
    if (isNaN(ts)) return null;
    if (nowMs - ts > MAX_AGE_MS || ts - nowMs > 24 * 60 * 60 * 1000) return null;
    return data;
  }

  /* Dominios en los que pudo quedar una cookie: host y sus padres. Pura. */
  function cookieDomains(hostname) {
    var out = [''];
    var parts = String(hostname || '').split('.');
    if (/^[0-9.]+$/.test(hostname) || parts.length < 2) return out.concat(hostname ? [hostname] : []);
    for (var i = 0; i <= parts.length - 2; i++) {
      var d = parts.slice(i).join('.');
      out.push(d, '.' + d);
    }
    return out;
  }

  var api = { parseRecord: parseRecord, cookieDomains: cookieDomains,
              STORAGE_KEY: STORAGE_KEY, CONSENT_VERSION: CONSENT_VERSION, MAX_AGE_MS: MAX_AGE_MS };
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
  if (!root || !root.document) return;

  var doc = root.document;
  var memoryChoice = null;   // si localStorage está bloqueado: vale para esta página

  function read() {
    var raw = null;
    try { raw = root.localStorage.getItem(STORAGE_KEY); } catch (e) { raw = null; }
    return parseRecord(raw, Date.now()) || memoryChoice;
  }

  function save(choice) {
    var rec = { choice: choice, ts: new Date().toISOString(), v: CONSENT_VERSION };
    memoryChoice = rec;
    try { root.localStorage.setItem(STORAGE_KEY, JSON.stringify(rec)); } catch (e) {
      /* modo privado estricto: la elección vale solo para esta página */
    }
  }

  function hasConsent() {
    var r = read();
    return !!r && r.choice === 'accepted';
  }

  function deleteMetaCookies() {
    var doms = cookieDomains(root.location.hostname);
    META_COOKIES.forEach(function (name) {
      if (doc.cookie.indexOf(name + '=') === -1) return;
      doms.forEach(function (d) {
        doc.cookie = name + '=; Max-Age=0; path=/' + (d ? '; domain=' + d : '');
      });
    });
    META_STORAGE.forEach(function (k) {
      try { root.localStorage.removeItem(k); } catch (e) {}
    });
  }

  /* Snippet oficial de Meta, solo tras aceptar. */
  function loadMetaPixel() {
    var id = root.AD_META_PIXEL_ID;
    if (!id || !hasConsent()) return;
    if (typeof root.fbq === 'function') { root.fbq('consent', 'grant'); return; }
    /* eslint-disable */
    !function(f,b,e,v,n,t,s)
    {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}(root, doc,'script',
    'https://connect.facebook.net/en_US/fbevents.js');
    /* eslint-enable */
    /* Sin eventos automáticos de Meta (SubscribedButtonClick, etc.): solo se
       envían PageView, InitiateCheckout y Purchase. Además, sin esto el clic en
       «Rechazar» para retirar el consentimiento llegaba a Meta (comprobado). */
    root.fbq('set', 'autoConfig', false, String(id));
    root.fbq('init', String(id));
    root.fbq('track', 'PageView');
  }

  function applyChoice() {
    if (hasConsent()) { loadMetaPixel(); return; }
    if (typeof root.fbq === 'function') { try { root.fbq('consent', 'revoke'); } catch (e) {} }
    deleteMetaCookies();
  }

  /* ---------- Aviso ---------- */

  function fecha(iso) {
    var d = new Date(iso);
    return isNaN(d) ? '' : d.toLocaleDateString('es-ES');
  }

  function build() {
    var prev = read();
    var estado = prev
      ? ' <span class="cookie-estado">Ahora: ' + (prev.choice === 'accepted' ? 'aceptadas' : 'rechazadas') +
        ' el ' + fecha(prev.ts) + '.</span>'
      : '';
    var wrap = doc.createElement('div');
    wrap.className = 'cookie-banner';
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Aviso de cookies');
    wrap.innerHTML = (
      '<p>Guardamos tu elección en este navegador y, si aceptas, usamos el píxel de Meta ' +
      'para medir nuestros anuncios. <a href="/cookies.html">Más información</a>.' + estado + '</p>' +
      '<div class="cookie-actions">' +
        '<button type="button" data-choice="rejected">Rechazar</button>' +
        '<button type="button" data-choice="accepted">Aceptar</button>' +
      '</div>'
    );
    return wrap;
  }

  /* El aviso va justo bajo la cabecera fija (si la hay). */
  function place(banner) {
    var top = 0;
    var h = doc.querySelector('body > header, header');
    if (h) {
      var pos = root.getComputedStyle(h).position;
      if (pos === 'fixed' || pos === 'sticky') top = Math.max(0, h.getBoundingClientRect().bottom);
    }
    banner.style.top = top + 'px';
  }

  function hide(banner) {
    banner.classList.remove('is-visible');
    root.removeEventListener('resize', banner._place);
    setTimeout(function () { if (banner.parentNode) banner.parentNode.removeChild(banner); }, 200);
  }

  function show() {
    var old = doc.querySelector('.cookie-banner');
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var banner = build();
    doc.body.appendChild(banner);
    banner._place = function () { place(banner); };
    place(banner);
    root.addEventListener('resize', banner._place);
    banner.classList.add('is-visible');

    banner.addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-choice]');
      if (!btn) return;
      var choice = btn.getAttribute('data-choice');
      save(choice);
      applyChoice();
      try { root.dispatchEvent(new CustomEvent('ad:consent', { detail: { choice: choice } })); } catch (e) {}
      hide(banner);
    });
  }

  root.ADCookies = {
    open: show,
    reset: show,
    choice: function () { var r = read(); return r ? r.choice : null; },
    hasConsent: hasConsent
  };

  /* Bloqueo previo: esto corre ANTES de pintar el aviso y antes que
     crea-tu-cancion-medicion.js (ambos defer, en este orden). */
  applyChoice();

  function init() { if (!read()) show(); }
  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
