/* ================================================================
   Oak Homeschooling Planner — Landing Page Scripts
   Vanilla JS · No dependencies
   ================================================================ */

(function () {
  "use strict";

  /* ── 1. Sticky nav shadow ── */
  var header = document.getElementById("nav");
  if (header) {
    window.addEventListener("scroll", function () {
      header.classList.toggle("scrolled", window.scrollY > 10);
    });
  }

  /* ── 2. Smooth scroll for anchor links ── */
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener("click", function (e) {
      var targetId = this.getAttribute("href");
      if (targetId === "#") return;
      var target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        var headerHeight = header ? header.offsetHeight : 0;
        var top =
          target.getBoundingClientRect().top + window.pageYOffset - headerHeight;
        window.scrollTo({ top: top, behavior: "smooth" });

        /* Close mobile menu if open */
        header.classList.remove("nav-open");
        var toggle = header.querySelector(".nav-toggle");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
      }
    });
  });

  /* ── 3. Mobile hamburger menu ── */
  var toggle = document.querySelector(".nav-toggle");
  if (toggle && header) {
    toggle.addEventListener("click", function () {
      var isOpen = header.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      toggle.setAttribute(
        "aria-label",
        isOpen ? "Close menu" : "Open menu"
      );
    });
  }

  /* ── 4. FAQ accordion — only one open at a time ── */
  var faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach(function (item) {
    item.addEventListener("toggle", function () {
      if (this.open) {
        faqItems.forEach(function (other) {
          if (other !== item) other.removeAttribute("open");
        });
      }
    });
  });
})();
