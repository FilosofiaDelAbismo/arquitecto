// Handlers del blog autogenerado.
// toggleArticle: expande/colapsa el .af-content del post al pulsar "Leer artículo completo →"
// toggleFaq: expande/colapsa la respuesta de una FAQ al pulsar la pregunta
// revealOnScroll: hace fade-in de .reveal cuando entra en viewport
(function () {
  'use strict';

  window.toggleArticle = function (contentId, btn) {
    var el = document.getElementById(contentId);
    if (!el) return;
    var expanded = el.classList.toggle('af-content-open');
    if (btn) {
      btn.textContent = expanded
        ? 'Cerrar artículo ↑'
        : 'Leer artículo completo →';
    }
  };

  window.toggleFaq = function (qEl) {
    if (!qEl) return;
    var parent = qEl.parentElement;
    if (!parent) return;
    parent.classList.toggle('faq-open');
  };

  // Reveal-on-scroll básico (sin librerías).
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('reveal-visible');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -40px 0px' });

    document.addEventListener('DOMContentLoaded', function () {
      document.querySelectorAll('.reveal').forEach(function (el) {
        io.observe(el);
      });
    });
  } else {
    // Fallback: muestra todo si no hay IntersectionObserver.
    document.addEventListener('DOMContentLoaded', function () {
      document.querySelectorAll('.reveal').forEach(function (el) {
        el.classList.add('reveal-visible');
      });
    });
  }
})();
