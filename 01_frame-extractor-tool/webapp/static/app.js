// ────────────────────────────── F-2: shared fetch helper + theme ──────────────────────────────

async function apiFetch(path, opts) {
  opts = opts || {};
  return fetch(path, opts);
}

// ── Theme ──

function applyTheme(pref) {
  if (pref === "dark" || pref === "light") {
    document.documentElement.setAttribute("data-theme", pref);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  localStorage.setItem("theme_preference", pref);
  updateThemePopoverSelection(pref);
}

function updateThemePopoverSelection(pref) {
  document.querySelectorAll("#theme-popover button").forEach((btn) => {
    btn.classList.toggle("selected", btn.dataset.themeChoice === pref);
  });
}

document.getElementById("theme-btn").addEventListener("click", () => {
  document.getElementById("theme-popover").classList.toggle("open");
});

document.querySelectorAll("#theme-popover button").forEach((btn) => {
  btn.addEventListener("click", () => {
    applyTheme(btn.dataset.themeChoice);
    document.getElementById("theme-popover").classList.remove("open");
  });
});

document.addEventListener("click", (e) => {
  const popover = document.getElementById("theme-popover");
  const themeBtn = document.getElementById("theme-btn");
  if (!popover.contains(e.target) && e.target !== themeBtn && !themeBtn.contains(e.target)) {
    popover.classList.remove("open");
  }
});

if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const pref = localStorage.getItem("theme_preference") || "system";
    if (pref === "system") {
      // CSS @media handles the visual update automatically; nothing to do here.
    }
  });
}

updateThemePopoverSelection(localStorage.getItem("theme_preference") || "system");

// ────────────────────────────── Tab switching ──────────────────────────────

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll("main > section").forEach((section) => {
    section.classList.toggle("hidden", section.id !== `${name}-section`);
  });
  document.querySelector("main").classList.toggle("wide", name === "annotate");
  if (name === "export") refreshExportPreview();
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.disabled) return;
    switchTab(btn.dataset.tab);
  });
});

// ────────────────────────────── F-3: Extract section ──────────────────────────────

let uploadedVideos = [];

document.getElementById("video-file-input").addEventListener("change", async (e) => {
  const files = e.target.files;
  if (!files.length) return;

  const formData = new FormData();
  for (const f of files) formData.append("files", f);

  const res = await apiFetch("/api/videos", { method: "POST", body: formData });
  if (res.ok) {
    await refreshVideoList();
  } else {
    const body = await res.json().catch(() => ({}));
    alert(body.detail || "Upload failed");
  }
  e.target.value = "";
});

async function refreshVideoList() {
  const res = await apiFetch("/api/videos");
  if (!res.ok) return;
  const data = await res.json();
  uploadedVideos = data.videos;
  const list = document.getElementById("video-list");
  list.innerHTML = "";
  uploadedVideos.forEach((v) => {
    const li = document.createElement("li");
    const sizeMb = (v.size_bytes / (1024 * 1024)).toFixed(1);
    const nameSpan = document.createElement("span");
    nameSpan.textContent = `${v.filename} (${sizeMb} MB)`;
    li.appendChild(nameSpan);
    const delBtn = document.createElement("button");
    delBtn.textContent = "Remove";
    delBtn.addEventListener("click", async () => {
      await apiFetch(`/api/videos/${v.id}`, { method: "DELETE" });
      refreshVideoList();
    });
    li.appendChild(delBtn);
    list.appendChild(li);
  });
}

// Mode field toggling — "All Frames" mode ignores compare/blur/max-attempts server-side,
// so grey those out client-side too (matches app.py's ExtractionTab behavior).
function updateModeDependentFields() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  document.getElementById("target-field").classList.toggle("hidden", mode !== "target");
  document.getElementById("interval-field").classList.toggle("hidden", mode !== "interval");

  const isAll = mode === "all";
  ["compare-method", "similarity-threshold", "filter-blur", "blur-threshold", "max-attempts"].forEach(
    (id) => {
      document.getElementById(id).disabled = isAll;
    }
  );
}

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", updateModeDependentFields);
});
updateModeDependentFields();

let currentExtractJobId = null;
let pollTimer = null;

document.getElementById("extract-start-btn").addEventListener("click", async () => {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const endSecValue = document.getElementById("end-sec").value;
  const resizeValue = document.getElementById("resize-max-px").value;
  const body = {
    video_ids: uploadedVideos.map((v) => v.id),
    mode: mode,
    interval_sec: parseFloat(document.getElementById("interval-sec").value),
    target_frames: parseInt(document.getElementById("target-frames").value, 10),
    compare_method: document.getElementById("compare-method").value,
    similarity_threshold: parseFloat(document.getElementById("similarity-threshold").value),
    filter_blur: document.getElementById("filter-blur").checked,
    blur_threshold: parseFloat(document.getElementById("blur-threshold").value),
    prefix: document.getElementById("prefix").value,
    max_attempts_per_slot: parseInt(document.getElementById("max-attempts").value, 10),
    separate_per_video: document.getElementById("separate-per-video").checked,
    start_sec: parseFloat(document.getElementById("start-sec").value) || 0,
    end_sec: endSecValue ? parseFloat(endSecValue) : null,
    resize_max_px: resizeValue ? parseInt(resizeValue, 10) : null,
  };

  const res = await apiFetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    alert(errBody.detail || "Failed to start extraction");
    return;
  }

  const data = await res.json();
  currentExtractJobId = data.job_id;
  document.getElementById("extract-start-btn").disabled = true;
  document.getElementById("extract-stop-btn").classList.remove("hidden");
  document.getElementById("extract-progress-wrap").classList.remove("hidden");
  document.getElementById("extract-log").innerHTML = "";
  document.getElementById("download-zip-btn").classList.add("hidden");
  startPolling();
});

document.getElementById("download-zip-btn").addEventListener("click", () => {
  if (!currentExtractJobId) return;
  window.location.href = `/api/extract/${currentExtractJobId}/zip`;
});

document.getElementById("extract-stop-btn").addEventListener("click", async () => {
  if (!currentExtractJobId) return;
  await apiFetch(`/api/extract/${currentExtractJobId}/stop`, { method: "POST" });
});

function classifyLogLine(line) {
  if (line.includes("[saved]") || line.includes("[detected]") || line.includes("เสร็จ")) return "log-ok";
  if (line.includes("[skip]") || line.includes("[empty]")) return "log-skip";
  if (line.includes("[blur]")) return "log-blur";
  if (line.includes("[error]")) return "log-skip";
  return "log-info";
}

function startPolling() {
  let lastLogLength = 0;
  pollTimer = setInterval(async () => {
    const res = await apiFetch(`/api/extract/${currentExtractJobId}`);
    if (!res.ok) return;
    const job = await res.json();

    document.getElementById("extract-progress-fill").style.width = job.progress + "%";
    document.getElementById("extract-progress-label").textContent =
      job.status + " — " + job.progress + "%";

    const logEl = document.getElementById("extract-log");
    for (let i = lastLogLength; i < job.log.length; i++) {
      const div = document.createElement("div");
      div.className = "log-line " + classifyLogLine(job.log[i]);
      div.textContent = job.log[i];
      logEl.appendChild(div);
    }
    lastLogLength = job.log.length;
    logEl.scrollTop = logEl.scrollHeight;

    if (job.status === "done" || job.status === "stopped") {
      clearInterval(pollTimer);
      document.getElementById("extract-start-btn").disabled = false;
      document.getElementById("extract-stop-btn").classList.add("hidden");
      document.getElementById("extract-progress-label").textContent =
        job.status + " — " + job.saved_total + " frames saved";
      document.getElementById("download-zip-btn").classList.toggle("hidden", job.saved_total === 0);
      lastExtractedFrameIds = job.frame_ids || [];
      updateDetectFramesInfo();
    }
  }, 1000);
}

// ────────────────────────────── F-4: Detect section ──────────────────────────────

let lastExtractedFrameIds = [];
let classColors = {};
let currentDetectJobId = null;
let detectPollTimer = null;
let detectFrames = [];
let detectPreviewIdx = 0;

function updateDetectFramesInfo() {
  const info = document.getElementById("detect-frames-info");
  const startBtn = document.getElementById("detect-start-btn");
  if (lastExtractedFrameIds.length) {
    info.textContent = `${lastExtractedFrameIds.length} frames ready from the last Extract run.`;
    startBtn.disabled = false;
  } else {
    info.textContent = "No frames yet — run Extract first.";
    startBtn.disabled = true;
  }
}

async function refreshModelOptions() {
  const res = await apiFetch("/api/models");
  if (!res.ok) return;
  const data = await res.json();
  const list = document.getElementById("model-datalist");
  list.innerHTML = "";
  data.models.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    list.appendChild(opt);
  });
}

let classNames = [];

async function refreshClasses() {
  const res = await apiFetch("/api/classes");
  if (!res.ok) return;
  const data = await res.json();
  classColors = data.class_colors || {};
  classNames = data.class_names || [];
  populateAnnotateClassSelect();
}

function updateBackendFields() {
  const backend = document.querySelector('input[name="detect-backend"]:checked').value;
  document.getElementById("local-fields").classList.toggle("hidden", backend !== "local");
  document.getElementById("roboflow-fields").classList.toggle("hidden", backend !== "roboflow");
}

document.querySelectorAll('input[name="detect-backend"]').forEach((el) => {
  el.addEventListener("change", updateBackendFields);
});
updateBackendFields();

function confirmRoboflowCall(frameCount) {
  return window.confirm(
    `This will send ${frameCount} frame(s) to the Roboflow Cloud API and may consume API credits. Continue?`
  );
}

document.getElementById("detect-conf").addEventListener("input", (e) => {
  document.getElementById("detect-conf-label").textContent = e.target.value;
});
document.getElementById("detect-iou").addEventListener("input", (e) => {
  document.getElementById("detect-iou-label").textContent = e.target.value;
});

document.getElementById("detect-start-btn").addEventListener("click", async () => {
  const backend = document.querySelector('input[name="detect-backend"]:checked').value;

  const body = {
    frame_ids: lastExtractedFrameIds,
    backend,
    model_path: document.getElementById("model-path").value,
    conf: parseFloat(document.getElementById("detect-conf").value),
    iou: parseFloat(document.getElementById("detect-iou").value),
    device: document.querySelector('input[name="device"]:checked').value,
  };

  if (backend === "roboflow") {
    const apiKey = document.getElementById("rf-api-key").value.trim();
    if (!apiKey) {
      alert("Please enter a Roboflow API Key first");
      return;
    }
    if (!confirmRoboflowCall(lastExtractedFrameIds.length)) return;
    body.api_key = apiKey;
    body.workspace_name = document.getElementById("rf-workspace").value.trim();
    body.workflow_id = document.getElementById("rf-workflow-id").value.trim();
  }

  const res = await apiFetch("/api/detect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    alert(errBody.detail || "Failed to start detection");
    return;
  }

  const data = await res.json();
  currentDetectJobId = data.job_id;
  document.getElementById("detect-start-btn").disabled = true;
  document.getElementById("detect-stop-btn").classList.remove("hidden");
  document.getElementById("detect-progress-wrap").classList.remove("hidden");
  document.getElementById("detect-log").innerHTML = "";
  document.getElementById("detect-preview-wrap").classList.add("hidden");
  startDetectPolling();
});

document.getElementById("detect-stop-btn").addEventListener("click", async () => {
  if (!currentDetectJobId) return;
  await apiFetch(`/api/detect/${currentDetectJobId}/stop`, { method: "POST" });
});

function startDetectPolling() {
  let lastLogLength = 0;
  detectPollTimer = setInterval(async () => {
    const res = await apiFetch(`/api/detect/${currentDetectJobId}`);
    if (!res.ok) return;
    const job = await res.json();

    document.getElementById("detect-progress-fill").style.width = job.progress + "%";
    document.getElementById("detect-progress-label").textContent =
      job.status + " — " + job.progress + "%";

    const logEl = document.getElementById("detect-log");
    for (let i = lastLogLength; i < job.log.length; i++) {
      const div = document.createElement("div");
      div.className = "log-line " + classifyLogLine(job.log[i]);
      div.textContent = job.log[i];
      logEl.appendChild(div);
    }
    lastLogLength = job.log.length;
    logEl.scrollTop = logEl.scrollHeight;

    if (job.status === "done" || job.status === "stopped") {
      clearInterval(detectPollTimer);
      document.getElementById("detect-start-btn").disabled = false;
      document.getElementById("detect-stop-btn").classList.add("hidden");
      document.getElementById("detect-progress-label").textContent =
        job.status + " — " + job.detected_total + "/" + job.frame_ids.length + " frames with objects";
      await loadDetectFrames(job.frame_ids);
    }
  }, 1000);
}

async function loadDetectFrames(frameIds) {
  if (!frameIds || !frameIds.length || !currentDetectJobId) return;
  const res = await apiFetch(`/api/detect/${currentDetectJobId}/frames`);
  if (!res.ok) return;
  const data = await res.json();
  detectFrames = data.frames;
  detectPreviewIdx = 0;
  if (detectFrames.length) {
    document.getElementById("detect-preview-wrap").classList.remove("hidden");
    showDetectPreview(0);
  }
  initAnnotateFrames(data.frames);
  refreshExportPreview();
}

function showDetectPreview(idx) {
  if (!detectFrames.length) return;
  detectPreviewIdx = Math.max(0, Math.min(idx, detectFrames.length - 1));
  const frame = detectFrames[detectPreviewIdx];
  document.getElementById("detect-preview-img").src = `/api/frames/${frame.id}/preview.jpg?t=${Date.now()}`;
  document.getElementById("detect-nav-label").textContent =
    `Frame ${detectPreviewIdx + 1} / ${detectFrames.length}`;
  renderDetectionChips(frame.detections || []);
}

document.getElementById("detect-prev-btn").addEventListener("click", () => showDetectPreview(detectPreviewIdx - 1));
document.getElementById("detect-next-btn").addEventListener("click", () => showDetectPreview(detectPreviewIdx + 1));

function renderDetectionChips(detections) {
  const container = document.getElementById("detect-chips");
  container.innerHTML = "";

  if (!detections.length) {
    const span = document.createElement("span");
    span.style.color = "var(--muted)";
    span.textContent = "— no objects detected —";
    container.appendChild(span);
    return;
  }

  let hasLowConf = false;
  detections.forEach((d) => {
    const chip = document.createElement("span");
    const isLow = d.confidence < 0.5;
    if (isLow) hasLowConf = true;
    chip.className = "chip" + (isLow ? " chip-warn" : "");
    const color = classColors[d.class_name] || "#AAAAAA";
    const dot = document.createElement("span");
    dot.style.color = color;
    dot.textContent = "●";
    chip.appendChild(dot);
    chip.appendChild(document.createTextNode(` ${d.class_name} ${d.confidence.toFixed(2)}`));
    container.appendChild(chip);
  });

  if (hasLowConf) {
    const warn = document.createElement("span");
    warn.style.color = "var(--highlight)";
    warn.textContent = "⚠️ Low Confidence";
    container.appendChild(warn);
  }
}

// ────────────────────────────── S-5: Annotate section ──────────────────────────────

let annotateFrames = [];
let annotateIdx = -1;
let annotateImg = null;
let annotateBoxes = [];
let annotateDragStart = null;

const annotateCanvas = document.getElementById("annotate-canvas");
const annotateCtx = annotateCanvas.getContext("2d");

function populateAnnotateClassSelect() {
  const select = document.getElementById("annotate-class-select");
  select.innerHTML = "";
  classNames.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });
}

function initAnnotateFrames(frames) {
  annotateFrames = frames || [];
  document.getElementById("annotate-frames-info").classList.toggle("hidden", annotateFrames.length > 0);
  document.getElementById("annotate-toolbar").classList.toggle("hidden", annotateFrames.length === 0);
  document.getElementById("annotate-workspace").classList.toggle("hidden", annotateFrames.length === 0);
  if (annotateFrames.length) {
    selectAnnotateFrame(0);
  } else {
    annotateIdx = -1;
    renderAnnotateFilmstrip();
  }
}

function frameBasename(path) {
  return path.split(/[\\/]/).pop();
}

function renderAnnotateFilmstrip() {
  const list = document.getElementById("annotate-filmstrip-list");
  list.innerHTML = "";
  annotateFrames.forEach((frame, idx) => {
    const li = document.createElement("li");
    const status = frame.reviewed ? "✅" : "🔴";
    li.textContent = `${status} ${frameBasename(frame.path)}`;
    li.className = idx === annotateIdx ? "selected" : "";
    li.addEventListener("click", () => selectAnnotateFrame(idx));
    list.appendChild(li);
  });
}

function updateAnnotateReviewStatus() {
  const frame = annotateFrames[annotateIdx];
  document.getElementById("annotate-review-status").textContent = frame.reviewed
    ? "✅ Reviewed"
    : "🔴 Needs Review";
}

function selectAnnotateFrame(idx) {
  annotateIdx = idx;
  const frame = annotateFrames[idx];
  annotateBoxes = (frame.detections || []).map((d) => ({ ...d }));
  renderAnnotateFilmstrip();
  updateAnnotateReviewStatus();
  loadAnnotateImage(frame);
}

function loadAnnotateImage(frame) {
  const idxAtLoad = annotateIdx;
  const img = new Image();
  img.onload = () => {
    if (annotateIdx !== idxAtLoad) return; // user navigated away before this finished loading
    annotateImg = img;
    annotateCanvas.width = img.naturalWidth;
    annotateCanvas.height = img.naturalHeight;
    drawAnnotateCanvas();
  };
  img.src = `/api/frames/${frame.id}/image.jpg?t=${Date.now()}`;
}

function drawAnnotateCanvas() {
  if (!annotateImg) return;
  annotateCtx.drawImage(annotateImg, 0, 0, annotateCanvas.width, annotateCanvas.height);
  annotateBoxes.forEach(drawAnnotateBox);
}

function drawAnnotateBox(d) {
  const w = annotateCanvas.width;
  const h = annotateCanvas.height;
  const x1 = (d.x_center - d.width / 2) * w;
  const y1 = (d.y_center - d.height / 2) * h;
  const bw = d.width * w;
  const bh = d.height * h;
  const color = classColors[d.class_name] || "#AAAAAA";
  annotateCtx.strokeStyle = color;
  annotateCtx.lineWidth = 2;
  annotateCtx.strokeRect(x1, y1, bw, bh);
  annotateCtx.fillStyle = color;
  annotateCtx.font = "13px sans-serif";
  annotateCtx.fillText(d.class_name, x1, y1 - 4 > 10 ? y1 - 4 : y1 + 12);
}

function canvasPointFromEvent(e) {
  const rect = annotateCanvas.getBoundingClientRect();
  const scaleX = annotateCanvas.width / rect.width;
  const scaleY = annotateCanvas.height / rect.height;
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY,
  };
}

annotateCanvas.addEventListener("mousedown", (e) => {
  if (annotateIdx < 0) return;
  annotateDragStart = canvasPointFromEvent(e);
});

annotateCanvas.addEventListener("mousemove", (e) => {
  if (!annotateDragStart) return;
  const p = canvasPointFromEvent(e);
  drawAnnotateCanvas();
  const color = classColors[document.getElementById("annotate-class-select").value] || "#AAAAAA";
  annotateCtx.strokeStyle = color;
  annotateCtx.lineWidth = 2;
  annotateCtx.strokeRect(
    Math.min(annotateDragStart.x, p.x),
    Math.min(annotateDragStart.y, p.y),
    Math.abs(p.x - annotateDragStart.x),
    Math.abs(p.y - annotateDragStart.y)
  );
});

annotateCanvas.addEventListener("mouseup", (e) => {
  if (!annotateDragStart) return;
  const start = annotateDragStart;
  const end = canvasPointFromEvent(e);
  annotateDragStart = null;

  // discard accidental-click boxes under 5px in either dimension (matches app.py's AnnotationTab)
  if (Math.abs(end.x - start.x) < 5 || Math.abs(end.y - start.y) < 5) {
    drawAnnotateCanvas();
    return;
  }

  const w = annotateCanvas.width;
  const h = annotateCanvas.height;
  const x1 = Math.min(start.x, end.x);
  const x2 = Math.max(start.x, end.x);
  const y1 = Math.min(start.y, end.y);
  const y2 = Math.max(start.y, end.y);
  const className = document.getElementById("annotate-class-select").value;

  annotateBoxes.push({
    class_id: classNames.indexOf(className),
    class_name: className,
    confidence: 1.0,
    x_center: (x1 + x2) / 2 / w,
    y_center: (y1 + y2) / 2 / h,
    width: (x2 - x1) / w,
    height: (y2 - y1) / h,
  });
  drawAnnotateCanvas();
});

document.getElementById("annotate-clear-btn").addEventListener("click", () => {
  if (annotateIdx < 0) return;
  annotateBoxes = [];
  drawAnnotateCanvas();
});

document.getElementById("annotate-save-btn").addEventListener("click", async () => {
  if (annotateIdx < 0) return;
  const frame = annotateFrames[annotateIdx];

  const res = await apiFetch(`/api/frames/${frame.id}/detections`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ detections: annotateBoxes }),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    alert(errBody.detail || "Failed to save annotations");
    return;
  }
  const saved = await res.json();
  frame.detections = saved.detections;

  // mirror app.py's _save_changes(), which always calls _mark_reviewed() too
  const reviewRes = await apiFetch(`/api/frames/${frame.id}/review`, { method: "POST" });
  if (reviewRes.ok) {
    frame.reviewed = true;
    updateAnnotateReviewStatus();
    renderAnnotateFilmstrip();
  }
  alert("Saved");
});

document.getElementById("annotate-mark-reviewed-btn").addEventListener("click", async () => {
  if (annotateIdx < 0) return;
  const frame = annotateFrames[annotateIdx];
  const res = await apiFetch(`/api/frames/${frame.id}/review`, { method: "POST" });
  if (!res.ok) return;
  frame.reviewed = true;
  updateAnnotateReviewStatus();
  renderAnnotateFilmstrip();
});

// ────────────────────────────── S-6: Export section ──────────────────────────────

let currentExportJobId = null;
let exportPollTimer = null;
let exportPoolTotal = 0;

async function refreshExportPreview() {
  if (!currentDetectJobId) {
    exportPoolTotal = 0;
    document.getElementById("export-frames-info").textContent = "No detected frames yet — run Detect first.";
    document.getElementById("export-start-btn").disabled = true;
    return;
  }
  const reviewedOnly = document.getElementById("export-reviewed-only").checked;
  const res = await apiFetch(`/api/export/preview?detect_job_id=${currentDetectJobId}&reviewed_only=${reviewedOnly}`);
  if (!res.ok) return;
  const stats = await res.json();
  exportPoolTotal = stats.total;
  document.getElementById("export-frames-info").textContent = `${stats.total} frame(s) available from the last Detect run.`;
  document.getElementById("export-stat-total").textContent = stats.total;
  document.getElementById("export-stat-classes").textContent = stats.class_count;
  document.getElementById("export-stat-unreviewed").textContent = stats.unreviewed;
  document.getElementById("export-start-btn").disabled = stats.total === 0;
  updateExportMaxSizeLabel();
}

document.getElementById("export-reviewed-only").addEventListener("change", refreshExportPreview);

function updateExportSplitLabel() {
  const trEl = document.getElementById("export-train-pct");
  const vaEl = document.getElementById("export-val-pct");
  const tr = parseInt(trEl.value, 10);
  let va = parseInt(vaEl.value, 10);
  if (tr + va > 100) {
    va = 100 - tr;
    vaEl.value = va;
  }
  const te = 100 - tr - va;
  document.getElementById("export-train-pct-label").textContent = tr;
  document.getElementById("export-val-pct-label").textContent = va;
  document.getElementById("export-split-summary").textContent = `${tr}% Train / ${va}% Val / ${te}% Test`;
  updateExportMaxSizeLabel();
}

function updateExportMaxSizeLabel() {
  const total = exportPoolTotal;
  const tr = parseInt(document.getElementById("export-train-pct").value, 10) / 100;
  const va = parseInt(document.getElementById("export-val-pct").value, 10) / 100;
  const trainCount = Math.floor(total * tr);
  const valCount = Math.floor(total * va);
  const testCount = total - trainCount - valCount;
  const mult = parseInt(document.getElementById("export-aug-multiplier").value, 10);
  const finalSize = trainCount * mult + valCount + testCount;
  document.getElementById("export-max-size-label").textContent = `Maximum Version Size: ${finalSize} images (${mult}x)`;
}

["export-train-pct", "export-val-pct"].forEach((id) => {
  document.getElementById(id).addEventListener("input", updateExportSplitLabel);
});
document.getElementById("export-aug-multiplier").addEventListener("input", (e) => {
  document.getElementById("export-aug-multiplier-label").textContent = e.target.value;
  updateExportMaxSizeLabel();
});

document.getElementById("export-start-btn").addEventListener("click", async () => {
  if (!currentDetectJobId) return;
  const tr = parseInt(document.getElementById("export-train-pct").value, 10) / 100;
  const va = parseInt(document.getElementById("export-val-pct").value, 10) / 100;
  const te = Math.max(0, 1 - tr - va);

  const body = {
    detect_job_id: currentDetectJobId,
    version_name: document.getElementById("export-version-name").value || "v1",
    reviewed_only: document.getElementById("export-reviewed-only").checked,
    splits: { train: tr, val: va, test: te },
    preprocess: { resize: document.getElementById("export-resize").checked, resize_size: 640 },
    augment: {
      multiplier: parseInt(document.getElementById("export-aug-multiplier").value, 10),
      flip: document.getElementById("export-aug-flip").checked,
      rotate: document.getElementById("export-aug-rotate").checked,
      blur: document.getElementById("export-aug-blur").checked,
      brightness: document.getElementById("export-aug-brightness").checked,
      crop: document.getElementById("export-aug-crop").checked,
    },
  };

  const res = await apiFetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    alert(errBody.detail || "Failed to start export");
    return;
  }
  const data = await res.json();
  currentExportJobId = data.job_id;
  document.getElementById("export-start-btn").disabled = true;
  document.getElementById("export-progress-wrap").classList.remove("hidden");
  document.getElementById("export-download-btn").classList.add("hidden");
  startExportPolling();
});

function startExportPolling() {
  exportPollTimer = setInterval(async () => {
    const res = await apiFetch(`/api/export/${currentExportJobId}`);
    if (!res.ok) return;
    const job = await res.json();
    document.getElementById("export-progress-fill").style.width = job.progress + "%";
    document.getElementById("export-progress-label").textContent = job.status + " — " + job.progress + "%";

    if (job.status === "done" || job.status === "error") {
      clearInterval(exportPollTimer);
      document.getElementById("export-start-btn").disabled = false;
      if (job.status === "done") {
        const total = job.summary ? job.summary.total_exported : "?";
        document.getElementById("export-progress-label").textContent = `done — ${total} images exported`;
        document.getElementById("export-download-btn").classList.remove("hidden");
      } else {
        alert(job.error || "Export failed");
      }
    }
  }, 1000);
}

document.getElementById("export-download-btn").addEventListener("click", () => {
  if (!currentExportJobId) return;
  window.location.href = `/api/export/${currentExportJobId}/download`;
});

// ────────────────────────────── Init ──────────────────────────────

refreshVideoList();
refreshModelOptions();
refreshClasses();
updateDetectFramesInfo();
