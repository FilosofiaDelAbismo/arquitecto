/* Banner de cookies para arquitectodigital.io
 * - Sin dependencias. Sin trackers de terceros.
 * - Guarda elección en localStorage["ad_cookie_consent"] = {choice, ts, v}.
 * - choice: "all" | "necessary".
 * - Versión del documento de cookies (CONSENT_VERSION): si sube, se vuelve a pedir.
 * - API publica: window.ADCookies.reset()  -> limpia y vuelve a mostrar.
 *                window.ADCookies.choice() -> "all" | "necessary" | null.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'ad_cookie_consent';
  var CONSENT_VERSION = 1;

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

  function save(choice) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        choice: choice,
        ts: new Date().toISOString(),
        v: CONSENT_VERSION
      }));
    } catch (e) {
      /* localStorage bloqueado (modo privado estricto): elección vive solo
         en la sesión actual; el banner reaparecerá la próxima vez. */
    }
  }

  function build() {
    var wrap = document.createElement('div');
    wrap.className = 'cookie-banner';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-live', 'polite');
    wrap.setAttribute('aria-label', 'Aviso de cookies');
    wrap.innerHTML = (
      '<p><strong>Cookies.</strong> Este sitio usa una cookie técnica para recordar tu elección y, si las aceptas, una analítica agregada para entender qué se lee. Nada más. Detalles en <a href="cookies.html">la política de cookies</a>.</p>' +
      '<div class="cookie-actions">' +
        '<button type="button" data-choice="necessary">Solo necesarias</button>' +
        '<button type="button" data-choice="all" class="primary">Aceptar todas</button>' +
      '</div>'
    );
    return wrap;
  }

  function apply(choice) {
    /* Hook para activar/desactivar trackers en el futuro.
       Hoy no hay analítica externa; este bloque queda preparado. */
    if (choice === 'all') {
      document.documentElement.setAttribute('data-cookies', 'all');
      /* TODO: aquí se inyectarían los scripts de analítica cuando existan. */
    } else {
      document.documentElement.setAttribute('data-cookies', 'necessary');
    }
  }

  function show() {
    if (document.querySelector('.cookie-banner')) return;
    var banner = build();
    document.body.appendChild(banner);
    requestAnimationFrame(function () { banner.classList.add('is-visible'); });

    banner.addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-choice]');
      if (!btn) return;
      var choice = btn.getAttribute('data-choice');
      save(choice);
      apply(choice);
      banner.classList.remove('is-visible');
      setTimeout(function () { banner.remove(); }, 200);
    });
  }

  function init() {
    var prev = read();
    if (prev && (prev.choice === 'all' || prev.choice === 'necessary')) {
      apply(prev.choice);
      return;
    }
    show();
  }

  /* API pública */
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
