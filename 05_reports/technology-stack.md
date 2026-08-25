# Technology Stack

This describes the stack behind the project's current flagship web app — the rare-class video
mining/labeling tool (`annotation-tool-webapp/` in this repo, originally built and verified as a
standalone project called `rare-class-labeler`). It's organized the same way as a peer capstone's
stack writeup (BP-MOBILE): **Frontend / Backend / Data & Messaging / Infrastructure**, each item
paired with why it was chosen over the alternatives that were actually considered.

The short version, stated up front because it explains almost every choice below: this codebase
follows a **minimal-tooling** philosophy throughout — stdlib and already-installed dependencies are
preferred over adding a new library or a new managed service, unless a concrete need forces the
issue. Every "why" section below traces back to that rule.

## Why this app exists

Worth stating before the stack itself, because it's the actual reason the frontend looks the way
it does: an earlier web app (`01_frame-extractor-tool/webapp/`, still in this repo, and the one
that produced the project's real training dataset) was presented to the supervising professor and
**rejected** — too hard to use, not automatic enough for an ordinary user, and missing the one
concrete thing needed next: a way to pull out just the frames of a rare class (e.g. `needle`) to
fix class imbalance in the training data. This app is the response to that rejection: a tool with
exactly three user actions — upload → pick classes → download — and nothing else.

## Frontend

**Plain HTML, CSS, and JavaScript. No framework, no build step.** The page is served as three
static files (`frontend/static/index.html`, `css/style.css`, `js/app.js`) directly by the backend.

**Why, over the alternatives actually tried**: the frontend went through two real builds before
landing here. The first was a **Gradio** app — a reasonable first choice, since `fastapi`/
`uvicorn`/`starlette` come bundled transitively with Gradio, so it wasn't "a new dependency" in
practice. After reviewing that build, the user's own words were: *"ไม่ชอบ frontend อยากให้จบในหน้า
เดียว ไปนำ mockup phase 0 v2 กลับมาใช้ได้ไหม"* ("don't like the frontend, want it to finish on one
page — can we bring back the phase 0 v2 mockup instead?"). The rebuild kept the already-installed
`fastapi`/`uvicorn`/`python-multipart` and dropped `gradio` entirely, choosing a hand-written
static page over both Gradio and a second framework — Gradio's own multipart-upload, Range-request,
and background-job handling didn't fit a single custom-designed page well, and hand-rolling all of
that on bare stdlib `http.server` was judged too fragile for real 200MB+ video uploads. A real bug
surfaced by this rebuild is worth noting as a concrete "why the switch mattered": the Gradio
build's own `asyncio.set_event_loop_policy(...)` fix for a Windows large-file Range-request bug
turned out not to actually take effect under Gradio's internal `uvicorn.Config` call — only
verified once the app ran on a plain `uvicorn.run(..., loop="none")` call it fully controlled.

Practically: the static page was split into separate `index.html`/`style.css`/`app.js` files
(2026-08-26, from one large inline-everything file) specifically so the source reads and edits
like an ordinary website — no framework indirection to work around when hand-tuning copy or
layout.

## Backend

**FastAPI 0.141 + Uvicorn (`[standard]`) + Starlette + Pydantic**, plus **Ultralytics 8.4 / PyTorch
2.13 + torchvision / OpenCV / imageio-ffmpeg** for the actual video/detection work.

**Why FastAPI**: see the Frontend section above — it was already present transitively via Gradio,
and its multipart upload + Range-request (video scrubbing) + background-thread job support are all
things this app genuinely needs for real video files, not boilerplate for its own sake.

**Why the detection/export logic isn't just inline FastAPI route handlers**: the routes in
`frontend/app.py` are deliberately thin — the actual frame-extraction, detection, filtering, and
dataset-export logic lives in a separate, reusable core package (`frame_miner`, vendored into this
repo as part of `annotation-tool-webapp/`) that the web layer only calls into. `frontend/app.py`'s
own docstring states the intent directly: *"Only file with web-framework code in the project."*
This keeps the detection pipeline usable outside a web server too (it's shared with a sibling CLI
tool), and means a future frontend rewrite would only ever have to change the thin route layer, not
the underlying logic.

## Data & Messaging

**No database. No message queue.** This is a deliberate simplicity tradeoff for a single-purpose
research tool, not an oversight:

- **Server-side job state** is a plain in-memory Python dict (`JOBS`) inside the FastAPI process,
  plus each job's real output files under `runs/<job_id>/` on disk. Both are wiped by a server
  restart — there's no durable job database.
- **No task queue.** Jobs run on a background thread inside the same process; the frontend polls a
  status endpoint over plain HTTP roughly twice a second. No Celery/RQ/Redis, no websockets.
- **Client-side "history"** is pure browser `localStorage` (key `rcl_history_v1`, capped at 10
  entries) holding only `{timestamp, video_name, picked_classes, total_detected, job_id}` — never
  synced anywhere. Reopening a history entry re-fetches the real result from the server by
  `job_id`; if the server has restarted since (job state gone), the app shows a Thai "expired"
  toast and silently removes that entry, rather than erroring.

The real limitation this trades away — no persistence across a server restart, no cross-device or
cross-browser history — is accepted deliberately: this is a research tool run by one person on one
machine at a time, not a multi-user product, so a database would be solving a problem this app
doesn't have.

## Infrastructure

**No containers.** The app runs from a plain Python virtual environment, launched only through
`run_web.ps1` — never `python frontend/app.py` directly, because the launcher sets
`PYTHONUTF8=1` in the process environment *before* the interpreter starts, which is required for
Thai filenames/text to survive multipart video uploads correctly and cannot be set from inside the
Python process itself once it's already running. No CI/CD pipeline exists; this is a
single-developer research tool, not a team project needing automated gatekeeping.

For contrast, the *earlier* web app in this repo (`01_frame-extractor-tool/webapp/`) does have a
documented path to a real public deployment — a Caddy reverse proxy with automatic HTTPS, a
systemd unit running a single Uvicorn worker, on a plain Ubuntu VPS, explicitly chosen over Docker
("a venv, a systemd unit, and a reverse proxy are enough for this app's shape"). That runbook
wasn't ported to this newer app because this app hasn't been deployed publicly yet — but it's the
template to reuse if/when it is, rather than a reason to introduce containers now.
