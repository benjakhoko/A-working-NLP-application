/* Dashboard: live statistics from the database, activity chart and recent records. */
(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const escape = ITA.escapeHtml;
  let chart = null;

  function typeBadge(type, label) {
    const map = {
      keywords: "badge-blue",
      extractive_summary: "badge-navy",
      abstractive_summary: "badge-violet",
      language: "badge-neutral",
      sentiment: "badge-amber",
      explanation: "badge-green",
      translation: "badge-blue",
    };
    return `<span class="badge ${map[type] || "badge-neutral"}">${escape(label)}</span>`;
  }

  function renderStats(data) {
    const totals = data.totals;
    const values = {
      documents: totals.documents_processed,
      analyses: totals.analyses_performed,
      keywords: totals.keywords_extracted,
      summaries: totals.summaries_generated,
    };
    Object.entries(values).forEach(([key, value]) => {
      const target = $(`[data-stat="${key}"]`);
      if (target) target.textContent = Number(value).toLocaleString();
    });
    const meta = {
      documents: totals.documents_processed ? "Stored extracted text" : "No documents uploaded yet",
      analyses: totals.failed_analyses ? `${totals.failed_analyses} failed` : "All completed successfully",
      keywords: "Across saved keyword analyses",
      summaries: "Extractive and abstractive",
    };
    Object.entries(meta).forEach(([key, value]) => {
      const target = $(`[data-stat-meta="${key}"]`);
      if (target) target.textContent = value;
    });
    const activityTotal = data.activity_chart.reduce((sum, item) => sum + item.count, 0);
    const badge = $("#activityTotal");
    if (badge) badge.textContent = `${activityTotal} in 14 days`;
  }

  function renderChart(points) {
    const canvas = document.getElementById("activityChart");
    if (!canvas || typeof Chart === "undefined") return;
    const labels = points.map((point) => {
      const date = new Date(`${point.date}T00:00:00`);
      return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    });
    if (chart) chart.destroy();
    chart = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Analyses",
          data: points.map((point) => point.count),
          borderColor: "#1e40af",
          backgroundColor: "rgba(37, 99, 235, 0.08)",
          borderWidth: 2,
          pointRadius: 2.5,
          pointHoverRadius: 4,
          pointBackgroundColor: "#1e40af",
          fill: true,
          tension: 0.25,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#0B1220",
            titleFont: { family: "Inter, Segoe UI", size: 11 },
            bodyFont: { family: "Inter, Segoe UI", size: 11 },
            padding: 9,
            cornerRadius: 5,
            displayColors: false,
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: "#94a3b8", font: { size: 10 }, maxRotation: 0, autoSkipPadding: 16 },
          },
          y: {
            beginAtZero: true,
            ticks: { color: "#94a3b8", font: { size: 10 }, precision: 0, maxTicksLimit: 5 },
            grid: { color: "#f1f5f9" },
            border: { display: false },
          },
        },
      },
    });
  }

  function renderToolUsage(rows) {
    const target = $("#toolUsage");
    if (!target) return;
    if (!rows.length) {
      target.innerHTML = `
        <div class="empty-state" style="padding:24px 8px">
          <div class="empty-icon"><i class="fa-solid fa-chart-simple"></i></div>
          <div class="empty-title">No tool usage yet</div>
          <div class="empty-text">Run your first analysis to see the distribution here.</div>
        </div>`;
      return;
    }
    const max = Math.max(...rows.map((row) => row.count), 1);
    target.innerHTML = rows.map((row) => `
      <div class="tool-usage-item">
        <div class="tool-usage-head"><span>${escape(row.label)}</span><span>${row.count}</span></div>
        <div class="tool-usage-bar"><div class="tool-usage-fill" style="width:${Math.max(4, (row.count / max) * 100)}%"></div></div>
      </div>`).join("");
  }

  function renderRecentAnalyses(items) {
    const target = $("#recentAnalyses");
    if (!target) return;
    if (!items.length) {
      target.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon"><i class="fa-solid fa-pen-nib"></i></div>
          <div class="empty-title">No analyses yet</div>
          <div class="empty-text">Open the workspace and process your first passage or document.</div>
          <a class="btn btn-primary btn-sm" href="/workspace">Start an analysis</a>
        </div>`;
      return;
    }
    target.innerHTML = `
      <table class="table">
        <thead><tr><th>Analysis</th><th>Type</th><th>Created</th><th class="text-right">Result</th></tr></thead>
        <tbody>
          ${items.map((item) => `
            <tr>
              <td>
                <div class="table-title">${escape(item.title)}</div>
                <div class="table-sub">${escape(item.document_name || "Pasted text")}${item.status === "failed" ? " · failed" : ""}</div>
              </td>
              <td>${typeBadge(item.analysis_type, item.analysis_label)}</td>
              <td class="tabular whitespace-nowrap">${ITA.relativeTime(item.created_at)}</td>
              <td class="text-right">
                <a class="btn btn-ghost btn-sm" href="/analysis/${item.id}">View <i class="fa-solid fa-arrow-right"></i></a>
              </td>
            </tr>`).join("")}
        </tbody>
      </table>`;
  }

  function renderRecentActivity(items) {
    const target = $("#recentActivity");
    if (!target) return;
    if (!items.length) {
      target.innerHTML = `<p class="small muted m-0">No activity recorded.</p>`;
      return;
    }
    const iconMap = {
      analysis_completed: ["fa-circle-check", "text-emerald-600"],
      analysis_failed: ["fa-circle-exclamation", "text-red-600"],
      document_uploaded: ["fa-file-arrow-up", "text-slate-500"],
      document_deleted: ["fa-trash-can", "text-slate-500"],
      report_generated: ["fa-file-pdf", "text-slate-500"],
      login: ["fa-right-to-bracket", "text-slate-400"],
      account_created: ["fa-user-plus", "text-slate-400"],
      profile_updated: ["fa-user-pen", "text-slate-400"],
      password_changed: ["fa-key", "text-slate-400"],
      role_changed: ["fa-shield-halved", "text-slate-500"],
      status_changed: ["fa-user-gear", "text-slate-500"],
    };
    target.innerHTML = `<div class="stack-12">${items.map((item) => {
      const [icon, color] = iconMap[item.action] || ["fa-circle", "text-slate-400"];
      return `<div class="flex items-start gap-2.5">
        <i class="fa-solid ${icon} ${color} text-[11px] mt-1"></i>
        <div class="min-w-0">
          <div class="text-[12px] text-slate-700 leading-snug">${escape(item.description)}</div>
          <div class="text-[10.5px] text-slate-400 mt-0.5">${ITA.relativeTime(item.created_at)}</div>
        </div>
      </div>`;
    }).join("")}</div>`;
  }

  async function load() {
    try {
      const { data } = await ITA.api("/api/dashboard/statistics");
      renderStats(data);
      renderChart(data.activity_chart);
      renderToolUsage(data.tool_usage);
      renderRecentAnalyses(data.recent_analyses);
      renderRecentActivity(data.recent_activity);
    } catch (error) {
      ITA.toast(error.message, "error");
      $("#toolUsage").innerHTML = `<div class="notice notice-danger"><i class="fa-solid fa-circle-exclamation"></i><span>${escape(error.message)}</span></div>`;
    }
  }

  load();
})();
