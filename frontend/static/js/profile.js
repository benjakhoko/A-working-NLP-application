/* Profile: account details, password change and usage counts. */
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const escape = ITA.escapeHtml;

  function setError(form, name, message) {
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
  }

  async function loadCounts() {
    try {
      const { data } = await ITA.api("/api/auth/me");
      $("#profileDocumentCount").textContent = Number(data.user.counts.documents).toLocaleString();
      $("#profileAnalysisCount").textContent = Number(data.user.counts.analyses).toLocaleString();
    } catch (error) {
      // Counts are supplementary.
    }
  }

  const profileForm = $("#profileForm");
  profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(profileForm);
    const fullName = $("#profileFullName").value.trim();
    const email = $("#profileEmailInput").value.trim();
    let invalid = false;
    if (fullName.length < 2) { setError(profileForm, "full_name", "Enter your full name."); invalid = true; }
    if (!ITA.isEmail(email)) { setError(profileForm, "email", "Enter a valid email address."); invalid = true; }
    if (invalid) return;

    const button = $("#saveProfile");
    ITA.buttonLoading(button, true, "Saving");
    try {
      const { data } = await ITA.api("/api/auth/profile", { method: "PUT", body: { full_name: fullName, email } });
      ITA.toast("Profile updated.", "success");
      $("#profileName").textContent = data.user.full_name;
      $("#profileEmail").textContent = data.user.email;
      $("#profileInitials").textContent = data.user.full_name.charAt(0).toUpperCase();
    } catch (error) {
      ITA.toast(error.message, "error");
    } finally {
      ITA.buttonLoading(button, false);
    }
  });

  const passwordForm = $("#passwordForm");
  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(passwordForm);
    const current = $("#currentPassword").value;
    const next = $("#newPassword").value;
    const confirm = $("#confirmPassword").value;
    let invalid = false;
    if (!current) { setError(passwordForm, "current_password", "Enter your current password."); invalid = true; }
    if (next.length < 8 || !/[A-Za-z]/.test(next) || !/\d/.test(next)) {
      setError(passwordForm, "new_password", "Use at least 8 characters with a letter and a number."); invalid = true;
    }
    if (next !== confirm) { setError(passwordForm, "confirm_password", "Passwords do not match."); invalid = true; }
    if (invalid) return;

    const button = $("#savePassword");
    ITA.buttonLoading(button, true, "Updating");
    try {
      await ITA.api("/api/auth/password", { method: "POST", body: { current_password: current, new_password: next } });
      ITA.toast("Password changed successfully.", "success");
      passwordForm.reset();
    } catch (error) {
      if (error.code === "invalid_credentials") setError(passwordForm, "current_password", error.message);
      ITA.toast(error.message, "error");
    } finally {
      ITA.buttonLoading(button, false);
    }
  });

  loadCounts();
})();
