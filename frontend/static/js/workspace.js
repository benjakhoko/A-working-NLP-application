/* Workspace: document loading, live statistics and NLP tool execution. */
(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const escape = ITA.escapeHtml;

  const textarea = $("#sourceText");
  const documentSelect = $("#documentSelect");
  const sourceBadge = $("#sourceBadge");
  const resultBody = $("#resultBody");
  const resultActions = $("#resultActions");
  const resultMeta = $("#resultMeta");
  const uploadStatus = $("#uploadStatus");
  const uploadStatusText = $("#uploadStatusText");
  const dropzone = $("#workspaceDropzone");
  const fileInput = $("#workspaceFileInput");
  const maxUploadMb = Number(dropzone?.dataset.maxMb || 10);

  const state = { documents: [], current: null, busy: false, initialDocumentId: textarea?.dataset.initialDocument || "" };

  const toolLabels = {
    keywords: "Extracting keywords",
    summary: "Summarising",
    language: "Detecting language",
    sentiment: "Analysing sentiment",
    explain: "Generating explanation",
    translate: "Translating",
  };

  function updateCounts() {
    const text = textarea.value || "";
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    const sentences = text.trim() ? (text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || []).filter((item) => item.trim()).length : 0;
    $("#wordCount").textContent = words.toLocaleString();
    $("#charCount").textContent = text.length.toLocaleString();
    $("#sentenceCount").textContent = sentences.toLocaleString();
    const limit = Number(textarea.maxLength || 50000);
    $("#limitLabel").textContent = `${text.length.toLocaleString()} / ${limit.toLocaleString()}`;
    $("#limitLabel").style.color = text.length > limit * 0.92 ? "var(--warning)" : "";
  }

  function setBadge(name) {
    if (name) {
      sourceBadge.textContent = name;
      sourceBadge.className = "badge badge-blue text-truncate";
      sourceBadge.style.maxWidth = "180px";
    } else {
      sourceBadge.textContent = "Pasted text";
      sourceBadge.className = "badge badge-neutral";
      sourceBadge.style.maxWidth = "";
    }
  }

  function resetResult() {
    state.current = null;
    resultActions.style.display = "none";
    resultMeta.style.display = "none";
    resultBody.innerHTML = `
      <div class="result-empty">
        <i class="fa-regular fa-square-check"></i>
        <p>Run a tool to see its result, method and statistics here.</p>
      </div>`;
  }

  function showLoading(tool) {
    resultActions.style.display = "none";
    resultMeta.style.display = "none";
    const slowNote = tool === "summary" && $("#summaryType").value === "abstractive"
      ? "The model may take up to 90 seconds on first use."
      : "Analysing the text with the selected model.";
    resultBody.innerHTML = `
      <div class="result-empty">
        <span class="spinner spinner-dark" style="width:22px;height:22px;border-width:2.5px;margin-bottom:12px"></span>
        <div class="text-[13px] font-medium text-slate-700">${escape(toolLabels[tool] || "Processing")}…</div>
        <p>${escape(slowNote)}</p>
      </div>`;
  }

  function showError(message, hint) {
    resultActions.style.display = "none";
    resultMeta.style.display = "none";
    resultBody.innerHTML = `
      <div class="notice notice-danger mb-3"><i class="fa-solid fa-circle-exclamation"></i><span>${escape(message)}</span></div>
      ${hint ? `<div class="notice notice-info"><i class="fa-solid fa-lightbulb"></i><span>${escape(hint)}</span></div>` : ""}
      <p class="text-[11.5px] text-slate-400 mt-3 mb-0">Failed attempts are recorded in your analysis history with a failure status.</p>`;
  }

  async function loadDocuments() {
    try {
      const { data } = await ITA.api("/api/documents?per_page=50");
      state.documents = data.documents || [];
      const currentValue = documentSelect.value;
      documentSelect.innerHTML = `<option value="">Pasted text</option>` + state.documents.map((doc) =>
        `<option value="${doc.id}">${escape(doc.filename)} · ${doc.word_count.toLocaleString()} words</option>`
      ).join("");
      if (currentValue && state.documents.some((doc) => String(doc.id) === currentValue)) {
        documentSelect.value = currentValue;
      }
      return state.documents;
    } catch (error) {
      ITA.toast(error.message, "error");
      return [];
    }
  }

  async function loadDocument(id) {
    if (!id) {
      textarea.value = "";
      setBadge(null);
      updateCounts();
      return;
    }
    try {
      const { data } = await ITA.api(`/api/documents/${encodeURIComponent(id)}`);
      const document = data.document;
      textarea.value = document.extracted_text || "";
      documentSelect.value = String(document.id);
      setBadge(document.filename);
      updateCounts();
      textarea.focus();
      textarea.setSelectionRange(0, 0);
    } catch (error) {
      ITA.toast(error.message, "error");
      documentSelect.value = "";
      setBadge(null);
    }
  }

  function setBusy(busy, button) {
    state.busy = busy;
    $$("[data-run]").forEach((item) => { item.disabled = busy; });
    if (button) ITA.buttonLoading(button, busy, "Processing");
  }

  function endpointFor(tool, payload) {
    if (tool === "keywords") return "/api/keywords/extract";
    if (tool === "summary") return payload.summary_type === "abstractive" ? "/api/summarization/abstractive" : "/api/summarization/extractive";
    if (tool === "language") return "/api/language/detect";
    if (tool === "sentiment") return "/api/sentiment/analyze";
    if (tool === "explain") return "/api/text/explain";
    if (tool === "translate") return "/api/translation/translate";
    throw new Error("Unknown tool");
  }

  function analysisTypeFor(tool, payload) {
    if (tool === "summary") return payload.summary_type === "abstractive" ? "abstractive_summary" : "extractive_summary";
    return { keywords: "keywords", language: "language", sentiment: "sentiment", explain: "explanation", translate: "translation" }[tool];
  }

  function buildPayload(tool) {
    const payload = { text: textarea.value, document_id: documentSelect.value || null };
    if (tool === "keywords") {
      payload.algorithm = $("#keywordAlgorithm").value;
      payload.top_n = Number($("#keywordCount").value);
    } else if (tool === "summary") {
      payload.summary_type = $("#summaryType").value;
      payload.length = $("#summaryLength").value;
    } else if (tool === "explain") {
      payload.complexity = $("#explainComplexity").value;
    } else if (tool === "translate") {
      payload.source = $("#translationSource").value;
      payload.target = $("#translationTarget").value;
    }
    return payload;
  }

  function renderMeta(data, type) {
    const result = data.result;
    const bits = [
      `<span>Method <strong>${escape(data.algorithm_label || result.algorithm_label || result.algorithm || result.model || result.provider_label || "—")}</strong></span>`,
      `<span>Processed in <strong>${Number(data.processing_time || 0).toFixed(2)}s</strong></span>`,
    ];
    if (result.original_word_count) bits.push(`<span>Source <strong>${Number(result.original_word_count).toLocaleString()} words</strong></span>`);
    if (type === "translation") bits.push(`<span>Provider <strong>${escape(result.provider_label || result.provider)}</strong></span>`);
    resultMeta.innerHTML = bits.join("");
    resultMeta.style.display = "flex";
  }

  async function runTool(tool, button) {
    const text = (textarea.value || "").trim();
    if (text.length < 3) {
      ITA.toast("Paste at least a few words before running an analysis.", "warning");
      textarea.focus();
      return;
    }
    if (state.busy) return;
    const payload = buildPayload(tool);
    if (tool === "translate" && payload.source !== "auto" && payload.source === payload.target) {
      ITA.toast("Source and target languages must be different.", "warning");
      return;
    }
    if (tool === "summary" && payload.summary_type === "abstractive" && text.split(/\s+/).length < 30) {
      ITA.toast("Abstractive summarisation requires at least 30 words.", "warning");
      return;
    }

    const type = analysisTypeFor(tool, payload);
    setBusy(true, button);
    showLoading(tool);
    try {
      const { data } = await ITA.api(endpointFor(tool, payload), { method: "POST", body: payload });
      state.current = { type, ...data };
      resultBody.innerHTML = ITAResults.render(type, data.result, text);
      renderMeta(data, type);
      resultActions.style.display = "flex";
      const saved = $("#openSaved");
      saved.href = `/analysis/${data.analysis_id}`;
      saved.title = "Open saved analysis";
      ITA.toast("Analysis completed and saved to history.", "success", 3000);
    } catch (error) {
      showError(error.message, error.details && error.details.hint);
    } finally {
      setBusy(false, button);
    }
  }

  // --- Tool tabs -----------------------------------------------------------
  function activateTool(tool) {
    const valid = $$(".tool-tab").some((tab) => tab.dataset.tool === tool);
    if (!valid) tool = "keywords";
    $$(".tool-tab").forEach((tab) => {
      const active = tab.dataset.tool === tool;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    $$(".tool-pane").forEach((pane) => pane.classList.toggle("active", pane.dataset.pane === tool));
    if (tool === "summary") toggleAbstractiveNote();
  }

  function toggleAbstractiveNote() {
    const note = $("#abstractiveNote");
    if (note) note.style.display = $("#summaryType").value === "abstractive" ? "flex" : "none";
  }

  $$(".tool-tab").forEach((tab) => tab.addEventListener("click", () => activateTool(tab.dataset.tool)));
  $$("[data-run]").forEach((button) => button.addEventListener("click", () => runTool(button.dataset.tool, button)));
  $("#summaryType").addEventListener("change", toggleAbstractiveNote);

  // --- Editor behaviour ----------------------------------------------------
  textarea.addEventListener("input", updateCounts);

  documentSelect.addEventListener("change", async () => {
    await loadDocument(documentSelect.value);
    resetResult();
  });

  $("#clearText").addEventListener("click", () => {
    textarea.value = "";
    documentSelect.value = "";
    setBadge(null);
    updateCounts();
    resetResult();
    textarea.focus();
  });

  $("#copyResult").addEventListener("click", () => {
    if (!state.current) return;
    ITA.copyText(ITAResults.copyText(state.current.type, state.current.result));
  });

  $("#downloadReport").addEventListener("click", () => {
    if (!state.current) return;
    ITA.downloadReport({ analysis_id: state.current.analysis_id });
  });

  // --- Upload --------------------------------------------------------------
  async function uploadFile(file) {
    if (!file) return;
    const extension = (file.name.split(".").pop() || "").toLowerCase();
    if (!["txt", "pdf", "docx"].includes(extension)) {
      ITA.toast("Only TXT, PDF and DOCX files are supported.", "error");
      return;
    }
    if (file.size > maxUploadMb * 1024 * 1024) {
      ITA.toast(`The file exceeds the ${maxUploadMb} MB limit.`, "error");
      return;
    }
    uploadStatus.classList.remove("hidden");
    uploadStatusText.textContent = `Uploading ${file.name} and extracting text…`;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const { data } = await ITA.api("/api/documents/upload", { method: "POST", formData });
      ITA.toast("Document uploaded and text extracted.", "success");
      await loadDocuments();
      await loadDocument(data.document.id);
      resetResult();
    } catch (error) {
      ITA.toast(error.message, "error", 7000);
    } finally {
      uploadStatus.classList.add("hidden");
      fileInput.value = "";
    }
  }

  $("#uploadTrigger").addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener("change", () => uploadFile(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  }));
  dropzone.addEventListener("drop", (event) => uploadFile(event.dataTransfer.files[0]));

  // --- Initial state -------------------------------------------------------
  (async function init() {
    updateCounts();
    const params = new URLSearchParams(window.location.search);
    activateTool(params.get("tool") || "keywords");
    await loadDocuments();
    const initial = state.initialDocumentId || params.get("document");
    if (initial) {
      await loadDocument(initial);
    }
  })();
})();
