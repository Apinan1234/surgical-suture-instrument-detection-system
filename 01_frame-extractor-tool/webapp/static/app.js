// ────────────────────────────── F-2: shared fetch helper + theme ──────────────────────────────

async function apiFetch(path, opts) {
  opts = opts || {};
  return fetch(path, opts);
}

// ── Job pointers ──
//
// A job id that lives only in a JS variable dies on reload, and that id is the only handle on what
// the job produced: this app has no job-list route and no job picker. 04ba847 fixed it for Detect,
// where the cost was a whole run of frames becoming unreachable. Extract and Export paid the same
// price more quietly, in two download buttons that vanished on refresh. One helper, three uses.
function makeJobPointer(storageKey, statusPath) {
  return {
    set(id) {
      if (id) localStorage.setItem(storageKey, id);
      else localStorage.removeItem(storageKey);
    },
    // The persisted id together with the server's current record for it, or null. A pointer the
    // server no longer knows (state.json reset, or a different data dir) is dropped quietly rather
    // than reported: from the user's side it is simply a job that is not there any more.
    async restore() {
      const id = localStorage.getItem(storageKey);
      if (!id) return null;
      const res = await apiFetch(statusPath + "/" + id);
      if (!res.ok) {
        localStorage.removeItem(storageKey);
        return null;
      }
      return { id: id, job: await res.json() };
    },
  };
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
  if (name === "analytics") refreshAnalytics();
}

// ── Footer step nav ──
//
// The tabs are at the top of the page and nowhere else, so reaching the next step after filling in a
// long form - Extract's especially - meant scrolling all the way back up. The steps are read off the
// tab buttons rather than listed again here, so their order and their labels cannot drift from the
// navigation they mirror.
function stepNavButton(label, target) {
  const btn = document.createElement("button");
  btn.className = "btn-download";
  btn.textContent = label;
  btn.addEventListener("click", () => {
    switchTab(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  return btn;
}

function buildStepNav() {
  const steps = Array.from(document.querySelectorAll(".tabs .tab")).map((btn) => ({
    name: btn.dataset.tab,
    label: btn.textContent.trim(),
  }));
  steps.forEach((step, i) => {
    const section = document.getElementById(step.name + "-section");
    if (!section) return;
    const nav = document.createElement("div");
    // space-between with an empty first slot, so a lone Next button still sits on the right.
    nav.style.cssText = "display:flex; justify-content:space-between; gap:8px; margin-top:24px;";
    nav.appendChild(
      i > 0 ? stepNavButton("← " + steps[i - 1].label, steps[i - 1].name) : document.createElement("span")
    );
    if (i < steps.length - 1) {
      nav.appendChild(stepNavButton(steps[i + 1].label + " →", steps[i + 1].name));
    }
    section.appendChild(nav);
  });
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
const extractJobPointer = makeJobPointer("extract_job_id", "/api/extract");

function setExtractJobId(id) {
  currentExtractJobId = id;
  extractJobPointer.set(id);
}
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
  setExtractJobId(data.job_id);
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

// The zip is only reachable through this id, and the button that uses it used to disappear on any
// refresh - which is exactly why the user could not find it.
async function restoreExtractJob() {
  const restored = await extractJobPointer.restore();
  if (!restored) return;
  const job = restored.job;
  setExtractJobId(restored.id);
  document.getElementById("extract-progress-wrap").classList.remove("hidden");

  if (job.status === "running") {
    document.getElementById("extract-start-btn").disabled = true;
    document.getElementById("extract-stop-btn").classList.remove("hidden");
    startPolling(); // re-renders the whole log, which is right: the log element is empty after a reload
    return;
  }
  document.getElementById("extract-progress-fill").style.width = job.progress + "%";
  document.getElementById("extract-progress-label").textContent =
    job.status + " - " + job.saved_total + " frames saved";
  document.getElementById("download-zip-btn").classList.toggle("hidden", job.saved_total === 0);
  lastExtractedFrameIds = job.frame_ids || [];
  updateDetectFramesInfo();
}

// ────────────────────────────── F-4: Detect section ──────────────────────────────

let lastExtractedFrameIds = [];
let classColors = {};
// Mirrors the server's MAX_BULK_FRAMES default so a too-long span is refused before it is built.
// The server is authoritative (it 422s regardless) — this only buys a clearer message.
const MAX_BULK_FRAMES = 500;
let currentDetectJobId = null;
let detectPollTimer = null;
let detectFrames = [];
let detectPreviewIdx = 0;

// Annotate and Export both hang off the last Detect run, and nothing else can reach a job by id —
// there is no picker and no list route. Losing this id on a reload therefore strands every frame in
// that run: re-running Extract mints new frame ids, so annotations already saved against the old
// ones stay in state.json but become unreachable from the UI. Persist it so a reload — or coming
// back the next day — lands back on the same frames.
const detectJobPointer = makeJobPointer("detect_job_id", "/api/detect");

function setDetectJobId(id) {
  currentDetectJobId = id;
  detectJobPointer.set(id);
}

async function restoreDetectJob() {
  const restored = await detectJobPointer.restore();
  if (!restored) return;
  const id = restored.id;
  const job = restored.job;
  currentDetectJobId = id;
  // Re-arm the Detect button with this run's frames: after retraining, re-detecting the same frames
  // with a better model is the natural next step, and skip_reviewed protects what is already done.
  lastExtractedFrameIds = job.frame_ids;
  updateDetectFramesInfo();
  document.getElementById("detect-progress-wrap").classList.remove("hidden");

  if (job.status === "running") {
    document.getElementById("detect-start-btn").disabled = true;
    document.getElementById("detect-stop-btn").classList.remove("hidden");
    startDetectPolling(); // loads the frames itself once the job reaches done/stopped
    return;
  }
  document.getElementById("detect-progress-fill").style.width = job.progress + "%";
  document.getElementById("detect-progress-label").textContent =
    job.status + " — " + job.detected_total + "/" + job.frame_ids.length + " frames with objects";
  await loadDetectFrames(job.frame_ids);
}

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

// Each pair is [<select> that lists what the server has, text input holding the path actually sent].
// The text input stays authoritative: a path can be typed for a model the scan does not know about.
const MODEL_PICKERS = [
  ["model-select", "model-path"],
  ["assist-model-select", "assist-model-path"],
];

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

  // A datalist on its own is not a picker. Chrome filters its suggestions against whatever is
  // already in the text box, and both boxes ship pre-filled with yolo11n.pt, so the list of models
  // on the server was effectively invisible - users went looking for an upload button and
  // re-uploaded a model the server already had.
  MODEL_PICKERS.forEach(([selectId, inputId]) => {
    const select = document.getElementById(selectId);
    const input = document.getElementById(inputId);
    if (!select || !input) return;
    select.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = data.models.length ? "Pick a model on the server..." : "No models found";
    select.appendChild(placeholder);
    data.models.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
    syncModelSelect(selectId, inputId);
  });
}

// Never let the dropdown claim a model the request will not actually use: it shows the placeholder
// whenever the typed path is not one of the scanned ones.
function syncModelSelect(selectId, inputId) {
  const select = document.getElementById(selectId);
  const input = document.getElementById(inputId);
  if (!select || !input) return;
  const match = Array.from(select.options).some((o) => o.value === input.value);
  select.value = match ? input.value : "";
}

MODEL_PICKERS.forEach(([selectId, inputId]) => {
  document.getElementById(selectId).addEventListener("change", (e) => {
    if (e.target.value) document.getElementById(inputId).value = e.target.value;
  });
  document.getElementById(inputId).addEventListener("input", () => syncModelSelect(selectId, inputId));
});

document.getElementById("model-upload-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  const res = await apiFetch("/api/models", { method: "POST", body: formData });
  if (res.ok) {
    const data = await res.json();
    await refreshModelOptions();
    document.getElementById("model-path").value = data.uploaded;
  } else {
    const body = await res.json().catch(() => ({}));
    alert(body.detail || "Upload failed");
  }
  e.target.value = "";
});

let classNames = [];

async function refreshClasses() {
  const res = await apiFetch("/api/classes");
  if (!res.ok) return;
  const data = await res.json();
  classColors = data.class_colors || {};
  classNames = data.class_names || [];
  populateAnnotateClassSelect();
  buildClassConfInputs("detect-class-conf");
  buildClassConfInputs("assist-class-conf");
}

// One number input per class, generated from the same `classNames` list the class dropdowns use, so
// a new class needs no HTML edit. A blank input means that class keeps the run's single `conf` —
// only the ones actually filled in are sent, which keeps request bodies unchanged when nobody uses
// the feature. Detect and Label Assist each get their own set, matching the existing convention that
// Assist's model picker is deliberately independent of Detect's.
function buildClassConfInputs(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const previous = readClassConf(containerId); // survive a /api/classes refresh mid-typing
  container.innerHTML = "";
  classNames.forEach((name) => {
    const row = document.createElement("div");
    row.style.cssText = "display:flex; align-items:center; gap:8px; margin-top:6px;";

    const label = document.createElement("label");
    label.htmlFor = `${containerId}-${name}`;
    label.textContent = name;
    label.style.cssText = "flex:1; margin:0; font-size:12px;";

    const input = document.createElement("input");
    input.className = "input";
    input.type = "number";
    input.id = `${containerId}-${name}`;
    input.dataset.className = name;
    input.min = "0.01";
    input.max = "0.99";
    input.step = "0.01";
    input.placeholder = "—";
    input.style.cssText = "width:84px; padding:4px 8px; font-size:12px;";
    if (previous[name] !== undefined) input.value = previous[name];

    row.appendChild(label);
    row.appendChild(input);
    container.appendChild(row);
  });
}

function readClassConf(containerId) {
  const out = {};
  document.querySelectorAll(`#${containerId} input[data-class-name]`).forEach((input) => {
    const value = parseFloat(input.value);
    if (!Number.isNaN(value)) out[input.dataset.className] = value;
  });
  return out;
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

  const classConf = readClassConf("detect-class-conf");
  if (Object.keys(classConf).length) body.class_conf = classConf;

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
  setDetectJobId(data.job_id);
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
  const label = document.getElementById("detect-progress-label");
  // startDetectPolling() writes the run summary immediately before awaiting this, so borrow the
  // label for loading progress and put the summary back rather than leaving a stale "loading…".
  const summaryText = label.textContent;
  const frames = await fetchAllJobFrames(currentDetectJobId, (loaded, total) => {
    if (total > FRAMES_PAGE_SIZE) label.textContent = `loading frames — ${loaded} / ${total}`;
  });
  label.textContent = summaryText;
  if (!frames) return;

  detectFrames = frames;
  detectPreviewIdx = 0;
  if (detectFrames.length) {
    document.getElementById("detect-preview-wrap").classList.remove("hidden");
    showDetectPreview(0);
  }
  initAnnotateFrames(frames);
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

// Unlike rectToNormalized (which takes pixel coords + imgW/imgH), this operates on already-normalized
// [0,1] polygon points directly — polygon points are stored normalized from the moment they're
// committed, whereas box-drag gesture state is naturally tracked in pixel/image space mid-drag.
// Mirrors detector.py's polygon_bbox() exactly — keep both in sync if either changes.
function polygonToNormalizedBBox(points) {
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const x1 = Math.min(...xs), x2 = Math.max(...xs);
  const y1 = Math.min(...ys), y2 = Math.max(...ys);
  return {
    x_center: clamp01((x1 + x2) / 2),
    y_center: clamp01((y1 + y2) / 2),
    width: clampPos(x2 - x1),
    height: clampPos(y2 - y1),
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

// Polygon vertex hit-testing — returns the index of the vertex under imgPt, or null.
function hitTestPolygonVertices(imgPt, box, imgW, imgH, tolImg) {
  if (!box.points) return null;
  for (let i = 0; i < box.points.length; i++) {
    const [nx, ny] = box.points[i];
    if (Math.abs(imgPt.x - nx * imgW) <= tolImg && Math.abs(imgPt.y - ny * imgH) <= tolImg) return i;
  }
  return null;
}

// Keypoint hit-testing — returns the index of the point under imgPt, or null. Ignores the 3rd
// (visibility) element of each [x, y, v] triple. Kept as its own function (not a generalization of
// hitTestPolygonVertices) since the tuple shape differs — [x,y,v] vs [x,y].
function hitTestKeypoints(imgPt, box, imgW, imgH, tolImg) {
  if (!box.keypoints) return null;
  for (let i = 0; i < box.keypoints.length; i++) {
    const [nx, ny] = box.keypoints[i];
    if (Math.abs(imgPt.x - nx * imgW) <= tolImg && Math.abs(imgPt.y - ny * imgH) <= tolImg) return i;
  }
  return null;
}

// A keypoint set's bbox derivation is the same "AABB of an arbitrary point array" operation as a
// polygon's — reuses polygonToNormalizedBBox on the (x,y) projection of each [x,y,v] keypoint.
function keypointsToNormalizedBBox(keypoints) {
  return polygonToNormalizedBBox(keypoints.map(([x, y]) => [x, y]));
}

// Orientation angle helper for a 2-point (base->tip) keypoint pair — shared by the committed-
// detection angle badge (renderDetectionList) and KeypointTool's live draw-time preview.
// Image/screen coordinate convention: 0deg = +x (right), 90deg = +y (down) — y grows downward,
// this is NOT flipped to "math"/Cartesian convention. MUST mirror train_roboflow_yolo.py's
// keypoint_angle_deg() bit-for-bit (same atan2(dy, dx) formula) or the webapp's displayed angle and
// the CSV-logged angle become incomparable numbers for the same annotation. Range: (-180, 180].
function keypointAngleDeg(dx, dy) {
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

// Angle for a committed instance's normalized keypoints [[x,y,v],[x,y,v]], or null if not exactly
// 2 points, or either point has v===0 (not-labeled — a meaningless placeholder position, not a
// real coordinate). imgW/imgH (Canvas.getImageSize()) de-normalize x and y on their own separate
// axis before the angle math — required for an aspect-correct angle on a non-square frame (x is
// stored normalized by width, y by height, independently).
function keypointPairAngleDeg(keypoints, imgW, imgH) {
  if (!keypoints || keypoints.length !== 2 || !imgW || !imgH) return null;
  const [[bx, by, bv], [tx, ty, tv]] = keypoints;
  if (bv === 0 || tv === 0) return null;
  return keypointAngleDeg((tx - bx) * imgW, (ty - by) * imgH);
}

function distToSegment(pt, a, b) {
  const abx = b.x - a.x, aby = b.y - a.y;
  const lenSq = abx * abx + aby * aby;
  let t = lenSq ? ((pt.x - a.x) * abx + (pt.y - a.y) * aby) / lenSq : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(pt.x - (a.x + t * abx), pt.y - (a.y + t * aby));
}

// Nearest polygon edge to imgPt within tolImg — used for double-click-to-insert-vertex.
function hitTestPolygonEdge(imgPt, box, imgW, imgH, tolImg) {
  const pts = box.points.map(([x, y]) => ({ x: x * imgW, y: y * imgH }));
  let best = null, bestDist = tolImg;
  for (let i = 0; i < pts.length; i++) {
    const d = distToSegment(imgPt, pts[i], pts[(i + 1) % pts.length]);
    if (d <= bestDist) { bestDist = d; best = { afterIndex: i }; }
  }
  return best;
}

// Ray-casting point-in-polygon test, image-space pixel coordinates.
function pointInPolygonImg(imgPt, normPoints, imgW, imgH) {
  const pts = normPoints.map(([x, y]) => ({ x: x * imgW, y: y * imgH }));
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i].x, yi = pts[i].y, xj = pts[j].x, yj = pts[j].y;
    const intersect = ((yi > imgPt.y) !== (yj > imgPt.y)) &&
      (imgPt.x < (xj - xi) * (imgPt.y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function hitTestBoxBody(imgPt, box, imgW, imgH) {
  if (box.points && box.points.length >= 3) return pointInPolygonImg(imgPt, box.points, imgW, imgH);
  const rect = boxRectImg(box, imgW, imgH);
  return imgPt.x >= rect.x1 && imgPt.x <= rect.x2 && imgPt.y >= rect.y1 && imgPt.y <= rect.y2;
}

function findTopBoxAt(imgPt, imgW, imgH) {
  const boxes = AnnotateState.getBoxes();
  for (let i = boxes.length - 1; i >= 0; i--) {
    if (hitTestBoxBody(imgPt, boxes[i], imgW, imgH)) return boxes[i];
  }
  return null;
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

// ── Keyframe interpolation math (pure functions, no state, no DOM) ──

// Normalized-space IoU. Used only to pair instances between two keyframes, never for hit-testing,
// so it deliberately ignores polygon/keypoint outlines and compares the bboxes those already derive.
function bboxIou(a, b) {
  const ax1 = a.x_center - a.width / 2, ax2 = a.x_center + a.width / 2;
  const ay1 = a.y_center - a.height / 2, ay2 = a.y_center + a.height / 2;
  const bx1 = b.x_center - b.width / 2, bx2 = b.x_center + b.width / 2;
  const by1 = b.y_center - b.height / 2, by2 = b.y_center + b.height / 2;
  const iw = Math.min(ax2, bx2) - Math.max(ax1, bx1);
  const ih = Math.min(ay2, by2) - Math.max(ay1, by1);
  if (iw <= 0 || ih <= 0) return 0;
  const inter = iw * ih;
  const union = a.width * a.height + b.width * b.height - inter;
  return union > 0 ? inter / union : 0;
}

// Two instances may be interpolated only if the result would be meaningful the whole way across:
// same class, and the same shape with the same number of vertices. Interpolating a 4-vertex polygon
// into a 7-vertex one, or a polygon into a plain box, has no correct answer — such a pair is left
// unmatched rather than guessed at.
function canPairForInterpolation(a, b) {
  if (a.class_name !== b.class_name) return false;
  const aPts = a.points ? a.points.length : 0, bPts = b.points ? b.points.length : 0;
  const aKps = a.keypoints ? a.keypoints.length : 0, bKps = b.keypoints ? b.keypoints.length : 0;
  return aPts === bPts && aKps === bKps;
}

// Greedy pairing between two keyframes' instances, best correspondence first. Greedy rather than
// optimal (Hungarian): with the handful of instances a surgical frame actually holds, the two agree
// in practice, and one obviously-correct pass beats a matrix solver nobody will maintain.
//
// Every class-compatible pair is a candidate — overlap is a ranking signal, NOT a requirement. A
// keyframe pair is often seconds apart, and an instrument that travelled further than its own width
// has zero IoU with itself; gating on overlap would refuse to interpolate in exactly the case the
// feature exists for. IoU orders the candidates where it discriminates, centre distance breaks the
// ties (which includes every zero-overlap pair).
//
// Instances left unpaired are simply not interpolated — an unpaired box means the object entered or
// left mid-span, and inventing a track for it would fabricate ground truth.
function matchInstances(aDets, zDets) {
  const candidates = [];
  (aDets || []).forEach((a, ai) => {
    (zDets || []).forEach((z, zi) => {
      if (!canPairForInterpolation(a, z)) return;
      candidates.push({
        ai, zi,
        iou: bboxIou(a, z),
        dist: Math.hypot(a.x_center - z.x_center, a.y_center - z.y_center),
      });
    });
  });
  candidates.sort((p, q) => (q.iou - p.iou) || (p.dist - q.dist));
  const usedA = new Set(), usedZ = new Set(), pairs = [];
  for (const c of candidates) {
    if (usedA.has(c.ai) || usedZ.has(c.zi)) continue;
    usedA.add(c.ai);
    usedZ.add(c.zi);
    pairs.push({ a: aDets[c.ai], z: zDets[c.zi] });
  }
  return pairs;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

// One interpolated instance at position t in (0, 1) between keyframe instances a and z.
function lerpDetection(a, z, t) {
  const out = {
    id: makeId(),
    class_id: a.class_id,
    class_name: a.class_name,
    confidence: lerp(a.confidence ?? 1, z.confidence ?? 1, t),
    x_center: lerp(a.x_center, z.x_center, t),
    y_center: lerp(a.y_center, z.y_center, t),
    width: lerp(a.width, z.width, t),
    height: lerp(a.height, z.height, t),
    source: "interpolated",
    // Attributes are carried only where both ends agree. Taking them from one end would assert an
    // occlusion the annotator never claimed for these frames.
    occluded: !!a.occluded && !!z.occluded,
    truncated: !!a.truncated && !!z.truncated,
  };
  if (a.points && z.points) {
    // Vertex i to vertex i: counts are equal (canPairForInterpolation) and the polygon tool appends
    // in draw order, so index correspondence is the ordering the annotator actually drew.
    out.points = a.points.map((p, i) => [lerp(p[0], z.points[i][0], t), lerp(p[1], z.points[i][1], t)]);
  }
  if (a.keypoints && z.keypoints) {
    // Position interpolates; visibility does not - v is a discrete label (0/1/2), and a midpoint
    // between "occluded" and "visible" is not a state. Take the lower of the two, so a point that is
    // unlabeled at either end stays unlabeled across the span instead of being promoted to a real
    // coordinate the annotator never placed.
    out.keypoints = a.keypoints.map((p, i) => [
      lerp(p[0], z.keypoints[i][0], t),
      lerp(p[1], z.keypoints[i][1], t),
      Math.min(p[2], z.keypoints[i][2]),
    ]);
  }
  return out;
}

// ── Api: one wrapper per endpoint used by Annotate ──

const Api = {
  putDetections(frameId, detections, rev) {
    // `rev` omitted (e.g. a frame loaded before the server grew one) -> server falls back to
    // last-writer-wins; sent -> the server compares and 409s instead of clobbering someone's edits.
    const payload = { detections };
    if (typeof rev === "number") payload.rev = rev;
    return apiFetch(`/api/frames/${frameId}/detections`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  putDetectionsBulk(items) {
    // items: [{ frame_id, detections, rev }]. All-or-nothing server-side — a 409 means nothing was
    // written, so the caller never has to work out how far a partial batch got.
    return apiFetch("/api/frames/detections/bulk", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
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
  postOcr(frameId) {
    return apiFetch(`/api/frames/${frameId}/ocr`, { method: "POST" });
  },
  startOcrJob(frameIds, skipExisting) {
    return apiFetch("/api/ocr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame_ids: frameIds, skip_existing: !!skipExisting }),
    });
  },
  ocrJobStatus(jobId) {
    return apiFetch(`/api/ocr/${jobId}`);
  },
  stopOcrJob(jobId) {
    return apiFetch(`/api/ocr/${jobId}/stop`, { method: "POST" });
  },
  imageUrl(frameId) {
    return `/api/frames/${frameId}/image.jpg?t=${Date.now()}`;
  },
  thumbnailUrl(frameId, max) {
    // stable, NOT cache-busted — letting the browser HTTP-cache thumbnails is the point of S-9
    return `/api/frames/${frameId}/thumbnail.jpg?max=${max || 160}`;
  },
};

const FRAMES_PAGE_SIZE = 500;

// Fetch a detect job's whole frame list in bounded chunks.
//
// What this buys: bounded RESPONSE size and per-request server encode work. A 20k-frame job goes
// from one multi-MB response (ocr_text and detections ride along per frame) to ~40 small ones.
// What it does NOT buy: client memory. Every page is concatenated, AnnotateState keeps all of them,
// and the filmstrip still builds one <li> + <img> per frame — that, not payload size, is the real
// ceiling on very large jobs. Windowing the filmstrip is deliberately out of scope.
async function fetchAllJobFrames(jobId, onProgress) {
  const all = [];
  let offset = 0;
  for (;;) {
    const res = await apiFetch(`/api/detect/${jobId}/frames?limit=${FRAMES_PAGE_SIZE}&offset=${offset}`);
    // Never return a truncated list: a short frame list would make Save & Next stop early and
    // silently drop frames from the filmstrip, which is worse than loading nothing.
    if (!res.ok) return null;
    const data = await res.json();
    all.push(...data.frames);
    if (onProgress) onProgress(all.length, data.total);
    if (!data.frames.length || all.length >= data.total) break;
    offset += data.frames.length; // advance by what arrived, never by the requested limit
  }
  return all;
}

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

  function hydrate(detections, reviewed) {
    // Machine-sourced boxes on a not-yet-reviewed frame are unconfirmed suggestions — render them
    // the same dashed/pending way Label Assist's own suggestions already do (setLineDash, confidence
    // badge, Accept All/Reject All, "Save implicitly confirms"), so bulk Detect (S-4) results and
    // interpolated spans go through the same human-review gate Label Assist (S-8) results have.
    // Tested against the two machine values explicitly rather than `!== "manual"`: frame records
    // written before `source` existed carry no such key, and those are human work, not suggestions.
    const machine = (s) => s === "model" || s === "interpolated";
    return (detections || []).map((d) => ({
      ...d,
      id: makeId(),
      ...(machine(d.source) && !reviewed ? { _pending: true } : {}),
    }));
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
    const tool = Tools[activeTool];
    if (tool && tool.onDeactivate) tool.onDeactivate(); // discard in-progress draw/drag before switching frames
    frameIdx = idx;
    boxes = hydrate(frames[idx].detections, frames[idx].reviewed);
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

  function deleteVertex(boxId, vIdx) {
    const box = boxes.find((b) => b.id === boxId);
    if (!box) return;
    if (box.points) {
      if (box.points.length <= 3) return; // floor: polygon never drops below 3 points
      const points = box.points.filter((_, i) => i !== vIdx);
      const bbox = polygonToNormalizedBBox(points);
      setBoxes(boxes.map((b) => (b.id === boxId ? { ...b, points, ...bbox } : b)));
    } else if (box.keypoints) {
      if (box.keypoints.length <= 1) return; // never drop the last point this way — delete the instance instead
      const keypoints = box.keypoints.filter((_, i) => i !== vIdx);
      const bbox = keypointsToNormalizedBBox(keypoints);
      setBoxes(boxes.map((b) => (b.id === boxId ? { ...b, keypoints, ...bbox } : b)));
    }
  }

  function setKeypointVisibility(boxId, vIdx, v) {
    const box = boxes.find((b) => b.id === boxId);
    if (!box || !box.keypoints) return;
    const keypoints = box.keypoints.map((p, i) => (i === vIdx ? [p[0], p[1], v] : p));
    setBoxes(boxes.map((b) => (b.id === boxId ? { ...b, keypoints } : b)));
  }

  function reassignClassByIds(ids, className) {
    if (!ids.length) return;
    const idSet = new Set(ids);
    const classId = classNames.indexOf(className);
    setBoxes(boxes.map((b) => (idSet.has(b.id) ? { ...b, class_id: classId, class_name: className } : b)));
  }

  function setBoxAttrByIds(ids, key, value) {
    if (!ids.length) return;
    const idSet = new Set(ids);
    // Spread-based and routed through setBoxes, exactly like reassignClassByIds: keeps id/_pending/
    // points/keypoints intact and makes a toggle one undoable step no matter how many boxes.
    setBoxes(boxes.map((b) => (idSet.has(b.id) ? { ...b, [key]: !!value } : b)));
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

  function setFrameDetections(idx, detections, rev) {
    if (!frames[idx]) return;
    frames[idx].detections = detections;
    // frames[idx] IS the server record, so its `rev` is what the next save sends back as its
    // precondition — keep it in step with the detections it belongs to.
    if (typeof rev === "number") frames[idx].rev = rev;
  }

  function setFrameRev(idx, rev) {
    if (frames[idx] && typeof rev === "number") frames[idx].rev = rev;
  }

  function setFrameOcrText(idx, text) {
    if (frames[idx]) frames[idx].ocr_text = text;
  }

  // Repaint every subscriber without touching `boxes` or the undo stack. selectFrame() is the usual
  // way to force a repaint, but it re-hydrates the canvas from the frame's last SERVER-saved
  // detections — which silently discards unsaved edits when the frame is already the current one.
  function repaint() {
    emit();
  }

  return {
    subscribe, init, selectFrame, currentFrame, getBoxes, setBoxes, addBoxes,
    selectBox, selectBoxes, getSelected, isSelected, getSelectedIds, getSelectedCount,
    reselectIfMissing, deleteBoxesByIds, deleteVertex, setKeypointVisibility, reassignClassByIds, setBoxAttrByIds, deleteSelectedBoxes, reassignSelectedBoxesClass,
    setActiveTool, getActiveTool: () => activeTool,
    getFrames: () => frames, getFrameIdx: () => frameIdx, getPrevFrame,
    findNextUnreviewedIndex, markReviewedLocal, setFrameDetections, setFrameRev, setFrameOcrText,
    repaint,
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
    const color = classColors[b.class_name] || "#AAAAAA";
    const lw = 2 / cssScale;
    const isSelected = AnnotateState.isSelected(b.id);
    const isPolygon = b.points && b.points.length >= 3;
    const isKeypoints = b.keypoints && b.keypoints.length > 0;

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.setLineDash(b._pending ? [6 / cssScale, 4 / cssScale] : []);

    let x1, y1, bw, bh, labelX, labelY;
    if (isPolygon) {
      const pts = b.points.map(([x, y]) => [x * imgW, y * imgH]);
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.closePath();
      ctx.stroke();
      x1 = Math.min(...pts.map((p) => p[0]));
      y1 = Math.min(...pts.map((p) => p[1]));
    } else if (isKeypoints) {
      const pts = b.keypoints.map(([x, y, v]) => [x * imgW, y * imgH, v]);
      pts.forEach(([px, py, v]) => {
        ctx.beginPath();
        if (v === 2) {
          ctx.fillStyle = color;
          ctx.arc(px, py, 4 / cssScale, 0, Math.PI * 2);
          ctx.fill();
        } else if (v === 1) {
          ctx.strokeStyle = color;
          ctx.lineWidth = lw;
          ctx.arc(px, py, 4 / cssScale, 0, Math.PI * 2);
          ctx.stroke();
        } else {
          ctx.fillStyle = "#888888";
          ctx.arc(px, py, 2 / cssScale, 0, Math.PI * 2);
          ctx.fill();
        }
      });
      x1 = Math.min(...pts.map((p) => p[0]));
      y1 = Math.min(...pts.map((p) => p[1]));
    } else {
      x1 = (b.x_center - b.width / 2) * imgW;
      y1 = (b.y_center - b.height / 2) * imgH;
      bw = b.width * imgW;
      bh = b.height * imgH;
      ctx.strokeRect(x1, y1, bw, bh);
    }
    ctx.setLineDash([]);

    if (isSelected && !isKeypoints) {
      // Keypoint selection feedback is drawn per-point by SelectTool.render instead — mirrors how
      // polygon vertex handles are also SelectTool's job, not drawBox's.
      ctx.strokeStyle = "#2563eb";
      ctx.lineWidth = lw * 1.5;
      ctx.setLineDash([4 / cssScale, 2 / cssScale]);
      if (isPolygon) {
        ctx.stroke(); // re-stroke the same path built above (still current — no beginPath since)
      } else {
        ctx.strokeRect(x1 - lw, y1 - lw, bw + 2 * lw, bh + 2 * lw);
      }
      ctx.setLineDash([]);
    }

    ctx.fillStyle = color;
    ctx.font = `${13 / cssScale}px sans-serif`;
    labelY = y1 - 4 / cssScale > 10 / cssScale ? y1 - 4 / cssScale : y1 + 12 / cssScale;
    ctx.fillText(b.class_name, x1, labelY);

    if (b._pending && b.confidence < 0.5) {
      ctx.fillStyle = "#e94560"; // var(--highlight) — identical across every theme in style.css
      ctx.fillText(`⚠ ${b.confidence.toFixed(2)}`, x1, labelY + 14 / cssScale);
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
    if (!panDragStart) setCursor(v ? "grab" : (["draw_box", "polygon", "keypoint"].includes(AnnotateState.getActiveTool()) ? "crosshair" : "default"));
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
    if (e.button !== 0) return; // right/middle click never drives move/resize/marquee/draw
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

  // The two view controls above are the only interactions a user cannot discover from the "?"
  // cheat-sheet, because that sheet is generated from Keyboard.SHORTCUTS and neither of these ever
  // reaches it: Space is consumed before the lookup table, and wheel/drag are not keydowns at all.
  // Their help text lives here, next to the handlers that implement them, for the same reason the
  // key labels live in SHORTCUTS — so the documentation cannot drift away from the behavior.
  const POINTER_HELP = [
    "Space + drag — Pan the image",
    "Mouse wheel — Zoom in / out at the cursor",
  ];
  canvas.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    if (!img) return;
    const imgPt = screenToImage(e.clientX, e.clientY);
    const imgW = img.naturalWidth, imgH = img.naturalHeight;

    const selected = AnnotateState.getSelected();
    if (AnnotateState.getActiveTool() === "select" && selected) {
      const tolImg = HANDLE_PX / cssScale;
      if (selected.points) {
        const vIdx = hitTestPolygonVertices(imgPt, selected, imgW, imgH, tolImg);
        if (vIdx !== null) {
          ContextMenu.openForVertex(e.clientX, e.clientY, selected, vIdx);
          return;
        }
      } else if (selected.keypoints) {
        const kIdx = hitTestKeypoints(imgPt, selected, imgW, imgH, tolImg);
        if (kIdx !== null) {
          ContextMenu.openForKeypoint(e.clientX, e.clientY, selected, kIdx);
          return;
        }
      }
    }

    const hit = findTopBoxAt(imgPt, imgW, imgH);
    if (hit) ContextMenu.openForBox(e.clientX, e.clientY, hit);
    else ContextMenu.close();
  });
  canvas.addEventListener("dblclick", (e) => {
    if (e.button !== 0) return;
    dispatch("onDoubleClick", e);
  });

  window.addEventListener("resize", () => resize());

  return {
    setImage, resize, requestRender, screenToImage, imageToScreen, zoomBy, setSpaceHeld, setCursor,
    getPointerHelp: () => POINTER_HELP.slice(),
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

  return { onPointerDown, onPointerMove, onPointerUp, render, onActivate, onDeactivate, cancel, onEscape: cancel };
})();

// ── PolygonTool: click to add vertices; double-click/Enter to close (≥3 pts); Esc cancels ──

const PolygonTool = (() => {
  let points = null;    // array of {x,y} in IMAGE space while drawing
  let cursorPt = null;  // live mouse position, for the rubber-band preview segment

  function onPointerDown(e) {
    if (!AnnotateState.currentFrame()) return;
    const pt = Canvas.screenToImage(e.clientX, e.clientY);
    if (!points) points = [];
    points.push(pt);
    cursorPt = pt;
    Canvas.requestRender();
  }

  function onPointerMove(e) {
    if (!points) return;
    cursorPt = Canvas.screenToImage(e.clientX, e.clientY);
    Canvas.requestRender();
  }

  function commit() {
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const normPoints = points.map((p) => [clamp01(p.x / imgW), clamp01(p.y / imgH)]);
    const bbox = polygonToNormalizedBBox(normPoints);
    const className = document.getElementById("annotate-class-select").value;
    AnnotateState.addBoxes([{
      id: makeId(),
      class_id: classNames.indexOf(className),
      class_name: className,
      confidence: 1.0,
      points: normPoints,
      ...bbox,
    }]);
    cancel();
  }

  function onDoubleClick(e) {
    if (!points) return;
    // A double-click delivers TWO pointerdown events at ~the same spot; the 2nd one already pushed
    // a near-duplicate point before this handler runs — drop it so we don't commit a degenerate
    // zero-length final edge.
    if (points.length >= 2) {
      const a = points[points.length - 1], b = points[points.length - 2];
      if (Math.hypot(a.x - b.x, a.y - b.y) * Canvas.getCssScale() < 5) points.pop();
    }
    if (points.length < 3) return; // no-op — keep drawing until there are enough vertices to close
    commit();
  }

  // Called from the global Enter shortcut; returns true if it consumed the keypress.
  function onEnter() {
    if (!points) return false; // not drawing — let Enter behave normally (Save & Next)
    if (points.length >= 3) commit();
    return true; // consumed while a draw is in progress, even as a no-op with <3 points
  }

  function cancel() {
    points = null;
    cursorPt = null;
    Canvas.requestRender();
  }

  function render(ctx) {
    if (!points || !points.length) return;
    const scale = Canvas.getCssScale();
    const className = document.getElementById("annotate-class-select").value;
    const color = classColors[className] || "#AAAAAA";
    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 2 / scale;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
    if (cursorPt) ctx.lineTo(cursorPt.x, cursorPt.y);                          // live segment to cursor
    if (points.length >= 3 && cursorPt) ctx.lineTo(points[0].x, points[0].y);  // preview closing edge
    ctx.stroke();
    points.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3 / scale, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }

  function onActivate() { Canvas.setCursor("crosshair"); }
  function onDeactivate() { cancel(); }

  return { onPointerDown, onPointerMove, onDoubleClick, onEnter, render, onActivate, onDeactivate, cancel, onEscape: cancel };
})();

// ── KeypointTool: click to add points (v=2/visible by default); Enter/double-click to commit ──
// No rubber-band preview needed — unlike PolygonTool, points never connect, so there's no "next
// segment" to draw a live preview of. Visibility (occluded/not-labeled) is a post-hoc edit via the
// Select tool's right-click menu, not a draw-time gesture.

const KeypointTool = (() => {
  let keypoints = null; // array of {x,y} in IMAGE space while drawing

  function onPointerDown(e) {
    if (!AnnotateState.currentFrame()) return;
    const pt = Canvas.screenToImage(e.clientX, e.clientY);
    if (!keypoints) keypoints = [];
    keypoints.push(pt);
    Canvas.requestRender();
  }

  function commit() {
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const normKeypoints = keypoints.map((p) => [clamp01(p.x / imgW), clamp01(p.y / imgH), 2]);
    const bbox = keypointsToNormalizedBBox(normKeypoints);
    const className = document.getElementById("annotate-class-select").value;
    AnnotateState.addBoxes([{
      id: makeId(),
      class_id: classNames.indexOf(className),
      class_name: className,
      confidence: 1.0,
      keypoints: normKeypoints,
      ...bbox,
    }]);
    cancel();
  }

  function onDoubleClick() {
    if (!keypoints || !keypoints.length) return;
    // Same duplicate-point artifact PolygonTool's dblclick has (the 2nd click's own pointerdown
    // already pushed a near-duplicate point before dblclick fires) — drop it.
    if (keypoints.length >= 2) {
      const a = keypoints[keypoints.length - 1], b = keypoints[keypoints.length - 2];
      if (Math.hypot(a.x - b.x, a.y - b.y) * Canvas.getCssScale() < 5) keypoints.pop();
    }
    commit();
  }

  // Called from the global Enter shortcut; returns true if it consumed the keypress.
  function onEnter() {
    if (!keypoints) return false; // not drawing — let Enter behave normally (Save & Next)
    if (keypoints.length >= 1) commit();
    return true; // consumed while a draw is in progress
  }

  function cancel() {
    keypoints = null;
    Canvas.requestRender();
  }

  function render(ctx) {
    if (!keypoints || !keypoints.length) return;
    const scale = Canvas.getCssScale();
    const className = document.getElementById("annotate-class-select").value;
    const color = classColors[className] || "#AAAAAA";
    ctx.save();
    ctx.fillStyle = color;
    ctx.font = `${11 / scale}px sans-serif`;
    keypoints.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4 / scale, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillText(String(i + 1), p.x + 6 / scale, p.y - 6 / scale);
    });
    if (keypoints.length === 2) {
      // Live angle preview while placing point 2 (base=point 1, tip=point 2, by placement order).
      // keypoints here are already raw IMAGE-pixel {x,y} — no width/height de-normalization needed
      // (unlike the committed-instance path in renderDetectionList).
      const angle = keypointAngleDeg(keypoints[1].x - keypoints[0].x, keypoints[1].y - keypoints[0].y);
      const midX = (keypoints[0].x + keypoints[1].x) / 2;
      const midY = (keypoints[0].y + keypoints[1].y) / 2;
      ctx.fillText(`∠ ${angle.toFixed(1)}°`, midX + 6 / scale, midY - 6 / scale);
    }
    ctx.restore();
  }

  function onActivate() { Canvas.setCursor("crosshair"); }
  function onDeactivate() { cancel(); }

  return { onPointerDown, onDoubleClick, onEnter, render, onActivate, onDeactivate, cancel, onEscape: cancel };
})();

// ── SelectTool: click to select, drag to move, drag a handle to resize ──

const SelectTool = (() => {
  let mode = null; // null | "move" | "resize" | "vertex-drag" | "marquee"
  let activeHandle = null;
  let activeVertexIndex = null;
  let startImgPt = null;
  let startBox = null;
  let preDragBoxes = null;
  let snapshotTaken = false;
  let marqueeStart = null;
  let marqueeCurrent = null;

  function onPointerDown(e) {
    if (!AnnotateState.currentFrame()) return;
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const imgPt = Canvas.screenToImage(e.clientX, e.clientY);
    const tolImg = HANDLE_PX / Canvas.getCssScale();

    const selected = AnnotateState.getSelected();
    if (selected && selected.points) {
      const vIdx = hitTestPolygonVertices(imgPt, selected, imgW, imgH, tolImg);
      if (vIdx !== null) {
        mode = "vertex-drag";
        activeVertexIndex = vIdx;
        startImgPt = imgPt;
        startBox = { ...selected, points: selected.points.map((p) => [...p]) };
        preDragBoxes = AnnotateState.getBoxes();
        snapshotTaken = false;
        return;
      }
    } else if (selected && selected.keypoints) {
      const kIdx = hitTestKeypoints(imgPt, selected, imgW, imgH, tolImg);
      if (kIdx !== null) {
        mode = "keypoint-drag";
        activeVertexIndex = kIdx; // reused — only one mode is ever active at a time
        startImgPt = imgPt;
        startBox = { ...selected, keypoints: selected.keypoints.map((p) => [...p]) };
        preDragBoxes = AnnotateState.getBoxes();
        snapshotTaken = false;
        return;
      }
      // no exact point hit — fall through to findTopBoxAt below, which (via hitTestBoxBody's
      // unmodified plain-AABB fallback) treats the instance's derived bbox as its "grab body".
    } else if (selected) {
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
      startBox = hit.points ? { ...hit, points: hit.points.map((p) => [...p]) }
               : hit.keypoints ? { ...hit, keypoints: hit.keypoints.map((p) => [...p]) }
               : { ...hit };
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
    if (selected && selected.points) {
      const vIdx = hitTestPolygonVertices(imgPt, selected, imgW, imgH, tolImg);
      if (vIdx !== null) {
        Canvas.setCursor("pointer");
        return;
      }
    } else if (selected && selected.keypoints) {
      const kIdx = hitTestKeypoints(imgPt, selected, imgW, imgH, tolImg);
      if (kIdx !== null) {
        Canvas.setCursor("pointer");
        return;
      }
    } else if (selected) {
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

    if (mode === "vertex-drag") {
      const points = startBox.points.map((p, i) => (i === activeVertexIndex
        ? [clamp01((p[0] * imgW + dx) / imgW), clamp01((p[1] * imgH + dy) / imgH)]
        : p));
      const bbox = polygonToNormalizedBBox(points);
      const boxes = AnnotateState.getBoxes().map((b) => (b.id === startBox.id ? { ...b, points, ...bbox } : b));
      AnnotateState.setBoxes(boxes, { pushUndo: false });
      return;
    }
    if (mode === "keypoint-drag") {
      const keypoints = startBox.keypoints.map((p, i) => (i === activeVertexIndex
        ? [clamp01((p[0] * imgW + dx) / imgW), clamp01((p[1] * imgH + dy) / imgH), p[2]]
        : p));
      const bbox = keypointsToNormalizedBBox(keypoints);
      const boxes = AnnotateState.getBoxes().map((b) => (b.id === startBox.id ? { ...b, keypoints, ...bbox } : b));
      AnnotateState.setBoxes(boxes, { pushUndo: false });
      return;
    }
    if (mode === "move" && startBox.points) {
      const points = startBox.points.map((p) => [clamp01((p[0] * imgW + dx) / imgW), clamp01((p[1] * imgH + dy) / imgH)]);
      const bbox = polygonToNormalizedBBox(points);
      const boxes = AnnotateState.getBoxes().map((b) => (b.id === startBox.id ? { ...b, points, ...bbox } : b));
      AnnotateState.setBoxes(boxes, { pushUndo: false });
      return;
    }
    if (mode === "move" && startBox.keypoints) {
      const keypoints = startBox.keypoints.map(([x, y, v]) =>
        [clamp01((x * imgW + dx) / imgW), clamp01((y * imgH + dy) / imgH), v]);
      const bbox = keypointsToNormalizedBBox(keypoints);
      const boxes = AnnotateState.getBoxes().map((b) => (b.id === startBox.id ? { ...b, keypoints, ...bbox } : b));
      AnnotateState.setBoxes(boxes, { pushUndo: false });
      return;
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
    activeVertexIndex = null;
    startImgPt = null;
    startBox = null;
    preDragBoxes = null;
    snapshotTaken = false;
  }

  function onDoubleClick(e) {
    const selected = AnnotateState.getSelected();
    if (!selected || !selected.points) return;
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    const imgPt = Canvas.screenToImage(e.clientX, e.clientY);
    const tolImg = HANDLE_PX / Canvas.getCssScale();
    const edge = hitTestPolygonEdge(imgPt, selected, imgW, imgH, tolImg);
    if (!edge) return;
    const points = selected.points.slice();
    points.splice(edge.afterIndex + 1, 0, [clamp01(imgPt.x / imgW), clamp01(imgPt.y / imgH)]);
    const bbox = polygonToNormalizedBBox(points);
    AnnotateState.setBoxes(AnnotateState.getBoxes().map((b) => (b.id === selected.id ? { ...b, points, ...bbox } : b)));
  }

  function nudgeSelected(dxSign, dySign, big) {
    const selected = AnnotateState.getSelected();
    if (!selected) return;
    const { w: imgW, h: imgH } = Canvas.getImageSize();
    if (!imgW || !imgH) return;
    const stepPx = big ? 10 : 1;
    const dxN = (dxSign * stepPx) / imgW, dyN = (dySign * stepPx) / imgH;
    if (selected.points) {
      const points = selected.points.map(([x, y]) => [clamp01(x + dxN), clamp01(y + dyN)]);
      const bbox = polygonToNormalizedBBox(points);
      AnnotateState.setBoxes(AnnotateState.getBoxes().map((b) => (b.id === selected.id ? { ...b, points, ...bbox } : b)));
      return;
    }
    if (selected.keypoints) {
      const keypoints = selected.keypoints.map(([x, y, v]) => [clamp01(x + dxN), clamp01(y + dyN), v]);
      const bbox = keypointsToNormalizedBBox(keypoints);
      AnnotateState.setBoxes(AnnotateState.getBoxes().map((b) => (b.id === selected.id ? { ...b, keypoints, ...bbox } : b)));
      return;
    }
    const nx = clamp01(selected.x_center + dxN);
    const ny = clamp01(selected.y_center + dyN);
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
    const dpr = window.devicePixelRatio || 1;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (selected.points) {
      selected.points.forEach(([nx, ny]) => {
        const pt = Canvas.imageToScreen(nx * imgW, ny * imgH);
        ctx.beginPath();
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "#2563eb";
        ctx.lineWidth = 1.5;
        ctx.arc(pt.x, pt.y, HANDLE_PX / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      });
    } else if (selected.keypoints) {
      selected.keypoints.forEach(([nx, ny]) => {
        const pt = Canvas.imageToScreen(nx * imgW, ny * imgH);
        ctx.beginPath();
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "#2563eb";
        ctx.lineWidth = 1.5;
        ctx.arc(pt.x, pt.y, HANDLE_PX / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      });
    } else {
      const handles = handlePositions(boxRectImg(selected, imgW, imgH));
      Object.values(handles).forEach((h) => {
        const pt = Canvas.imageToScreen(h.x, h.y);
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "#2563eb";
        ctx.lineWidth = 1.5;
        ctx.fillRect(pt.x - HANDLE_PX / 2, pt.y - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX);
        ctx.strokeRect(pt.x - HANDLE_PX / 2, pt.y - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX);
      });
    }
    ctx.restore();
  }

  function onActivate() {
    Canvas.setCursor("default");
  }

  function onDeactivate() {
    mode = null;
    activeHandle = null;
    activeVertexIndex = null;
    preDragBoxes = null;
    snapshotTaken = false;
    marqueeStart = null;
    marqueeCurrent = null;
  }

  return {
    onPointerDown, onPointerMove, onPointerUp, onDoubleClick, render, onActivate, onDeactivate,
    nudgeSelected,
  };
})();

Tools.draw_box = DrawBoxTool;
Tools.select = SelectTool;
Tools.polygon = PolygonTool;
Tools.keypoint = KeypointTool;

// ── ContextMenu: right-click canvas → Delete / Reassign class (flat list, no submenus) ──

const ContextMenu = (() => {
  const el = document.getElementById("annotate-context-menu");

  function buildRows(ids) {
    el.innerHTML = "";
    const delBtn = document.createElement("button");
    delBtn.className = "danger";
    delBtn.textContent = ids.length >= 2 ? `Delete Selected (${ids.length})` : "Delete";
    delBtn.addEventListener("click", () => { AnnotateState.deleteBoxesByIds(ids); close(); });
    el.appendChild(delBtn);

    if (classNames.length) el.appendChild(document.createElement("hr"));
    classNames.forEach((name) => {
      const btn = document.createElement("button");
      btn.textContent = `Reassign to: ${name}`;
      btn.addEventListener("click", () => { AnnotateState.reassignClassByIds(ids, name); close(); });
      el.appendChild(btn);
    });
  }

  function positionAt(clientX, clientY) {
    el.classList.add("open");
    const w = el.offsetWidth, h = el.offsetHeight;
    el.style.left = `${Math.max(8, Math.min(clientX, window.innerWidth - w - 8))}px`;
    el.style.top = `${Math.max(8, Math.min(clientY, window.innerHeight - h - 8))}px`;
  }

  function openForBox(clientX, clientY, box) {
    const keepMulti = AnnotateState.isSelected(box.id) && AnnotateState.getSelectedCount() >= 2;
    if (!keepMulti) AnnotateState.selectBox(box.id);
    buildRows(AnnotateState.getSelectedIds());
    positionAt(clientX, clientY);
  }

  function buildVertexRows(box, vIdx) {
    el.innerHTML = "";
    const delBtn = document.createElement("button");
    delBtn.className = "danger";
    const canDelete = box.points.length > 3;
    delBtn.textContent = "Delete vertex";
    delBtn.disabled = !canDelete;
    if (!canDelete) delBtn.title = "A polygon needs at least 3 points — delete the whole shape instead.";
    delBtn.addEventListener("click", () => {
      if (!canDelete) return;
      AnnotateState.deleteVertex(box.id, vIdx);
      close();
    });
    el.appendChild(delBtn);
  }

  function openForVertex(clientX, clientY, box, vIdx) {
    buildVertexRows(box, vIdx);
    positionAt(clientX, clientY);
  }

  function buildKeypointVertexRows(box, vIdx) {
    el.innerHTML = "";
    const currentV = box.keypoints[vIdx][2];
    [[2, "Mark Visible"], [1, "Mark Occluded"], [0, "Mark Not Labeled"]].forEach(([v, label]) => {
      const btn = document.createElement("button");
      btn.textContent = (currentV === v ? "✓ " : "") + label;
      btn.addEventListener("click", () => { AnnotateState.setKeypointVisibility(box.id, vIdx, v); close(); });
      el.appendChild(btn);
    });
    el.appendChild(document.createElement("hr"));
    const delBtn = document.createElement("button");
    delBtn.className = "danger";
    const canDelete = box.keypoints.length > 1;
    delBtn.textContent = "Delete point";
    delBtn.disabled = !canDelete;
    if (!canDelete) delBtn.title = "A keypoint instance needs at least 1 point — delete the whole shape instead.";
    delBtn.addEventListener("click", () => {
      if (!canDelete) return;
      AnnotateState.deleteVertex(box.id, vIdx);
      close();
    });
    el.appendChild(delBtn);
  }

  function openForKeypoint(clientX, clientY, box, vIdx) {
    buildKeypointVertexRows(box, vIdx);
    positionAt(clientX, clientY);
  }

  function close() { el.classList.remove("open"); }
  function isOpen() { return el.classList.contains("open"); }

  // Capture phase: closes before Canvas's own bubble-phase pointerdown can start a drag underneath it.
  document.addEventListener("pointerdown", (e) => {
    if (isOpen() && e.button === 0 && !el.contains(e.target)) close();
  }, true);

  return { openForBox, openForVertex, openForKeypoint, close, isOpen };
})();

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
    const tool = Tools[AnnotateState.getActiveTool()];
    if (tool && tool.onEscape) tool.onEscape();
    else AnnotateState.selectBox(null);
  }

  function toggleCheatSheet() {
    const popover = document.getElementById("annotate-cheatsheet");
    if (!popover) return;
    if (!popover.classList.contains("open")) {
      popover.innerHTML = "";
      const pre = document.createElement("pre");
      // Mouse/view controls come from Canvas, which owns them — see its POINTER_HELP comment.
      pre.textContent = SHORTCUTS.filter((s) => s.label).map((s) => s.label)
        .concat(Canvas.getPointerHelp())
        .join("\n");
      popover.appendChild(pre);
    }
    popover.classList.toggle("open");
  }

  function toggleAttrOnSelection(key) {
    const ids = AnnotateState.getSelectedIds();
    if (!ids.length) return;
    // Toggle a multi-selection against the FIRST box so a mixed selection converges on one value
    // instead of flip-flopping each box independently.
    const first = AnnotateState.getBoxes().find((b) => b.id === ids[0]);
    AnnotateState.setBoxAttrByIds(ids, key, !(first && first[key]));
  }

  const SHORTCUTS = [
    { key: "v", label: "V — Select tool", handler: () => AnnotateState.setActiveTool("select") },
    { key: "b", label: "B — Draw box tool", handler: () => AnnotateState.setActiveTool("draw_box") },
    { key: "p", label: "P — Polygon tool", handler: () => AnnotateState.setActiveTool("polygon") },
    { key: "k", label: "K — Keypoint tool", handler: () => AnnotateState.setActiveTool("keypoint") },
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
    { key: "s", label: "S — Set start keyframe (interpolation)", handler: () => Interpolate.setStart() },
    { key: "i", label: "I — Interpolate from start keyframe to here", handler: () => Interpolate.run() },
    { key: "o", label: "O — Toggle occluded on selected box(es)", handler: () => toggleAttrOnSelection("occluded") },
    { key: "t", label: "T — Toggle truncated on selected box(es)", handler: () => toggleAttrOnSelection("truncated") },
    { key: "Enter", label: "Enter — Save & Next (or close polygon while drawing)", handler: () => {
        const tool = Tools[AnnotateState.getActiveTool()];
        if (tool && tool.onEnter && tool.onEnter()) return; // tool consumed Enter (e.g. closed a polygon)
        saveAndNext();
      }
    },
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
    if (e.key === "Escape" && ContextMenu.isOpen()) {
      ContextMenu.close();
      e.preventDefault();
      return; // don't fall through to onEscape()'s deselect/cancel-draw
    }
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
  Interpolate.clear(); // frame indices are about to change; a keyframe pinned to an old one is junk
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

  function hasOcrText(frame) {
    return !!(frame.ocr_text && frame.ocr_text.trim());
  }

  function frameBadge(frame) {
    const base = frame.reviewed ? "✅" : (frame.detections || []).length ? "🏷" : "🔴";
    return hasOcrText(frame) ? base + "📄" : base;
  }

  function passesFilter(frame, filter, query) {
    if (filter === "unreviewed" && frame.reviewed) return false;
    if (filter === "reviewed" && !frame.reviewed) return false;
    if (filter === "has_ocr" && !hasOcrText(frame)) return false;
    if (filter === "no_ocr" && hasOcrText(frame)) return false;
    // Free-text search ANDs with the dropdown. Frames with no OCR text never match a non-empty query.
    if (query && !(frame.ocr_text || "").toLowerCase().includes(query)) return false;
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
    const query = document.getElementById("annotate-filmstrip-search").value.trim().toLowerCase();
    let shown = 0;
    Array.from(list.children).forEach((li, i) => {
      const frame = frames[i];
      if (!frame) return;
      li.className = i === idx ? "selected" : "";
      if (passesFilter(frame, filter, query)) shown++;
      else li.classList.add("hidden-by-filter");
      const label = li.querySelector(".filmstrip-label");
      label.textContent = `${frameBadge(frame)} ${frame.filename}`;
    });
    const countEl = document.getElementById("annotate-filmstrip-match-count");
    countEl.textContent =
      query || filter !== "all" ? `${shown} / ${frames.length} shown` : "";
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
// Frame count is unchanged while typing, so render() takes the cheap patch() path and never tears
// down the <img> elements — rebuilding here would re-trigger every S-9 thumbnail fetch on each keystroke.
document.getElementById("annotate-filmstrip-search").addEventListener("input", () => Filmstrip.render());

// ── PropertyPanel: per-box detection list (class dropdown + confidence badge + click-to-highlight) ──

function attrToggle(b, key, glyph, title) {
  const label = document.createElement("label");
  label.className = "attr-toggle" + (b[key] ? " on" : "");
  label.title = title;
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = !!b[key];
  cb.addEventListener("change", () => {
    AnnotateState.setBoxAttrByIds([b.id], key, cb.checked);
    // Keyboard.isTextInput() treats any focused <input> as a text field and swallows every
    // shortcut while it has focus, so hand focus back after the toggle.
    cb.blur();
  });
  label.appendChild(cb);
  label.appendChild(document.createTextNode(glyph));
  return label;
}

function renderDetectionList() {
  const list = document.getElementById("annotate-detection-list");
  list.innerHTML = "";
  const boxes = AnnotateState.getBoxes();
  const { w: imgW, h: imgH } = Canvas.getImageSize();

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
      // Superset of the old SELECT/BUTTON check: the attribute toggles are an <input> inside a
      // <label>, and without those two a toggle click would also switch the active tool and
      // collapse a multi-selection down to this one box.
      if (e.target.closest("select, button, label, input")) return;
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

    // Orientation angle badge — only for a 2-keypoint (base+tip) instance with both points
    // labeled (v != 0). Recomputed on every render, so this stays live while dragging an endpoint
    // (SelectTool's keypoint-drag mode already calls setBoxes → full renderDetectionList rebuild).
    let angleBadge = null;
    if (b.keypoints && b.keypoints.length === 2) {
      const angle = keypointPairAngleDeg(b.keypoints, imgW, imgH);
      if (angle !== null) {
        angleBadge = document.createElement("span");
        angleBadge.className = "angle-badge";
        angleBadge.title = "Orientation: point 1 = base, point 2 = tip";
        angleBadge.textContent = `∠ ${angle.toFixed(1)}°`;
      }
    }

    const del = document.createElement("button");
    del.className = "del-btn";
    del.textContent = "✕";
    del.title = "Delete box";
    del.addEventListener("click", () => {
      AnnotateState.deleteBoxesByIds([b.id]);
    });

    li.appendChild(select);
    li.appendChild(badge);
    if (angleBadge) li.appendChild(angleBadge);
    li.appendChild(del);

    // Own full-width row below the class picker: at 240px the sidebar has no room for the toggles
    // beside a select that already truncates "needle_holder".
    const attrs = document.createElement("div");
    attrs.className = "attr-row";
    attrs.appendChild(attrToggle(b, "occluded", "occluded", "Occluded — partly hidden behind another object (O)"));
    attrs.appendChild(attrToggle(b, "truncated", "truncated", "Truncated — runs off the edge of the frame (T)"));
    li.appendChild(attrs);

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
  document.getElementById("annotate-tool-polygon-btn").classList.toggle("active-tool", tool === "polygon");
  document.getElementById("annotate-tool-keypoint-btn").classList.toggle("active-tool", tool === "keypoint");
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

function renderOcrPanel(frame) {
  const resultEl = document.getElementById("ocr-result");
  if (!frame || frame.ocr_text === undefined || frame.ocr_text === null) {
    resultEl.textContent = "Not run yet.";
  } else if (frame.ocr_text === "") {
    resultEl.textContent = "(No text detected)";
  } else {
    resultEl.textContent = frame.ocr_text;
  }
}

let _lastLoadedFrameIdx = -2; // sentinel distinct from the -1 "no frame selected" state
AnnotateState.subscribe(() => {
  const idx = AnnotateState.getFrameIdx();
  if (idx !== _lastLoadedFrameIdx) {
    _lastLoadedFrameIdx = idx;
    const frame = AnnotateState.currentFrame();
    if (frame) {
      loadAnnotateImage(frame, idx);
      maybeAutoAssist(frame);
    }
    renderOcrPanel(frame); // frame may be null (no frames loaded yet) — handles that itself
  }
  Canvas.requestRender();
  Filmstrip.render();
  renderDetectionList();
  updateStatusBar();
  updateAnnotateReviewStatus();
  updateToolButtons();
  updateBulkActionsBar();
  Interpolate.renderStatus();
  ContextMenu.close();
});

document.querySelector('.tab[data-tab="annotate"]').addEventListener("click", () => Canvas.resize());

document.getElementById("annotate-tool-select-btn").addEventListener("click", () => AnnotateState.setActiveTool("select"));
document.getElementById("annotate-tool-draw-btn").addEventListener("click", () => AnnotateState.setActiveTool("draw_box"));
document.getElementById("annotate-tool-polygon-btn").addEventListener("click", () => AnnotateState.setActiveTool("polygon"));
document.getElementById("annotate-tool-keypoint-btn").addEventListener("click", () => AnnotateState.setActiveTool("keypoint"));

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

// ── Interpolate: fill the frames between two keyframes from their matched instances ──

const Interpolate = (() => {
  // Captured when "Set start keyframe" is pressed, not read back at run time. "Set keyframe" then
  // means exactly what it says — it anchors the boxes as they are at that moment — and the feature
  // works on frames the user has not saved yet, with no dependency on save order.
  let start = null; // { idx, frameId, boxes }

  function setStart() {
    const frame = AnnotateState.currentFrame();
    if (!frame) return;
    const boxes = AnnotateState.getBoxes();
    if (!boxes.length) {
      alert("This frame has no boxes — annotate it first, then set it as the start keyframe.");
      return;
    }
    start = { idx: AnnotateState.getFrameIdx(), frameId: frame.id, boxes: structuredClone(boxes) };
    renderStatus();
  }

  function clear() {
    start = null;
    renderStatus();
  }

  function renderStatus() {
    const el = document.getElementById("interpolate-status");
    const runBtn = document.getElementById("interpolate-run-btn");
    if (!el || !runBtn) return;
    if (!start) {
      el.textContent = "No start keyframe";
      runBtn.disabled = true;
      return;
    }
    const n = start.boxes.length;
    el.textContent = `Start: frame ${start.idx + 1} (${n} box${n === 1 ? "" : "es"})`;
    runBtn.disabled = AnnotateState.getFrameIdx() <= start.idx;
  }

  // The start frame may have been dropped by a reload, in which case its index means nothing.
  function startStillValid() {
    const frames = AnnotateState.getFrames();
    return !!start && frames[start.idx] && frames[start.idx].id === start.frameId;
  }

  async function run() {
    const frames = AnnotateState.getFrames();
    const endIdx = AnnotateState.getFrameIdx();
    if (!start) {
      alert("Set a start keyframe first (S), then move to a later frame and interpolate.");
      return;
    }
    if (!startStillValid()) {
      alert("The start keyframe is no longer in the frame list. Set it again.");
      clear();
      return;
    }
    if (endIdx <= start.idx) {
      alert(`The end frame must come after the start keyframe (frame ${start.idx + 1}).`);
      return;
    }
    const span = endIdx - start.idx;
    if (span < 2) {
      alert("These two keyframes are adjacent — there are no frames between them to fill.");
      return;
    }

    const endBoxes = AnnotateState.getBoxes();
    const pairs = matchInstances(start.boxes, endBoxes);
    if (!pairs.length) {
      // Writing zero boxes to every frame in the span would silently erase whatever Detect put
      // there, which is never what someone pressing "Interpolate" wants.
      alert(
        "No instances could be paired between the two keyframes.\n\n" +
          "Instances pair by class, and polygons/keypoints must also have the same number of " +
          "points. Nothing was changed."
      );
      return;
    }

    const targets = [];
    let skipped = 0;
    for (let i = start.idx + 1; i < endIdx; i++) {
      if (frames[i].reviewed) { skipped += 1; continue; } // never overwrite human-confirmed work
      targets.push(i);
    }
    if (!targets.length) {
      alert(`All ${skipped} frame(s) between the keyframes are already reviewed — nothing to fill.`);
      return;
    }
    if (targets.length > MAX_BULK_FRAMES) {
      alert(`That span is ${targets.length} frames; the limit is ${MAX_BULK_FRAMES} per interpolation.`);
      return;
    }

    const unpairedA = start.boxes.length - pairs.length;
    const unpairedZ = endBoxes.length - pairs.length;
    const ok = window.confirm(
      `Interpolate frames ${start.idx + 2}–${endIdx} from keyframes ${start.idx + 1} and ${endIdx + 1}?\n\n` +
        `Instances tracked: ${pairs.length}` +
        (unpairedA || unpairedZ ? `  (${unpairedA} unmatched at the start, ${unpairedZ} at the end — these are not carried)` : "") +
        `\nFrames to fill: ${targets.length}` +
        (skipped ? `\nSkipped (already reviewed): ${skipped}` : "") +
        `\n\nThis REPLACES existing boxes on those frames and cannot be undone with Ctrl+Z. ` +
        `The new boxes arrive unconfirmed (dashed) for you to review.`
    );
    if (!ok) return;

    const items = targets.map((i) => ({
      frame_id: frames[i].id,
      rev: frames[i].rev,
      detections: pairs.map((p) => toWireDetection(lerpDetection(p.a, p.z, (i - start.idx) / span))),
    }));

    const res = await Api.putDetectionsBulk(items);
    if (res.status === 409) {
      const detail = (await res.json().catch(() => ({}))).detail || {};
      const names = (detail.conflicts || []).slice(0, 5).map((c) => c.frame_id).join(", ");
      alert(
        "Nothing was changed — some of those frames were modified by someone else.\n\n" +
          `Conflicting frames: ${names}${(detail.conflicts || []).length > 5 ? ", …" : ""}\n\n` +
          "Re-run Detect (or reload the page) to pick up the current frame list, then try again."
      );
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(typeof err.detail === "string" ? err.detail : "Failed to write interpolated frames");
      return;
    }

    const { results } = await res.json();
    const revByFrameId = new Map(results.map((r) => [r.frame_id, r.rev]));
    // Indices are re-resolved against the CURRENT frame list, not the `frames` captured before the
    // await: a Detect job finishing mid-write runs initAnnotateFrames, which swaps the array out from
    // under us. An index from the old array would graft these detections onto an unrelated frame.
    const liveFrames = AnnotateState.getFrames();
    items.forEach((item) => {
      const idx = liveFrames.findIndex((f) => f.id === item.frame_id);
      if (idx >= 0) AnnotateState.setFrameDetections(idx, item.detections, revByFrameId.get(item.frame_id));
    });
    // Repaint, do NOT re-select: the end keyframe is the current frame, and its boxes may be unsaved
    // work this very run interpolated FROM (endBoxes comes off the live canvas). selectFrame() would
    // re-hydrate them from the server record and reset the undo stack, throwing that work away.
    AnnotateState.repaint();
    alert(`Filled ${targets.length} frame(s) with ${pairs.length} interpolated instance(s) each.`);
  }

  return { setStart, run, renderStatus, clear };
})();

document.getElementById("interpolate-start-btn").addEventListener("click", () => Interpolate.setStart());
document.getElementById("interpolate-run-btn").addEventListener("click", () => Interpolate.run());
Interpolate.renderStatus(); // the run button starts disabled until a keyframe exists

document.getElementById("annotate-save-next-btn").addEventListener("click", saveAndNext);

// The one place that knows the server's detection shape. Client-only keys (id, _pending) are
// excluded by construction rather than deleted, so a new client-side field can never leak into a PUT.
function toWireDetection(d) {
  return {
    class_id: d.class_id,
    class_name: d.class_name,
    confidence: d.confidence,
    x_center: d.x_center,
    y_center: d.y_center,
    width: d.width,
    height: d.height,
    source: d.source || (d._pending ? "model" : "manual"),
    points: d.points || null,
    keypoints: d.keypoints || null,
    // `!!` is load-bearing: boxes from a tool commit have no such key, and an explicit
    // undefined/null would 422 against the server's `bool` field.
    occluded: !!d.occluded,
    truncated: !!d.truncated,
  };
}

async function saveCurrentFrame() {
  const frame = AnnotateState.currentFrame();
  if (!frame) return false;
  const cleanBoxes = AnnotateState.getBoxes().map(toWireDetection);

  const res = await Api.putDetections(frame.id, cleanBoxes, frame.rev);
  // 409 must be handled BEFORE the generic branch below: its `detail` is an object, and the generic
  // handler alerts `errBody.detail` directly, which would render as "[object Object]".
  if (res.status === 409) {
    const conflict = (await res.json().catch(() => ({}))).detail || {};
    const idx = AnnotateState.getFrameIdx();
    const theirs = (conflict.detections || []).length;
    const keepTheirs = window.confirm(
      "Someone else saved this frame while you were editing it.\n\n" +
        `Theirs: ${theirs} box(es)  (rev ${conflict.current_rev})\n` +
        `Yours:  ${cleanBoxes.length} box(es)  (rev ${conflict.your_rev})\n\n` +
        "OK = discard my edits and load their version\n" +
        "Cancel = keep mine (the next Save overwrites theirs)"
    );
    if (keepTheirs) {
      AnnotateState.setFrameDetections(idx, conflict.detections || [], conflict.current_rev);
      AnnotateState.markReviewedLocal(!!conflict.reviewed);
      AnnotateState.selectFrame(idx); // re-hydrates the canvas from the now-updated record
    } else {
      // Adopt their rev so the next Save is a deliberate overwrite rather than a second 409, and
      // store MY boxes as this record's detections. Adopting the rev alone left the record holding
      // the pre-conflict snapshot, so any navigation (which re-hydrates from the record) replaced the
      // edits this branch just promised to keep — and the next Save then passed the rev check and
      // overwrote their work with content neither side authored.
      AnnotateState.setFrameDetections(idx, cleanBoxes, conflict.current_rev);
    }
    return false;
  }
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    alert(errBody.detail || "Failed to save annotations");
    return false;
  }
  const saved = await res.json();
  AnnotateState.setFrameDetections(AnnotateState.getFrameIdx(), saved.detections, saved.rev);
  // Save implicitly confirms any still-dashed boxes — a bookkeeping side-effect, not an undoable edit.
  // Also stamp `source` onto the live boxes so a later Save in the same session (e.g. after editing a
  // different box) doesn't recompute from a now-cleared `_pending` and lose track of which boxes were
  // already accepted from the model.
  AnnotateState.setBoxes(
    AnnotateState.getBoxes().map((d) => {
      const c = { ...d, source: d.source || (d._pending ? "model" : "manual") };
      delete c._pending;
      return c;
    }),
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
  document.getElementById("assist-auto-toggle").disabled = backend === "roboflow";
  document.getElementById("assist-auto-hint").classList.toggle("hidden", backend !== "roboflow");
}
document.querySelectorAll('input[name="assist-backend"]').forEach((el) => {
  el.addEventListener("change", updateAssistBackendFields);
});
updateAssistBackendFields();

const assistAutoToggle = document.getElementById("assist-auto-toggle");
assistAutoToggle.checked = localStorage.getItem("annotate_auto_assist") === "true";
assistAutoToggle.addEventListener("change", () => {
  localStorage.setItem("annotate_auto_assist", assistAutoToggle.checked ? "true" : "false");
});

async function runAssist(opts) {
  opts = opts || {};
  const frame = AnnotateState.currentFrame();
  if (!frame) return;
  const runBtn = document.getElementById("assist-run-btn");
  if (runBtn.disabled) return; // in-flight guard — also what makes auto-trigger safe to call freely

  const backend = document.querySelector('input[name="assist-backend"]:checked').value;
  const body = { backend, model_path: document.getElementById("assist-model-path").value };

  const classConf = readClassConf("assist-class-conf");
  if (Object.keys(classConf).length) body.class_conf = classConf;

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

  const idxAtRun = AnnotateState.getFrameIdx();
  runBtn.disabled = true;
  try {
    const res = await Api.postAssist(frame.id, body);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      if (opts.silent) {
        console.warn("Auto-assist failed:", errBody.detail || res.status);
      } else {
        alert(errBody.detail || "Assist failed");
      }
      return;
    }
    const data = await res.json();
    if (AnnotateState.getFrameIdx() !== idxAtRun) return; // navigated away before this resolved
    const newBoxes = (data.detections || []).map((d) => ({ ...d, id: makeId(), _pending: true }));
    if (newBoxes.length) AnnotateState.addBoxes(newBoxes);
  } finally {
    runBtn.disabled = false;
  }
}

document.getElementById("assist-run-btn").addEventListener("click", () => runAssist());

function maybeAutoAssist(frame) {
  if (localStorage.getItem("annotate_auto_assist") !== "true") return;
  const backend = document.querySelector('input[name="assist-backend"]:checked').value;
  if (backend !== "local") return; // hard gate, re-checked at fire time — never touches Roboflow
  if (frame.reviewed) return; // never re-touch a finalized frame
  if (AnnotateState.getBoxes().length !== 0) return; // already has boxes (detected or hand-drawn)
  if (document.getElementById("assist-run-btn").disabled) return; // in-flight guard
  runAssist({ silent: true });
}

document.getElementById("confirm-all-btn").addEventListener("click", () => {
  const boxes = AnnotateState.getBoxes();
  if (!boxes.some((b) => b._pending)) return;
  AnnotateState.setBoxes(boxes.map((b) => { const c = { ...b }; delete c._pending; return c; }));
});

document.getElementById("reject-all-btn").addEventListener("click", () => {
  const boxes = AnnotateState.getBoxes();
  if (!boxes.some((b) => b._pending)) return;
  AnnotateState.setBoxes(boxes.filter((b) => !b._pending));
});

// ── OCR ──

async function runOcr() {
  const frame = AnnotateState.currentFrame();
  if (!frame) return;
  const runBtn = document.getElementById("ocr-run-btn");
  if (runBtn.disabled) return;

  const idxAtRun = AnnotateState.getFrameIdx();
  runBtn.disabled = true;
  document.getElementById("ocr-result").textContent = "Running OCR…";
  try {
    const res = await Api.postOcr(frame.id);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      alert(errBody.detail || "OCR failed");
      if (AnnotateState.getFrameIdx() === idxAtRun) renderOcrPanel(AnnotateState.currentFrame());
      return;
    }
    const data = await res.json();
    AnnotateState.setFrameOcrText(idxAtRun, data.ocr_text); // stash even if user navigated away
    if (AnnotateState.getFrameIdx() !== idxAtRun) return; // don't repaint the wrong frame's panel
    renderOcrPanel(AnnotateState.currentFrame());
  } finally {
    runBtn.disabled = false;
  }
}

document.getElementById("ocr-run-btn").addEventListener("click", runOcr);

let ocrBatchJobId = null;
let ocrBatchPollTimer = null;

async function runBatchOcr() {
  const frames = AnnotateState.getFrames();
  if (!frames.length) return;
  const batchBtn = document.getElementById("ocr-batch-btn");
  if (batchBtn.disabled) return;

  const statusEl = document.getElementById("ocr-batch-status");
  batchBtn.disabled = true;
  statusEl.textContent = "Starting…";

  const res = await Api.startOcrJob(frames.map((f) => f.id), true);
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    statusEl.textContent = errBody.detail || "Failed to start batch OCR";
    batchBtn.disabled = false;
    return;
  }
  ocrBatchJobId = (await res.json()).job_id;
  document.getElementById("ocr-batch-stop-btn").classList.remove("hidden");
  startOcrBatchPolling();
}

function startOcrBatchPolling() {
  const statusEl = document.getElementById("ocr-batch-status");
  ocrBatchPollTimer = setInterval(async () => {
    const res = await Api.ocrJobStatus(ocrBatchJobId);
    if (!res.ok) return;
    const job = await res.json();
    statusEl.textContent = `${job.status} — ${job.progress}%`;

    if (job.status === "done" || job.status === "stopped") {
      clearInterval(ocrBatchPollTimer);
      ocrBatchPollTimer = null;
      document.getElementById("ocr-batch-btn").disabled = false;
      document.getElementById("ocr-batch-stop-btn").classList.add("hidden");
      const lastErr = (job.log || []).filter((l) => l.startsWith("[error]")).pop();
      const skipped = job.skipped_total ? `, ${job.skipped_total} skipped` : "";
      statusEl.textContent = lastErr
        ? lastErr
        : `${job.status} — ${job.text_found_total} / ${job.frame_ids.length} frames with text${skipped}`;
      await mergeOcrTextFromServer();
    }
  }, 1000);
}

// Pull the freshly-OCR'd text back in WITHOUT re-initialising AnnotateState. Calling
// loadDetectFrames()/initAnnotateFrames() here would rebuild the whole frame list and throw away any
// unsaved box edits the user has on the current frame, so only ocr_text is merged, matched by id.
async function mergeOcrTextFromServer() {
  if (!currentDetectJobId) return;
  const frames = await fetchAllJobFrames(currentDetectJobId);
  if (!frames) return;
  const textById = new Map(frames.map((f) => [f.id, f.ocr_text]));
  AnnotateState.getFrames().forEach((frame, idx) => {
    if (textById.has(frame.id)) AnnotateState.setFrameOcrText(idx, textById.get(frame.id));
  });
  renderOcrPanel(AnnotateState.currentFrame());
  Filmstrip.render();
}

document.getElementById("ocr-batch-btn").addEventListener("click", runBatchOcr);

document.getElementById("ocr-batch-stop-btn").addEventListener("click", async () => {
  if (!ocrBatchJobId) return;
  await Api.stopOcrJob(ocrBatchJobId);
  document.getElementById("ocr-batch-status").textContent = "Stopping…";
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
const exportJobPointer = makeJobPointer("export_job_id", "/api/export");

function setExportJobId(id) {
  currentExportJobId = id;
  exportJobPointer.set(id);
}
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
  // exportPollTimer is the one signal that a version is still building. Without it this line
  // would hand Start back mid-run every time the tab is switched away and back, and a restored
  // running job would lose its disabled state on the first tab switch after a reload.
  document.getElementById("export-start-btn").disabled = stats.total === 0 || exportPollTimer !== null;
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
  // Augmentation is server-side force-disabled for any non-"detect" task (segment, pose) — see
  // dataset_exporter.py's do_augment gate — so the size estimate must match for both, not just segment.
  const isDetect = document.querySelector('input[name="export-task"]:checked').value === "detect";
  const mult = isDetect ? parseInt(document.getElementById("export-aug-multiplier").value, 10) : 1;
  const finalSize = trainCount * mult + valCount + testCount;
  document.getElementById("export-max-size-label").textContent = `Maximum Version Size: ${finalSize} images (${mult}x)`;
}

function updateExportTaskUI() {
  const isDetect = document.querySelector('input[name="export-task"]:checked').value === "detect";
  const card = document.getElementById("export-augment-card");
  card.style.opacity = isDetect ? "" : "0.5";
  card.querySelectorAll("input").forEach((el) => { el.disabled = !isDetect; });
  updateExportMaxSizeLabel();
}

["export-train-pct", "export-val-pct"].forEach((id) => {
  document.getElementById(id).addEventListener("input", updateExportSplitLabel);
});
document.getElementById("export-aug-multiplier").addEventListener("input", (e) => {
  document.getElementById("export-aug-multiplier-label").textContent = e.target.value;
  updateExportMaxSizeLabel();
});
document.querySelectorAll('input[name="export-task"]').forEach((el) => {
  el.addEventListener("change", updateExportTaskUI);
});
updateExportTaskUI();

// The five Export cards stayed editable while a version was building, so the settings on screen could
// drift from the ones the running job actually used. Start and Download are <button>s and so fall
// outside this selector already, which is what we want: Start is gated by refreshExportPreview(), and
// Download has to stay clickable the moment it appears.
function setExportControlsDisabled(disabled) {
  document.querySelectorAll("#export-section input, #export-section select").forEach((el) => {
    el.disabled = disabled;
  });
  // updateExportTaskUI() owns a disabled rule of its own (the augment inputs are off unless the task
  // is detect), so re-enabling everything blindly would undo it. Let it reassert on the way back.
  if (!disabled) updateExportTaskUI();
}

document.getElementById("export-start-btn").addEventListener("click", async () => {
  if (!currentDetectJobId) return;
  const tr = parseInt(document.getElementById("export-train-pct").value, 10) / 100;
  const va = parseInt(document.getElementById("export-val-pct").value, 10) / 100;
  const te = Math.max(0, 1 - tr - va);

  const body = {
    detect_job_id: currentDetectJobId,
    version_name: document.getElementById("export-version-name").value || "v1",
    reviewed_only: document.getElementById("export-reviewed-only").checked,
    task: document.querySelector('input[name="export-task"]:checked').value,
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
  setExportJobId(data.job_id);
  document.getElementById("export-start-btn").disabled = true;
  setExportControlsDisabled(true);
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
      exportPollTimer = null;
      document.getElementById("export-start-btn").disabled = false;
      setExportControlsDisabled(false); // both branches: an errored job must not leave the form dead
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

// A built version is downloadable for as long as its zip is on disk, so the button belongs back on
// screen after a reload - not only in the minute after the job finished.
async function restoreExportJob() {
  const restored = await exportJobPointer.restore();
  if (!restored) return;
  const job = restored.job;
  setExportJobId(restored.id);
  document.getElementById("export-progress-wrap").classList.remove("hidden");
  document.getElementById("export-progress-fill").style.width = job.progress + "%";

  if (job.status === "running") {
    document.getElementById("export-start-btn").disabled = true;
    setExportControlsDisabled(true);
    startExportPolling();
    return;
  }
  if (job.status === "done") {
    const total = job.summary ? job.summary.total_exported : "?";
    document.getElementById("export-progress-label").textContent = `done - ${total} images exported`;
    // zip_path is cleared if the file never got written; the download route would 400 on it anyway.
    document.getElementById("export-download-btn").classList.toggle("hidden", !job.zip_path);
    return;
  }
  document.getElementById("export-progress-label").textContent = job.error || job.status;
}

document.getElementById("export-download-btn").addEventListener("click", () => {
  if (!currentExportJobId) return;
  window.location.href = `/api/export/${currentExportJobId}/download`;
});

// ────────────────────────────── Analytics section ──────────────────────────────

function analyticsCell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

async function refreshAnalytics() {
  const res = await apiFetch("/api/analytics");
  if (!res.ok) return;
  const data = await res.json();

  document.getElementById("analytics-accept-rate").textContent = `${data.accept_rate.rate_pct}%`;
  document.getElementById("analytics-suggested-total").textContent = data.accept_rate.suggested_total;
  document.getElementById("analytics-accepted-total").textContent = data.accept_rate.accepted_total;
  document.getElementById("analytics-assist-calls").textContent = data.accept_rate.assist_call_count;

  document.getElementById("analytics-total-frames").textContent = data.dataset.total;
  document.getElementById("analytics-with-detection").textContent = data.dataset.with_detection;
  document.getElementById("analytics-reviewed").textContent = data.dataset.reviewed;

  const classBody = document.querySelector("#analytics-class-table tbody");
  classBody.innerHTML = "";
  Object.entries(data.class_counts).forEach(([name, count]) => {
    const tr = document.createElement("tr");
    const nameTd = document.createElement("td");
    const dot = document.createElement("span");
    dot.className = "class-dot";
    dot.style.background = classColors[name] || "#AAAAAA";
    nameTd.appendChild(dot);
    nameTd.appendChild(document.createTextNode(name));
    tr.appendChild(nameTd);
    tr.appendChild(analyticsCell(count));
    classBody.appendChild(tr);
  });

  const jobsBody = document.querySelector("#analytics-jobs-table tbody");
  jobsBody.innerHTML = "";
  if (!data.detect_jobs.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.style.color = "var(--muted)";
    td.textContent = "No Detect jobs run yet.";
    tr.appendChild(td);
    jobsBody.appendChild(tr);
  } else {
    data.detect_jobs.forEach((job) => {
      const tr = document.createElement("tr");
      const when = job.created_at ? new Date(job.created_at).toLocaleString() : "— (before tracking)";
      const model = job.backend === "roboflow" ? (job.workflow_id || "—") : (job.model_path || "—");
      tr.appendChild(analyticsCell(when));
      tr.appendChild(analyticsCell(job.backend));
      tr.appendChild(analyticsCell(model));
      tr.appendChild(analyticsCell(job.frame_count));
      tr.appendChild(analyticsCell(job.detected_total));
      tr.appendChild(analyticsCell(job.status));
      jobsBody.appendChild(tr);
    });
  }
}

// ────────────────────────────── Init ──────────────────────────────

buildStepNav();
refreshVideoList();
refreshModelOptions();
refreshClasses();
updateDetectFramesInfo();
// Sequenced rather than fired together: restoreExtractJob and restoreDetectJob both write
// lastExtractedFrameIds, and Detect has to win - its run is the one Annotate and Export hang off.
// Last of all, because they await: the calls above get their requests out first.
restoreExtractJob().then(restoreDetectJob);
restoreExportJob();
