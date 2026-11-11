/* Analysis history with filtering, pagination, deletion and reports. */
(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const escape = ITA.escapeHtml;
  const state = { page: 1, type: "", status: "", from: "", to: "", query: "" };

  const typeClasses = {
    keywords: "badge-blue",
    extractive_summary: "badge-navy",
    abstractive_summary: "badge-violet",
    language: "badge-neutral",
    sentiment: "badge-amber",
    explanation: "badge-green",
    translation: "badge-blue",
  };

  function renderSummary(summary) {
    const target = $("#historySummary");
    target.innerHTML = `
      <span class="badge badge-neutral badge-dot">${summary.total} total</span>
      <span class="badge badge-green badge-dot">${summary.completed} completed</span>
      <span class="badge badge-red badge-dot">${summary.failed} failed</span>`;
  }

  function renderTypes(types) {
    const select = $("#historyType");
    const current = select.value;
    select.innerHTML = `<option value="">All types</option>` + types.map((type) =>
      `<option value="${type.code}">${escape(type.label)}</option>`
    ).join("");
    select.value = current;
  }

  function renderRows(items) {
    if (!items.length) {
      $("#historyTable").innerHTML = `
        <div class="empty-state">
          <div class="empty-icon"><i class="fa-solid fa-clock-rotate-left"></i></div>
          <div class="empty-title">No analyses found</div>
          <div class="empty-text">${state.type || state.status || state.query || state.from || state.to ? "No records match the current filters." : "Run a tool in the workspace and it will appear here automatically."}</div>
          <a class="btn btn-primary btn-sm" href="/workspace">Open workspace</a>
        </div>`;
      $("#historyPagination").style.display = "none";
      return;
    }
    $("#historyTable").innerHTML = `
      <table class="table">
        <thead>
          <tr><th>Analysis</th><th>Type</th><th>Document</th><th>Created</th><th>Status</th><th class="text-right">Actions</th></tr>
        </thead>
        <tbody>
          ${items.map((item) => `
            <tr>
              <td>
                <div class="table-title">${escape(item.title)}</div>
                <div class="table-sub">${escape(item.preview || "No preview available")}</div>
              </td>
              <td><span class="badge ${typeClasses[item.analysis_type] || "badge-neutral"}">${escape(item.analysis_label)}</span></td>
              <td class="whitespace-nowrap">${item.document_name ? escape(item.document_name) : '<span class="text-slate-400">Pasted text</span>'}</td>
              <td class="whitespace-nowrap">${ITA.formatDate(item.created_at)}</td>
              <td>
                <span class="badge ${item.status === "completed" ? "badge-green" : "badge-red"} badge-dot">${escape(item.status)}</span>
              </td>
              <td>
                <div class="table-actions">
                  <a class="icon-btn" href="/analysis/${item.id}" title="View result"><i class="fa-regular fa-eye"></i></a>
                  ${item.status === "completed" ? `<button class="icon-btn" data-report="${item.id}" title="Download report"><i class="fa-solid fa-file-pdf"></i></button>` : ""}
                  <button class="icon-btn danger" data-delete="${item.id}" title="Delete record"><i class="fa-regular fa-trash-can"></i></button>
                </div>
              </td>
            </tr>`).join("")}
        </tbody>
      </table>`;

    document.querySelectorAll("[data-report]").forEach((button) => button.addEventListener("click", () => ITA.downloadReport({ analysis_id: Number(button.dataset.report) })));
    document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => removeAnalysis(button.dataset.delete)));
  }

  function renderPagination(pagination) {
    const wrapper = $("#historyPagination");
    if (!pagination || pagination.pages <= 1) { wrapper.style.display = "none"; return; }
    wrapper.style.display = "flex";
    wrapper.innerHTML = `
      <span>Page ${pagination.page} of ${pagination.pages} · ${pagination.total} record${pagination.total === 1 ? "" : "s"}</span>
      <div class="pagination-buttons">
        <button class="btn btn-secondary btn-sm" ${pagination.has_prev ? "" : "disabled"} data-page="${pagination.page - 1}"><i class="fa-solid fa-chevron-left"></i> Previous</button>
        <button class="btn btn-secondary btn-sm" ${pagination.has_next ? "" : "disabled"} data-page="${pagination.page + 1}">Next <i class="fa-solid fa-chevron-right"></i></button>
      </div>`;
    wrapper.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => {
      state.page = Number(button.dataset.page);
      load();
    }));
  }

  async function load() {
    const params = new URLSearchParams({ page: state.page, per_page: 15 });
    if (state.type) params.set("type", state.type);
    if (state.status) params.set("status", state.status);
    if (state.from) params.set("date_from", state.from);
    if (state.to) params.set("date_to", state.to);
    if (state.query) params.set("q", state.query);
    try {
      const { data } = await ITA.api(`/api/history?${params}`);
      renderTypes(data.available_types || []);
      renderRows(data.analyses);
      renderPagination(data.pagination);
    } catch (error) {
      ITA.toast(error.message, "error");
      $("#historyTable").innerHTML = `<div class="p-4"><div class="notice notice-danger"><i class="fa-solid fa-circle-exclamation"></i><span>${escape(error.message)}</span></div></div>`;
    }
  }

  async function loadSummary() {
    try {
      const { data } = await ITA.api("/api/history/summary");
      renderSummary(data);
    } catch (error) {
      // Summary is supplementary; the table error message is sufficient.
    }
  }

  async function removeAnalysis(id) {
    const confirmed = await ITA.confirm({
      title: "Delete analysis record",
      message: "This analysis will be permanently removed from your history. The original document, if any, is not affected.",
      confirmLabel: "Delete record",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await ITA.api(`/api/history/${id}`, { method: "DELETE" });
      ITA.toast("Analysis deleted.", "success");
      loadSummary();
      load();
    } catch (error) {
      ITA.toast(error.message, "error");
    }
  }

  $("#applyFilters").addEventListener("click", () => {
    state.type = $("#historyType").value;
    state.status = $("#historyStatus").value;
    state.from = $("#dateFrom").value;
    state.to = $("#dateTo").value;
    state.query = $("#historySearch").value.trim();
    if (state.from && state.to && state.from > state.to) {
      ITA.toast("The start date must be before the end date.", "warning");
      return;
    }
    state.page = 1;
    load();
  });

  $("#resetFilters").addEventListener("click", () => {
    $("#historyType").value = "";
    $("#historyStatus").value = "";
    $("#dateFrom").value = "";
    $("#dateTo").value = "";
    $("#historySearch").value = "";
    state.type = state.status = state.from = state.to = state.query = "";
    state.page = 1;
    load();
  });

  $("#historySearch").addEventListener("keydown", (event) => {
    if (event.key === "Enter") $("#applyFilters").click();
  });

  loadSummary();
  load();
})();
