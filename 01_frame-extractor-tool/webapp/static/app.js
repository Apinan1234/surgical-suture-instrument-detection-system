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
    li.innerHTML = `<span>${v.filename} (${sizeMb} MB)</span>`;
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
  if (line.includes("[saved]") || line.includes("เสร็จ")) return "log-ok";
  if (line.includes("[skip]")) return "log-skip";
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
    }
  }, 1000);
}

// ────────────────────────────── Init ──────────────────────────────

refreshVideoList();
