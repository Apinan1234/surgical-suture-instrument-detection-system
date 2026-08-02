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

// ────────────────────────────── S-5 / F-7: Annotate canvas engine ──────────────────────────────
// Modules: Api, UndoManager, AnnotateState, Canvas, DrawBoxTool, SelectTool, Tools, Keyboard,
// then DOM wiring at the bottom. See _archive/WORK_PLAN.md "✏️ Annotation Workflow & Tool Design".

// ── shared helpers ──

let _idCounter = 0;
function makeId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
  return `box-${Date.now()}-${_idCounter++}`;
}

function cloneBoxes(arr) {
  if (typeof structuredClone === "function") return structuredClone(arr);
  return JSON.parse(JSON.stringify(arr));
}

function clamp01(v) {
  return Math.min(1, Math.max(0, v));
}

function clampPos(v) {
  return Math.min(1, Math.max(0.001, v)); // backend requires width/height > 0
}

const HANDLE_PX = 8; // fixed screen-px handle size, regardless of zoom
const CURSOR_BY_HANDLE = {
  nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize",
  n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize",
};

function boxRectImg(b, imgW, imgH) {
  const x1 = (b.x_center - b.width / 2) * imgW;
  const y1 = (b.y_center - b.height / 2) * imgH;
  const x2 = (b.x_center + b.width / 2) * imgW;
  const y2 = (b.y_center + b.height / 2) * imgH;
  return { x1, y1, x2, y2 };
}

function handlePositions(rect) {
  const { x1, y1, x2, y2 } = rect;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return {
    nw: { x: x1, y: y1 }, n: { x: mx, y: y1 }, ne: { x: x2, y: y1 },
    w: { x: x1, y: my }, e: { x: x2, y: my },
    sw: { x: x1, y: y2 }, s: { x: mx, y: y2 }, se: { x: x2, y: y2 },
  };
}

function rectToNormalized(x1, y1, x2, y2, imgW, imgH) {
  const nx1 = Math.min(x1, x2), nx2 = Math.max(x1, x2);
  const ny1 = Math.min(y1, y2), ny2 = Math.max(y1, y2);
  return {
    x_center: clamp01((nx1 + nx2) / 2 / imgW),
    y_center: clamp01((ny1 + ny2) / 2 / imgH),
    width: clampPos((nx2 - nx1) / imgW),
    height: clampPos((ny2 - ny1) / imgH),
  };
}

function hitTestHandles(imgPt, box, imgW, imgH, tolImg) {
  const handles = handlePositions(boxRectImg(box, imgW, imgH));
  for (const name in handles) {
    const h = handles[name];
    if (Math.abs(imgPt.x - h.x) <= tolImg && Math.abs(imgPt.y - h.y) <= tolImg) return name;
  }
  return null;
}

function hitTestBoxBody(imgPt, box, imgW, imgH) {
  const rect = boxRectImg(box, imgW, imgH);
  return imgPt.x >= rect.x1 && imgPt.x <= rect.x2 && imgPt.y >= rect.y1 && imgPt.y <= rect.y2;
}

function boxIntersectsRect(rect, box, imgW, imgH) {
  const b = boxRectImg(box, imgW, imgH);
  return b.x1 < rect.x2 && b.x2 > rect.x1 && b.y1 < rect.y2 && b.y2 > rect.y1;
}

function drawMarquee(ctx, start, current, scale) {
  const x1 = Math.min(start.x, current.x), y1 = Math.min(start.y, current.y);
  const w = Math.abs(current.x - start.x), h = Math.abs(current.y - start.y);
  ctx.save();
  ctx.fillStyle = "rgba(37, 99, 235, 0.1)";
  ctx.fillRect(x1, y1, w, h);
  ctx.strokeStyle = "#2563eb";
  ctx.lineWidth = 1 / scale;
  ctx.setLineDash([4 / scale, 3 / scale]);
  ctx.strokeRect(x1, y1, w, h);
  ctx.setLineDash([]);
  ctx.restore();
}

// ── Api: one wrapper per endpoint used by Annotate ──

const Api = {
  putDetections(frameId, detections) {
    return apiFetch(`/api/frames/${frameId}/detections`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ detections }),
    });
  },
  postReview(frameId, reviewed) {
    return apiFetch(`/api/frames/${frameId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed: reviewed !== false }),
    });
  },
  postAssist(frameId, body) {
    return apiFetch(`/api/frames/${frameId}/assist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
  imageUrl(frameId) {
    return `/api/frames/${frameId}/image.jpg?t=${Date.now()}`;
  },
  thumbnailUrl(frameId, max) {
    // stable, NOT cache-busted — letting the browser HTTP-cache thumbnails is the point of S-9
    return `/api/frames/${frameId}/thumbnail.jpg?max=${max || 160}`;
  },
};

// ── UndoManager: capped whole-array snapshot stack ──

const UndoManager = (() => {
  const CAP = 50;
  let past = [];
  let future = [];

  function reset() {
    past = [];
    future = [];
  }

  function recordSnapshot(boxesArray) {
    past.push(cloneBoxes(boxesArray));
    if (past.length > CAP) past.shift();
    future = [];
  }

  function undo(currentBoxes) {
    if (!past.length) return null;
    const prev = past.pop();
    future.push(cloneBoxes(currentBoxes));
    return prev;
  }

  function redo(currentBoxes) {
    if (!future.length) return null;
    const next = future.pop();
    past.push(cloneBoxes(currentBoxes));
    return next;
  }

  return { reset, recordSnapshot, undo, redo };
})();

// ── AnnotateState: frames/boxes/selection/active-tool + pub/sub ──

const AnnotateState = (() => {
  let frames = [];
  let frameIdx = -1;
  let boxes = [];
  let selectedIds = new Set();
  let activeTool = "draw_box";
  const listeners = [];

  function emit() {
    listeners.forEach((fn) => fn());
  }

  function subscribe(fn) {
    listeners.push(fn);
  }

  function hydrate(detections) {
    return (detections || []).map((d) => ({ ...d, id: makeId() }));
  }

  function init(frameList) {
    frames = frameList || [];
    frameIdx = -1;
    boxes = [];
    selectedIds = new Set();
    UndoManager.reset();
    if (frames.length) {
      selectFrame(0);
    } else {
      emit();
    }
  }

  function selectFrame(idx) {
    if (idx < 0 || idx >= frames.length) return;
    frameIdx = idx;
    boxes = hydrate(frames[idx].detections);
    selectedIds = new Set();
    UndoManager.reset();
    emit();
  }

  function currentFrame() {
    return frameIdx >= 0 ? frames[frameIdx] : null;
  }

  function getBoxes() {
    return boxes;
  }

  function setBoxes(next, opts) {
    opts = opts || {};
    if (opts.pushUndo !== false) UndoManager.recordSnapshot(boxes);
    boxes = next;
    emit();
  }

  function addBoxes(newOnes) {
    if (!newOnes.length) return;
    setBoxes(boxes.concat(newOnes));
  }

  function selectBox(id) {
    selectedIds = id ? new Set([id]) : new Set();
    emit();
  }

  function selectBoxes(ids) {
    selectedIds = new Set(ids);
    emit();
  }

  function getSelected() {
    if (selectedIds.size !== 1) return null;
    const id = selectedIds.values().next().value;
    return boxes.find((b) => b.id === id) || null;
  }

  function isSelected(id) {
    return selectedIds.has(id);
  }

  function getSelectedIds() {
    return Array.from(selectedIds);
  }

  function getSelectedCount() {
    return selectedIds.size;
  }

  function reselectIfMissing() {
    let changed = false;
    selectedIds.forEach((id) => {
      if (!boxes.find((b) => b.id === id)) {
        selectedIds.delete(id);
        changed = true;
      }
    });
    if (changed) emit();
  }

  function deleteBoxesByIds(ids) {
    if (!ids.length) return;
    const idSet = new Set(ids);
    idSet.forEach((id) => selectedIds.delete(id));
    setBoxes(boxes.filter((b) => !idSet.has(b.id)));
  }

  function reassignClassByIds(ids, className) {
    if (!ids.length) return;
    const idSet = new Set(ids);
    const classId = classNames.indexOf(className);
    setBoxes(boxes.map((b) => (idSet.has(b.id) ? { ...b, class_id: classId, class_name: className } : b)));
  }

  function deleteSelectedBoxes() {
    deleteBoxesByIds(getSelectedIds());
  }

  function reassignSelectedBoxesClass(className) {
    if (!selectedIds.size) return false;
    reassignClassByIds(getSelectedIds(), className);
    return true;
  }

  function setActiveTool(name) {
    if (activeTool === name || !Tools[name]) return;
    const prev = Tools[activeTool];
    if (prev && prev.onDeactivate) prev.onDeactivate();
    activeTool = name;
    selectedIds = new Set();
    const next = Tools[activeTool];
    if (next && next.onActivate) next.onActivate();
    emit();
  }

  function getPrevFrame() {
    return frameIdx > 0 ? frames[frameIdx - 1] : null;
  }

  function findNextUnreviewedIndex(fromIdx) {
    for (let i = fromIdx + 1; i < frames.length; i++) {
      if (!frames[i].reviewed) return i;
    }
    return -1;
  }

  function markReviewedLocal(v) {
    const f = currentFrame();
    if (f) f.reviewed = v;
    emit();
  }

  function setFrameDetections(idx, detections) {
    if (frames[idx]) frames[idx].detections = detections;
  }

  return {
    subscribe, init, selectFrame, currentFrame, getBoxes, setBoxes, addBoxes,
    selectBox, selectBoxes, getSelected, isSelected, getSelectedIds, getSelectedCount,
    reselectIfMissing, deleteBoxesByIds, reassignClassByIds, deleteSelectedBoxes, reassignSelectedBoxesClass,
    setActiveTool, getActiveTool: () => activeTool,
    getFrames: () => frames, getFrameIdx: () => frameIdx, getPrevFrame,
    findNextUnreviewedIndex, markReviewedLocal, setFrameDetections,
  };
})();

// ── Tool registry (filled in below by DrawBoxTool/SelectTool) ──

const Tools = {};

// ── Canvas: owns <canvas>, viewport/pan/zoom transform, rAF-batched redraw ──

const Canvas = (() => {
  const canvas = document.getElementById("annotate-canvas");
  const ctx = canvas.getContext("2d");
  let img = null;
  let cssScale = 1; // image-px -> CSS-px
  let panX = 0, panY = 0; // image-space coords shown at canvas-local (0,0)
  let rafScheduled = false;
  let spaceHeld = false;
  let panDragStart = null;

  function requestRender() {
    if (rafScheduled) return;
    rafScheduled = true;
    requestAnimationFrame(() => {
      rafScheduled = false;
      render();
    });
  }

  function drawBox(b) {
    const imgW = img.naturalWidth, imgH = img.naturalHeight;
    const x1 = (b.x_center - b.width / 2) * imgW;
    const y1 = (b.y_center - b.height / 2) * imgH;
    const bw = b.width * imgW;
    const bh = b.height * imgH;
    const color = classColors[b.class_name] || "#AAAAAA";
    const lw = 2 / cssScale;
    const isSelected = AnnotateState.isSelected(b.id);

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.setLineDash(b._pending ? [6 / cssScale, 4 / cssScale] : []);
    ctx.strokeRect(x1, y1, bw, bh);
    ctx.setLineDash([]);

    if (isSelected) {
      ctx.strokeStyle = "#2563eb";
      ctx.lineWidth = lw * 1.5;
      ctx.setLineDash([4 / cssScale, 2 / cssScale]);
      ctx.strokeRect(x1 - lw, y1 - lw, bw + 2 * lw, bh + 2 * lw);
      ctx.setLineDash([]);
    }

    ctx.fillStyle = color;
    ctx.font = `${13 / cssScale}px sans-serif`;
    const labelY = y1 - 4 / cssScale > 10 / cssScale ? y1 - 4 / cssScale : y1 + 12 / cssScale;
    ctx.fillText(b.class_name, x1, labelY);

    if (b._pending && b.confidence < 0.5) {
      ctx.fillStyle = "#e94560"; // var(--highlight) — identical across every theme in style.css
      const warnY = y1 + bh + 14 / cssScale < imgH ? y1 + bh + 14 / cssScale : y1 + bh - 4 / cssScale;
      ctx.fillText(`⚠ ${b.confidence.toFixed(2)}`, x1, warnY);
    }
    ctx.restore();
  }

  function render() {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (img) {
      const bufferScale = cssScale * dpr;
      ctx.setTransform(bufferScale, 0, 0, bufferScale, -panX * bufferScale, -panY * bufferScale);
      ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight);
      AnnotateState.getBoxes().forEach(drawBox);
      const tool = Tools[AnnotateState.getActiveTool()];
      if (tool && tool.render) tool.render(ctx);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  function fitToImage() {
    if (!img) {
      requestRender();
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.width / dpr;
    const cssH = canvas.height / dpr;
    cssScale = Math.min(cssW / img.naturalWidth, cssH / img.naturalHeight);
    if (!isFinite(cssScale) || cssScale <= 0) cssScale = 1;
    const dispW = img.naturalWidth * cssScale;
    const dispH = img.naturalHeight * cssScale;
    panX = -((cssW - dispW) / 2) / cssScale;
    panY = -((cssH - dispH) / 2) / cssScale;
    requestRender();
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const wrap = canvas.parentElement;
    const cssW = wrap.clientWidth || 640;
    const cssH = wrap.clientHeight || 640;
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    fitToImage();
  }

  function setImage(newImg) {
    img = newImg;
    resize();
  }

  function screenToImage(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const cx = clientX - rect.left;
    const cy = clientY - rect.top;
    return { x: panX + cx / cssScale, y: panY + cy / cssScale };
  }

  function imageToScreen(imgX, imgY) {
    return { x: (imgX - panX) * cssScale, y: (imgY - panY) * cssScale };
  }

  function panBy(dxCss, dyCss) {
    panX -= dxCss / cssScale;
    panY -= dyCss / cssScale;
    requestRender();
  }

  function zoomBy(factor, clientX, clientY) {
    if (!img) return;
    const before = screenToImage(clientX, clientY);
    cssScale = Math.min(20, Math.max(0.05, cssScale * factor));
    const after = screenToImage(clientX, clientY);
    panX += before.x - after.x;
    panY += before.y - after.y;
    requestRender();
  }

  function setCursor(name) {
    canvas.style.cursor = name;
  }

  function setSpaceHeld(v) {
    spaceHeld = v;
    if (!panDragStart) setCursor(v ? "grab" : (AnnotateState.getActiveTool() === "draw_box" ? "crosshair" : "default"));
  }

  function dispatch(method, e) {
    const tool = Tools[AnnotateState.getActiveTool()];
    if (tool && tool[method]) tool[method](e);
  }

  canvas.addEventListener("pointerdown", (e) => {
    if (spaceHeld) {
      panDragStart = { x: e.clientX, y: e.clientY };
      canvas.setPointerCapture(e.pointerId);
      setCursor("grabbing");
      return;
    }
    dispatch("onPointerDown", e);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (panDragStart) {
      panBy(e.clientX - panDragStart.x, e.clientY - panDragStart.y);
      panDragStart = { x: e.clientX, y: e.clientY };
      return;
    }
    dispatch("onPointerMove", e);
  });
  canvas.addEventListener("pointerup", (e) => {
    if (panDragStart) {
      panDragStart = null;
      setCursor(spaceHeld ? "grab" : "default");
      return;
    }
    dispatch("onPointerUp", e);
  });
  canvas.addEventListener("wheel", (e) => {
    if (!img) return;
    e.preventDefault();
    zoomBy(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX, e.clientY);
  }, { passive: false });

  window.addEventListener("resize", () => resize());

  return {
    setImage, resize, requestRender, screenToImage, imageToScreen, zoomBy, setSpaceHeld, setCursor,
    getCssScale: () => cssScale,
    getImageSize: () => (img ? { w: img.naturalWidth, h: img.naturalHeight } : { w: 0, h: 0 }),
  };
})();

// ── DrawBoxTool: click-drag to create a new box; stays active across multiple boxes ──

const DrawBoxTool = (() => {
  let dragStart = null;
  let dragCurrent = null;

  function onPointerDown(e) {
    if (!AnnotateState.currentFrame()) return;
    dragStart = Canvas.screenToImage(e.clientX, e.clientY);
    dragCurrent = dragStart;
  }

  function onPointerMove(e) {
    if (!dragStart) return;
    dragCurrent = Canvas.screenToImage(e.clientX, e.clientY);
    Canvas.requestRender();
  }

  function onPointerUp(e) {
    if (!dragStart) return;
    const start = dragStart;
    const end = Canvas.screenToImage(e.clientX, e.clientY);
    dragStart = null;
    dragCurrent = null;

    const scale = Canvas.getCssScale();
    const dxPx = Math.abs(end.x - start.x) * scale;
    const dyPx = Math.abs(end.y - start.y) * scale;
    if (dxPx < 5 || dyPx < 5) {
      // accidental-click guard, ~5 screen px (mirrors the old desktop app's behavior)
      Canvas.requestRender();
      return;
    }

    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const className = document.getElementById("annotate-class-select").value;
    const norm = rectToNormalized(start.x, start.y, end.x, end.y, imgW, imgH);
    AnnotateState.addBoxes([{
      id: makeId(),
      class_id: classNames.indexOf(className),
      class_name: className,
      confidence: 1.0,
      ...norm,
    }]);
  }

  function cancel() {
    dragStart = null;
    dragCurrent = null;
    Canvas.requestRender();
  }

  function render(ctx) {
    if (!dragStart || !dragCurrent) return;
    const className = document.getElementById("annotate-class-select").value;
    const color = classColors[className] || "#AAAAAA";
    const scale = Canvas.getCssScale();
    const x1 = Math.min(dragStart.x, dragCurrent.x);
    const y1 = Math.min(dragStart.y, dragCurrent.y);
    const w = Math.abs(dragCurrent.x - dragStart.x);
    const h = Math.abs(dragCurrent.y - dragStart.y);
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2 / scale;
    ctx.strokeRect(x1, y1, w, h);
    ctx.restore();
  }

  function onActivate() {
    Canvas.setCursor("crosshair");
  }

  function onDeactivate() {
    cancel();
  }

  return { onPointerDown, onPointerMove, onPointerUp, render, onActivate, onDeactivate, cancel };
})();

// ── SelectTool: click to select, drag to move, drag a handle to resize ──

const SelectTool = (() => {
  let mode = null; // null | "move" | "resize" | "marquee"
  let activeHandle = null;
  let startImgPt = null;
  let startBox = null;
  let preDragBoxes = null;
  let snapshotTaken = false;
  let marqueeStart = null;
  let marqueeCurrent = null;

  function findTopBoxAt(imgPt, imgW, imgH) {
    const boxes = AnnotateState.getBoxes();
    for (let i = boxes.length - 1; i >= 0; i--) {
      if (hitTestBoxBody(imgPt, boxes[i], imgW, imgH)) return boxes[i];
    }
    return null;
  }

  function onPointerDown(e) {
    if (!AnnotateState.currentFrame()) return;
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const imgPt = Canvas.screenToImage(e.clientX, e.clientY);
    const tolImg = HANDLE_PX / Canvas.getCssScale();

    const selected = AnnotateState.getSelected();
    if (selected) {
      const handle = hitTestHandles(imgPt, selected, imgW, imgH, tolImg);
      if (handle) {
        mode = "resize";
        activeHandle = handle;
        startImgPt = imgPt;
        startBox = { ...selected };
        preDragBoxes = AnnotateState.getBoxes();
        snapshotTaken = false;
        return;
      }
    }

    const hit = findTopBoxAt(imgPt, imgW, imgH);
    if (hit) {
      AnnotateState.selectBox(hit.id);
      mode = "move";
      startImgPt = imgPt;
      startBox = { ...hit };
      preDragBoxes = AnnotateState.getBoxes();
      snapshotTaken = false;
    } else {
      mode = "marquee";
      marqueeStart = imgPt;
      marqueeCurrent = imgPt;
    }
  }

  function updateHoverCursor(e) {
    if (!AnnotateState.currentFrame()) {
      Canvas.setCursor("default");
      return;
    }
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const imgPt = Canvas.screenToImage(e.clientX, e.clientY);
    const tolImg = HANDLE_PX / Canvas.getCssScale();
    const selected = AnnotateState.getSelected();
    if (selected) {
      const handle = hitTestHandles(imgPt, selected, imgW, imgH, tolImg);
      if (handle) {
        Canvas.setCursor(CURSOR_BY_HANDLE[handle]);
        return;
      }
    }
    const hit = findTopBoxAt(imgPt, imgW, imgH);
    Canvas.setCursor(hit ? "move" : "default");
  }

  function onPointerMove(e) {
    if (!mode) {
      updateHoverCursor(e);
      return;
    }
    const imgPt = Canvas.screenToImage(e.clientX, e.clientY);
    if (mode === "marquee") {
      marqueeCurrent = imgPt;
      Canvas.requestRender();
      return;
    }
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const dx = imgPt.x - startImgPt.x;
    const dy = imgPt.y - startImgPt.y;
    if (dx === 0 && dy === 0) return;

    if (!snapshotTaken) {
      UndoManager.recordSnapshot(preDragBoxes);
      snapshotTaken = true;
    }

    let { x1, y1, x2, y2 } = boxRectImg(startBox, imgW, imgH);
    if (mode === "move") {
      x1 += dx; x2 += dx; y1 += dy; y2 += dy;
    } else {
      if (activeHandle.includes("w")) x1 += dx;
      if (activeHandle.includes("e")) x2 += dx;
      if (activeHandle.includes("n")) y1 += dy;
      if (activeHandle.includes("s")) y2 += dy;
    }
    const norm = rectToNormalized(x1, y1, x2, y2, imgW, imgH);
    const boxes = AnnotateState.getBoxes().map((b) => (b.id === startBox.id ? { ...b, ...norm } : b));
    AnnotateState.setBoxes(boxes, { pushUndo: false });
  }

  function onPointerUp() {
    if (mode === "marquee") {
      const scale = Canvas.getCssScale();
      const dxPx = Math.abs(marqueeCurrent.x - marqueeStart.x) * scale;
      const dyPx = Math.abs(marqueeCurrent.y - marqueeStart.y) * scale;
      if (dxPx < 5 || dyPx < 5) {
        // negligible drag == the old "click empty space to deselect" behavior
        AnnotateState.selectBox(null);
      } else {
        const { w: imgW, h: imgH } = Canvas.getImageSize();
        const rect = {
          x1: Math.min(marqueeStart.x, marqueeCurrent.x), x2: Math.max(marqueeStart.x, marqueeCurrent.x),
          y1: Math.min(marqueeStart.y, marqueeCurrent.y), y2: Math.max(marqueeStart.y, marqueeCurrent.y),
        };
        const ids = AnnotateState.getBoxes()
          .filter((b) => boxIntersectsRect(rect, b, imgW, imgH))
          .map((b) => b.id);
        AnnotateState.selectBoxes(ids);
      }
      marqueeStart = null;
      marqueeCurrent = null;
      Canvas.requestRender();
    }
    mode = null;
    activeHandle = null;
    startImgPt = null;
    startBox = null;
    preDragBoxes = null;
    snapshotTaken = false;
  }

  function nudgeSelected(dxSign, dySign, big) {
    const selected = AnnotateState.getSelected();
    if (!selected) return;
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    if (!imgW || !imgH) return;
    const stepPx = big ? 10 : 1;
    const nx = clamp01(selected.x_center + (dxSign * stepPx) / imgW);
    const ny = clamp01(selected.y_center + (dySign * stepPx) / imgH);
    AnnotateState.setBoxes(AnnotateState.getBoxes().map((b) =>
      b.id === selected.id ? { ...b, x_center: nx, y_center: ny } : b
    ));
  }

  function render(ctx) {
    if (mode === "marquee" && marqueeStart && marqueeCurrent) {
      drawMarquee(ctx, marqueeStart, marqueeCurrent, Canvas.getCssScale());
      return;
    }
    const selected = AnnotateState.getSelected();
    if (!selected) return;
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const handles = handlePositions(boxRectImg(selected, imgW, imgH));
    const dpr = window.devicePixelRatio || 1;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    Object.values(handles).forEach((h) => {
      const pt = Canvas.imageToScreen(h.x, h.y);
      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = "#2563eb";
      ctx.lineWidth = 1.5;
      ctx.fillRect(pt.x - HANDLE_PX / 2, pt.y - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX);
      ctx.strokeRect(pt.x - HANDLE_PX / 2, pt.y - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX);
    });
    ctx.restore();
  }

  function onActivate() {
    Canvas.setCursor("default");
  }

  function onDeactivate() {
    mode = null;
    activeHandle = null;
    preDragBoxes = null;
    snapshotTaken = false;
    marqueeStart = null;
    marqueeCurrent = null;
  }

  return {
    onPointerDown, onPointerMove, onPointerUp, render, onActivate, onDeactivate,
    nudgeSelected,
  };
})();

Tools.draw_box = DrawBoxTool;
Tools.select = SelectTool;

// ── Keyboard: one listener + one lookup table (also renders the "?" cheat-sheet) ──

const Keyboard = (() => {
  function isTextInput(el) {
    return !!(el && el.closest && el.closest("input, textarea, select, [contenteditable]"));
  }

  function setClassByNumber(n) {
    const name = classNames[n - 1];
    if (!name) return;
    if (!AnnotateState.reassignSelectedBoxesClass(name)) {
      document.getElementById("annotate-class-select").value = name;
    }
  }

  function doUndo() {
    const prev = UndoManager.undo(AnnotateState.getBoxes());
    if (prev) {
      AnnotateState.setBoxes(prev, { pushUndo: false });
      AnnotateState.reselectIfMissing();
    }
  }

  function doRedo() {
    const next = UndoManager.redo(AnnotateState.getBoxes());
    if (next) {
      AnnotateState.setBoxes(next, { pushUndo: false });
      AnnotateState.reselectIfMissing();
    }
  }

  function navFrame(delta) {
    const idx = AnnotateState.getFrameIdx() + delta;
    if (idx >= 0 && idx < AnnotateState.getFrames().length) AnnotateState.selectFrame(idx);
  }

  function onEscape() {
    if (AnnotateState.getActiveTool() === "draw_box") {
      DrawBoxTool.cancel();
    } else {
      AnnotateState.selectBox(null);
    }
  }

  function toggleCheatSheet() {
    const popover = document.getElementById("annotate-cheatsheet");
    if (!popover) return;
    if (!popover.classList.contains("open")) {
      popover.innerHTML = "";
      const pre = document.createElement("pre");
      pre.textContent = SHORTCUTS.filter((s) => s.label).map((s) => s.label).join("\n");
      popover.appendChild(pre);
    }
    popover.classList.toggle("open");
  }

  const SHORTCUTS = [
    { key: "v", label: "V — Select tool", handler: () => AnnotateState.setActiveTool("select") },
    { key: "b", label: "B — Draw box tool", handler: () => AnnotateState.setActiveTool("draw_box") },
    { key: "1", label: "1-5 — Set class", handler: () => setClassByNumber(1) },
    { key: "2", handler: () => setClassByNumber(2) },
    { key: "3", handler: () => setClassByNumber(3) },
    { key: "4", handler: () => setClassByNumber(4) },
    { key: "5", handler: () => setClassByNumber(5) },
    { key: "Delete", label: "Delete — Remove selected box(es)", handler: () => AnnotateState.deleteSelectedBoxes() },
    { key: "Backspace", handler: () => AnnotateState.deleteSelectedBoxes() },
    { key: "a", ctrlKey: true, label: "Ctrl+A — Select all boxes", handler: () => AnnotateState.selectBoxes(AnnotateState.getBoxes().map((b) => b.id)) },
    { key: "z", ctrlKey: true, shiftKey: false, label: "Ctrl+Z — Undo", handler: () => doUndo() },
    { key: "z", ctrlKey: true, shiftKey: true, label: "Ctrl+Shift+Z — Redo", handler: () => doRedo() },
    { key: "ArrowLeft", label: "Arrows — Nudge selected box (Shift=10px)", handler: (e) => SelectTool.nudgeSelected(-1, 0, e.shiftKey) },
    { key: "ArrowRight", handler: (e) => SelectTool.nudgeSelected(1, 0, e.shiftKey) },
    { key: "ArrowUp", handler: (e) => SelectTool.nudgeSelected(0, -1, e.shiftKey) },
    { key: "ArrowDown", handler: (e) => SelectTool.nudgeSelected(0, 1, e.shiftKey) },
    { key: "[", label: "[ / ] — Prev / Next frame", handler: () => navFrame(-1) },
    { key: "]", handler: () => navFrame(1) },
    { key: "a", label: "A — Run Assist", handler: () => document.getElementById("assist-run-btn").click() },
    { key: "r", label: "R — Toggle reviewed", handler: () => toggleReviewed() },
    { key: "Enter", label: "Enter — Save & Next", handler: () => saveAndNext() },
    { key: "Escape", label: "Esc — Cancel draw / deselect", handler: () => onEscape() },
    { key: "?", label: "? — Show this cheat-sheet", handler: () => toggleCheatSheet() },
  ];

  function match(e, sc) {
    if (e.key.toLowerCase() !== sc.key.toLowerCase()) return false;
    if (!!sc.ctrlKey !== e.ctrlKey) return false;
    // shiftKey is only enforced when a shortcut explicitly cares (e.g. Ctrl+Z vs Ctrl+Shift+Z) —
    // left unspecified for arrows (Shift is a nudge-size modifier, not a distinct binding) and for
    // symbol keys like "?" whose e.key already encodes the shift state.
    if (sc.shiftKey !== undefined && sc.shiftKey !== e.shiftKey) return false;
    return true;
  }

  document.addEventListener("keydown", (e) => {
    if (isTextInput(e.target)) return;
    if (e.code === "Space") {
      Canvas.setSpaceHeld(true);
      e.preventDefault();
      return;
    }
    for (const sc of SHORTCUTS) {
      if (match(e, sc)) {
        e.preventDefault();
        sc.handler(e);
        return;
      }
    }
  });

  document.addEventListener("keyup", (e) => {
    if (e.code === "Space") Canvas.setSpaceHeld(false);
  });

  return {};
})();

function populateAnnotateClassSelect() {
  const select = document.getElementById("annotate-class-select");
  select.innerHTML = "";
  classNames.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });

  const bulkSelect = document.getElementById("annotate-bulk-class-select");
  bulkSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Reassign class to…";
  placeholder.selected = true;
  placeholder.disabled = true;
  bulkSelect.appendChild(placeholder);
  classNames.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    bulkSelect.appendChild(opt);
  });
}

function initAnnotateFrames(frames) {
  const list = frames || [];
  document.getElementById("annotate-frames-info").classList.toggle("hidden", list.length > 0);
  document.getElementById("annotate-toolbar").classList.toggle("hidden", list.length === 0);
  document.getElementById("annotate-workspace").classList.toggle("hidden", list.length === 0);
  document.getElementById("annotate-statusbar").classList.toggle("hidden", list.length === 0);
  Filmstrip.forceRebuild();
  AnnotateState.init(list);
}

// ── Filmstrip: lazy-loaded thumbnails via IntersectionObserver; structural rebuild only
// when the frame list/filter changes, cheap per-row patch otherwise (never tears down <img>s
// on every box edit, or S-9's lazy-load benefit is defeated) ──

const Filmstrip = (() => {
  let builtForLength = -1;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const img = entry.target;
      if (img.dataset.src && img.src !== img.dataset.src) img.src = img.dataset.src;
      observer.unobserve(img);
    });
  }, { root: document.querySelector(".annotate-filmstrip"), rootMargin: "200px" });

  function frameBadge(frame) {
    if (frame.reviewed) return "✅";
    return (frame.detections || []).length ? "🏷" : "🔴";
  }

  function passesFilter(frame, filter) {
    if (filter === "unreviewed") return !frame.reviewed;
    if (filter === "reviewed") return !!frame.reviewed;
    return true;
  }

  function build() {
    const list = document.getElementById("annotate-filmstrip-list");
    list.innerHTML = "";
    const frames = AnnotateState.getFrames();
    frames.forEach((frame, i) => {
      const li = document.createElement("li");
      li.dataset.idx = i;

      const img = document.createElement("img");
      img.className = "filmstrip-thumb";
      img.alt = "";
      img.dataset.src = Api.thumbnailUrl(frame.id, 160);
      observer.observe(img);

      const label = document.createElement("span");
      label.className = "filmstrip-label";

      li.appendChild(img);
      li.appendChild(label);
      li.addEventListener("click", () => AnnotateState.selectFrame(i));
      list.appendChild(li);
    });
    builtForLength = frames.length;
  }

  function patch() {
    const list = document.getElementById("annotate-filmstrip-list");
    const frames = AnnotateState.getFrames();
    const idx = AnnotateState.getFrameIdx();
    const filter = document.getElementById("annotate-filmstrip-filter").value;
    Array.from(list.children).forEach((li, i) => {
      const frame = frames[i];
      if (!frame) return;
      li.className = i === idx ? "selected" : "";
      if (!passesFilter(frame, filter)) li.classList.add("hidden-by-filter");
      const label = li.querySelector(".filmstrip-label");
      label.textContent = `${frameBadge(frame)} ${frame.filename}`;
    });
  }

  function render() {
    const frames = AnnotateState.getFrames();
    if (frames.length !== builtForLength) build();
    patch();
  }

  function forceRebuild() {
    builtForLength = -1;
  }

  return { render, forceRebuild };
})();

document.getElementById("annotate-filmstrip-filter").addEventListener("change", () => Filmstrip.render());

// ── PropertyPanel: per-box detection list (class dropdown + confidence badge + click-to-highlight) ──

function renderDetectionList() {
  const list = document.getElementById("annotate-detection-list");
  list.innerHTML = "";
  const boxes = AnnotateState.getBoxes();

  if (!boxes.length) {
    const empty = document.createElement("div");
    empty.className = "detection-list-empty";
    empty.textContent = "No boxes on this frame yet.";
    list.appendChild(empty);
    return;
  }

  boxes.forEach((b) => {
    const li = document.createElement("li");
    li.className = AnnotateState.isSelected(b.id) ? "selected" : "";
    li.addEventListener("click", (e) => {
      if (e.target.tagName === "SELECT" || e.target.tagName === "BUTTON") return;
      AnnotateState.setActiveTool("select");
      AnnotateState.selectBox(b.id);
    });

    const select = document.createElement("select");
    classNames.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === b.class_name) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", () => {
      AnnotateState.reassignClassByIds([b.id], select.value);
    });

    const badge = document.createElement("span");
    badge.className = "conf-badge" + (b.confidence < 0.5 ? " low" : "");
    badge.textContent = (b._pending ? "🏷 " : "") + b.confidence.toFixed(2);

    const del = document.createElement("button");
    del.className = "del-btn";
    del.textContent = "✕";
    del.title = "Delete box";
    del.addEventListener("click", () => {
      AnnotateState.deleteBoxesByIds([b.id]);
    });

    li.appendChild(select);
    li.appendChild(badge);
    li.appendChild(del);
    list.appendChild(li);
  });
}

function updateStatusBar() {
  const frames = AnnotateState.getFrames();
  const idx = AnnotateState.getFrameIdx();
  if (idx < 0) return;
  const boxes = AnnotateState.getBoxes();
  const pendingCount = boxes.filter((b) => b._pending).length;
  const reviewedCount = frames.filter((f) => f.reviewed).length;
  document.getElementById("annotate-statusbar-frame").textContent = `Frame ${idx + 1} / ${frames.length}`;
  document.getElementById("annotate-statusbar-boxes").textContent =
    `${boxes.length} box(es)` + (pendingCount ? ` (${pendingCount} unconfirmed AI)` : "");
  document.getElementById("annotate-statusbar-progress").textContent =
    `${reviewedCount} / ${frames.length} reviewed`;
}

function updateAnnotateReviewStatus() {
  const frame = AnnotateState.currentFrame();
  if (!frame) return;
  document.getElementById("annotate-review-status").textContent = frame.reviewed
    ? "✅ Reviewed"
    : "🔴 Needs Review";
}

function updateToolButtons() {
  const tool = AnnotateState.getActiveTool();
  document.getElementById("annotate-tool-select-btn").classList.toggle("active-tool", tool === "select");
  document.getElementById("annotate-tool-draw-btn").classList.toggle("active-tool", tool === "draw_box");
}

function updateBulkActionsBar() {
  const n = AnnotateState.getSelectedCount();
  document.getElementById("annotate-bulk-actions").classList.toggle("hidden", n < 2);
  if (n >= 2) {
    document.getElementById("annotate-bulk-delete-btn").textContent = `Delete Selected (${n})`;
  }
}

function loadAnnotateImage(frame, idxAtLoad) {
  const img = new Image();
  img.onload = () => {
    if (AnnotateState.getFrameIdx() !== idxAtLoad) return; // user navigated away before this finished loading
    Canvas.setImage(img);
  };
  img.src = Api.imageUrl(frame.id);
}

let _lastLoadedFrameIdx = -2; // sentinel distinct from the -1 "no frame selected" state
AnnotateState.subscribe(() => {
  const idx = AnnotateState.getFrameIdx();
  if (idx !== _lastLoadedFrameIdx) {
    _lastLoadedFrameIdx = idx;
    const frame = AnnotateState.currentFrame();
    if (frame) loadAnnotateImage(frame, idx);
  }
  Canvas.requestRender();
  Filmstrip.render();
  renderDetectionList();
  updateStatusBar();
  updateAnnotateReviewStatus();
  updateToolButtons();
  updateBulkActionsBar();
});

document.querySelector('.tab[data-tab="annotate"]').addEventListener("click", () => Canvas.resize());

document.getElementById("annotate-tool-select-btn").addEventListener("click", () => AnnotateState.setActiveTool("select"));
document.getElementById("annotate-tool-draw-btn").addEventListener("click", () => AnnotateState.setActiveTool("draw_box"));

document.getElementById("annotate-bulk-delete-btn").addEventListener("click", () => AnnotateState.deleteSelectedBoxes());
document.getElementById("annotate-bulk-class-select").addEventListener("change", (e) => {
  if (!e.target.value) return;
  AnnotateState.reassignSelectedBoxesClass(e.target.value);
  e.target.value = "";
});

document.getElementById("annotate-copy-prev-btn").addEventListener("click", () => {
  const prev = AnnotateState.getPrevFrame();
  if (!prev) {
    alert("This is the first frame — no previous frame to copy from.");
    return;
  }
  const copied = (prev.detections || []).map((d) => ({ ...d, id: makeId() }));
  if (!copied.length) {
    alert("Previous frame has no boxes to copy.");
    return;
  }
  AnnotateState.addBoxes(copied);
});

document.getElementById("annotate-save-next-btn").addEventListener("click", saveAndNext);

async function saveCurrentFrame() {
  const frame = AnnotateState.currentFrame();
  if (!frame) return false;
  const cleanBoxes = AnnotateState.getBoxes().map((d) => ({
    class_id: d.class_id,
    class_name: d.class_name,
    confidence: d.confidence,
    x_center: d.x_center,
    y_center: d.y_center,
    width: d.width,
    height: d.height,
  }));

  const res = await Api.putDetections(frame.id, cleanBoxes);
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    alert(errBody.detail || "Failed to save annotations");
    return false;
  }
  const saved = await res.json();
  AnnotateState.setFrameDetections(AnnotateState.getFrameIdx(), saved.detections);
  // Save implicitly confirms any still-dashed boxes — a bookkeeping side-effect, not an undoable edit
  AnnotateState.setBoxes(
    AnnotateState.getBoxes().map((d) => { const c = { ...d }; delete c._pending; return c; }),
    { pushUndo: false }
  );

  const reviewRes = await Api.postReview(frame.id, true);
  if (reviewRes.ok) AnnotateState.markReviewedLocal(true);
  return true;
}

async function toggleReviewed() {
  const frame = AnnotateState.currentFrame();
  if (!frame) return;
  const next = !frame.reviewed;
  const res = await Api.postReview(frame.id, next);
  if (res.ok) AnnotateState.markReviewedLocal(next);
}

async function saveAndNext() {
  if (!AnnotateState.currentFrame()) return;
  const ok = await saveCurrentFrame();
  if (!ok) return;
  const nextIdx = AnnotateState.findNextUnreviewedIndex(AnnotateState.getFrameIdx());
  if (nextIdx === -1) {
    alert("Saved — no more unreviewed frames.");
  } else {
    AnnotateState.selectFrame(nextIdx);
  }
}

function updateAssistBackendFields() {
  const backend = document.querySelector('input[name="assist-backend"]:checked').value;
  document.getElementById("assist-local-fields").classList.toggle("hidden", backend !== "local");
  document.getElementById("assist-roboflow-fields").classList.toggle("hidden", backend !== "roboflow");
}
document.querySelectorAll('input[name="assist-backend"]').forEach((el) => {
  el.addEventListener("change", updateAssistBackendFields);
});
updateAssistBackendFields();

document.getElementById("assist-run-btn").addEventListener("click", async () => {
  const frame = AnnotateState.currentFrame();
  if (!frame) return;
  const backend = document.querySelector('input[name="assist-backend"]:checked').value;
  const body = { backend, model_path: document.getElementById("assist-model-path").value };

  if (backend === "roboflow") {
    const apiKey = document.getElementById("assist-rf-api-key").value.trim();
    if (!apiKey) {
      alert("Please enter a Roboflow API Key first");
      return;
    }
    if (!confirmRoboflowCall(1)) return;
    body.api_key = apiKey;
    body.workspace_name = document.getElementById("assist-rf-workspace").value.trim();
    body.workflow_id = document.getElementById("assist-rf-workflow-id").value.trim();
  }

  const runBtn = document.getElementById("assist-run-btn");
  runBtn.disabled = true;
  try {
    const res = await Api.postAssist(frame.id, body);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      alert(errBody.detail || "Assist failed");
      return;
    }
    const data = await res.json();
    const newBoxes = (data.detections || []).map((d) => ({ ...d, id: makeId(), _pending: true }));
    if (newBoxes.length) AnnotateState.addBoxes(newBoxes);
  } finally {
    runBtn.disabled = false;
  }
});

document.getElementById("assist-accept-all-btn").addEventListener("click", () => {
  const boxes = AnnotateState.getBoxes();
  if (!boxes.some((b) => b._pending)) return;
  AnnotateState.setBoxes(boxes.map((b) => { const c = { ...b }; delete c._pending; return c; }));
});

document.getElementById("assist-reject-all-btn").addEventListener("click", () => {
  const boxes = AnnotateState.getBoxes();
  if (!boxes.some((b) => b._pending)) return;
  AnnotateState.setBoxes(boxes.filter((b) => !b._pending));
});

document.getElementById("annotate-clear-btn").addEventListener("click", () => {
  if (!AnnotateState.currentFrame() || !AnnotateState.getBoxes().length) return;
  AnnotateState.setBoxes([]);
  AnnotateState.selectBox(null);
});

document.getElementById("annotate-save-btn").addEventListener("click", async () => {
  if (!AnnotateState.currentFrame()) return;
  const ok = await saveCurrentFrame();
  if (ok) alert("Saved");
});

document.getElementById("annotate-mark-reviewed-btn").addEventListener("click", async () => {
  const frame = AnnotateState.currentFrame();
  if (!frame) return;
  const res = await Api.postReview(frame.id, true);
  if (!res.ok) return;
  AnnotateState.markReviewedLocal(true);
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
