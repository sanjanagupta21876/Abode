// ============================================================
// SmartHostel — Main JS
// Sidebar, dropdowns, alerts, forms, micro-interactions
// ============================================================

(function () {
  'use strict';

  // ── Sidebar toggle (mobile + desktop) ──────────────────
  const sidebar        = document.getElementById('sidebar');
  const sidebarToggle  = document.getElementById('sidebarToggle');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const mainContent    = document.getElementById('mainContent');

  function openSidebar() {
    sidebar?.classList.add('open');
    sidebarOverlay?.classList.add('open');
    sidebarToggle?.classList.add('is-open');
  }

  function closeSidebar() {
    sidebar?.classList.remove('open');
    sidebarOverlay?.classList.remove('open');
    sidebarToggle?.classList.remove('is-open');
  }

  function toggleDesktopCollapse() {
    const collapsed = sidebar?.classList.toggle('collapsed');
    sidebarToggle?.classList.toggle('is-open', !collapsed);
    mainContent?.classList.toggle('sidebar-collapsed', collapsed);
    document.querySelector('.topbar')?.classList.toggle('sidebar-collapsed', collapsed);
  }

  sidebarToggle?.addEventListener('click', () => {
    if (window.innerWidth <= 768) {
      sidebar?.classList.contains('open') ? closeSidebar() : openSidebar();
    } else {
      toggleDesktopCollapse();
    }
  });

  sidebarOverlay?.addEventListener('click', closeSidebar);

  // Close sidebar on nav link click (mobile)
  sidebar?.querySelectorAll('.sidebar-link').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth < 769) closeSidebar();
    });
  });

  // ── Notification dropdown ───────────────────────────────
  const notifWrap = document.getElementById('notifWrap');
  const notifBtn  = document.getElementById('notifBtn');

  notifBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    profileWrap?.classList.remove('open');
    notifWrap?.classList.toggle('open');
  });

  // ── Profile dropdown ────────────────────────────────────
  const profileWrap = document.getElementById('profileWrap');
  const profileBtn  = document.getElementById('profileBtn');

  profileBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    notifWrap?.classList.remove('open');
    profileWrap?.classList.toggle('open');
  });

  // Close dropdowns on outside click
  document.addEventListener('click', (e) => {
    if (!notifWrap?.contains(e.target))   notifWrap?.classList.remove('open');
    if (!profileWrap?.contains(e.target)) profileWrap?.classList.remove('open');
  });

  // ── Auto-dismiss flash alerts ───────────────────────────
  document.querySelectorAll('.alert').forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity .4s, transform .4s';
      alert.style.opacity    = '0';
      alert.style.transform  = 'translateY(-8px)';
      setTimeout(() => alert.remove(), 400);
    }, 5000);
  });

  // ── Register page: toggle role fields ──────────────────
  window.toggleRoleFields = function () {
    const role = document.getElementById('roleSelect');
    const stu  = document.getElementById('studentFields');
    const war  = document.getElementById('wardenFields');
    if (!role || !stu || !war) return;
    if (role.value === 'warden') {
      stu.style.display = 'none';
      war.style.display = 'block';
    } else {
      stu.style.display = 'block';
      war.style.display = 'none';
    }
  };

  // ── Attendance: collect rows before submit ──────────────
  window.collectAttendance = function (e) {
    const form = e.target.closest('form');
    if (!form) return;
    form.querySelectorAll('input[name="statuses[]"][type="hidden"]').forEach(el => el.remove());
    form.querySelectorAll('tbody tr').forEach(row => {
      const checked = row.querySelector('input[type="radio"]:checked');
      if (checked) {
        const input = document.createElement('input');
        input.type  = 'hidden';
        input.name  = 'statuses[]';
        input.value = checked.value;
        form.appendChild(input);
      }
    });
  };


  // ── Search bar: highlight sidebar link ──────────────
  const searchInput = document.getElementById('topSearch');
  if (searchInput) {
    searchInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const q = searchInput.value.toLowerCase().trim();
        if (!q) return;
        const links = document.querySelectorAll('.sidebar-link');
        for (const link of links) {
          if (link.textContent.toLowerCase().includes(q)) {
            link.click();
            break;
          }
        }
      }
    });
  }

  // ── Count-up animation for stat values ─────────────────
  // Usage: add data-count="42" (and optional data-suffix=" kg") to the element
  function animateCountUp(el) {
    const target  = parseFloat(el.dataset.count);
    if (isNaN(target)) return;
    const isDecimal = String(el.dataset.count).includes('.');
    const decimals  = isDecimal ? 1 : 0;
    const duration  = 1200;
    const suffix    = el.dataset.suffix || '';
    const start     = performance.now();

    function update(now) {
      const elapsed  = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = (eased * target).toFixed(decimals) + suffix;
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  const countEls = document.querySelectorAll('[data-count]');
  if (countEls.length) {
    if ('IntersectionObserver' in window) {
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            animateCountUp(entry.target);
            obs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.3 });
      countEls.forEach(el => obs.observe(el));
    } else {
      countEls.forEach(el => animateCountUp(el));
    }
  }

  // ── Ripple effect on button clicks ─────────────────────
  function createRipple(e) {
    const btn  = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const x    = e.clientX - rect.left - size / 2;
    const y    = e.clientY - rect.top  - size / 2;

    const ripple = document.createElement('span');
    ripple.style.cssText = [
      'position:absolute',
      'width:'  + size + 'px',
      'height:' + size + 'px',
      'left:'   + x   + 'px',
      'top:'    + y   + 'px',
      'border-radius:50%',
      'background:rgba(255,255,255,0.28)',
      'transform:scale(0)',
      'animation:rippleAnim .55s linear',
      'pointer-events:none'
    ].join(';');

    if (getComputedStyle(btn).position === 'static') {
      btn.style.position = 'relative';
    }
    btn.style.overflow = 'hidden';
    btn.appendChild(ripple);
    ripple.addEventListener('animationend', () => ripple.remove());
  }

  // Inject ripple keyframes once
  if (!document.getElementById('rippleStyles')) {
    const s = document.createElement('style');
    s.id = 'rippleStyles';
    s.textContent = '@keyframes rippleAnim { to { transform:scale(1); opacity:0; } }';
    document.head.appendChild(s);
  }

  document.querySelectorAll('.btn, .btn-primary, .btn-outline, .btn-ghost, .btn-danger, .btn-green-solid').forEach(btn => {
    btn.addEventListener('click', createRipple);
  });

})();
