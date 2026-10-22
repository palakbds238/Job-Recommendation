/* CareerAI — small progressive-enhancement helpers (no dependencies) */
(function () {
  // ── mobile navigation ──────────────────────────────────────
  var toggle = document.getElementById('navToggle');
  var links = document.getElementById('navLinks');
  if (toggle && links) {
    function setOpen(open) {
      links.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.textContent = open ? '✕' : '☰';
    }
    toggle.addEventListener('click', function () { setOpen(!links.classList.contains('open')); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
    document.addEventListener('click', function (e) {
      if (links.classList.contains('open') && !links.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
    });
    window.addEventListener('resize', function () { if (window.innerWidth > 1080) setOpen(false); });
  }

  // ── stop double submits on POST forms ──────────────────────
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented || !f || (f.method || '').toLowerCase() !== 'post' || f.hasAttribute('data-no-lock')) return;
    var btn = f.querySelector('button[type=submit], input[type=submit]');
    if (!btn) return;
    setTimeout(function () {                 // let the browser start the submit first
      btn.disabled = true; btn.setAttribute('data-label', btn.textContent); if (btn.tagName === 'BUTTON') btn.textContent = 'Please wait…';
    }, 0);
  });
  window.addEventListener('pageshow', function () {   // back/forward cache: re-enable
    document.querySelectorAll('button[data-label]').forEach(function (b) { b.disabled = false; b.textContent = b.getAttribute('data-label'); });
  });
})();
