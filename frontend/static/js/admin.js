/* Administrator user management. */
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const escape = ITA.escapeHtml;
  const currentUserId = Number(document.body.dataset.userId || 0);
  const state = { page: 1, query: "" };

  function initials(name) {
    return String(name || "?").split(/\s+/).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join("");
  }

  function renderUsers(items) {
    if (!items.length) {
      $("#adminTable").innerHTML = `<div class="empty-state"><div class="empty-icon"><i class="fa-solid fa-users"></i></div><div class="empty-title">No users found</div><div class="empty-text">No accounts match this search.</div></div>`;
      return;
    }
    $("#adminTable").innerHTML = `
      <table class="table">
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Documents</th><th>Analyses</th><th>Joined</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          ${items.map((user) => `
            <tr>
              <td>
                <div class="flex items-center gap-2.5">
                  <div class="avatar avatar-light" style="width:30px;height:30px">${escape(initials(user.full_name))}</div>
                  <div>
                    <div class="table-title">${escape(user.full_name)} ${user.id === currentUserId ? '<span class="badge badge-blue ml-1">You</span>' : ""}</div>
                    <div class="table-sub">${escape(user.email)}</div>
                  </div>
                </div>
              </td>
              <td><span class="badge ${user.role === "admin" ? "badge-violet" : "badge-neutral"}">${escape(user.role)}</span></td>
              <td><span class="badge ${user.is_active ? "badge-green" : "badge-red"} badge-dot">${user.is_active ? "Active" : "Disabled"}</span></td>
              <td class="tabular">${user.document_count}</td>
              <td class="tabular">${user.analysis_count}</td>
              <td class="whitespace-nowrap">${ITA.formatDate(user.created_at, false)}</td>
              <td>
                <div class="table-actions">
                  ${user.id === currentUserId ? '<span class="text-[11px] text-slate-400 pr-2">This is your account</span>' : `
                    <select class="select select-sm" style="width:auto" data-role="${user.id}" aria-label="Role for ${escape(user.email)}">
                      <option value="user" ${user.role === "user" ? "selected" : ""}>Member</option>
                      <option value="admin" ${user.role === "admin" ? "selected" : ""}>Administrator</option>
                    </select>
                    <button class="icon-btn ${user.is_active ? "danger" : ""}" data-status="${user.id}" data-active="${user.is_active}" title="${user.is_active ? "Deactivate" : "Activate"}">
                      <i class="fa-solid ${user.is_active ? "fa-user-slash" : "fa-user-check"}"></i>
                    </button>`}
                </div>
              </td>
            </tr>`).join("")}
        </tbody>
      </table>`;

    document.querySelectorAll("[data-role]").forEach((select) => {
      select.dataset.previous = select.value;
      select.addEventListener("change", () => changeRole(select));
    });
    document.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", () => changeStatus(button)));
  }

  function renderPagination(pagination) {
    const wrapper = $("#adminPagination");
    if (!pagination || pagination.pages <= 1) { wrapper.style.display = "none"; return; }
    wrapper.style.display = "flex";
    wrapper.innerHTML = `
      <span>Page ${pagination.page} of ${pagination.pages} · ${pagination.total} users</span>
      <div class="pagination-buttons">
        <button class="btn btn-secondary btn-sm" ${pagination.page <= 1 ? "disabled" : ""} data-page="${pagination.page - 1}"><i class="fa-solid fa-chevron-left"></i> Previous</button>
        <button class="btn btn-secondary btn-sm" ${pagination.page >= pagination.pages ? "disabled" : ""} data-page="${pagination.page + 1}">Next <i class="fa-solid fa-chevron-right"></i></button>
      </div>`;
    wrapper.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => {
      state.page = Number(button.dataset.page);
      load();
    }));
  }

  async function load() {
    const params = new URLSearchParams({ page: state.page, per_page: 20 });
    if (state.query) params.set("q", state.query);
    try {
      const { data } = await ITA.api(`/api/admin/users?${params}`);
      $("#adminTotalUsers").textContent = Number(data.totals.users).toLocaleString();
      $("#adminTotalAdmins").textContent = Number(data.totals.admins).toLocaleString();
      $("#adminTotalAnalyses").textContent = Number(data.totals.analyses).toLocaleString();
      renderUsers(data.users);
      renderPagination(data.pagination);
    } catch (error) {
      ITA.toast(error.message, "error");
      $("#adminTable").innerHTML = `<div class="p-4"><div class="notice notice-danger"><i class="fa-solid fa-circle-exclamation"></i><span>${escape(error.message)}</span></div></div>`;
    }
  }

  async function changeRole(select) {
    const userEmail = select.closest("tr").querySelector(".table-sub").textContent;
    const previous = select.dataset.previous;
    const role = select.value;
    const confirmed = await ITA.confirm({
      title: "Change user role",
      message: `Grant the “${role === "admin" ? "Administrator" : "Member"}” role to ${userEmail}?`,
      confirmLabel: "Change role",
    });
    if (!confirmed) { select.value = previous; return; }
    try {
      await ITA.api(`/api/admin/users/${select.dataset.role}/role`, { method: "PATCH", body: { role } });
      ITA.toast("User role updated.", "success");
      load();
    } catch (error) {
      select.value = previous;
      ITA.toast(error.message, "error");
    }
  }

  async function changeStatus(button) {
    const active = button.dataset.active === "true";
    const userEmail = button.closest("tr").querySelector(".table-sub").textContent;
    const confirmed = await ITA.confirm({
      title: active ? "Deactivate account" : "Activate account",
      message: `${active ? "Prevent" : "Allow"} ${userEmail} from signing in?`,
      confirmLabel: active ? "Deactivate" : "Activate",
      danger: active,
    });
    if (!confirmed) return;
    try {
      await ITA.api(`/api/admin/users/${button.dataset.status}/status`, { method: "PATCH", body: { is_active: !active } });
      ITA.toast("Account status updated.", "success");
      load();
    } catch (error) {
      ITA.toast(error.message, "error");
    }
  }

  $("#adminSearch").addEventListener("input", ITA.debounce((event) => {
    state.query = event.target.value.trim();
    state.page = 1;
    load();
  }, 300));
  $("#refreshUsers").addEventListener("click", load);

  load();
})();
