/**
 * TourVsTravel — Main UI Logic
 * Engineering Foundation Phase
 * Minimal JS: mobile navigation only
 */

(function () {
  function initMobileNav() {
    const toggle = document.querySelector('[data-nav-toggle]');
    const menu = document.querySelector('[data-nav-menu]');

    if (!toggle || !menu) return;

    function closeMenu() {
      toggle.setAttribute('aria-expanded', 'false');
      menu.classList.remove('is-open');
    }

    function openMenu() {
      toggle.setAttribute('aria-expanded', 'true');
      menu.classList.add('is-open');
    }

    function toggleMenu() {
      const isOpen = toggle.getAttribute('aria-expanded') === 'true';
      if (isOpen) {
        closeMenu();
      } else {
        openMenu();
      }
    }

    toggle.addEventListener('click', toggleMenu);

    document.addEventListener('click', (event) => {
      const clickedInsideMenu = menu.contains(event.target);
      const clickedToggle = toggle.contains(event.target);

      if (!clickedInsideMenu && !clickedToggle) {
        closeMenu();
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeMenu();
        toggle.focus();
      }
    });

    window.addEventListener('resize', () => {
      if (window.innerWidth > 860) {
        menu.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.documentElement.classList.add('js');
    initMobileNav();
  });
})();
