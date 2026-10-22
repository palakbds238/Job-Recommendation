/* ============================================================
   CareerAI — Main JavaScript
   ============================================================ */

// Auto-dismiss flash messages after 4 seconds
document.addEventListener('DOMContentLoaded', function () {

  // Flash message auto-dismiss
  setTimeout(function () {
    document.querySelectorAll('.flash').forEach(function (el) {
      el.style.transition = 'opacity 0.4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    });
  }, 4000);

  // Animate match bars when they enter viewport
  if ('IntersectionObserver' in window) {
    const bars = document.querySelectorAll('.mb-fill, .conf-fill');
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          const el = entry.target;
          const target = el.style.width;
          el.style.width = '0%';
          setTimeout(function () { el.style.width = target; }, 50);
          observer.unobserve(el);
        }
      });
    }, { threshold: 0.2 });
    bars.forEach(function (bar) { observer.observe(bar); });
  }

  // Animate stat numbers
  document.querySelectorAll('.stat-num').forEach(function (el) {
    const text = el.textContent.trim();
    const num = parseFloat(text.replace(/[^0-9.]/g, ''));
    if (!isNaN(num) && num > 0 && num < 10000) {
      let start = 0;
      const duration = 1000;
      const step = num / (duration / 16);
      const timer = setInterval(function () {
        start += step;
        if (start >= num) {
          start = num;
          clearInterval(timer);
        }
        el.textContent = text.replace(/[\d.]+/, Math.floor(start));
      }, 16);
    }
  });

  // Job card animation delay
  document.querySelectorAll('.job-card').forEach(function (card, i) {
    card.style.animationDelay = (i * 0.05) + 's';
  });

  // Confirm on all delete buttons
  document.querySelectorAll('[data-confirm]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      if (!confirm(btn.dataset.confirm)) e.preventDefault();
    });
  });

  // Resume file name display
  const resumeInput = document.getElementById('resume');
  if (resumeInput) {
    resumeInput.addEventListener('change', function () {
      const nameEl = document.querySelector('.upload-text');
      if (nameEl && this.files[0]) {
        nameEl.textContent = '✅ ' + this.files[0].name;
      }
    });
  }

  // Close modal on backdrop click
  document.querySelectorAll('.modal').forEach(function (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) modal.style.display = 'none';
    });
  });

  // Escape key closes modal
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal').forEach(function (m) {
        m.style.display = 'none';
      });
    }
  });

});

// Global toast function
function showToast(msg) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function () { t.classList.add('show'); }, 10);
  setTimeout(function () {
    t.classList.remove('show');
    setTimeout(function () { t.remove(); }, 300);
  }, 3000);
}
