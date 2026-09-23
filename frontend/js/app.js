(() => {
  "use strict";

  const API = {
    extract: "/api/extract",
    download: "/api/download",
    events: (id) => `/api/download/${id}/events`,
    cancel: (id) => `/api/download/${id}/cancel`,
    file: (id) => `/api/download/${id}/file`,
    history: "/api/history",
    historyItem: (id) => `/api/history/${id}`,
    redownload: (id) => `/api/history/${id}/redownload`,
  };

  const PLATFORMS = [
    { key: "youtube", icon: "▶️", re: /(^|\.)youtube\.com$|^youtu\.be$/i },
    { key: "tiktok", icon: "🎵", re: /(^|\.)tiktok\.com$/i },
    { key: "instagram", icon: "📸", re: /(^|\.)instagram\.com$/i },
    { key: "twitter", icon: "🐦", re: /(^|\.)(twitter\.com|x\.com)$/i },
    { key: "facebook", icon: "📘", re: /(^|\.)(facebook\.com|fb\.watch)$/i },
    { key: "telegram", icon: "✈️", re: /(^|\.)(t\.me|telegram\.org|telegram\.me)$/i },
    { key: "vimeo", icon: "🎬", re: /(^|\.)vimeo\.com$/i },
    { key: "soundcloud", icon: "🎧", re: /(^|\.)soundcloud\.com$/i },
  ];

  const el = (id) => document.getElementById(id);

  const urlInput = el("url-input");
  const urlForm = el("url-form");
  const urlHint = el("url-hint");
  const platformIconEl = el("platform-icon");
  const fetchBtn = el("fetch-btn");
  const pasteBtn = el("paste-btn");
  const errorBanner = el("error-banner");
  const mediaPreview = el("media-preview");
  const mediaThumb = el("media-thumb");
  const mediaTitle = el("media-title");
  const mediaMeta = el("media-meta");
  const formatList = el("format-list");
  const videoFormatsEl = el("video-formats");
  const audioFormatsEl = el("audio-formats");
  const activeDownload = el("active-download");
  const progressTitle = el("progress-title");
  const progressBar = el("progress-bar");
  const progressPercent = el("progress-percent");
  const progressSpeed = el("progress-speed");
  const progressEta = el("progress-eta");
  const cancelBtn = el("cancel-btn");
  const downloadActions = el("download-actions");
  const saveLink = el("save-link");
  const retryBtn = el("retry-btn");
  const historyList = el("history-list");
  const historyEmpty = el("history-empty");
  const clearHistoryBtn = el("clear-history-btn");

  const formatBtnTemplate = el("format-btn-template");
  const historyItemTemplate = el("history-item-template");

  let currentExtraction = null;
  let currentEventSource = null;
  let currentJobId = null;
  let lastDownloadRequest = null;

  // ---------------------------------------------------------------- tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      el(btn.dataset.tab).classList.add("active");
      if (btn.dataset.tab === "history") loadHistory();
    });
  });

  // ---------------------------------------------------------------- validation
  function detectPlatform(rawUrl) {
    try {
      const u = new URL(rawUrl);
      const host = u.hostname.toLowerCase();
      for (const p of PLATFORMS) {
        if (p.re.test(host)) return p;
      }
      return { key: "generic", icon: "🔗" };
    } catch {
      return null;
    }
  }

  function validateUrl(rawUrl) {
    const value = rawUrl.trim();
    if (!value) return { valid: false, message: "" };
    let parsed;
    try {
      parsed = new URL(value);
    } catch {
      return { valid: false, message: "This doesn't look like a valid URL." };
    }
    if (!/^https?:$/.test(parsed.protocol)) {
      return { valid: false, message: "Only http:// and https:// links are supported." };
    }
    return { valid: true, message: `Looks good — ${detectPlatform(value)?.key || "generic"} link detected.` };
  }

  urlInput.addEventListener("input", () => {
    const value = urlInput.value;
    const platform = detectPlatform(value.trim());
    platformIconEl.textContent = platform ? platform.icon : "🔗";
    const result = validateUrl(value);
    urlHint.textContent = result.message;
    urlHint.classList.toggle("valid", result.valid);
    urlHint.classList.toggle("invalid", !result.valid && value.trim().length > 0);
  });

  pasteBtn.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        urlInput.dispatchEvent(new Event("input"));
      }
    } catch {
      urlHint.textContent = "Clipboard access denied — paste manually.";
      urlHint.classList.add("invalid");
    }
  });

  // ---------------------------------------------------------------- errors
  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = false;
  }

  function hideError() {
    errorBanner.hidden = true;
    errorBanner.textContent = "";
  }

  async function parseErrorResponse(response) {
    try {
      const data = await response.json();
      return data.message || data.detail || `Request failed (${response.status}).`;
    } catch {
      return `Request failed (${response.status}).`;
    }
  }

  // ---------------------------------------------------------------- extract
  function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return "";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024;
      i++;
    }
    return `${value.toFixed(1)} ${units[i]}`;
  }

  function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return "";
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return h > 0
      ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
      : `${m}:${String(sec).padStart(2, "0")}`;
  }

  function renderFormats(data) {
    videoFormatsEl.innerHTML = "";
    audioFormatsEl.innerHTML = "";
    const videoFormats = data.formats.filter((f) => f.type === "video");
    const audioFormats = data.formats.filter((f) => f.type === "audio");

    const makeBtn = (fmt) => {
      const node = formatBtnTemplate.content.cloneNode(true);
      const btn = node.querySelector(".format-btn");
      node.querySelector(".format-label").textContent = fmt.label;
      const metaParts = [fmt.ext.toUpperCase()];
      if (fmt.filesize) metaParts.push(formatBytes(fmt.filesize));
      if (fmt.requires_merge) metaParts.push("merged w/ audio");
      node.querySelector(".format-meta").textContent = metaParts.join(" · ");
      btn.addEventListener("click", () => beginDownload(fmt));
      return node;
    };

    videoFormats.forEach((f) => videoFormatsEl.appendChild(makeBtn(f)));
    audioFormats.forEach((f) => audioFormatsEl.appendChild(makeBtn(f)));
    formatList.hidden = false;
  }

  function renderPreview(data) {
    mediaPreview.hidden = false;
    mediaThumb.src = data.thumbnail || "/app/icons/icon.png";
    mediaTitle.textContent = data.title;
    const bits = [`${data.platform_icon} ${data.platform_label}`];
    if (data.uploader) bits.push(data.uploader);
    if (data.duration) bits.push(formatDuration(data.duration));
    mediaMeta.textContent = bits.join(" · ");
  }

  urlForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideError();
    const rawUrl = urlInput.value.trim();
    const validation = validateUrl(rawUrl);
    if (!validation.valid) {
      showError(validation.message || "Please enter a valid URL.");
      return;
    }

    fetchBtn.disabled = true;
    fetchBtn.querySelector(".spinner").hidden = false;
    formatList.hidden = true;
    mediaPreview.hidden = true;
    activeDownload.hidden = true;

    try {
      const response = await fetch(API.extract, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: rawUrl }),
      });
      if (!response.ok) {
        showError(await parseErrorResponse(response));
        return;
      }
      const data = await response.json();
      currentExtraction = data;
      renderPreview(data);
      renderFormats(data);
    } catch (err) {
      showError("Network error: could not reach the Allin1 server. Check your connection and try again.");
    } finally {
      fetchBtn.disabled = false;
      fetchBtn.querySelector(".spinner").hidden = true;
    }
  });

  // ---------------------------------------------------------------- download + SSE
  function resetProgressUI() {
    progressBar.style.width = "0%";
    progressPercent.textContent = "0%";
    progressSpeed.textContent = "";
    progressEta.textContent = "";
    downloadActions.hidden = true;
    retryBtn.hidden = true;
    cancelBtn.hidden = false;
    cancelBtn.disabled = false;
  }

  async function beginDownload(fmt) {
    if (!currentExtraction) return;
    hideError();
    activeDownload.hidden = false;
    resetProgressUI();
    progressTitle.textContent = `Downloading ${fmt.label}…`;

    const requestBody = {
      url: currentExtraction.webpage_url,
      format_id: fmt.format_id,
      media_type: fmt.type,
      ext: fmt.ext,
      requires_merge: !!fmt.requires_merge,
      title: currentExtraction.title,
      thumbnail: currentExtraction.thumbnail,
      platform_key: currentExtraction.platform_key,
      platform_label: currentExtraction.platform_label,
    };
    lastDownloadRequest = requestBody;

    try {
      const response = await fetch(API.download, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) {
        showError(await parseErrorResponse(response));
        activeDownload.hidden = true;
        return;
      }
      const { job_id } = await response.json();
      currentJobId = job_id;
      subscribeToJob(job_id);
    } catch (err) {
      showError("Network error: could not start the download.");
      activeDownload.hidden = true;
    }
  }

  function subscribeToJob(jobId) {
    if (currentEventSource) currentEventSource.close();
    // EventSource cannot send headers, so the API key rides along as ?key=.
    const source = new EventSource(API.events(jobId) + (window.Allin1Auth?.query() || ""));
    currentEventSource = source;

    source.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      updateProgressUI(payload);
      if (["completed", "error", "canceled"].includes(payload.status)) {
        source.close();
        currentEventSource = null;
        if (payload.status === "completed") loadHistory();
      }
    };

    source.onerror = () => {
      source.close();
      currentEventSource = null;
    };
  }

  function updateProgressUI(payload) {
    if (payload.percent !== undefined) {
      progressBar.style.width = `${payload.percent}%`;
      progressPercent.textContent = `${payload.percent}%`;
    }
    if (payload.speed) progressSpeed.textContent = `${formatBytes(payload.speed)}/s`;
    if (payload.eta !== undefined && payload.eta !== null) progressEta.textContent = `ETA ${payload.eta}s`;

    if (payload.status === "processing") {
      progressTitle.textContent = "Processing (ffmpeg)…";
    } else if (payload.status === "completed") {
      progressTitle.textContent = "Download complete";
      progressBar.style.width = "100%";
      progressPercent.textContent = "100%";
      cancelBtn.hidden = true;
      downloadActions.hidden = false;
      // Plain <a download> links cannot send headers either.
      saveLink.href = API.file(payload.job_id) + (window.Allin1Auth?.query() || "");
      retryBtn.hidden = true;
    } else if (payload.status === "canceled") {
      progressTitle.textContent = "Canceled";
      cancelBtn.hidden = true;
      downloadActions.hidden = false;
      saveLink.hidden = true;
      retryBtn.hidden = false;
    } else if (payload.status === "error") {
      progressTitle.textContent = "Download failed";
      cancelBtn.hidden = true;
      downloadActions.hidden = false;
      saveLink.hidden = true;
      retryBtn.hidden = false;
      showError(payload.error?.message || "The download failed.");
    }
  }

  cancelBtn.addEventListener("click", async () => {
    if (!currentJobId) return;
    cancelBtn.disabled = true;
    try {
      await fetch(API.cancel(currentJobId), { method: "POST" });
    } catch {
      /* SSE stream will still report the final state */
    }
  });

  retryBtn.addEventListener("click", async () => {
    if (!lastDownloadRequest) return;
    hideError();
    resetProgressUI();
    saveLink.hidden = false;
    activeDownload.hidden = false;
    progressTitle.textContent = "Retrying…";
    try {
      const response = await fetch(API.download, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastDownloadRequest),
      });
      if (!response.ok) {
        showError(await parseErrorResponse(response));
        return;
      }
      const { job_id } = await response.json();
      currentJobId = job_id;
      subscribeToJob(job_id);
    } catch {
      showError("Network error while retrying the download.");
    }
  });

  // ---------------------------------------------------------------- history
  async function loadHistory() {
    try {
      const response = await fetch(API.history);
      if (!response.ok) throw new Error("failed");
      const items = await response.json();
      renderHistory(items);
    } catch {
      historyEmpty.hidden = false;
      historyEmpty.textContent = "Could not load history right now.";
    }
  }

  function statusLabel(status) {
    return {
      queued: "Queued",
      downloading: "Downloading…",
      processing: "Processing…",
      completed: "Completed",
      error: "Failed",
      canceled: "Canceled",
    }[status] || status;
  }

  function renderHistory(items) {
    historyList.innerHTML = "";
    historyEmpty.hidden = items.length > 0;
    historyEmpty.textContent = "No downloads yet. Fetch a link to get started!";

    for (const item of items) {
      const node = historyItemTemplate.content.cloneNode(true);
      node.querySelector(".history-thumb").src = item.thumbnail || "/app/icons/icon.png";
      node.querySelector(".history-platform").textContent = platformIconFor(item.platform_key);
      node.querySelector(".history-title").textContent = item.title || item.url;
      node.querySelector(".history-sub").textContent = `${item.platform_label || "Direct"} · ${(item.format_id || "").toUpperCase()}`;
      const statusEl = node.querySelector(".history-status");
      statusEl.textContent = statusLabel(item.status) + (item.error_message ? `: ${item.error_message}` : "");
      statusEl.classList.add(item.status);

      node.querySelector(".redownload-btn").addEventListener("click", () => redownloadItem(item.id));
      node.querySelector(".delete-btn").addEventListener("click", () => deleteItem(item.id));
      historyList.appendChild(node);
    }
  }

  function platformIconFor(key) {
    const found = PLATFORMS.find((p) => p.key === key);
    return found ? found.icon : "🔗";
  }

  async function redownloadItem(id) {
    try {
      const response = await fetch(API.redownload(id), { method: "POST" });
      if (!response.ok) {
        showError(await parseErrorResponse(response));
        return;
      }
      await loadHistory();
    } catch {
      showError("Network error while re-downloading.");
    }
  }

  async function deleteItem(id) {
    try {
      await fetch(API.historyItem(id), { method: "DELETE" });
      await loadHistory();
    } catch {
      showError("Network error while deleting history item.");
    }
  }

  clearHistoryBtn.addEventListener("click", async () => {
    if (!confirm("Clear the entire download history? This also deletes saved files on the server.")) return;
    try {
      await fetch(API.history, { method: "DELETE" });
      await loadHistory();
    } catch {
      showError("Network error while clearing history.");
    }
  });

  // ---------------------------------------------------------------- PWA
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    });
  }

  loadHistory();
})();
