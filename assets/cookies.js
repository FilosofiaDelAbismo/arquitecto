/* Aviso de cookies para arquitectodigital.io
 * - Sin dependencias. Sin trackers de terceros.
 * - El sitio NO instala cookies: no hay nada que consentir, solo que informar.
 *   Por eso el aviso tiene un unico boton [Entendido] y no Aceptar/Rechazar.
 * - Guarda el cierre en localStorage["ad_cookie_consent"] = {choice, ts, v}.
 * - CONSENT_VERSION: si sube, el aviso se vuelve a mostrar a todo el mundo.
 *   v1 = banner antiguo de dos botones (texto inexacto). v2 = aviso actual.
 * - API publica: window.ADCookies.reset()  -> limpia y vuelve a mostrar.
 *                window.ADCookies.choice() -> "seen" | null.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'ad_cookie_consent';
  var CONSENT_VERSION = 2;

  function read() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || typeof data !== 'object') return null;
      if (data.v !== CONSENT_VERSION) return null;
      return data;
    } catch (e) {
      return null;
    }
  }

  function save() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        choice: 'seen',
        ts: new Date().toISOString(),
        v: CONSENT_VERSION
      }));
    } catch (e) {
      /* localStorage bloqueado (modo privado estricto): el cierre vive solo
         en la sesion actual; el aviso reaparecera la proxima vez. */
    }
  }

  function build() {
    var wrap = document.createElement('div');
    wrap.className = 'cookie-banner';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-live', 'polite');
    wrap.setAttribute('aria-label', 'Aviso de cookies');
    wrap.innerHTML = (
      '<p><strong>Sin cookies.</strong> Este sitio no instala cookies. La analítica es ' +
      'Plausible, alojada en nuestro propio servidor, y mide de forma anónima y agregada, ' +
      'sin cookies ni identificadores personales. Para no repetirte este aviso guardamos una ' +
      'preferencia en el almacenamiento local de tu navegador (que no es una cookie). En ' +
      'Portfolio hay vídeos de YouTube en modo sin cookies, que no cargan nada de Google ' +
      'hasta que pulsas play. Detalles en <a href="cookies.html">la política de cookies</a>.</p>' +
      '<div class="cookie-actions">' +
        '<button type="button" data-close="1" class="primary">Entendido</button>' +
      '</div>'
    );
    return wrap;
  }

  function show() {
    if (document.querySelector('.cookie-banner')) return;
    var banner = build();
    document.body.appendChild(banner);
    requestAnimationFrame(function () { banner.classList.add('is-visible'); });

    banner.addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-close]');
      if (!btn) return;
      save();
      banner.classList.remove('is-visible');
      setTimeout(function () { banner.remove(); }, 200);
    });
  }

  function init() {
    if (read()) return;
    show();
  }

  /* API publica */
  window.ADCookies = {
    reset: function () {
      try { window.localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      var existing = document.querySelector('.cookie-banner');
      if (existing) existing.remove();
      show();
    },
    choice: function () {
      var prev = read();
      return prev ? prev.choice : null;
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
