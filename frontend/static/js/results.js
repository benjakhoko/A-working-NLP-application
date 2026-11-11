/* Shared HTML renderers for every NLP result type. */
(function () {
  "use strict";

  const escape = ITA.escapeHtml;

  const LABELS = {
    keywords: "Keyword extraction",
    extractive_summary: "Extractive summary",
    abstractive_summary: "Abstractive summary",
    language: "Language detection",
    sentiment: "Sentiment analysis",
    explanation: "Text explanation",
    translation: "Translation",
  };

  function metric(label, value) {
    return `<div class="metric"><div class="metric-label">${escape(label)}</div><div class="metric-value">${escape(value)}</div></div>`;
  }

  function notice(message, kind = "info", icon = "fa-circle-info") {
    return `<div class="notice notice-${kind}"><i class="fa-solid ${icon}"></i><span>${escape(message)}</span></div>`;
  }

  function keywordList(items) {
    if (!items || !items.length) return notice("No keywords were returned for this text.", "warning");
    return `<div class="keyword-list">${items.map((item) => `
      <div class="keyword-row">
        <div class="keyword-rank">${item.rank}</div>
        <div class="keyword-term">${escape(item.keyword)}</div>
        <div class="keyword-bar"><span style="width:${Math.max(3, Math.round((item.relevance_score || 0) * 100))}%"></span></div>
        <div class="keyword-score">${Number(item.relevance_score || 0).toFixed(3)}</div>
      </div>`).join("")}</div>`;
  }

  function renderKeywords(result) {
    if (result.mode === "comparison") {
      const algorithms = result.algorithms || {};
      const cards = Object.entries(algorithms).map(([code, data]) => `
        <div class="compare-col">
          <div class="compare-head">${escape(data.algorithm_label)} <span class="text-slate-400 font-normal">· ${data.count}</span></div>
          ${(data.keywords || []).slice(0, 10).map((item) => `
            <div class="compare-item"><span>${escape(item.keyword)}</span><span class="compare-score">${Number(item.relevance_score).toFixed(2)}</span></div>
          `).join("")}
        </div>`).join("");
      const errors = Object.entries(result.errors || {}).map(([code, message]) => notice(`${code.toUpperCase()}: ${message}`, "warning")).join("");
      return `
        <div class="result-section">
          <div class="result-label">Algorithm comparison · top ${result.requested_count} requested</div>
          <div class="compare-grid">${cards}</div>
        </div>
        ${errors ? `<div class="result-section">${errors}</div>` : ""}
        ${notice(result.note || "", "info", "fa-circle-info")}`;
    }
    return `
      <div class="result-section">
        <div class="flex items-center justify-between gap-3 mb-2">
          <div class="result-label mb-0">${escape(result.algorithm_label)} · ${result.count} keywords</div>
          <span class="badge badge-blue">${escape(result.algorithm.toUpperCase())}</span>
        </div>
        ${keywordList(result.keywords)}
      </div>
      <div class="result-section">${notice(result.score_note || "Scores are normalised to 0–1.", "info")}</div>
      ${(result.warnings || []).map((warning) => notice(warning, "warning", "fa-triangle-exclamation")).join("")}`;
  }

  function renderSummary(result) {
    const isAbstractive = result.method === "abstractive";
    return `
      <div class="result-section">
        <div class="result-label">${isAbstractive ? "Generated abstractive summary" : "Extractive summary"}</div>
        <div class="result-quote">${escape(result.summary || "No summary returned.")}</div>
      </div>
      <div class="result-section">
        <div class="result-grid">
          ${metric("Original words", result.original_word_count ?? "—")}
          ${metric("Summary words", result.summary_word_count ?? "—")}
          ${metric("Compression", `${result.compression_percentage ?? 0}%`)}
          ${metric("Sentences used", isAbstractive ? (result.chunks_processed || 1) + " chunk(s)" : `${result.selected_sentences || 0}/${result.total_sentences || 0}`)}
        </div>
      </div>
      <div class="result-section">
        <div class="result-label">Method</div>
        <p class="result-text m-0">${escape(result.algorithm || "—")}</p>
      </div>
      ${isAbstractive ? notice(result.note || "Generated summaries may contain inaccuracies.", "warning", "fa-triangle-exclamation") : notice(result.note || "", "info")}
    `;
  }

  function renderLanguage(result) {
    return `
      <div class="lang-hero">
        <div class="lang-code">${escape(result.code || "—")}</div>
        <div>
          <div class="lang-name">${escape(result.name || "Unknown")}</div>
          <div class="lang-sub">Language code <span class="mono">${escape(result.code || "—")}</span> · confidence ${Number(result.confidence_percentage || 0).toFixed(1)}%</div>
        </div>
      </div>
      <div class="result-section">
        <div class="result-label">Classifier confidence</div>
        <div class="progress"><div class="progress-bar" style="width:${Math.max(1, Number(result.confidence_percentage || 0))}%"></div></div>
        <div class="flex justify-between mt-1.5 text-[10.5px] text-slate-400">
          <span>${result.reliable ? "Likely reliable" : "Treat as uncertain"}</span><span>${Number(result.confidence_percentage || 0).toFixed(1)}%</span>
        </div>
      </div>
      ${(result.alternatives || []).length ? `
      <div class="result-section">
        <div class="result-label">Other candidates</div>
        <div class="inline-8">
          ${result.alternatives.map((item) => `<span class="term-chip">${escape(item.name)} · ${(item.confidence * 100).toFixed(1)}%</span>`).join("")}
        </div>
      </div>` : ""}
      ${result.warning ? notice(result.warning, "warning", "fa-triangle-exclamation") : ""}
      <div class="mt-3">${notice(result.limitations || "", "info")}</div>
      <div class="mt-2 text-[10.5px] text-slate-400">Technique: ${escape(result.technique || "langdetect")}</div>
    `;
  }

  function renderSentiment(result) {
    const icon = result.label === "positive" ? "fa-arrow-trend-up" : result.label === "negative" ? "fa-arrow-trend-down" : "fa-minus";
    const compound = Number(result.compound_score || 0);
    const marker = Math.min(100, Math.max(0, ((compound + 1) / 2) * 100));
    const sentences = result.sentences || [];
    const positiveTerms = (result.lexicon && result.lexicon.positive_terms) || [];
    const negativeTerms = (result.lexicon && result.lexicon.negative_terms) || [];
    return `
      <div class="sentiment-hero">
        <div class="sentiment-icon ${escape(result.label)}"><i class="fa-solid ${icon}"></i></div>
        <div>
          <div class="sentiment-score-label">${escape(result.label)}</div>
          <div class="sentiment-score-sub">Compound score ${compound >= 0 ? "+" : ""}${compound.toFixed(3)} · ${escape(result.model || "VADER")}</div>
        </div>
        <span class="badge ${result.label === "positive" ? "badge-green" : result.label === "negative" ? "badge-red" : "badge-neutral"} ml-auto">${escape(result.label)}</span>
      </div>
      <div class="result-section">
        <div class="result-label">Polarity breakdown</div>
        <div class="score-bars">
          <div class="score-row"><span>Positive</span><div class="score-track"><div class="score-fill pos" style="width:${Number(result.positive_score || 0) * 100}%"></div></div><span class="score-value">${Number(result.positive_score || 0).toFixed(3)}</span></div>
          <div class="score-row"><span>Neutral</span><div class="score-track"><div class="score-fill neu" style="width:${Number(result.neutral_score || 0) * 100}%"></div></div><span class="score-value">${Number(result.neutral_score || 0).toFixed(3)}</span></div>
          <div class="score-row"><span>Negative</span><div class="score-track"><div class="score-fill neg" style="width:${Number(result.negative_score || 0) * 100}%"></div></div><span class="score-value">${Number(result.negative_score || 0).toFixed(3)}</span></div>
        </div>
      </div>
      <div class="result-section">
        <div class="result-label">Compound scale (−1 to +1)</div>
        <div class="compound-track"><div class="compound-marker" style="left:${marker}%"></div></div>
        <div class="compound-scale"><span>−1.0 negative</span><span>0.0 neutral</span><span>+1.0 positive</span></div>
      </div>
      ${(positiveTerms.length || negativeTerms.length) ? `
      <div class="result-section">
        <div class="result-label">Lexicon evidence</div>
        <div>
          ${positiveTerms.map((item) => `<span class="term-chip" title="VADER valence ${item.score}">${escape(item.term)} <span class="text-emerald-700 ml-1">+${item.score}</span></span>`).join("")}
          ${negativeTerms.map((item) => `<span class="term-chip" title="VADER valence ${item.score}">${escape(item.term)} <span class="text-red-700 ml-1">${item.score}</span></span>`).join("")}
        </div>
      </div>` : ""}
      ${sentences.length ? `
      <div class="result-section">
        <div class="result-label">Sentence-level scoring</div>
        <div class="sentence-list">
          ${sentences.map((item) => `<div class="sentence-item"><span class="sentence-dot ${escape(item.label)}"></span><span>${escape(item.sentence)}</span><span class="ml-auto tabular text-[10.5px] ${item.compound > 0 ? "text-emerald-700" : item.compound < 0 ? "text-red-700" : "text-slate-400"} whitespace-nowrap">${item.compound >= 0 ? "+" : ""}${Number(item.compound).toFixed(2)}</span></div>`).join("")}
        </div>
      </div>` : ""}
      ${(result.warnings || []).map((warning) => notice(warning, "warning", "fa-triangle-exclamation")).join("")}
      <div class="mt-3">${notice(result.disclaimer || "", "info")}</div>
    `;
  }

  function highlightTerms(text, terms) {
    let html = escape(text || "");
    (terms || []).slice().sort((a, b) => b.length - a.length).forEach((term) => {
      const safe = escape(term).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      html = html.replace(new RegExp(`(\\b${safe}\\b)`, "gi"), '<mark class="term-highlight">$1</mark>');
    });
    return html;
  }

  function renderExplanation(result, inputText) {
    return `
      <div class="result-section">
        <div class="flex items-center justify-between gap-2 mb-2">
          <div class="result-label mb-0">Plain-language explanation</div>
          <span class="badge badge-violet">${escape(result.complexity || "standard")}</span>
        </div>
        <div class="result-quote">${escape(result.explanation || "No explanation returned.")}</div>
      </div>
      ${(result.key_terms || []).length ? `
      <div class="result-section">
        <div class="result-label">Key terminology</div>
        <div>${result.key_terms.map((term) => `<span class="term-chip">${escape(term)}</span>`).join("")}</div>
      </div>` : ""}
      ${inputText ? `
      <div class="result-section">
        <div class="result-label">Highlighted source</div>
        <div class="result-text text-[12.5px] leading-7">${highlightTerms(inputText.slice(0, 1800), result.key_terms || [])}${inputText.length > 1800 ? "…" : ""}</div>
      </div>` : ""}
      <div class="result-section">
        <div class="result-meta-line px-0 border-0">
          <span>Provider <strong>${escape(result.provider_label || result.provider || "—")}</strong></span>
        </div>
      </div>
      ${notice(result.disclaimer || "", "warning", "fa-triangle-exclamation")}
    `;
  }

  function renderTranslation(result) {
    const source = result.source_language || {};
    const target = result.target_language || {};
    return `
      <div class="result-section">
        <div class="flex items-center gap-2 mb-2 flex-wrap">
          <span class="badge badge-neutral">${escape(source.name || "Unknown")}</span>
          <i class="fa-solid fa-arrow-right text-[10px] text-slate-400"></i>
          <span class="badge badge-blue">${escape(target.name || "Target")}</span>
          ${result.source_detected ? '<span class="text-[10.5px] text-slate-400">source auto-detected</span>' : ""}
        </div>
        <div class="translation-output">${escape(result.translated_text || "")}</div>
      </div>
      <div class="result-section">
        <div class="result-grid">
          ${metric("Provider", result.provider_label || result.provider || "—")}
          ${metric("Characters", result.character_count ?? "—")}
          ${metric("Source", result.source_detected ? "Detected" : "Selected")}
          ${metric("Target code", target.code || "—")}
        </div>
      </div>
      ${notice(result.limitations || "", "warning", "fa-triangle-exclamation")}
    `;
  }

  function render(type, result, inputText) {
    if (!result) return notice("No result data is available for this analysis.", "warning");
    switch (type) {
      case "keywords": return renderKeywords(result);
      case "extractive_summary":
      case "abstractive_summary": return renderSummary(result);
      case "language": return renderLanguage(result);
      case "sentiment": return renderSentiment(result);
      case "explanation": return renderExplanation(result, inputText);
      case "translation": return renderTranslation(result);
      default: return notice("Unknown analysis type.", "warning");
    }
  }

  function copyText(type, result) {
    if (!result) return "";
    switch (type) {
      case "keywords": {
        if (result.mode === "comparison") {
          return Object.entries(result.algorithms || {}).map(([code, data]) =>
            `${data.algorithm_label}\n${(data.keywords || []).map((item, index) => `${index + 1}. ${item.keyword} (${item.relevance_score.toFixed(3)})`).join("\n")}`
          ).join("\n\n");
        }
        return (result.keywords || []).map((item, index) => `${index + 1}. ${item.keyword} — ${item.relevance_score.toFixed(3)}`).join("\n");
      }
      case "extractive_summary":
      case "abstractive_summary": return result.summary || "";
      case "language": return `${result.name} (${result.code}) — confidence ${(result.confidence * 100).toFixed(1)}%`;
      case "sentiment": return `Sentiment: ${result.label}\nCompound: ${result.compound_score}\nPositive: ${result.positive_score}\nNeutral: ${result.neutral_score}\nNegative: ${result.negative_score}`;
      case "explanation": return result.explanation || "";
      case "translation": return result.translated_text || "";
      default: return "";
    }
  }

  window.ITAResults = { render, copyText, labels: LABELS, reportFor: null };
})();
