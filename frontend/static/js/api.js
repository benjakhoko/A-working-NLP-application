/* Shared frontend utilities: API client, CSRF, notifications and formatting. */
(function () {
  "use strict";

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

  class ApiError extends Error {
    constructor(message, status, code, details) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
      this.details = details;
    }
  }

  async function request(path, options = {}) {
    const { method = "GET", body, formData, headers = {}, raw = false } = options;
    const requestHeaders = { Accept: raw ? "application/pdf, application/json" : "application/json", ...headers };
    if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) {
      requestHeaders["X-CSRFToken"] = csrfToken;
    }
    let payload = body;
    if (body !== undefined && !(body instanceof FormData)) {
      requestHeaders["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    if (formData) payload = formData;

    let response;
    try {
      response = await fetch(path, { method, headers: requestHeaders, body: payload, credentials: "same-origin" });
    } catch (error) {
      throw new ApiError("Network error. Check your connection and try again.", 0, "network_error");
    }

    if (raw && response.ok) {
      return { response, blob: await response.blob() };
    }

    const contentType = response.headers.get("content-type") || "";
    let data = null;
    if (contentType.includes("application/json")) {
      data = await response.json().catch(() => null);
    }
    if (!response.ok) {
      const err = data && data.error ? data.error : {};
      const message = err.message || `Request failed (HTTP ${response.status}).`;
      if (response.status === 401 && err.code === "unauthorized") {
        setTimeout(() => {
          const next = encodeURIComponent(window.location.pathname + window.location.search);
          window.location.href = `/login?next=${next}`;
        }, 1200);
      }
      throw new ApiError(message, response.status, err.code || "http_error", err.details || null);
    }
    return data;
  }

  const icons = { success: "fa-circle-check", error: "fa-circle-exclamation", warning: "fa-triangle-exclamation", info: "fa-circle-info" };

  function toast(message, type = "info", timeout = 5000) {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    const element = document.createElement("div");
    element.className = `toast ${type}`;
    element.setAttribute("role", "status");
    element.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i><span></span><button class="toast-close" aria-label="Dismiss">&times;</button>`;
    element.querySelector("span").textContent = message;
    const remove = () => {
      if (!element.isConnected) return;
      element.style.opacity = "0";
      element.style.transform = "translateY(4px)";
      element.style.transition = "all 140ms ease";
      setTimeout(() => element.remove(), 150);
    };
    element.querySelector(".toast-close").addEventListener("click", remove);
    container.appendChild(element);
    if (timeout > 0) setTimeout(remove, timeout);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatDate(value, withTime = true) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    });
  }

  function relativeTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    const diff = Date.now() - date.getTime();
    const minutes = Math.round(diff / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} hr ago`;
    const days = Math.round(hours / 24);
    if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
    return formatDate(value, false);
  }

  function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(2)} MB`;
  }

  function isEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(value || "").trim());
  }

  async function copyText(text) {
    const value = String(text ?? "");
    if (!value) {
      toast("There is nothing to copy.", "warning");
      return false;
    }
    try {
      await navigator.clipboard.writeText(value);
      toast("Copied to clipboard.", "success", 2500);
      return true;
    } catch (error) {
      const area = document.createElement("textarea");
      area.value = value;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      toast(ok ? "Copied to clipboard." : "Copy failed. Select the text manually.", ok ? "success" : "error");
      return ok;
    }
  }

  function filenameFromResponse(response, fallback) {
    const disposition = response.headers.get("content-disposition") || "";
    const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    if (utf8) return decodeURIComponent(utf8[1]);
    const plain = /filename="?([^";]+)"?/i.exec(disposition);
    return plain ? plain[1] : fallback;
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  async function downloadReport(payload) {
    try {
      const { response, blob } = await request("/api/reports/generate", {
        method: "POST",
        body: payload,
        raw: true,
      });
      const filename = filenameFromResponse(response, "analysis-report.pdf");
      triggerDownload(blob, filename);
      toast("Report downloaded.", "success");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  function confirmAction({ title = "Confirm action", message = "Are you sure?", confirmLabel = "Confirm", danger = false } = {}) {
    return new Promise((resolve) => {
      const backdrop = document.createElement("div");
      backdrop.className = "modal-backdrop open";
      backdrop.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="confirmTitle" style="max-width:420px">
          <div class="modal-header">
            <div class="modal-title" id="confirmTitle"></div>
            <button class="icon-btn" data-close aria-label="Close"><i class="fa-solid fa-xmark"></i></button>
          </div>
          <div class="modal-body"><p class="text-[13px] text-slate-600 leading-relaxed" data-message></p></div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-cancel>Cancel</button>
            <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-confirm></button>
          </div>
        </div>`;
      backdrop.querySelector(".modal-title").textContent = title;
      backdrop.querySelector("[data-message]").textContent = message;
      backdrop.querySelector("[data-confirm]").textContent = confirmLabel;
      const close = (value) => { backdrop.remove(); resolve(value); };
      backdrop.querySelector("[data-close]").addEventListener("click", () => close(false));
      backdrop.querySelector("[data-cancel]").addEventListener("click", () => close(false));
      backdrop.querySelector("[data-confirm]").addEventListener("click", () => close(true));
      backdrop.addEventListener("click", (event) => { if (event.target === backdrop) close(false); });
      document.body.appendChild(backdrop);
      backdrop.querySelector("[data-confirm]").focus();
    });
  }

  function debounce(fn, wait = 250) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  function buttonLoading(button, active, label) {
    if (!button) return;
    if (active) {
      if (!button.dataset.original) button.dataset.original = button.innerHTML;
      button.disabled = true;
      button.innerHTML = `<span class="spinner"></span><span>${escapeHtml(label || "Working")}</span>`;
    } else {
      button.disabled = false;
      if (button.dataset.original) button.innerHTML = button.dataset.original;
    }
  }

  window.ITA = {
    api: request,
    ApiError,
    toast,
    escapeHtml,
    formatDate,
    relativeTime,
    formatBytes,
    isEmail,
    copyText,
    triggerDownload,
    downloadReport,
    confirm: confirmAction,
    debounce,
    buttonLoading,
    csrfToken,
  };
})();
