# Surgical Suture Instrument Detection System

ระบบตรวจจับอุปกรณ์การเย็บแผลด้วยปัญญาประดิษฐ์

**Authors**: Apinan Ayuyong · Teerutai Kaeyiwa · Fasai Khwanpan
**Program**: Computer Engineering and Artificial Intelligence — Academic Year 2025 (2568)

An AI object-detection system that locates and classifies surgical suture instruments, hands, and
wounds in video of suturing practice, plus a full web-application toolchain — extraction,
annotation, model-assisted labeling, dataset export, and rare-class mining — built to produce and
maintain that system's own training data.

📄 **[Project Poster (PDF)](05_reports/poster.pdf)** · [System diagram](<05_reports/แผนภาพระบบ-โครงการตรวจจับเครื่องมือผ่าตัดด้วย-AI (1).pdf>) · [Technology Stack](05_reports/technology-stack.md) · [Model results](05_reports/model-results-2026-08-13.md)

> **Poster**: `05_reports/poster.pdf` — the project's single-page research poster, summarizing the
> problem, the pipeline, and the same results reported in [Results](#results) below.

---

## Introduction

### Problem Statement

Manually annotating video for object detection training is slow, and — for a *rare* class like
`needle`, which appears far less often than the other instruments in a suturing video — it's
inefficient to sift through hours of ordinary footage by hand looking for the few frames that
actually contain one. An earlier internal web tool built for this project's own annotation work was
presented to the supervising professor and rejected outright: too hard to use, not automatic enough
for an ordinary user, and missing the one thing that mattered most — a way to pull out just the
rare-class frames needed to fix class imbalance in the dataset.

### Objectives

1. Train a YOLO11-based model that automatically localizes and classifies nine object classes —
   suture instruments, hands, and wounds — in real suturing-practice video.
2. Build a web application covering the full data lifecycle: extracting frames from video,
   annotating them, using the model itself to assist annotation, and exporting a clean dataset for
   the next training round.
3. Specifically address the rare-class problem the earlier tool couldn't: give a user a one-click
   way to mine just the frames containing an underrepresented class.

### Scope

The system targets **suturing-practice video recorded on a training pad**, not live surgery — nine
target classes (`finger`, `needle_holder`, `wound`, `needle`, `hand`, `forcep`, `Tip_needle_holder`,
`Tip_forcep`, `Stitch Scissors`), CPU-feasible inference (no GPU-cloud dependency assumed for
deployment), and a single-researcher usage model (no multi-user accounts, no database — see
[Technology Stack](05_reports/technology-stack.md) for why that's a deliberate choice, not a gap).

## Methodology

### Process

1. Record suturing-practice video on a training pad.
2. Sample frames from the video using the project's own extraction tool.
3. Annotate frames with bounding boxes across the nine target classes.
4. Discover and fix a real data-quality issue found mid-project: the exported dataset mixed two
   annotation formats (bounding boxes and polygons) — a conversion/cleaning step now runs before
   every training run, not just once.
5. Train YOLO11n, using a controlled A/B methodology: change exactly one variable per experiment
   run (augmentation on/off, then image resolution) while holding dataset, base model, epoch count,
   batch size, and random seed identical, so a result can be attributed to the one thing that
   changed.
6. Use the trained model to assist further annotation (model-in-the-loop labeling), then re-export
   an updated dataset — a train → assist → review → retrain cycle, not a single one-shot training
   run.

### Datasets & splitting

The final 9-class dataset comprises **2,190 images and 22,957 bounding boxes**, split
**1,575 / 400 / 215** (train / validation / test). The web application built for this project has
since been used to produce the project's own real working dataset: **2,726 frames and 21,127
bounding boxes**, tracked in the annotation tool's own state, independent of any single training
snapshot.

### System architecture

Three cooperating pieces, each documented in its own place rather than duplicated here:

- **The model**: YOLO11n, trained and evaluated across four controlled experiment rounds (baseline,
  augmentation A/B, extended training, resolution change) — see
  [Results](#results) and the full [Technology Stack](05_reports/technology-stack.md) writeup.
- **The dataset-producing tool** (`01_frame-extractor-tool/webapp/`): a FastAPI + vanilla-JS web app
  implementing the full Extract → Detect → Find Class → Annotate → Export pipeline used to build
  and grow the real training dataset above.
- **The flagship demo app** (`annotation-tool-webapp/`): a focused, three-action rare-class mining
  tool (upload → pick classes → download) built specifically to fix the "too hard to use" rejection
  described in the Problem Statement — see [Engineering & Knowledge](#engineering--knowledge) below.

A full system-framework diagram is included at
[`05_reports/แผนภาพระบบ-โครงการตรวจจับเครื่องมือผ่าตัดด้วย-AI (1).pdf`](<05_reports/แผนภาพระบบ-โครงการตรวจจับเครื่องมือผ่าตัดด้วย-AI (1).pdf>).

## Engineering & Knowledge

This project actually contains **three related but distinct tools**, built in sequence — worth
being explicit about which is which rather than letting them blur together:

| Tool | Location | What it is |
|---|---|---|
| Desktop prototype | `01_frame-extractor-tool/app.py` | The original Tkinter GUI: a 3-step Extract Frames → Detection → Export Dataset pipeline over 5 classes. Early prototype. |
| Full annotation tool | `01_frame-extractor-tool/webapp/` | A FastAPI web app that grew the prototype into a real 6-tab pipeline (Extract, Detect, **Find Class**, Annotate, Export, Analytics) — this is where the project's actual 9-class, 2,726-frame training dataset was produced. |
| **Flagship demo** | `annotation-tool-webapp/` | The current featured web app — a focused rebuild aimed directly at the rejection described in [Introduction](#introduction): exactly three user actions (upload → pick classes → download), no configuration screen, purpose-built for pulling out rare-class frames. |

**Pipeline detail, flagship app**: upload a video → the backend runs YOLO11 detection on every
frame via a reusable, vendored core package (`frame_miner/`) → results are grouped by class with
real thumbnail crops and per-class counts → classes present in *this run* below `RARE_MAX_FRACTION`
of the run's max count (and not already roughly balanced) are flagged **หายาก** (rare) —
data-driven per run, never hardcoded to a specific class name → the user picks which classes they
want → a labeled-dataset zip is generated and downloaded. No step requires a model picker,
confidence/IoU sliders, or any other configuration UI — deliberately, per the same "too hard to
use" lesson from Introduction.

### How the web app actually reaches the trained model (traced end to end)

Worth demonstrating with real code citations, not just asserting the pieces are wired together —
here is the exact call chain from an uploaded video to a real inference call and back:

1. `POST /api/jobs` saves the upload to `runs/<job_id>/input.*` and spawns a background thread
   (`frontend/app.py:187-204`).
2. That thread's `_run_job()` calls `pipeline.run_pipeline(video_path, ...)`
   (`frontend/app.py:119` → `backend/pipeline.py:84`).
3. `run_pipeline()` calls `model_loader.load_model()` (`backend/pipeline.py:121`) — this returns the
   **same cached model object** loaded once at process startup
   (`frontend/app.py:40`, `_, CLASS_NAMES = model_loader.load_model()`), not reloaded per request.
4. For every decoded frame, `run_pipeline()` calls
   `object_detection.detect_and_annotate(model, class_names, ef.image)` (`backend/pipeline.py:137`).
5. That function's one real inference line —
   `results = model.predict(frame, conf=conf, iou=iou, imgsz=IMGSZ, verbose=False)`
   (`backend/object_detection.py:53`) — is a literal Ultralytics `YOLO.predict()` call, on the real
   decoded frame array from the actual uploaded video, run through the real loaded checkpoint.
   `IMGSZ=960` is pinned explicitly here (`object_detection.py:11-17`), not left to inherit a
   default, because it must match the checkpoint's own training resolution — the same comment cites
   the exact accuracy cost of getting it wrong (needle/wound recall drops from 0.36 to 0.24 at the
   wrong resolution — the same numbers reported in [Results](#results) above).
6. The real `Detection` objects that come back are drawn onto the output video and tallied by
   `ClassTracker` — the per-class counts and thumbnails the frontend eventually shows are read
   straight from that tally, nothing simulated or hardcoded.
7. The frontend itself never talks to the model — it only polls `GET /api/jobs/{id}/status` and
   later reads `GET /api/jobs/{id}/result`, which reports exactly what step 6 counted.

This was also verified by direct execution, not just by reading the source: importing
`frontend.app` from this app's actual repo location loads the real checkpoint and reports its 9
real class names (`Stitch Scissors`, `Tip_forcep`, `Tip_needle_holder`, `finger`, `forcep`, `hand`,
`needle`, `needle_holder`, `wound`) — see the commit history for the exact verification output.

**A concrete methodology story worth calling out** (also detailed in
[Discussion & Innovation](#discussion--innovation)): the `needle` class was the model's weakest by
a wide margin. Rather than guessing at a fix, `analyze_box_sizes.py` was written to measure it
directly — `needle` boxes have a median short side of just 12.4 px at 640×640, with 80.9% falling
under COCO's small-object threshold. That measurement, not intuition, is what motivated retraining
at a higher image resolution (see [Results](#results)).

## Technology Stack

Summarized here; full writeup with the actual reasoning behind each choice is in
[`05_reports/technology-stack.md`](05_reports/technology-stack.md).

- **Frontend**: plain HTML/CSS/JS, no framework, no build step.
- **Backend**: FastAPI + Uvicorn, wrapping a reusable Ultralytics/PyTorch/OpenCV detection core.
- **Data & Messaging**: no database, no queue — in-memory job state + on-disk run artifacts on the
  server, plain browser `localStorage` for client-side history. A deliberate simplicity tradeoff
  for a single-researcher tool, not an oversight.
- **Infrastructure**: no containers — a Python venv and a launcher script; the sibling annotation
  tool has a documented (not-yet-executed) Caddy + systemd VPS deploy path for when public
  deployment is needed.

## Results

All numbers below are read directly from real experiment output, not from memory — see
[`05_reports/model-results-2026-08-13.md`](05_reports/model-results-2026-08-13.md) for the full
comparison, per-class breakdown, and the caveats that go with it.

Four controlled experiment rounds, changing one variable per round, `yolo11n.pt` base, 9-class
dataset, seed 42:

| Round | epochs | imgsz | val mAP50 | val recall | test mAP50 | test recall |
|---|---:|---:|---:|---:|---:|---:|
| `noaug` (control) | 50 | 640 | 0.5746 | 0.5417 | 0.5585 | 0.5618 |
| `aug` | 50 | 640 | 0.6559 | 0.6641 | 0.6146 | 0.5951 |
| `aug150` | 150 | 640 | 0.7163 | 0.7090 | 0.6658 | 0.6376 |
| **`aug960`** (current best) | 150 | **960** | 0.7160 | **0.7173** | **0.7015** | **0.6926** |

**Data augmentation helped clearly and unambiguously** — every principal metric improved, and the
non-augmented model overfit early (best epoch 10 of 50) while the augmented model kept improving
through the final epoch.

**The needle problem, measured rather than guessed at**: `needle` was the weakest class by far
(val mAP50 0.30 at 640px) — 0.45 of real needle instances were being missed entirely (read as
background), not misclassified (precision stayed high at 0.74 whenever the model did see one).
Direct measurement (`analyze_box_sizes.py`) found `needle`'s median box is only 12.4 px on its
short side at 640px — 80.9% below COCO's own small-object cutoff, nearly 3× smaller than the next
smallest class (`wound`). Retraining at `imgsz=960` (the one deliberate variable change in the
`aug960` round) moved needle recall **0.2435 → 0.3579** (val) and **0.2513 → 0.3579** (test), and
cut the miss-as-background rate from 0.45 to 0.37. **The gain is not solved, only diagnosed and
measurably improved**: needle mAP50 (0.36) remains the lowest of all nine classes, and the fix that
worked (resolution) points at what to try next (more resolution, more data) rather than more
training time.

**Two limitations the project reports on itself, not just externally-found**: `Stitch Scissors` has
only 16/10/3 train/val/test instances — its scores swing meaninglessly between runs (test mAP50
0.43 → 0.67 from a single extra correct prediction) and, holding 1/9 of the class-averaged mAP50,
currently inflates the reported average above what the other eight classes alone would show
(0.716 vs 0.699 for the remaining 8). And the model actually deployed in production must be run at
`imgsz=960` — inference at 640 silently reverts small-object performance to the earlier, worse
numbers.

## Discussion & Innovation

### ✅ Strengths

- **Diagnose before you fix.** The needle investigation (see [Results](#results)) is the clearest
  example of this project's actual working method: a measurement script written specifically to
  test a hypothesis (object size, not detector capacity) before spending GPU-hours on a fix, and
  reporting the honest result — real improvement, not full resolution — rather than overselling it.
- **Iterate on real user feedback, not on assumption.** The flagship rare-class-labeling app went
  through two real frontend builds before landing on its current design: a Gradio version was built
  first, reviewed by the actual user, and replaced after direct feedback ("don't like the frontend,
  want it to finish on one page") — not because Gradio was technically wrong, but because it didn't
  fit how the tool was actually meant to be used. That rebuild also caught a real bug the Gradio
  version's own "verified" fix had silently failed to actually apply (a Windows async-event-loop
  policy that Gradio's internal server setup bypassed) — a fix that looked done but wasn't, caught
  by rebuilding rather than assuming.
- **Minimal tooling, held to consistently.** No database, no message queue, no containers, no new
  frontend framework anywhere in this system — every one of those is a deliberate choice against a
  more "standard" alternative, made the same way across every tool in this project (see
  [Technology Stack](05_reports/technology-stack.md)).

### ⚠️ Limitations

- `needle` mAP50 (0.36) remains the lowest of all nine classes even after the resolution fix —
  diagnosed and measurably improved, not solved.
- `Stitch Scissors` has only 16/10/3 train/val/test instances — too few for its scores to mean much
  run to run, and it currently inflates the reported class-averaged mAP50 above what the other
  eight classes alone would show (0.716 vs 0.699).
- The flagship app has no public deployment yet — the sibling annotation tool has a documented
  Caddy + systemd VPS runbook, but it hasn't been executed for this app.

### 💡 Core Innovation

- A rare-class mining workflow built to answer a specific, real rejection ("too hard to use, no way
  to pull out the rare frames") rather than an assumed or generic need.
- Rare-class flagging is fully data-driven per run (`rare_classes()` in `frontend/app.py`) — never
  hardcoded to `needle` or any other specific class name — so the same tool generalizes to whatever
  class turns out to be scarce in a given video, not just the one class this project happened to
  care about most.
- The "measure before you fix" discipline applied to a concrete failure (needle detection) rather
  than treated as an abstract principle — a written diagnostic script, not intuition, is what
  identified image resolution as the lever to pull.

## Impact

- **Researchers/annotators**: manual full-video review — the actual bottleneck in growing this kind
  of training dataset — becomes a mostly-automated pass to check, not perform from scratch, via
  model-assisted labeling and one-click rare-class mining.
- **The dataset itself**: this isn't hypothetical — the tooling has already produced this project's
  own real working dataset, 2,726 frames and 21,127 bounding boxes.
- **The next model round**: the rare-class mining tool gives a direct, actionable path to closing
  the project's own most honestly-reported gap (needle) instead of an open-ended "collect more
  data" instruction with no way to find the frames that would actually help.
- **The original rejection this project answers**: the flagship app is a direct, purpose-built
  response to the supervising professor's stated reason for rejecting the earlier tool — not a
  broader redesign, specifically the missing rare-class capability and the too-hard-to-use
  complaint.

## ABET Student Outcomes

- **SO1 Problem-Solving**: Diagnosed the `needle` class's near-total detection failure by direct
  measurement (median box size vs. COCO's small-object threshold) before attempting any fix, then
  validated the fix against held-out test data rather than assuming it worked.
- **SO2 Design in Constraints**: Rebuilt the flagship web app under a hard, externally-imposed
  constraint — exactly three user actions, no settings or configuration screen at all — after an
  earlier version was rejected by the supervising professor for being too hard to use.
- **SO3 Communication**: The same work is documented across multiple formats for different
  audiences: a Thai-language thesis report, a 70+ slide defense deck built programmatically from
  code (not hand-placed), a research poster, and this showcase repository.
- **SO4 Ethics**: Uses only training-pad practice video, never real patient data. The model's real
  limitations (needle still the weakest class) are reported with numbers, not glossed over. The web
  app has no login — a deliberate choice for a single-researcher local tool — but gained rate
  limiting, request-size caps, and security headers specifically ahead of any public deployment,
  rather than shipping open-ended.
- **SO5 Teamwork**: A three-person team (Apinan Ayuyong, Teerutai Kaeyiwa, Fasai Khwanpan) sharing
  model training, web-application, and report work under one shared git history.
- **SO6 Experimentation**: Four controlled experiment rounds, changing exactly one variable per
  round (augmentation on/off, then image resolution), across a 2,190-image / 22,957-box dataset —
  the same one-variable-at-a-time discipline throughout, so each result is attributable.
- **SO7 Lifelong Learning**: Adopted new tools as the actual problem demanded them, not by default —
  moved the flagship app's whole frontend from Gradio to a plain FastAPI + vanilla-JS build after
  real usage feedback, and worked through small-object-detection literature (COCO's own
  size-threshold convention) to correctly diagnose the needle class instead of guessing.

## Conclusion

The model detects suture instruments accurately enough to serve as a genuine annotation aid — not a
finished, fully-solved system, but one whose remaining weaknesses (needle, and to a lesser extent
Stitch Scissors) are diagnosed with real measurements rather than left as an unexplained gap. The
web tooling built alongside it has already done real work: producing this project's own dataset,
and — after being rejected once for being too hard to use — being rebuilt around a deliberately
minimal, three-action workflow that directly answers that feedback. Future work identified by the
project itself: higher image resolution and more samples to keep closing the small-object gap, and
a recurrent-sequence model to classify the temporal steps of suturing rather than detecting objects
frame-by-frame alone.
