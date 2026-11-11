/* Global application behaviour: navigation drawer and logout. */
(function () {
  "use strict";

  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const toggle = document.getElementById("menuToggle");

  function setSidebar(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    overlay?.classList.toggle("open", open);
    toggle?.setAttribute("aria-expanded", String(open));
  }

  toggle?.addEventListener("click", () => setSidebar(!sidebar.classList.contains("open")));
  overlay?.addEventListener("click", () => setSidebar(false));

  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await ITA.api("/api/auth/logout", { method: "POST" });
      } catch (error) {
        // The session may already be gone; continue to the login page.
      }
      window.location.href = "/login";
    });
  });

  // Close the mobile drawer when navigating.
  document.querySelectorAll(".sidebar a").forEach((link) => {
    link.addEventListener("click", () => setSidebar(false));
  });

  // Mark the current page's tool links active where relevant.
  const params = new URLSearchParams(window.location.search);
  if (params.get("tool")) {
    document.querySelectorAll(`.nav-link[href*="tool=${params.get("tool")}"]`).forEach((link) => {
      link.style.color = "#fff";
      link.style.background = "rgba(255,255,255,0.055)";
    });
  }
})();
