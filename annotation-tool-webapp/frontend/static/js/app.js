(function () {
  // Real ssid9 checkpoint class order (Stitch Scissors, Tip_forcep, Tip_needle_holder,
  // finger, forcep, hand, needle, needle_holder, wound) -- kept accurate even though
  // counts/thumbnails below are placeholder, so this mockup doesn't misrepresent a real run.
  // Colors are deliberately a cool blue/teal/violet family for every class EXCEPT needle,
  // which alone uses the warm --rare token -- so the rare class reads as visually different
  // even before anyone reads its badge or count.
  var CHECK_SVG = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="3.5 8.5 6.5 11.5 12.5 4.5"/></svg>';
  var RARE_BADGE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3z"/><line x1="12" y1="9" x2="12" y2="13"/><circle cx="12" cy="16" r="1" fill="currentColor" stroke="none"/></svg>';
  var TOAST_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16 9"/></svg>';
  var CLOCK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>';
  var CHEVRON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>';

  var HISTORY_KEY = 'rcl_history_v1';
  var HISTORY_MAX = 10;

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  var state = { objectUrl: null, jobId: null, videoName: null, classes: null, pollTimer: null };

  var topbar = document.getElementById('topbar');
  var dropzone = document.getElementById('dropzone');
  var fileInput = document.getElementById('file-input');
  var previewArea = document.getElementById('preview-area');
  var previewVideo = document.getElementById('preview-video');
  var outputVideo = document.getElementById('output-video');
  var fileNameEl = document.getElementById('file-name');
  var fileSizeEl = document.getElementById('file-size');

  window.addEventListener('scroll', function () {
    topbar.classList.toggle('is-scrolled', window.scrollY > 8);
  }, { passive: true });

  // ---- section nav: scroll-spy + click-to-scroll (pattern borrowed from the
  // reference site's active-section nav, adapted for a pipeline where later
  // sections don't exist yet -- their nav buttons stay disabled until revealed) ----
  var sectionNav = document.getElementById('section-nav');
  var navButtons = Array.prototype.slice.call(sectionNav.querySelectorAll('button'));
  var NAV_GATE = { 'step-processing': 'step-processing', 'card-output': 'step-results', 'card-grid': 'step-results', 'card-download': 'step-results' };
  var NAV_TARGETS = navButtons.map(function (b) { return b.dataset.target; });
  var navVisible = {};

  function updateNavLockState() {
    navButtons.forEach(function (btn) {
      var gateId = NAV_GATE[btn.dataset.target];
      if (!gateId) return;
      btn.disabled = document.getElementById(gateId).hidden;
    });
  }

  function setActiveNav(target) {
    navButtons.forEach(function (btn) {
      var isActive = btn.dataset.target === target;
      btn.classList.toggle('is-active', isActive);
      if (isActive) btn.setAttribute('aria-current', 'location');
      else btn.removeAttribute('aria-current');
    });
  }

  function recomputeActiveNav() {
    var visibleIds = NAV_TARGETS.filter(function (id) { return navVisible[id]; });
    if (visibleIds.length === 0) return;
    var best = visibleIds.reduce(function (a, b) {
      var ra = Math.abs(document.getElementById(a).getBoundingClientRect().top);
      var rb = Math.abs(document.getElementById(b).getBoundingClientRect().top);
      return ra < rb ? a : b;
    });
    setActiveNav(best);
  }

  var sectionObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) { navVisible[entry.target.id] = entry.isIntersecting; });
    recomputeActiveNav();
  }, { rootMargin: '-15% 0px -70% 0px', threshold: 0 });
  NAV_TARGETS.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) sectionObserver.observe(el);
  });

  navButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.disabled) return;
      var el = document.getElementById(btn.dataset.target);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  updateNavLockState();

  function fmtSize(bytes) {
    if (bytes > 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / 1024).toFixed(0) + ' KB';
  }

  function showToast(msg, ms) {
    var t = document.getElementById('toast');
    t.innerHTML = TOAST_ICON_SVG + '<span>' + msg + '</span>';
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.classList.remove('show'); }, ms || 3200);
  }

  dropzone.addEventListener('click', function () { fileInput.click(); });
  dropzone.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  ['dragenter', 'dragover'].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add('drag-over'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.remove('drag-over'); });
  });
  dropzone.addEventListener('drop', function (e) {
    var f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) handleFile(f);
  });
  fileInput.addEventListener('change', function (e) {
    if (e.target.files[0]) handleFile(e.target.files[0]);
  });

  document.getElementById('btn-change-file').addEventListener('click', function () { resetAll(); });

  function handleFile(file) {
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = URL.createObjectURL(file);
    state.videoName = file.name;

    previewVideo.src = state.objectUrl;
    fileNameEl.textContent = file.name;
    fileSizeEl.textContent = fmtSize(file.size);

    dropzone.hidden = true;
    previewArea.hidden = false;

    markStep('step-upload', 'done');
    enterProcessingUI();

    var form = new FormData();
    form.append('file', file);
    fetch('/api/jobs', { method: 'POST', body: form })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.data.error_message || 'อัปโหลดไม่สำเร็จ', 4200); resetAll(); return; }
        beginPolling(res.data.job_id);
      })
      .catch(function () { showToast('อัปโหลดไม่สำเร็จ กรุณาลองใหม่อีกครั้ง', 4200); resetAll(); });
  }

  function enterProcessingUI() {
    revealStep('step-processing');
    markStep('step-processing', 'active');
  }

  function markStep(id, kind) {
    var el = document.getElementById(id);
    el.classList.remove('is-active', 'is-done');
    if (kind) el.classList.add('is-' + kind);
  }

  function revealStep(id) {
    var el = document.getElementById(id);
    el.hidden = false;
    var body = el.querySelector('.step-body');
    body.classList.add('reveal-init');
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        body.classList.remove('reveal-init');
        body.classList.add('reveal-in');
      });
    });
    updateNavLockState();
  }

  function beginPolling(jobId) {
    state.jobId = jobId;
    pollStatus(jobId);
  }

  function pollStatus(jobId) {
    fetch('/api/jobs/' + jobId + '/status')
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (state.jobId !== jobId) return; // superseded by resetAll() -- drop stale results
        if (!res.ok || res.data.status === 'error') {
          showToast((res.data && res.data.error_message) || 'เกิดข้อผิดพลาด', 4500);
          resetAll();
          return;
        }
        var fill = document.getElementById('progress-fill');
        var msgEl = document.getElementById('progress-msg');
        var pctEl = document.getElementById('progress-pct');
        fill.style.width = (res.data.frac * 100) + '%';
        msgEl.textContent = res.data.message;
        pctEl.textContent = Math.round(res.data.frac * 100) + '%';
        if (res.data.status === 'done') {
          markStep('step-processing', 'done');
          fetchResult(jobId);
        } else {
          state.pollTimer = setTimeout(function () { pollStatus(jobId); }, 700);
        }
      })
      .catch(function () {
        if (state.jobId !== jobId) return;
        state.pollTimer = setTimeout(function () { pollStatus(jobId); }, 1500);
      });
  }

  function fetchResult(jobId) {
    fetch('/api/jobs/' + jobId + '/result')
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (state.jobId !== jobId) return;
        if (!res.ok) { showToast(res.data.error_message || 'เกิดข้อผิดพลาด', 4200); resetAll(); return; }
        showResults(res.data, null);
      })
      .catch(function () {
        if (state.jobId !== jobId) return;
        showToast('เกิดข้อผิดพลาดขณะโหลดผลลัพธ์', 4200);
        resetAll();
      });
  }

  function showResults(data, checkedOverride) {
    state.classes = data.classes;
    outputVideo.src = data.output_video_url;
    revealStep('step-results');
    markStep('step-results', 'active');
    buildGrid(checkedOverride);
    updateDownloadSummary();
  }

  function buildGrid(checkedOverride) {
    var grid = document.getElementById('results-grid');
    grid.innerHTML = '';
    state.classes.forEach(function (c, idx) {
      var checked = checkedOverride ? checkedOverride.has(c.name) : true;
      var media = c.thumbnail
        ? '<img class="swatch" src="' + c.thumbnail + '" alt="">'
        : '<div class="swatch swatch-empty"></div>';
      var tile = document.createElement('label');
      tile.className = 'class-tile' + (checked ? ' checked' : '') + (c.is_rare ? ' is-rare' : '');
      tile.innerHTML =
        '<input type="checkbox" data-idx="' + idx + '"' + (checked ? ' checked' : '') + '>' +
        (c.is_rare ? '<span class="rare-corner">' + RARE_BADGE_SVG + 'คลาสหายาก</span>' : '') +
        '<span class="tile-check">' + CHECK_SVG + '</span>' +
        media +
        '<div class="class-name">' + escapeHtml(c.name) + '</div>' +
        '<div class="class-count"><b>' + c.count + '</b> เฟรม</div>';
      grid.appendChild(tile);
      var cb = tile.querySelector('input');
      cb.addEventListener('change', function () {
        tile.classList.toggle('checked', cb.checked);
        updateDownloadSummary();
      });
    });
  }

  function updateDownloadSummary() {
    var boxes = document.querySelectorAll('#results-grid input[type="checkbox"]');
    var checked = 0, frames = 0;
    boxes.forEach(function (b) {
      if (b.checked) {
        checked++;
        frames += state.classes[+b.dataset.idx].count;
      }
    });
    document.getElementById('picked-count-label').textContent = 'เลือกไว้ ' + checked + ' / ' + state.classes.length + ' คลาส';
    document.getElementById('sum-classes').textContent = checked;
    document.getElementById('sum-frames').textContent = frames;
    document.getElementById('btn-download').disabled = checked === 0;
  }

  document.getElementById('btn-select-all').addEventListener('click', function () {
    document.querySelectorAll('#results-grid input[type="checkbox"]').forEach(function (b) {
      b.checked = true;
      b.closest('.class-tile').classList.add('checked');
    });
    updateDownloadSummary();
  });
  document.getElementById('btn-select-none').addEventListener('click', function () {
    document.querySelectorAll('#results-grid input[type="checkbox"]').forEach(function (b) {
      b.checked = false;
      b.closest('.class-tile').classList.remove('checked');
    });
    updateDownloadSummary();
  });

  document.getElementById('btn-download').addEventListener('click', function () {
    var picked = [];
    document.querySelectorAll('#results-grid input[type="checkbox"]').forEach(function (b) {
      if (b.checked) picked.push(state.classes[+b.dataset.idx].name);
    });
    if (picked.length === 0) return;
    var btn = document.getElementById('btn-download');
    btn.disabled = true;
    fetch('/api/jobs/' + state.jobId + '/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ classes: picked }),
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.data.error_message || 'เกิดข้อผิดพลาด', 4200); return; }
        var a = document.createElement('a');
        a.href = res.data.download_url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        a.remove();
        var note = res.data.unlabeled_detected_classes.length
          ? ' (พบ ' + res.data.unlabeled_detected_classes.join(', ') + ' ด้วยแต่ไม่ได้เลือก)' : '';
        showToast('ดาวน์โหลดชุดข้อมูลพร้อมแล้ว — ' + picked.length + ' คลาส' + note, 4200);
        pushHistoryEntry(picked);
      })
      .catch(function () { showToast('เกิดข้อผิดพลาดขณะสร้างไฟล์ดาวน์โหลด กรุณาลองใหม่อีกครั้ง', 4200); })
      .finally(function () { updateDownloadSummary(); });
  });

  document.getElementById('btn-reset').addEventListener('click', resetAll);

  function resetAll() {
    clearTimeout(state.pollTimer);
    state.jobId = null;
    document.getElementById('step-processing').hidden = true;
    document.getElementById('step-results').hidden = true;
    markStep('step-processing', null);
    markStep('step-results', null);
    markStep('step-upload', 'active');
    dropzone.hidden = false;
    previewArea.hidden = true;
    fileInput.value = '';
    document.getElementById('progress-fill').style.width = '0%';
    updateNavLockState();
    navVisible = {};
    setActiveNav('step-upload');
  }

  // ---- history (localStorage, survives page reload) ----
  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function saveHistory(list) { localStorage.setItem(HISTORY_KEY, JSON.stringify(list)); }

  function pushHistoryEntry(picked) {
    var entry = {
      timestamp: new Date().toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', hour12: false }),
      video_name: state.videoName,
      picked_classes: picked,
      total_detected: state.classes.length,
      job_id: state.jobId,
    };
    saveHistory([entry].concat(loadHistory()).slice(0, HISTORY_MAX));
    renderHistory();
  }

  function chipsHtml(entry) {
    if (entry.picked_classes.length >= entry.total_detected) {
      return '<span class="chip">ทั้ง ' + entry.total_detected + ' คลาส</span>';
    }
    return entry.picked_classes.map(function (n) {
      return '<span class="chip">' + escapeHtml(n) + '</span>';
    }).join('');
  }

  function renderHistory() {
    var list = loadHistory();
    var container = document.getElementById('history-list');
    var emptyNote = document.getElementById('history-empty-note');
    if (emptyNote) emptyNote.hidden = list.length > 0;
    container.innerHTML = '';
    list.forEach(function (entry) {
      var row = document.createElement('div');
      row.className = 'history-row';
      row.innerHTML =
        '<span class="time-wrap mono">' + CLOCK_SVG + entry.timestamp + '</span>' +
        '<span class="video-name">' + escapeHtml(entry.video_name) + '</span>' +
        '<span class="chips">' + chipsHtml(entry) + '</span>' +
        '<span class="reload">โหลดค่ากลับ' + CHEVRON_SVG + '</span>';
      row.addEventListener('click', function () { reloadHistoryEntry(entry); });
      container.appendChild(row);
    });
  }

  function reloadHistoryEntry(entry) {
    fetch('/api/jobs/' + entry.job_id + '/result')
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (!res.ok) {
          showToast('ผลลัพธ์นี้หมดอายุแล้ว หรือถูกลบไปแล้ว กรุณาอัปโหลดวิดีโอใหม่อีกครั้ง', 4200);
          saveHistory(loadHistory().filter(function (e) { return e.job_id !== entry.job_id; }));
          renderHistory();
          return;
        }
        state.jobId = entry.job_id;
        state.videoName = entry.video_name;
        markStep('step-upload', 'done');
        revealStep('step-processing');
        markStep('step-processing', 'done');
        document.getElementById('progress-fill').style.width = '100%';
        document.getElementById('progress-msg').textContent = 'เสร็จสิ้น';
        document.getElementById('progress-pct').textContent = '100%';
        showResults(res.data, new Set(entry.picked_classes));
        showToast('โหลดผลลัพธ์เดิมของ ' + entry.video_name + ' กลับมาแล้ว', 2600);
      })
      .catch(function () { showToast('เกิดข้อผิดพลาดขณะโหลดประวัติ', 3200); });
  }

  renderHistory();

  // ---- quickstart: run the local example video without a browser upload ----
  var quickstartTile = document.getElementById('quickstart-tile');

  function triggerQuickstart() {
    dropzone.hidden = true;
    previewArea.hidden = false;
    fileNameEl.textContent = 'กำลังโหลดไฟล์ตัวอย่าง...';
    fileSizeEl.textContent = '';
    enterProcessingUI();

    fetch('/api/jobs/example', { method: 'POST' })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.data.error_message || 'โหลดไฟล์ตัวอย่างไม่สำเร็จ', 4200); resetAll(); return; }
        state.videoName = res.data.video_name;
        previewVideo.src = '/api/jobs/' + res.data.job_id + '/source';
        fileNameEl.textContent = res.data.video_name;
        fileSizeEl.textContent = fmtSize(res.data.size_bytes);
        markStep('step-upload', 'done');
        beginPolling(res.data.job_id);
      })
      .catch(function () { showToast('โหลดไฟล์ตัวอย่างไม่สำเร็จ กรุณาลองใหม่อีกครั้ง', 4200); resetAll(); });
  }
  quickstartTile.addEventListener('click', triggerQuickstart);
  quickstartTile.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); triggerQuickstart(); }
  });
})();
