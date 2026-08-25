# rare-class-labeler — new project, built from scratch

## Context

The old `01_frame-extractor-tool/webapp` was presented to the professor and rejected: too hard
to use, not automatic enough for an ordinary user, and — the concrete gap — no way to pull out
just the rare-class frames (e.g. `needle`) needed to fix class imbalance. A quick prototype
(`rodo1985/yolo_world_video`, cloned to `C:\Users\USER\yolo_wv`, copied to `yolo_wv_custom` for
tinkering) proved the "upload video → draw boxes → watch result" shape works, but the user has
now scoped a real product on top of it — Backend/Frontend/Model/Frame-extraction, plus whatever
else the pipeline needs, as distinct phases — and decided this deserves a clean, brand-new
project rather than another layer on the prototype. **`yolo_wv` and `yolo_wv_custom` are not
touched by this plan at all** — they stay exactly as they are, kept only as reference for the
processing-loop shape that already worked. The new project lives entirely at:

```
C:\Users\USER\rare-class-labeler\
```

— a fourth, fully separate folder alongside `yolo_wv`, `yolo_wv_custom`, and `yolo-frame-miner`,
matching the user's repeated instruction to keep each tool's folder decisively separate.

**Architecture call**: "Backend" and "Frontend" are organized as separate Python modules inside
this one project (a Gradio app whose UI file calls into plain backend modules with no business
logic of its own) — not two separate running services. This keeps the minimal-tooling shape
already established across every other tool in this workspace while still giving each concern —
model handling, frame sampling, detection, filtering/storage, export — its own file and its own
testable boundary.

**Workflow revision (2026-08-23, finalized after two follow-up rounds)** — the end user (someone
visiting the finished site, not the developer) has **exactly three actions, nothing else**:

1. **Upload a video.** Everything else in the detection pipeline runs automatically — model
   loading, frame sampling, detection across every class the model knows — with fixed, proven
   defaults (confidence 0.25, IoU 0.7) baked into the backend, not exposed as sliders. There is
   **no model-choice or threshold UI of any kind** — the earlier idea of an "Advanced" accordion
   (swap to a custom uploaded model, tune confidence/IoU) is cut entirely, not just hidden/
   optional. The only model is the bundled ssid9 checkpoint, always.
2. **Pick which class(es) to keep**, from a results grid shown once processing finishes — one
   tile per class the model actually detected in *this* video, each showing a representative
   thumbnail cropped live from a real detection plus the count of instances found.
3. **Download** the resulting dataset zip.

Two convenience features from the original brief are kept **despite** being extra clicks, because
the user explicitly confirmed they should stay (they're shortcuts, not detection configuration):
a one-click Examples entry that loads and runs the local WIN_ test video automatically, and a
session-history panel that reloads a previous run's video/class-pick. Both were weighed against
the "cut everything else" instruction and kept on purpose — see the updated gap #8 and #3 below.

## Gap analysis — issues found in the user's original feature list, and how each is resolved

1. **Large-video preview is provably broken in the prototype today.** Confirmed live this
   session: uploading the real 202MB `WIN_20260525_14_47_12_Pro_muted.mp4` into `yolo_wv`'s app
   reproduces `h11._util.LocalProtocolError: Too little data for declared Content-Length` +
   `ConnectionResetError` the moment the browser's `<video>` element issues real
   (concurrent/overlapping) byte-range requests — a single sequential curl range request does
   *not* reproduce it, so it's specific to how browsers stream video, not the file or its H.264
   codec. This is a known Windows `ProactorEventLoop` + Starlette large-file range-response race.
   Since "ใส่วิดีโอยาวได้" is requirement #1, the new project must get this right from the start —
   see Phase 1.
2. **Long videos + full-frame CPU inference is slow with no feedback — and there's no manual step
   to break up the wait.** Measured elsewhere in this workspace: ~140ms/frame median on CPU
   (`results_960/inference_benchmark.md`) → a 10-minute 30fps clip is 40+ minutes of inference.
   Since upload is the *only* required action, a visible progress indicator matters more, not
   less. Fix: real `gr.Progress()` wiring via a `progress_callback(frame_idx, n_frames)` closure,
   the same mechanism `yolo-frame-miner/web/app.py`'s `run_mine()` already uses and already works.
3. **Model upload is no longer part of this product's attack surface — the RCE mitigation
   changes shape accordingly.** Arbitrary `.pt` upload + `ultralytics.YOLO(path)` is
   CVE-2025-32434 (unsafe `torch.load` deserialization); the original plan mitigated this with a
   path-jail (`_resolve_model_path` pattern) for an upload feature. **That upload feature is now
   cut** (2026-08-23 workflow revision — no model-choice UI at all), so the path-jail has no
   input to guard and is dropped from scope entirely — building it for a feature that doesn't
   exist would be exactly the unneeded complexity this user consistently rejects elsewhere. What
   stays, as cheap defense-in-depth on the one bundled checkpoint the app *does* load: setting
   `ULTRALYTICS_SAFE_LOAD` before any ultralytics import, mirroring `yolo-frame-miner/web/app.py`'s
   own choice to set this even though *it* also only ever loads its one bundled model with no
   public upload path.
4. **Class order must never be trusted as a raw index.** Learned the hard way in sibling
   projects — a model's own `model.names` order is its own business, translate by name, never by
   position. This project resolves classes via `frame_miner.classes.native_order(model.names)`
   every time the bundled model loads, which also satisfies "real model data, not mockup."
5. **Partial-label export — risk accepted, mitigated with a paper trail.** Key-frame exports
   label *only* the class(es) picked from the post-processing results grid, even if other real
   classes are visible in the same frame. Accepted risk: if merged into a dataset used for full
   multi-class training later, the unlabeled-but-present other objects become false negatives.
   Mitigation: every export writes a `PARTIAL_LABELS.md` note plus a field in
   `export_summary.json` naming exactly which class(es) were labeled, so the scope is traceable
   at merge time. The boxed-image QA folder doubles as a visual check.
6. **No dedup — accepted.** Sample-interval alone controls frame density; no phash step.
7. **Dataset export/merge — reuse via dependency, never reimplementation.** `pip install -e
   C:\Users\USER\yolo-frame-miner` into this project's own venv; import `frame_miner.classes`,
   `frame_miner.export`, `frame_miner.merge`, `frame_miner.source` directly.
   `frame_miner.mine.mine_source()` itself is **not** reused as-is — it always labels every
   detected class, which conflicts with decision #5 — so the mining/filter loop here is custom,
   but everything downstream of "which frames got staged" (split allocator, `data.yaml` writer,
   merge-plan/apply) is the untouched, already-verified `frame_miner` code.
8. **Examples and History are deliberately kept, even though they're extra clicks beyond the
   "3 actions" rule.** Explicitly re-confirmed 2026-08-23 after asking directly: they're
   shortcuts/convenience, not detection configuration the way the cut model/threshold controls
   were, so they don't violate "the end user doesn't need to choose [any pipeline settings]."
   `gr.Examples` is a static preset list, not "history of runs this session" — history needs its
   own small component (a `gr.State` list appended after each run, rendered in a
   `gr.Dataframe`/`gr.Gallery`). Keep `gr.Examples` only for the one-click local WIN_ video
   quick-start; build history separately.
9. **Class-picker image grid has no prior art anywhere in this workspace**, and per the workflow
   revision it needs no pre-made thumbnail assets either: since class selection happens *after*
   detection, each tile's thumbnail is cropped live from a real detection in the video the user
   just uploaded (e.g. the highest-confidence box seen for that class) — works identically
   regardless of what model produced it.
10. **No open-vocabulary code path exists anywhere in this project.** With only the bundled
    ssid9 checkpoint in scope, `model.set_classes()` never applies. Categories is always a
    *filter* over a fixed class list.
11. **Merge into the big dataset stays a manual CLI step**, matching the precedent
    `yolo-frame-miner` already set for its own web UI (no `merge` button there either). This
    project exports a zip in the exact layout `frame_miner.merge` expects; folding it into
    `03_dataset\ssid.yolov11new` is a deliberate, separate `frame-miner merge --from ... --into
    ... --apply` run by the user afterward — not exposed to end users at all.

Phase names below follow the user's requested categories (Backend/Frontend/Model/
Frame-extraction/"whatever else is needed"), with Phase 0 — a throwaway design-review mockup —
inserted at the front per the user's 2026-08-23 request. **Listing order ≠ build order** —
Frontend can't be meaningfully built or tested before Model/Frame-extraction/the
detection-and-export pipeline exist, so implementation proceeds Phase 0 → 1 → 4 → 5 → 6 → 2 → 3
→ 7 in practice, even though Phases 1-7 are numbered in the order the user named them.

## Phase 0 — Frontend mockup (design review, before any real code)

**Still not to be built until the user explicitly says so** — this section is now the detailed,
ready-to-execute spec for when that go-ahead comes, so building it takes one pass with no further
clarifying rounds needed.

**Purpose & shape.** Let the user click through the actual design, copy, and simulated flow
before any real backend/model/pipeline work starts. Fully static: no Python, no real model, no
real video processing, and no Gradio requirement — plain self-contained HTML/JS is the right
shape, since none of this code survives into Phase 3 (fully throwaway; Phase 3 is built fresh
from the user's feedback on this mockup, not by editing it). **Do not publish it as a Claude
Artifact unless the user asks** — last time this was built it was published proactively and the
user had to say "not yet, delete it"; this time the local file alone is the deliverable, and
publishing is a separate ask.

**Design plan** (a considered visual identity for a Thai-language surgical-instrument video
tool, not a generic AI-tool look):
- **Color** — a clinical, sterile-field palette, not a generic purple/blue AI gradient:
  `--bg: #F1F6F4` (cool mint-white, evokes a clean field), `--surface: #FFFFFF`,
  `--ink: #142420` (near-black with a green bias, not pure black),
  `--accent: #0E7C6B` (surgical teal-green — the one bold color, used only for the primary
  action and active states), `--rare: #BE6229` (warm terracotta, reserved *only* for marking the
  rare class in the results grid — semantic, not decorative, so it stays meaningful). Full dark
  variant defined too (`--bg: #0D1512`, `--accent: #3ECDAF`, etc.) since Artifacts render in
  whatever theme the viewer has set.
- **Type** — `IBM Plex Sans Thai` paired with `IBM Plex Sans` (one Google Fonts family covering
  both scripts cleanly, unlike relying on a Latin face to fall back for Thai) for all UI text;
  `IBM Plex Mono` for anything that is a real measurement — frame counts, confidence-style
  numbers, timestamps — so numbers visually read as "measured," not decorative.
- **Layout** — a single-column vertical flow (not a dashboard of side-by-side panels), with a
  numbered-circle rail connecting Upload → Results down the left edge. This is a deliberate
  content choice, not decoration: the rail's numbers track a literal one-way pipeline the system
  runs *for* the user, not a form wizard the user must step through — reinforced by the fact that
  step 2 (processing) has no button, it just happens.

**Content, section by section** (Thai copy; class names must be the real ssid9 order —
`Stitch Scissors, Tip_forcep, Tip_needle_holder, finger, forcep, hand, needle, needle_holder,
wound` — even though counts/thumbnails are placeholder, so the mockup doesn't misrepresent what a
real run will show):
1. **Masthead** — tool name + one-line tagline stating the automatic, upload-only nature.
2. **Upload** — drag-and-drop dropzone + click-to-browse, a *real* `<input type="file">` and
   client-side `<video>` preview (genuinely functional, not faked) — this is the one interaction
   in the whole mockup that isn't simulated.
3. **Automatic processing** — appears the instant a file is dropped, no button click starts it:
   a progress bar plus rotating Thai status lines ("กำลังโหลดโมเดล...", "กำลังตรวจจับวัตถุ...",
   "กำลังประกอบวิดีโอผลลัพธ์...").
4. **Output video** — autoplaying/looping preview (reuses the uploaded file in the mockup, since
   there's no real detector), clearly labeled as a placeholder result, not a real detection.
5. **Results grid** — 9 tiles, real class names in real ssid9 order, each with a colored icon
   swatch (not a fake photo — a photo would imply detection accuracy that doesn't exist yet) and
   a plausible instance count; `needle` deliberately given the lowest count of the nine, with a
   small "rare class" tag, so the tool's actual motivation stays visible even in a mockup.
   Checkboxes, all checked by default.
6. **Download** — button plus a short, accurate description of the real zip contents once built
   (`images/` + `labels/` filtered to picked classes, `preview/` with boxes drawn in,
   `PARTIAL_LABELS.md`) — this copy should already read as final, since it's describing Phase 6's
   real behavior, not a placeholder.
7. **Examples** — the WIN_ quick-start tile, shown disabled with an honest one-line note that a
   browser-hosted mockup can't reach a local file path.
8. **History** — 1-2 simulated past-run rows (timestamp, video name, classes picked), clickable
   but only toast-confirming, not restoring real state.

**Explicitly absent, confirmed twice now**: no Advanced accordion, no model dropdown, no
confidence/IoU sliders, no free-text class entry — anywhere in the page.

**Deliverable**: a single file at `C:\Users\USER\rare-class-labeler\mockup\index.html`,
self-contained (inline CSS/JS, Google Fonts link only, no build step, no other files).

## Phase 1 — Project scaffolding & infra/security prerequisites

- Create `C:\Users\USER\rare-class-labeler\` with its own `venv`, `pyproject.toml`
  (`gradio`, `ultralytics`, `opencv-python`, `imageio-ffmpeg`, `torch>=2.6`), and
  `run_web.ps1` (sets `PYTHONUTF8=1` before launching, same proven pattern as
  `yolo-frame-miner/run_web.ps1` and `yolo_wv/run_web.ps1`).
- `pip install -e C:\Users\USER\yolo-frame-miner` into this new venv. Verify with
  `python -c "import frame_miner; print(frame_miner.__file__)"`.
- At the top of the app entry point, before any other import: `os.environ.setdefault(
  "ULTRALYTICS_SAFE_LOAD", "true")` — confirm which literal string the installed `ultralytics`
  version actually honors (`"true"` vs `"1"`) before relying on it. This is the only model-loading
  safeguard needed now that model upload is out of scope (gap #3) — no `model_security.py`
  path-jail module is built, since there is no untrusted model path to guard.
- Add `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` before
  `demo.launch()` — this is the primary fix for gap #1. Safe here because the only subprocess
  call (ffmpeg transcode) will be a blocking `subprocess.run(...)`, not
  `asyncio.create_subprocess_exec`, so it doesn't need Proactor. Verify against the real 202MB
  WIN_ file specifically (not a short test clip). If that alone doesn't fully fix it, add
  `-movflags +faststart` re-encoding on ingest as a second layer.

## Phase 2 — Backend

`backend/pipeline.py` — **two** entry points Frontend calls (revised from an earlier
single-`run()`-function sketch once Phase 6's actual `export_run()` shape made the two-stage
flow concrete): `run_pipeline(video_path, ...)` — loads the bundled ssid9 model (Phase 4) always,
unconditionally, no model-choice branch, rejects videos over `MAX_VIDEO_SECONDS` up front (before
loading the model), runs the full detect-every-class pass with fixed `conf=0.25, iou=0.7`
constants while writing the annotated output video (Phase 5/6), stages every detected class's
candidate frames + tracks live thumbnails/counts (Phase 6), and returns a `RunResult` with
everything Frontend needs to render the output video and results grid; and `export_picks(run_result,
picked_classes, ...)` — a thin wrapper delegating to `dataset_export.export_run()`. This is the one
place that wires Phases 4-6 together. It does **not** own `gr.Progress()` plumbing — it takes a
plain `progress_callback: Callable[[int, int], None] | None` with zero gradio knowledge (mirroring
`yolo-frame-miner/frame_miner/mine.py`'s own decoupling from its web layer); Frontend adapts that
callback to `gr.Progress()` itself.

## Phase 3 — Frontend

**Superseded 2026-08-24**: originally built in Gradio (see the Phase 3 status block below for that
build's own record) — the user reviewed it and asked for the actual approved Phase 0 v2 mockup
back instead, as a real single page. Rebuilt as a static page + small REST API — see the newer
"Phase 3 REDO" status block (topmost) for the current, actual design. This section's text below
now describes the REDO, not the original Gradio build.

Implements the finalized 3-action flow exactly — **no Advanced accordion, no model dropdown, no
confidence/IoU sliders**:

`frontend/static/index.html` (the approved Phase 0 v2 mockup, edited in place — real fetch() calls
replace its fake/simulated data) served by `frontend/app.py` (FastAPI + uvicorn — the only file
with web-framework code, calls into `backend/pipeline.py`/`backend/model_loader.py` only):
- **Upload** — selecting/dropping a file immediately `POST`s to `/api/jobs`, which starts
  `pipeline.run_pipeline()` in a background thread and returns a `job_id`. Nothing to configure
  first.
- **Progress** — the page polls `GET /api/jobs/{id}/status` every 700ms, driving the mockup's
  existing single progress bar + rotating Thai status line from `run_pipeline`'s real
  `progress_callback` (gap #2).
- **Output video** — once done, `GET /api/jobs/{id}/video` (Range-enabled) plays the real
  annotated clip, boxing *every* class the model detected (not filtered by the pick below — that
  only affects the download).
- **Results grid** — one tile per class actually detected in this video, each with a real
  thumbnail (base64 JPEG embedded in the `/result` JSON), real count, and a data-driven
  "หายาก" (rare) badge — never hardcoded to `needle`.
- **Download** — `POST /api/jobs/{id}/export` then `GET .../export/download` zips the picked
  classes' clean images + labels (target-class-only, per gap #5's `PARTIAL_LABELS.md` note) plus
  the QA preview folder.
- **Examples / history** (kept — gap #8) — a "Quickstart" tile `POST`s `/api/jobs/example`, which
  reads `02_web-app\WIN_20260525_14_47_12_Pro_muted.mp4` server-side directly (the browser never
  uploads the 202MB file); history is `localStorage`-backed (survives a page reload, unlike the
  old `gr.State` — a real improvement), appending `(timestamp, video name, classes picked,
  job_id)` on a successful download, click-to-reload restores that run's already-computed results
  instantly via `GET /result` (no re-detection).

## Phase 4 — Model

`backend/model_loader.py`:
- Bundled ssid9 checkpoint path only (fixed, matches
  `01_frame-extractor-tool/models/ssid9_960px_150ep_20260813_map50-716.pt`), loaded
  unconditionally the first time a video is processed. **No upload path, no model choice at
  all** — cut per the workflow revision (gap #3).
- `load_model(path) -> (model, class_names)` — `class_names = frame_miner.classes.native_order(
  model.names)`, real data every time, never a hardcoded list (gap #4).

## Phase 5 — Frame extraction

`backend/frame_extraction.py` — thin wrapper around `frame_miner.source.iter_video_frames()`
(reused directly, not reimplemented) for the sample-interval walk
(`frame_step = max(1, int(fps * interval_sec))`); a separate full-frame iterator (plain
`cv2.VideoCapture` read loop, every frame) drives the annotated output video — one full decode
pass total, not two, with the interval check applied inline to decide which of those frames also
get evaluated as key-frame candidates in Phase 6.

## Phase 6 — อะไรก็แล้วแต่ที่ต้องใช้ (detection, filtering, live results & export)

Everything downstream of "a frame came in" — folded into one phase since the exact internal
boundaries don't matter, only the outcome:
- **Detection** (`backend/object_detection.py`) — `model.predict(frame, conf=0.25, iou=0.7,
  verbose=False)` per frame (fixed constants, no UI-supplied values), across *every* class the
  model knows, drawing boxes + class name + confidence for the annotated output video (drawing
  code shape ported fresh from the `yolo_wv` prototype's `utils.py` — no open-vocab branch, since
  only the one fixed-class model is ever in scope).
- **Live per-class tracking** — for every class seen at all, keep a running count and the single
  best representative crop (e.g. highest-confidence box) to populate the Frontend results grid.
- **Filter + storage** (`backend/filter_and_storage.py`) — for each interval-sampled candidate
  frame, stage the clean image + a boxed preview copy for *every* detected class into a per-run
  staging directory laid out exactly as `frame_miner.export.export_dataset()` expects
  (`images/`, `labels/`, `preview/`); label files are written per-class so that, once the user
  picks classes in the results grid, export can filter down to *only* those classes' label lines
  (`frame_miner.classes.class_id_for_name()`, never a raw model-native id) without re-running
  detection. No dedup step (per decision #6) — sample-interval is the only density control.
- **Gallery + download / export** (`backend/dataset_export.py`) — once the user picks classes and
  clicks download: calls `frame_miner.export.export_dataset()` on the class-filtered staging set
  (reusing the largest-remainder split allocator and Roboflow-layout `data.yaml` writer as-is),
  writes `PARTIAL_LABELS.md` (gap #5), assembles the boxed-image QA folder, and zips it for
  `gr.File`.

## Phase 7 — Verification

- The golden path itself: upload the real 202MB WIN_ file and confirm the *entire* flow —
  automatic model load, detection, output video, results grid with real counts, download —
  completes with **zero clicks beyond the upload and the final class pick + download**. Also the
  concrete regression test for gap #1 (input preview breaking on large files).
- Class-order correctness: load the real ssid9 checkpoint, confirm the grid labels match
  `model.names` exactly, and confirm an exported label file's indices match `frame_miner`'s
  resolved `classes_used.txt`, not the checkpoint's raw internal order.
- Confirm the exported zip is a valid `frame_miner.merge` source: `frame-miner merge --from
  <export> --into <a scratch copy of 03_dataset\ssid.yolov11new>` (dry-run, no `--apply`), expect
  zero errors/collisions.
- Confirm there is genuinely no way for an end user to load an arbitrary model — no upload
  control anywhere in the UI, no route/endpoint accepting a model file — since gap #3's mitigation
  now relies on that being true rather than on a path-jail.
- Confirm `yolo_wv`, `yolo_wv_custom`, and `rare-class-labeler` all run independently on separate
  ports with no shared state and no shared files.

---
Status: **Phase 3 REDO (Frontend, static page + FastAPI) built and verified 2026-08-24**, same
day, right after the Gradio build below — the user reviewed that build and said (Thai) "ไม่ชอบ
frontend อยากให้จบในหน้าเดียว ไปนำ mockup phase 0 v2 กลับมาใช้ได้ไหม" (don't like it, want it to be
a single page, bring back the approved Phase 0 v2 mockup). Asked to pick the backend framework,
they delegated: "ทำใหม่ก็ได้ แค่อยากให้หน้าเหมือน phase 0 v2". **Decision: FastAPI + uvicorn**, not
Gradio, not stdlib `http.server` — `fastapi`/`uvicorn`/`starlette` were already installed
transitively via `gradio`, so this wasn't "a new dependency" in practice; hand-rolling multipart
upload + Range support + background jobs on stdlib was judged too fragile for 200MB+ files versus
reusing an already-installed, well-tested framework. `gradio>=6` removed from `pyproject.toml`;
`fastapi`, `uvicorn[standard]`, `python-multipart` added explicitly (the last one is easy to
miss — confirmed this session it was only ever pulled in transitively by `gradio`, so it silently
stops being installed once `gradio` is dropped).

**A real bug in the *previous* Gradio build's own "verified" fix was caught during this redo's
planning**, not assumed away: that build's gap #1 fix
(`asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())`) was very likely a
no-op the whole time. Verified empirically this session by actually running code against the
installed `uvicorn==0.52.4`: its default `loop="auto"` calls a loop factory directly, bypassing
whatever policy is set, and always produces a `ProactorEventLoop` on Windows regardless — same
code path Gradio's own internal `uvicorn.Config` call uses. Only passing `loop="none"` to
`uvicorn.run()` makes it fall through to `asyncio.new_event_loop()`, which actually honors the
policy — confirmed directly (`_WindowsSelectorEventLoop` only appeared with `loop="none"`, never
with the default). The corrected two-line fix is now in `frontend/app.py`.

Built: `frontend/static/index.html` (the approved `mockup/index.html` copied in, JS rewired from
fake `setTimeout`/hardcoded-array simulation to real `fetch()` calls, several "this is simulated"
copy strings corrected — including one that hardcoded `needle` as "the" rare class, now wrong
since rarity is computed per-run — CSS/DOM otherwise unchanged, per the user's explicit ask for
visual fidelity to the mockup); `frontend/app.py` (FastAPI app: `POST /api/jobs` streams a
multipart upload to `run_dir/input.<ext>` in 4MB chunks then starts a `threading.Thread` running
`pipeline.run_pipeline()`; `POST /api/jobs/example` does the same directly against the local WIN_
path with no browser upload at all; `GET .../status` for polling; `GET .../result` returns
per-class counts/thumbnails(base64 JPEG via `cv2.imencode`, BGR direct, no RGB flip needed since
this isn't going through `gr.Image` anymore)/`is_rare`; `GET .../video` and `.../export/download`
resolve straight from disk via a regex-validated `job_id`, deliberately not through the in-memory
`JOBS` dict, so both survive a server restart as long as the file's still there). Ported unchanged
from the Gradio build: eager model warm-up at import, `sweep_stale_runs()` at startup, the
`rare_classes()` heuristic, the `VideoTooLongError`/broad-exception Thai error handling,
`cleanup_run()` never called from any route. History moved to `localStorage` (survives a page
reload, a real improvement over the old `gr.State`) — a new edge case this introduces (a history
row's `job_id` invalid after a restart, since `JOBS` is pure in-memory with no persistence) gets a
clean Thai expiry toast + self-pruning from `localStorage`, verified by actually restarting the
server and confirming a pre-restart `job_id` cleanly 404s with that exact message.

Verified via plain REST calls (`requests`), not `gradio_client` (doesn't apply anymore): the same
8s/241-frame real test clip used for the Gradio build's verification produced *identical* per-class
counts end to end (confirms no regression from the rewrite) — upload→202, 64 status polls over
~32.6s to `done`, `/result` returned all 8 classes with real non-empty base64 thumbnails and correct
`is_rare` flags, `GET /video` with a `Range` header returned a real `206` with correct
`Content-Range`/`Accept-Ranges` and no `Content-Disposition` (confirms inline playback, verified
directly against installed Starlette 1.6.0 source that `FileResponse` only sets that header when
`filename=` is passed), a partial-pick export produced a real zip with correct
`Content-Disposition: attachment` and the right `unlabeled_detected_classes` note. Also verified:
the too-long path rejects in 0.31s with a clean Thai message; an unknown/malformed `job_id`
(including a path-traversal attempt) cleanly 404s rather than touching the filesystem or crashing;
the quickstart endpoint returns immediately with the real 202MB size and its `/source` route
serves a real `206` Range response with no upload having occurred. **Not verified this session**:
an actual browser click-through (the mockup's step-reveal animations, drag-drop, and `localStorage`
persistence across a real page reload were reviewed in code but not visually exercised) — recommend
this before Phase 7 is called complete. All test `runs/` directories deleted after; confirmed
empty. Test server left running at `http://127.0.0.1:7860`.

---
Status: **Phase 3 (Frontend `frontend/app.py`, Gradio — superseded by the REDO above) built and
verified 2026-08-24**, same day as
Phase 2 below, completing the build order (Phase 0→1→4→5→6→2→**3**→7 — only Phase 7 remains).
Designed by 3 parallel Explore agents (this plan + `frontend_design_brief.md`; `backend/
pipeline.py` + the mockup design files; `yolo-frame-miner/web/app.py` + `sessions.py`) feeding one
Plan agent that empirically verified the installed `gradio==6.25.0` API rather than assuming from
memory (`css=`/`head=`/`theme=` are `.launch()` kwargs not `Blocks()` kwargs in this version;
`gr.Video` natively supports `autoplay`/`loop`; `gr.Examples` needs explicit
`cache_examples=False` or it eagerly runs inference on the example video at server startup). One
open design question — what clicking a History row should do — was put to the user explicitly
(confirmed: instantly restore that run's already-computed results, never re-run detection).

Built `frontend/app.py` as a full rewrite of the Phase 1 stub (the only file with gradio UI code
in the project, importing only `backend.pipeline`/`backend.model_loader`, never `cv2`/`numpy`/
`backend.dataset_export`/etc. directly): eager `model_loader.load_model()` warm-up at import time
(so every `run_pipeline()` call's internal load is a cache hit — the "loading model" progress
stage is now genuinely near-instant, including on the first run); 9 pre-allocated
`(Column, Image, HTML, Checkbox)` tile groups toggled by `.visible`/value per run (Gradio has no
true dynamic-length component list, and `CLASS_NAMES` is fixed-length and known at import time);
a data-driven rare-class badge (classes ≤30% of the run's max count, skipped entirely on a
roughly-balanced run — never hardcoded to `"needle"`); `cleanup_run()` deliberately never wired to
any button (no reliable way to know a `gr.File` download has actually finished transferring, so
button-triggered cleanup would risk deleting `export.zip` mid-download) — cleanup relies solely on
the existing `sweep_stale_runs()` 6h startup backstop, same as the sibling project's own
precedent. Corrected this section's own line above (previously said `pipeline.run()`, stale since
Phase 2 named it `run_pipeline()`).

Verified against the live server (`gradio_client`, since a real browser upload is capped at 10MB
by Claude's own tooling, far under real test files): an 8s/241-frame clip trimmed from the real
WIN_ file processed end-to-end in ~27s with no errors — correct per-class counts, correct
thumbnails (confirmed a real detection crop reaches the client as a valid 80×78 WebP, and a
not-detected class correctly returns a null image), correct checkbox defaults (checked only for
detected classes), correct rare-badge placement. A partial-pick download (`needle` only) produced
a real `export.zip` on disk with the exact expected structure (`train/`, `valid/`, `preview/`,
`data.yaml`, `export_summary.json`, `PARTIAL_LABELS.md`) and a correct
`unlabeled_detected_classes` note listing the other 7 detected-but-unpicked classes; the history
table gained the correct row. A synthetic 190s video correctly hit `VideoTooLongError` in 0.18s
(model never loaded) with a clean Thai error message, no raw traceback. Two things this
`gradio_client`-based approach could **not** verify (not app bugs, just what a scripted client
can't see): `gr.Column`/`gr.Button` visibility/interactivity updates don't appear in
`gradio_client`'s typed return value at all (silently dropped by its schema, even though the same
`detected`/`n_detected>0` booleans also drive the tile HTML/checkbox values that *were* observed
correctly) — so the results-section reveal and the download button's enable/disable were verified
by code inspection, not by direct client observation; and the History-row-click restore path
(`on_history_select`) is wired to a `.select()` event, which needs a real UI click to synthesize
`SelectData` — not exercised by this scripted pass. **A real browser click-through (including a
History-row reload) is still recommended before calling Phase 7 verification complete.** All test
run directories created during this verification were deleted afterward; `runs/` confirmed empty.
Test server left running at `http://127.0.0.1:7860` (the Phase 1 stub's stale PIDs from earlier
this session were stopped first).

---
Status: **Phase 2 (Backend `pipeline.py`) built and verified 2026-08-24**, same day as Phase 6
below, immediately after it per the build order (Phase 0→1→4→5→6→**2**→3→7). Planned via a
Plan-agent design pass that read Phases 4-6's actual current signatures directly (not from memory)
plus `yolo-frame-miner`'s progress-callback and run-dir-lifecycle precedents, then two design
questions were put to the user explicitly rather than assumed: function naming
(`run_pipeline()`/`export_picks()`, chosen over bare `run()`/`export()` to match this codebase's
verb_noun convention) and where a video-duration guard belongs (the user chose to put it in
`pipeline.py` itself, unlike the sibling project which puts its `MAX_VIDEO_SECONDS` cap in the web
layer).

Built: `backend/pipeline.py` — `VideoTooLongError(ValueError)` + `MAX_VIDEO_SECONDS = 180`
(reasoning in-code: Phase 6's verification video showed a ~5.4x realtime processing ratio at
182ms/frame CPU, so 180s of video ≈ 16 min processing), checked immediately after
`frame_extraction.open_frame_source()` returns metadata — before the model loads or a run_dir is
allocated, the cheapest possible rejection point; `RunResult` dataclass (run_dir, class_names,
output_video_path, counts, best, manifest — deliberately not VideoMeta or the original video_path,
which Frontend already has); `new_run_dir()`/`cleanup_run()`/`sweep_stale_runs()` mirroring
`yolo-frame-miner/web/sessions.py`'s three-piece pattern (`<project_root>/runs/<uuid4hex>/`, not
system temp, matching Phase 6's own manual verification-run precedent) but with zero import-time
side effects — `sweep_stale_runs()` is only ever called by Phase 3, never from within this module;
`run_pipeline()` itself, which is the per-frame driver loop Phase 6 deliberately left unbuilt,
wrapped in a `try/finally` that guarantees `writer.release()` runs even if inference raises
mid-loop (never catching/translating the exception itself — that's Phase 3's job, matching the
sibling project's own hands-off web layer); `export_picks()`, a thin wrapper over
`dataset_export.export_run()` so Frontend never imports that module directly.

A real bug was caught during verification, not assumed away: `run_pipeline()` only created
`run_dir` via `new_run_dir()`'s own `mkdir()` — when a caller passed an explicit `run_dir` that
didn't already exist (exactly the test-harness use case the parameter exists for), `cv2.VideoWriter`
failed *silently* (no exception, just a no-op writer), producing no video at all and only surfacing
much later as a confusing "ffmpeg: no such file" error in `finalize_output_video()`. Fixed with an
unconditional `run_dir.mkdir(parents=True, exist_ok=True)` right after `run_dir` is resolved,
regardless of which branch produced it.

Verified end-to-end against the same real 202MB WIN_ file Phase 6 used
(`02_web-app/WIN_20260525_14_47_12_Pro_muted.mp4`), 24/24 checks passed: the `VideoTooLongError`
guard rejects in <2s with the model never loaded and the source file not left locked
(`frames.close()` confirmed to force-release `cv2.VideoCapture` immediately rather than waiting on
GC); a synthetic mid-loop failure (monkeypatched `detect_and_annotate` to raise on the 3rd frame)
still leaves `output_raw.mp4` present and unlocked, confirming `writer.release()` ran via the
`finally`, while the `RuntimeError` itself propagated to the caller unmodified; `sweep_stale_runs()`
removes a fake old-mtime run dir and keeps a fresh one; the real full pass (2726 frames, 304s this
run) produced a `RunResult` with non-empty `counts`/`best`/`manifest`, staged image/label counts
exactly matching the manifest size, monotonic progress callbacks reaching the final frame, a
playable transcoded output video with the raw intermediate deleted; `export_picks()` on all
detected classes produced a zip inside `run_dir` with `labeled_classes` matching what was picked;
and — since (same as Phase 6's own finding) every one of the 9 real classes was staged in this
particular video — the "detected but never staged" `EmptyExportError` path could not occur
naturally here either, so this was accepted as already covered by Phase 6's own synthetic-manifest
test rather than re-invented. All verification run artifacts under `runs/verify_phase2_*` were
deleted after verification; `runs/` confirmed empty afterward.

`rare_class_plan_TH.md` kept in sync with this status block. Phases 3 (Frontend) and 7
(Verification) remain not started, each still waiting on its own explicit go-ahead.

---
Status: **Phase 6 (Detection/filter/export) built and verified 2026-08-24**, same day as Phase 5
below. Designed via three parallel research passes (`yolo_wv/app/utils.py`'s drawing/VideoWriter
code, `frame_miner`'s export/classes/merge contracts, this project's current backend state) plus a
Plan-agent validation pass that read the actual `frame_miner` source and this workspace's
`01_frame-extractor-tool/detector.py`, surfacing several real bugs designed around up front:
`frame_miner.export.export_dataset()` succeeds silently on an empty staging set (no exception) —
`dataset_export.py` now raises `EmptyExportError` before ever calling it; `export_dataset()` never
copies `preview/` into its output (confirmed by reading the source, not assumed) — `dataset_export.py`
copies it separately for the QA folder; `frame_miner.merge` requires an exact `data.yaml` `names`
match against the real merge target, so the full 9-class list is always passed to `export_dataset()`,
never a picked subset — partial labeling happens by dropping label *lines* and excluding *frames*,
never by shrinking the class list; omitting `imgsz` from `model.predict()` does not silently run at
ultralytics' 640 default (the checkpoint's own trained 960 is inherited via `model.overrides`,
per `01_frame-extractor-tool/detector.py:340-381`) but `IMGSZ=960` is pinned explicitly anyway since
this project pins a different ultralytics version (8.4.127) than where that inheritance was verified
(8.4.114); crops for the live results-grid tracker are clamped to frame bounds before slicing (numpy
slicing wraps on negative indices, unlike `cv2.rectangle`/`putText` which clip silently); staged
images use `cv2.imencode`+`write_bytes` rather than `cv2.imwrite`, which silently returns `False` on
non-ASCII Windows paths (same fix as `frame_miner.mine`'s own `_write_image()`).

Built: `backend/object_detection.py` (`Detection` dataclass, `detect()`/`draw_detections()`/
`detect_and_annotate()` — the last guarantees the clean frame is never mutated, `ClassTracker` for
live per-class counts + best-confidence crop, `open_raw_writer()`/`finalize_output_video()` for the
annotated output video via the same OpenCV-mp4v-then-ffmpeg-transcode two-stage pattern
`yolo_wv/app/utils.py` uses, minus that file's bugs: float fps end-to-end, not `int()`-truncated;
per-run unique paths, not hardcoded filenames; a fixed deterministic 9-color palette by class_id,
not fresh `random.randint()` per run; raw intermediate deleted after a successful transcode).
`backend/filter_and_storage.py` (`stage_candidate()` — writes `images/`/`preview/`/`labels/` under a
`run_dir`, returns the set of class-ids present for the caller's in-memory manifest, `None` if the
frame had no detections). `backend/dataset_export.py` (`export_run()` — filters to only frames
containing a picked class, filters label lines to only picked classes, calls `export_dataset()` with
the full class list, copies `preview/` and writes `PARTIAL_LABELS.md` itself, injects
`labeled_classes`/`unlabeled_detected_classes` into the JSON summary since `ExportSummary` the object
doesn't carry those fields, zips the result).

Verified against the real 202MB WIN_ file, one full pass over all 2726 frames (~495s, ~182ms/frame
at imgsz=960 on CPU): 29/30 checks passed on the first run; the 1 "failure" was the test script's own
edge-case setup finding every one of the 9 real classes staged in at least one candidate frame in
this particular video, so the "detected but never staged" `EmptyExportError` scenario couldn't occur
naturally — confirmed instead with a synthetic manifest (3/3 checks: empty `picked_classes` raises,
a detected-but-never-staged class raises, a genuinely-present class does not). Also verified: `detect_
and_annotate()` never mutates the clean frame; `imgsz=640` vs `960` produces different box counts on
real sampled frames (confirmed on this project's own ultralytics 8.4.127, not assumed from the
8.4.114 result); `ClassTracker.counts` exactly matches an independent manual tally; no degenerate
crops; output video frame count/fps/codec (`h264`, not `mp4v`) all correct, raw intermediate deleted;
staged `images/`/`preview/` stem sets always equal; all label lines well-formed; non-ASCII `run_dir`
path staging works; exported labels contain zero leaked lines for unpicked classes; every exported
image has a matching top-level `preview/` file; `PARTIAL_LABELS.md`/`export_summary.json` correct;
unknown class name raises plain `ValueError` (not `EmptyExportError`); and a real `frame-miner merge
--from <export> --into 03_dataset\ssid.yolov11new` dry-run (no `--apply`, genuinely read-only —
confirmed by reading `merge.py` before running it against the real target) reported 73 train / 18
valid to add with zero errors. All verification artifacts (`runs/phase6_verify*`, ~179MB) were
deleted after verification — ephemeral, nothing downstream depends on them.

Phase 6 is complete. Phases 2 (Backend `pipeline.py`), 3 (Frontend), 7 (Verification) remain not
started, each still waiting on its own explicit go-ahead (Phase 0→1→4→5→6→**2**→3→7 next). Note for
Phase 2: the per-video driver loop (open the video, loop frames, call `detect_and_annotate()` +
`ClassTracker.update()` + `stage_candidate()` when `is_candidate`) was deliberately left out of
Phase 6's shipped modules — that orchestration, plus the `gr.Progress()` callback plumbing, is
Phase 2's job.

---
Status: **Phase 5 (Frame extraction) built and verified 2026-08-24**, same day as Phase 4 below.
Research this session found the original Phase 5 paragraph's premise didn't hold:
`frame_miner.source.iter_video_frames()` (`frame_miner/source.py:26-58`) grab()-skips (no decode)
frames outside the sample interval — fine for `frame-miner`'s own JPEG-staging use, but
incompatible with needing every frame decoded here for the annotated output video. **Design
correction**: `backend/frame_extraction.py` is a fresh single-open, full-decode generator (shape
ported from `yolo_wv/app/utils.py:83-107`'s own read loop) that reuses only `iter_video_frames()`'s
`frame_step = max(1, int(fps * interval_sec))` formula, not the function itself — this keeps "one
full decode pass, not two" intact. Built: `open_frame_source(path, interval_sec=1.0) -> (VideoMeta,
Iterator[ExtractedFrame])` — `VideoMeta` (fps/n_frames/width/height/frame_step) is read once
up-front from a single `cv2.VideoCapture` and returned before iteration starts (so Phase 6 can size
its `VideoWriter` before the first frame), and `ExtractedFrame` (index/image/timestamp_sec/
is_candidate) is yielded once per decoded frame. No progress-callback param and no
`VideoWriter`/ffmpeg here by design — those belong to Phase 6/2, which already has `index` and
`meta.n_frames` on hand from consuming this generator. Verified against the real 202MB WIN_ file:
`meta = VideoMeta(fps=30.03, n_frames=2726, width=1920, height=1080, frame_step=30)`; the generator
yielded exactly 2726 frames (zero diff vs. `meta.n_frames`); `is_candidate` was `True` at exactly
the 91 indices where `index % 30 == 0` and `False` everywhere else (checked every single frame, not
sampled); `open_frame_source()` raised `ValueError` on a nonexistent path as designed; bare decode
(no inference) ran at ~4.5ms/frame, terminating cleanly with the capture released. Phase 5 is
complete. Phases 6 (Detection/filter/export), 2 (Backend `pipeline.py`), 3 (Frontend), 7
(Verification) remain not started, each still waiting on its own explicit go-ahead per this
project's phase-by-phase convention (Phase 0 → 1 → 4 → 5 → **6** → 2 → 3 → 7 next).

---
Status: **Phase 4 (Model) built and verified 2026-08-24**, same session as the design below — the
prior session's design/verification plan was carried out exactly as written, no changes.
`backend/model_loader.py` was created verbatim per the approved design. All three planned
verification checks passed against the real venv and checkpoint: (1) `load_model()`'s `class_names`
matched the confirmed real order exactly (`['Stitch Scissors', 'Tip_forcep', 'Tip_needle_holder',
'finger', 'forcep', 'hand', 'needle', 'needle_holder', 'wound']`); (2) two calls to `load_model()`
returned the identical model object (`is`), confirming the module-level cache short-circuits
reload; (3) importing `backend.model_loader` alone, without `frontend.app` having run first, still
set `os.environ["ULTRALYTICS_SAFE_LOAD"] == "1"`. Phase 4 is complete. Phases 5 (Frame extraction),
6 (Detection/filter/export), 2 (Backend `pipeline.py`), 3 (Frontend), 7 (Verification) remain not
started, each still waiting on its own explicit go-ahead per this project's phase-by-phase
convention.

---
Status: **Phase 1 code-reviewed (no bugs found) and Phase 4 (Model) fully designed + approved,
2026-08-24, same day as the Phase 1 build below — not yet implemented, waiting on explicit
go-ahead.** User confirmed keeping the Phase 1 scaffolding work (built without that confirmation
first — see `feedback_plan_as_backlog.md`'s 2026-08-24 entry for the process note). A manual review
of the 5 Phase 1 files (`pyproject.toml`, `run_web.ps1`, `backend/__init__.py`,
`frontend/__init__.py`, `frontend/app.py`) found no bugs; one theoretical concern (whether
`backend`/`frontend` are importable when `frontend/app.py` is run by direct path, as `run_web.ps1`
does) was empirically checked and confirmed fine — the editable install (`pip install -e .` with
`[tool.setuptools.packages.find]` scoped to `backend*`/`frontend*`) makes both packages importable
from anywhere in the venv regardless of invocation style.

Also confirmed with the user that "next phase" (they'd said "phase 2") means **Phase 4 (Model)**
per this plan's own stated build order (Phase 0 → 1 → **4** → 5 → 6 → 2 → 3 → 7), not literal
numbered Phase 2 (Backend/`pipeline.py`, which can't be meaningfully built before Model/Frame-
extraction/Detection exist). Phase 4 was then researched and designed in full:

- Confirmed against the real checkpoint (`ultralytics` 8.4.127, `torch` 2.13.0+cpu, this project's
  own venv): `model.names = {0: 'Stitch Scissors', 1: 'Tip_forcep', 2: 'Tip_needle_holder',
  3: 'finger', 4: 'forcep', 5: 'hand', 6: 'needle', 7: 'needle_holder', 8: 'wound'}`, and
  `frame_miner.classes.native_order(model.names)` — `C:\Users\USER\yolo-frame-miner\frame_miner\
  classes.py:42-47`, `return [model_names[i] for i in sorted(model_names)]`, a pure function with
  no I/O — reproduces this plan's documented class order exactly. Reuse directly, no
  reimplementation needed.
- `frame-miner` itself has **no caching pattern to port**: its own `frame_miner/detect.py
  load_model(path, device="cpu") -> YOLO` reloads the checkpoint fresh on every call (no cache
  anywhere in that codebase). Since this plan wants "loaded unconditionally the first time" (i.e.
  cached after), the closest existing shape is `yolo_wv/app/utils.py`'s `yolo_model` class
  (instantiate once, store on `self`) — simplified to plain module-level globals here, since unlike
  `yolo_wv` there's no reload/model-swap path to support (gap #3 cut that UI entirely).
- Approved design for `backend/model_loader.py` (not yet written — see next status entry once
  built):
  ```python
  import os
  os.environ.setdefault("ULTRALYTICS_SAFE_LOAD", "1")  # belt-and-suspenders vs. frontend/app.py's
  # own guard, in case this module is ever imported standalone before that one runs

  from ultralytics import YOLO
  from frame_miner.classes import native_order

  MODEL_PATH = (
      r"C:\Users\USER\OneDrive\Documents\BEAM\VideoFrameExtractor\01_frame-extractor-tool"
      r"\models\ssid9_960px_150ep_20260813_map50-716.pt"
  )
  _model = None
  _class_names = None

  def load_model(path: str = MODEL_PATH):
      global _model, _class_names
      if _model is None:
          _model = YOLO(path)
          _class_names = native_order(_model.names)
      return _model, _class_names
  ```
  Verification plan once built: (1) `class_names` from `load_model()` exactly matches the confirmed
  real order above; (2) calling `load_model()` twice returns the *same* model object (identity
  check) — confirms caching actually caches; (3) `ULTRALYTICS_SAFE_LOAD` lands in `os.environ` when
  `backend.model_loader` is imported alone, without `frontend.app` having run first.

**This design was approved via `ExitPlanMode`, but per the standing project convention the agent
stopped and asked explicitly before writing any code** — that question was still open (unanswered
in-session) when the user ran `/handoff` again; the next session should pick up right at "does the
user want `backend/model_loader.py` written now," not re-plan Phase 4 from scratch.

---
Status: **Phase 1 (project scaffolding & infra/security prerequisites) built and verified
2026-08-24.** Before planning Phase 1, resolved the Gradio-vs-not discrepancy this plan file had
been carrying (Phase 1's `pyproject.toml`/`run_web.ps1` and Phase 3's "Built fresh in Gradio" text
contradicted a prior handoff claiming Gradio was rejected after a live A/B comparison) — asked the
user directly, who chose to **keep Gradio**, so this plan's existing Phase 1/3 text stands
unchanged; the "Frontend will NOT be Gradio" claim from the 2026-08-23 handoff no longer holds.
Then built, in `C:\Users\USER\rare-class-labeler\`: `pyproject.toml` (`gradio>=6`,
`ultralytics>=8.3`, `torch>=2.6`, `opencv-python>=4.8`, `imageio-ffmpeg`, plus
`[tool.setuptools.packages.find]` scoped to `backend*`/`frontend*`), a Python 3.10 `.venv`
(matching `yolo-frame-miner`'s own proven interpreter choice — not the machine's default Python
3.14), `run_web.ps1` (sets `PYTHONUTF8=1` before launch, mirroring `yolo-frame-miner`'s script),
empty `backend/`/`frontend/` packages, and `frontend/app.py` as a smoke-test stub (env vars +
`ULTRALYTICS_SAFE_LOAD=1` + `WindowsSelectorEventLoopPolicy` + a bare `gr.Video` component — no
real UI yet, that's Phase 3). `pip install -e .` and `pip install -e C:\Users\USER\yolo-frame-miner`
both succeeded; `import frame_miner` resolves to the sibling project; `pip check` reports no
conflicts. **Verified gap #1's fix holds against the real file**: launched the stub app, uploaded
the actual 202MB `WIN_20260525_14_47_12_Pro_muted.mp4` via Gradio's own `/gradio_api/upload`
endpoint, then fired 16 concurrent, deliberately overlapping Range GET requests at the served file
(the pattern a browser's `<video>` element produces, and the one gap #1 notes a single sequential
curl request does *not* reproduce) — all 16 returned `206 Partial Content` with correct byte
counts, no `h11._util.LocalProtocolError`/`ConnectionResetError`, and the server kept responding
afterward. (This was done via a direct HTTP client, not literally a browser — Claude's browser
automation tool caps file uploads at 10MB, far under this file's 202MB — but it reproduces the
specific concurrent-overlapping-range-request pattern gap #1 identifies as the trigger, which a
single sequential request does not.) Real-browser confirmation of the same file is still worth
doing manually if the user wants extra confidence, but isn't required to call gap #1 resolved.
Phases 2–7 remain not started, waiting for their own go-ahead. The stub server was left running at
`http://127.0.0.1:7860` (PID visible via `Get-Process python`) in case the user wants to try it
live; stop it whenever, it holds no state Phase 2+ depends on.

Status: **A parallel Phase 0 v3 exists at `mockup/v3_pocari/index.html` (2026-08-24)** — same
content/behavior as v2, but the whole visual shell (two-tier sticky navbar, full-bleed hero, wide
section layout, and specifically the results grid, which now uses the reference site's literal
Scene/"こんなときにも" 8-card grid pattern) is ported directly from the reference site's actual
design system/layout rather than v2's looser reinterpretation. **v2 (`mockup/index.html`) is kept
as-is per the user** — v3 is an alternate exploration, not a replacement; the user will pick a
direction after reviewing both.

Status: **Phase 0 v2 (redesign) built 2026-08-24** at `mockup/index.html`, replacing the
2026-08-23 build now archived at `mockup/v1_archived/index.html` — same content/behavior, new
visual design applying design-grid/component/motion patterns drawn from a user-supplied reference
site (concepts only, no branding/copy carried over). New: `mockup/DESIGN_SYSTEM.md`, a single
consolidated color/type/spacing/radius/shadow/motion/component reference for this product (not
split into multiple "design system" documents). Not published as an Artifact (per this plan's own
note not to, unless asked). Waiting on the user's review/feedback before Phase 3 (the real
Frontend) is written. Phases 1-7 (the real implementation) remain not started, still waiting for
their own explicit go-ahead phase by phase.
Last revised 2026-08-24: re-evaluated the confidence/IoU-exposure question a third time at the
user's request (options considered: fully hidden-fixed / hidden-fixed-with-contextual-rescan /
YOLO-World-style visible sliders) — user confirmed **fully hidden, fixed in the backend**, so the
2026-08-23 decision stands unchanged; nothing added to the mockup for this.
Previously (2026-08-23): finalized the end-user flow to exactly 3 actions (upload → pick classes →
download); cut the Advanced accordion (model swap, confidence/IoU sliders) entirely rather than
just making it optional; kept Examples/History as confirmed shortcuts; dropped the model-upload
path-jail from scope since there is no upload feature to guard, while keeping `ULTRALYTICS_SAFE_LOAD`
as defense-in-depth on the one bundled model.
