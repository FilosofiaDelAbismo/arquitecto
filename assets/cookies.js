/* Aviso de cookies para arquitectodigital.io (compacto, 14-11-2026)
 * - Sin dependencias. Sin trackers de terceros.
 * - El sitio NO instala cookies: no hay nada que consentir, solo que informar.
 *   Por eso el aviso tiene un unico boton [Entendido] y no Aceptar/Rechazar.
 * - El aviso es una franja EN EL FLUJO de la pagina, justo debajo de la
 *   cabecera (no es fijo ni tapa nada). Su HTML esta en partials/header.html
 *   (#aviso-cookies, sale con `hidden`) y un script en linea alli mismo lo
 *   ensena antes de pintar si no se pulso «Entendido». Este fichero solo hace
 *   que «Entendido» lo quite y que «Ver el aviso de cookies» lo vuelva a poner.
 * - Guarda el cierre en localStorage["ad_cookie_consent"] = {choice, ts, v}.
 * - CONSENT_VERSION: si sube, el aviso se vuelve a mostrar a todo el mundo
 *   (y hay que subirla tambien en el script en linea de partials/header.html).
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

  function banner() {
    return document.getElementById('aviso-cookies');
  }

  /* Alto de la cabecera fija: la franja se coloca justo debajo (ver styles.css). */
  function place(b) {
    var h = b.previousElementSibling;
    var fixed = h && h.tagName === 'HEADER' && getComputedStyle(h).position === 'fixed';
    document.documentElement.style.setProperty('--ad-cab', (fixed ? h.getBoundingClientRect().height : 0) + 'px');
  }

  function show() {
    var b = banner();
    if (!b) return;
    place(b);
    b.hidden = false;
  }

  function hide() {
    var b = banner();
    if (b) b.hidden = true;
  }

  function init() {
    var b = banner();
    if (!b) return;
    b.addEventListener('click', function (ev) {
      if (!ev.target.closest('button[data-close]')) return;
      save();
      hide();
    });
    /* Si la cabecera cambia de alto (giro del movil, carga de fuentes).
     * Tambien sin aviso: --ad-cab baja el contenido de las legales y contratar. */
    var again = function () { place(b); };
    window.addEventListener('resize', again);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(again);
    if (read()) hide(); else show();
  }

  /* API publica */
  window.ADCookies = {
    reset: function () {
      try { window.localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      show();
      /* Vuelve a salir arriba, en su sitio: se sube para que se vea. */
      var b = banner();
      if (b) {
        window.scrollTo(0, 0);
        var btn = b.querySelector('button[data-close]');
        if (btn) btn.focus({ preventScroll: true });
      }
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
