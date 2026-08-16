# Surgical-instrument annotation tool — run & deploy

FastAPI + vanilla-JS web version of the Tkinter desktop app. Extract → Detect → Annotate → Export,
with Label Assist and OCR. In-memory state persisted to a single `state.json`, background jobs on
`threading.Thread`, HTTP polling. No database.

## Run it locally

From the repo root (`VideoFrameExtractor/`):

```
01_frame-extractor-tool/webapp/.venv/Scripts/python -m uvicorn webapp.server:app \
  --host 127.0.0.1 --port 8010 --app-dir 01_frame-extractor-tool
```

Then open http://127.0.0.1:8010 — no login, the app loads straight in.

**No auth gate.** Every route is open to anything that can reach the port. That's fine on
`127.0.0.1`/LAN; once this is reachable from the open internet (see "Deploying it publicly" below),
what stands in for auth is: `ULTRALYTICS_SAFE_LOAD` (restricted/weights_only model loading — see
`detector.py`, blocks arbitrary code execution from a malicious uploaded `.pt`) plus the abuse
guardrails in `.env.example` (disk-space floor, per-IP rate limits on expensive routes, a request-body
size cap). There is deliberately no per-user isolation: anyone who reaches the app can see, edit, or
delete anyone else's uploaded videos/frames/annotations — an accepted tradeoff, not an oversight.

## Dependencies

Two requirements files, and a fresh host needs **both** — the webapp one deliberately omits
`opencv-python` / `ultralytics` / `numpy` because it layers on the parent tool:

```
pip install -r 01_frame-extractor-tool/requirements.txt      # torch/ultralytics/opencv/…
pip install -r 01_frame-extractor-tool/webapp/requirements.txt  # fastapi/uvicorn/pytesseract/…
```

Neither is fully version-pinned except `torch>=2.5` (required for safe model loading — see below). If
you need a reproducible deploy, pin the resolved versions after a known-good install (`pip freeze`).

**OCR needs the Tesseract binary**, not just the `pytesseract` wrapper. Install it separately
(Windows: the UB-Mannheim build; Debian/Ubuntu: `apt install tesseract-ocr`) and make sure it is on
`PATH`, or the OCR tab errors at call time. Everything else in the app works without it.

## Environment variables

Set in `webapp/.env` (see `.env.example` for the full annotated list). The important ones:

| Var | Default | Notes |
|---|---|---|
| `ULTRALYTICS_SAFE_LOAD` | `true` | Restricted (weights_only) model loading, so a malicious `.pt` is rejected instead of executed. This is the real defence on the model-upload/model-load routes now that there's no login gate — do not turn it off on a public deployment. |
| `MIN_FREE_DISK_MB` | 2048 | Write-heavy routes (upload, extract) refuse new work with a `507` below this much free disk. |
| `RATE_LIMIT_EXPENSIVE_MAX` / `RATE_LIMIT_EXPENSIVE_WINDOW_SEC` | 20 / 300 | Per-IP cap on assist/ocr/detect/extract/export requests. |
| `MAX_REQUEST_BODY_MB` | 64 | Ceiling on non-multipart (JSON) request bodies. |
| `DATA_DIR` | `webapp/data` | Where the workspace lives (see below). |
| `ROBOFLOW_API_KEY` | — | Only used by `../train_roboflow_yolo.py`, not the server. |

## Where the data lives — back it up before touching anything

- `webapp/state.json` — the whole workspace (frames, boxes, review flags). **This is the real work.**
- `webapp/data/` — uploaded videos, extracted frames, exports.
- `webapp/data/backups/` — automatic `state.json` snapshots every 15 min, last 10 only. **Not a real
  backup** (short window, same disk). Before any deploy, migration, or risky change, use the Export tab
  to download a dataset zip, or copy `state.json` + `data/` somewhere safe.

## Deploying it publicly

The app now runs with no login, by decision — it's meant to be reachable like any other open web
tool. **`deploy/DEPLOY.md` is the ordered command list** (provision → copy code → app setup → systemd
→ Caddy → verify), with ready-to-copy `deploy/frame-extractor.service` and `deploy/Caddyfile`. The
reasoning behind the choices those files encode:

- **Single uvicorn worker, always.** State (`_state` in `server.py`) is a plain in-process dict,
  persisted to `state.json` on mutation. A second worker process gets its own copy and the two
  clobber each other's writes to `state.json` — never run this with `--workers > 1` or behind a
  multi-process manager. A process restart also drops any job that was mid-run (marked `"error":
  "Interrupted by a server restart"` on the next load), which is expected, not a bug to route around.
- **VPS sizing**: a small CPU box is enough — CPU inference already works (`device=cpu` default), no
  GPU needed. The venvs alone are GB-scale once torch/opencv/ultralytics are installed, and `data/`
  grows from public uploads with no cap other than `MIN_FREE_DISK_MB` — size disk with headroom.
  Plain Ubuntu LTS + `apt`, no Docker — a venv, a systemd unit, and a reverse proxy are enough for
  this app's shape.
- **`--proxy-headers --forwarded-allow-ips=<proxy>`** (in the shipped unit file) matters even with no
  login: `_client_ip()` in `server.py` is what the per-IP rate limiter keys on, and without this flag
  every request looks like it came from the proxy's own address, making the limiter useless. Never
  set `--forwarded-allow-ips` to `*` — that lets a client spoof its own IP past the limiter.
- **Caddy** over nginx+certbot: automatic Let's-Encrypt HTTPS from a one-line config, no manual cert
  renewal to maintain. Needs a real domain (or subdomain) pointed at the server's IP first; Caddy
  can't issue a cert for a bare IP.
- **Firewall**: only 22/80/443 open. uvicorn stays on `127.0.0.1` — never bind it to a public
  interface directly, even behind the proxy.
- **Code transfer**: this repo isn't pushed to `origin/main` (and the webapp changes are typically
  uncommitted locally) — a `git clone`/`pull`-based deploy won't have the latest work. Use `rsync -a`
  (or `scp -p`) to copy the app directory directly; `-a`/`-p` matters because model file `mtime`
  drives the default-model picker (`_scan_models()` in `server.py` / `app.js`'s first-visit logic) —
  a plain copy without it re-stamps every `.pt` to the copy time and silently breaks that ordering.
- **Data**: don't copy the local `webapp/data/` (videos/frames/exports — this machine's real
  annotated dataset) to a public instance. Start a public deployment with an empty `data/` (created
  automatically on first run) and only the trained `.pt` files under `models/`, so inference and the
  default-model picker work from the start.

## Hosting: the two apps

`02_web-app/` (the React landing page) is a separate, unrelated static app — it carries no secrets and
needs no compute, so it belongs on free static hosting, deployed independently of the annotation tool
above. When both have real URLs, point the landing page at the tool via `02_web-app/.env`'s
`VITE_TOOL_URL` (falls back to `http://localhost:8010`).

Create any hosting account and enter any credentials yourself — those steps are not automated here.
