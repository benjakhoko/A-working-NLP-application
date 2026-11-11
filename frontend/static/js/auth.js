/* Authentication forms. Errors are rendered inline and from JSON API responses. */
(function () {
  "use strict";

  function setFieldError(form, name, message) {
    const field = form.querySelector(`[data-field="${name}"]`);
    if (!field) return;
    field.classList.toggle("has-error", Boolean(message));
    const target = field.querySelector("[data-error]");
    if (target) target.textContent = message || "";
  }

  function clearErrors(form) {
    form.querySelectorAll("[data-field]").forEach((field) => {
      field.classList.remove("has-error");
      const target = field.querySelector("[data-error]");
      if (target) target.textContent = "";
    });
    const banner = document.getElementById("authError");
    if (banner) banner.classList.add("hidden");
  }

  function showBanner(message) {
    const banner = document.getElementById("authError");
    const text = document.getElementById("authErrorText");
    if (banner && text) {
      text.textContent = message;
      banner.classList.remove("hidden");
    }
  }

  function loading(button, active, label) {
    if (!button) return;
    button.disabled = active;
    button.innerHTML = active
      ? `<span class="spinner"></span><span>${label}</span>`
      : `${label}<i class="fa-solid fa-arrow-right"></i>`;
  }

  // Password visibility toggles
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      const icon = button.querySelector("i");
      if (icon) icon.className = showing ? "fa-regular fa-eye" : "fa-regular fa-eye-slash";
      button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    });
  });

  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearErrors(loginForm);
      const email = loginForm.email.value.trim();
      const password = loginForm.password.value;
      let invalid = false;
      if (!ITA.isEmail(email)) { setFieldError(loginForm, "email", "Enter a valid email address."); invalid = true; }
      if (!password) { setFieldError(loginForm, "password", "Enter your password."); invalid = true; }
      if (invalid) return;

      const button = document.getElementById("loginButton");
      loading(button, true, "Signing in");
      try {
        await ITA.api("/api/auth/login", {
          method: "POST",
          body: { email, password, remember: document.getElementById("remember").checked },
        });
        window.location.href = "/dashboard";
      } catch (error) {
        showBanner(error.message);
        loading(button, false, "Sign in");
      }
    });
  }

  const registerForm = document.getElementById("registerForm");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearErrors(registerForm);
      const fullName = registerForm.full_name.value.trim();
      const email = registerForm.email.value.trim();
      const password = registerForm.password.value;
      const confirm = registerForm.confirm_password.value;
      let invalid = false;
      if (fullName.length < 2) { setFieldError(registerForm, "full_name", "Enter your full name."); invalid = true; }
      if (!ITA.isEmail(email)) { setFieldError(registerForm, "email", "Enter a valid email address."); invalid = true; }
      if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        setFieldError(registerForm, "password", "Use at least 8 characters with a letter and a number."); invalid = true;
      }
      if (confirm !== password) { setFieldError(registerForm, "confirm_password", "Passwords do not match."); invalid = true; }
      if (invalid) return;

      const button = document.getElementById("registerButton");
      loading(button, true, "Creating account");
      try {
        await ITA.api("/api/auth/register", {
          method: "POST",
          body: { full_name: fullName, email, password, confirm_password: confirm },
        });
        window.location.href = "/login?registered=1";
      } catch (error) {
        showBanner(error.message);
        if (error.details && typeof error.details === "object") {
          Object.entries(error.details).forEach(([key, value]) => setFieldError(registerForm, key, String(value)));
        }
        loading(button, false, "Create account");
      }
    });
  }
})();
