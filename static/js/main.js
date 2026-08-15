// BigThinkers — main.js
document.addEventListener("DOMContentLoaded", function () {

  // Hamburger menu — toggles the full nav dropdown open/closed and animates the icon
  const hamburger = document.getElementById("btHamburger");
  const navLinks = document.getElementById("btNavLinks");

  if (hamburger && navLinks) {
    const closeMenu = function () {
      navLinks.classList.remove("bt-nav-open");
      hamburger.classList.remove("active");
      hamburger.setAttribute("aria-expanded", "false");
    };

    const openMenu = function () {
      navLinks.classList.add("bt-nav-open");
      hamburger.classList.add("active");
      hamburger.setAttribute("aria-expanded", "true");
    };

    hamburger.addEventListener("click", function (e) {
      e.stopPropagation();
      const isOpen = navLinks.classList.contains("bt-nav-open");
      if (isOpen) { closeMenu(); } else { openMenu(); }
    });

    // Close the dropdown after a nav link is tapped
    navLinks.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeMenu);
    });

    // Close when tapping outside the menu
    document.addEventListener("click", function (e) {
      if (!navLinks.contains(e.target) && !hamburger.contains(e.target)) {
        closeMenu();
      }
    });

    // Reset state if the viewport grows back to desktop size
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900) { closeMenu(); }
    });
  }

  // Password show/hide toggles
  document.querySelectorAll(".bt-toggle-password").forEach(function (icon) {
    icon.addEventListener("click", function () {
      const targetId = icon.getAttribute("data-target");
      const input = document.getElementById(targetId);
      if (!input) return;
      if (input.type === "password") {
        input.type = "text";
        icon.classList.remove("fa-eye");
        icon.classList.add("fa-eye-slash");
      } else {
        input.type = "password";
        icon.classList.remove("fa-eye-slash");
        icon.classList.add("fa-eye");
      }
    });
  });

  // Auto-dismiss flash messages after 6 seconds
  document.querySelectorAll(".bt-flash").forEach(function (flash) {
    setTimeout(function () {
      flash.style.transition = "opacity 0.4s ease";
      flash.style.opacity = "0";
      setTimeout(function () { flash.remove(); }, 400);
    }, 6000);
  });

});
