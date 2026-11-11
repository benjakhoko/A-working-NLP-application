/* Document management: upload, list, preview, analyse, report and delete. */
(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const escape = ITA.escapeHtml;
  const state = { page: 1, query: "", type: "", selectedFile: null, currentDocument: null };

  const uploadModal = $("#uploadModal");
  const documentModal = $("#documentModal");
  const dropzone = $("#documentDropzone");
  const fileInput = $("#documentFileInput");
  const selectedFile = $("#selectedFile");
  const confirmUpload = $("#confirmUpload");
  const progressWrap = $("#uploadProgressWrap");
  const maxMb = Number(dropzone.dataset.maxMb || 10);

  function typeBadge(type) {
    const map = { pdf: "badge-red", docx: "badge-blue", txt: "badge-neutral" };
    return `<span class="badge ${map[type] || "badge-neutral"}">${escape(String(type || "").toUpperCase())}</span>`;
  }

  function openModal(modal) {
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }
  function closeModal(modal) {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  function renderEmpty() {
    $("#documentsTable").innerHTML = `
      <div class="empty-state">
        <div class="empty-icon"><i class="fa-regular fa-folder-open"></i></div>
        <div class="empty-title">No documents found</div>
        <div class="empty-text">${state.query || state.type ? "No uploads match the current filters." : "Upload a PDF, DOCX or TXT document to extract its text and start analysing it."}</div>
        <button class="btn btn-primary btn-sm" id="emptyUpload"><i class="fa-solid fa-arrow-up-from-bracket"></i> Upload document</button>
      </div>`;
    $("#emptyUpload")?.addEventListener("click", () => openModal(uploadModal));
    $("#documentsPagination").style.display = "none";
  }

  function renderDocuments(items) {
    if (!items.length) return renderEmpty();
    $("#documentsTable").innerHTML = `
      <table class="table">
        <thead>
          <tr><th>Document</th><th>Type</th><th>Words</th><th>Size</th><th>Uploaded</th><th>Analyses</th><th class="text-right">Actions</th></tr>
        </thead>
        <tbody>
          ${items.map((doc) => `
            <tr>
              <td>
                <div class="table-title">${escape(doc.filename)}</div>
                <div class="table-sub">ID ${doc.id}</div>
              </td>
              <td>${typeBadge(doc.file_type)}</td>
              <td class="tabular">${Number(doc.word_count).toLocaleString()}</td>
              <td class="tabular whitespace-nowrap">${ITA.formatBytes(doc.file_size)}</td>
              <td class="whitespace-nowrap">${ITA.formatDate(doc.created_at)}</td>
              <td><span class="badge badge-neutral">${doc.analysis_count}</span></td>
              <td>
                <div class="table-actions">
                  <a class="icon-btn" href="/workspace/document/${doc.id}" title="Analyse"><i class="fa-solid fa-pen-nib"></i></a>
                  <button class="icon-btn" data-view="${doc.id}" title="View extracted text"><i class="fa-regular fa-eye"></i></button>
                  <button class="icon-btn" data-report="${doc.id}" title="Download PDF report"><i class="fa-solid fa-file-pdf"></i></button>
                  <button class="icon-btn danger" data-delete="${doc.id}" data-name="${escape(doc.filename)}" title="Delete"><i class="fa-regular fa-trash-can"></i></button>
                </div>
              </td>
            </tr>`).join("")}
        </tbody>
      </table>`;

    document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => viewDocument(button.dataset.view)));
    document.querySelectorAll("[data-report]").forEach((button) => button.addEventListener("click", () => ITA.downloadReport({ document_id: Number(button.dataset.report) })));
    document.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", () => deleteDocument(button.dataset.delete, button.dataset.name)));
  }

  function renderPagination(pagination) {
    const wrapper = $("#documentsPagination");
    if (!pagination || pagination.pages <= 1) { wrapper.style.display = "none"; return; }
    wrapper.style.display = "flex";
    wrapper.innerHTML = `
      <span>Showing page ${pagination.page} of ${pagination.pages} · ${pagination.total} document${pagination.total === 1 ? "" : "s"}</span>
      <div class="pagination-buttons">
        <button class="btn btn-secondary btn-sm" ${pagination.has_prev ? "" : "disabled"} data-page="${pagination.page - 1}"><i class="fa-solid fa-chevron-left"></i> Previous</button>
        <button class="btn btn-secondary btn-sm" ${pagination.has_next ? "" : "disabled"} data-page="${pagination.page + 1}">Next <i class="fa-solid fa-chevron-right"></i></button>
      </div>`;
    wrapper.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => {
      state.page = Number(button.dataset.page);
      loadDocuments();
    }));
  }

  async function loadDocuments() {
    const params = new URLSearchParams({ page: state.page, per_page: 12 });
    if (state.query) params.set("q", state.query);
    if (state.type) params.set("file_type", state.type);
    try {
      const { data } = await ITA.api(`/api/documents?${params}`);
      renderDocuments(data.documents);
      renderPagination(data.pagination);
    } catch (error) {
      ITA.toast(error.message, "error");
      $("#documentsTable").innerHTML = `<div class="p-4"><div class="notice notice-danger"><i class="fa-solid fa-circle-exclamation"></i><span>${escape(error.message)}</span></div></div>`;
    }
  }

  async function viewDocument(id) {
    try {
      const { data } = await ITA.api(`/api/documents/${id}`);
      const doc = data.document;
      state.currentDocument = doc;
      $("#documentModalTitle").textContent = doc.filename;
      $("#documentModalMeta").textContent = `${doc.file_type.toUpperCase()} · ${ITA.formatBytes(doc.file_size)} · uploaded ${ITA.formatDate(doc.created_at)}`;
      $("#documentStats").innerHTML = [
        ["Words", Number(doc.word_count).toLocaleString()],
        ["Characters", Number(doc.char_count).toLocaleString()],
        ["Analyses", doc.analyses.length],
        ["File size", ITA.formatBytes(doc.file_size)],
      ].map(([label, value]) => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${escape(value)}</div></div>`).join("");
      $("#documentText").textContent = doc.extracted_text || "";
      $("#analyseFromModal").onclick = () => { window.location.href = `/workspace/document/${doc.id}`; };
      openModal(documentModal);
    } catch (error) {
      ITA.toast(error.message, "error");
    }
  }

  async function deleteDocument(id, name) {
    const confirmed = await ITA.confirm({
      title: "Delete document",
      message: `“${name}” and all of its analysis history will be permanently deleted. This cannot be undone.`,
      confirmLabel: "Delete document",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await ITA.api(`/api/documents/${id}`, { method: "DELETE" });
      ITA.toast("Document deleted.", "success");
      loadDocuments();
    } catch (error) {
      ITA.toast(error.message, "error");
    }
  }

  // --- Upload flow --------------------------------------------------------
  function selectFile(file) {
    if (!file) return;
    const extension = (file.name.split(".").pop() || "").toLowerCase();
    if (!["txt", "pdf", "docx"].includes(extension)) {
      ITA.toast("Only TXT, PDF and DOCX files are supported.", "error");
      return;
    }
    if (file.size > maxMb * 1024 * 1024) {
      ITA.toast(`The file exceeds the ${maxMb} MB limit.`, "error");
      return;
    }
    state.selectedFile = file;
    selectedFile.innerHTML = `
      <div class="file-selected">
        <i class="fa-solid fa-file-lines"></i>
        <div class="min-w-0">
          <div class="file-selected-name text-truncate">${escape(file.name)}</div>
          <div class="file-selected-meta">${ITA.formatBytes(file.size)}</div>
        </div>
        <button class="icon-btn ml-auto" id="removeSelected" aria-label="Remove file"><i class="fa-solid fa-xmark"></i></button>
      </div>`;
    confirmUpload.disabled = false;
    $("#removeSelected").addEventListener("click", () => {
      state.selectedFile = null;
      selectedFile.innerHTML = "";
      confirmUpload.disabled = true;
      fileInput.value = "";
    });
  }

  async function upload() {
    if (!state.selectedFile) return;
    confirmUpload.disabled = true;
    progressWrap.classList.remove("hidden");
    $("#uploadProgressText").textContent = "Uploading and extracting text…";
    const formData = new FormData();
    formData.append("file", state.selectedFile);
    try {
      await ITA.api("/api/documents/upload", { method: "POST", formData });
      $("#uploadProgressText").textContent = "Document processed.";
      ITA.toast("Document uploaded and text extracted.", "success");
      state.selectedFile = null;
      selectedFile.innerHTML = "";
      fileInput.value = "";
      closeModal(uploadModal);
      state.page = 1;
      loadDocuments();
    } catch (error) {
      ITA.toast(error.message, "error", 7000);
      $("#uploadProgressText").textContent = "Upload failed.";
      confirmUpload.disabled = false;
    } finally {
      setTimeout(() => progressWrap.classList.add("hidden"), 600);
    }
  }

  $("#openUpload").addEventListener("click", () => openModal(uploadModal));
  document.querySelectorAll("[data-close-upload]").forEach((button) => button.addEventListener("click", () => closeModal(uploadModal)));
  document.querySelectorAll("[data-close-document]").forEach((button) => button.addEventListener("click", () => closeModal(documentModal)));
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeModal(backdrop);
  }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") document.querySelectorAll(".modal-backdrop.open").forEach((modal) => closeModal(modal));
  });

  $("#confirmUpload").addEventListener("click", upload);
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.click(); } });
  fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove("dragover"); }));
  dropzone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));

  $("#documentSearch").addEventListener("input", ITA.debounce((event) => {
    state.query = event.target.value.trim();
    state.page = 1;
    loadDocuments();
  }, 300));
  $("#documentType").addEventListener("change", (event) => {
    state.type = event.target.value;
    state.page = 1;
    loadDocuments();
  });
  $("#refreshDocuments").addEventListener("click", loadDocuments);

  loadDocuments();
})();
