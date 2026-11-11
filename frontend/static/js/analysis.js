/* Saved analysis detail page. */
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const escape = ITA.escapeHtml;
  const analysisId = Number($("#analysisPage").dataset.analysisId);
  let analysis = null;

  const typeClasses = {
    keywords: "badge-blue",
    extractive_summary: "badge-navy",
    abstractive_summary: "badge-violet",
    language: "badge-neutral",
    sentiment: "badge-amber",
    explanation: "badge-green",
    translation: "badge-blue",
  };

  function renderMeta(item) {
    const stats = (item.result && item.result.original_statistics) || {};
    const bits = [
      `<span>Processed <strong>${ITA.formatDate(item.created_at)}</strong></span>`,
      `<span>Time <strong>${Number(item.processing_time).toFixed(2)}s</strong></span>`,
      `<span>Document <strong>${escape(item.document_name || "Pasted text")}</strong></span>`,
    ];
    if (stats.word_count) bits.push(`<span>Source <strong>${Number(stats.word_count).toLocaleString()} words</strong></span>`);
    $("#analysisMeta").innerHTML = bits.join("");
  }

  function renderFailure(item) {
    return `
      <div class="notice notice-danger mb-3">
        <i class="fa-solid fa-circle-exclamation"></i>
        <span><strong>This analysis failed.</strong> ${escape(item.error_message || "The model or service was unavailable.")}</span>
      </div>
      <p class="text-[12px] text-slate-500 m-0">No result was generated. Failed jobs remain in history so the processing status is auditable. Try again from the workspace, or check the model/provider configuration.</p>`;
  }

  async function load() {
    try {
      const { data } = await ITA.api(`/api/history/${analysisId}`);
      analysis = data.analysis;
      document.title = `${analysis.title} · Intelligent Text Analysis System`;
      $("#analysisTitle").textContent = analysis.title;
      $("#analysisSubtitle").textContent = `${analysis.analysis_label}${analysis.document_name ? ` · ${analysis.document_name}` : " · pasted text"}`;
      $("#analysisTypeBadge").className = `badge ${typeClasses[analysis.analysis_type] || "badge-neutral"}`;
      $("#analysisTypeBadge").textContent = analysis.analysis_label;
      $("#analysisStatusBadge").className = `badge ${analysis.status === "completed" ? "badge-green" : "badge-red"} badge-dot`;
      $("#analysisStatusBadge").textContent = analysis.status;
      $("#analysisAlgorithm").textContent = analysis.algorithm_used || "—";

      if (analysis.status === "completed" && analysis.result) {
        $("#analysisResultBody").innerHTML = ITAResults.render(analysis.analysis_type, analysis.result, analysis.input_text || "");
        renderMeta(analysis);
      } else {
        $("#analysisMeta").style.display = "none";
        $("#analysisResultBody").innerHTML = renderFailure(analysis);
        $("#downloadAnalysisReport").disabled = true;
      }

      if (analysis.input_text) {
        $("#sourceCard").style.display = "block";
        $("#analysisSourceText").textContent = analysis.input_text;
        const words = analysis.input_text.trim() ? analysis.input_text.trim().split(/\s+/).length : 0;
        $("#sourceMeta").textContent = `${words.toLocaleString()} words · ${analysis.input_text.length.toLocaleString()} characters`;
      }
    } catch (error) {
      $("#analysisResultBody").innerHTML = `<div class="notice notice-danger"><i class="fa-solid fa-circle-exclamation"></i><span>${escape(error.message)}</span></div>`;
      $("#analysisTitle").textContent = "Analysis unavailable";
      $("#analysisSubtitle").textContent = "The record could not be loaded.";
      $("#downloadAnalysisReport").disabled = true;
      $("#copyAnalysisResult").disabled = true;
    }
  }

  $("#copyAnalysisResult").addEventListener("click", () => {
    if (!analysis || !analysis.result) return;
    ITA.copyText(ITAResults.copyText(analysis.analysis_type, analysis.result));
  });

  $("#downloadAnalysisReport").addEventListener("click", () => {
    if (!analysis) return;
    ITA.downloadReport({ analysis_id: analysis.id });
  });

  load();
})();
