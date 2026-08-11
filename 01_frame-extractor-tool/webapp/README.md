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

Then open http://127.0.0.1:8010 and log in.

**`APP_PASSWORD` is required — the server refuses to start without it.** Set it in
`01_frame-extractor-tool/webapp/.env` (gitignored). Copy `.env.example` to `.env` and fill it in. This
machine's `.env` already holds a local development password; pick a new one before the app is
reachable by anyone but you. Never write the real value into a tracked file — `.env` is gitignored
precisely so it stays out of the history.

Why it is mandatory: every API route is otherwise open, and `POST /api/models` + `POST /api/models/load`
load a `.pt`, which is a pickle — an unauthenticated caller reaching them is remote code execution.
Auth is that route's real mitigation (see `detector.py` for the load-time hardening that backs it up).

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
| `APP_PASSWORD` | — | **Required.** Single shared login password. No default; server won't start without it. |
| `SESSION_COOKIE_SECURE` | off | Set `true` **only** when served over HTTPS, so the session cookie is flagged Secure. Leave off for plain-HTTP localhost/LAN or login silently won't stick. |
| `SESSION_TTL_HOURS` | 10 | How long a login lasts. |
| `ULTRALYTICS_SAFE_LOAD` | `true` | Restricted (weights_only) model loading, so a malicious `.pt` is rejected instead of executed. Set `0` only if you fully trust every model file. |
| `DATA_DIR` | `webapp/data` | Where the workspace lives (see below). |
| `ROBOFLOW_API_KEY` | — | Only used by `../train_roboflow_yolo.py`, not the server. |

## Where the data lives — back it up before touching anything

- `webapp/state.json` — the whole workspace (frames, boxes, review flags). **This is the real work.**
- `webapp/data/` — uploaded videos, extracted frames, exports.
- `webapp/data/backups/` — automatic `state.json` snapshots every 15 min, last 10 only. **Not a real
  backup** (short window, same disk). Before any deploy, migration, or risky change, use the Export tab
  to download a dataset zip, or copy `state.json` + `data/` somewhere safe.

## Behind a reverse proxy (if you must expose it)

Terminate TLS at the proxy (nginx/Caddy) and run uvicorn bound to loopback with proxy headers trusted,
so client IPs (used by login rate-limiting) and the HTTPS scheme are read correctly:

```
uvicorn webapp.server:app --host 127.0.0.1 --port 8010 --app-dir 01_frame-extractor-tool \
  --proxy-headers --forwarded-allow-ips="127.0.0.1"
```

Set `SESSION_COOKIE_SECURE=true` once TLS is in front of it. `--forwarded-allow-ips` must name the
proxy's address, not `*` — trusting `X-Forwarded-For` from anyone lets a client spoof its IP past the
rate limiter.

## Hosting: the two apps go separately

`02_web-app/` (the React landing page) is static, carries no secrets, and needs no compute — it
belongs on free static hosting. **This annotation tool stays local or LAN-only**, behind the login,
for three concrete reasons:

1. With one shared password, everyone who can log in can load a model — i.e. run code on the host.
   That is fine for a trusted local user, not for the open internet.
2. It needs torch + opencv + the Tesseract binary: a multi-GB install and a host with real RAM, for
   CPU inference.
3. Its entire value is the workspace on this machine (thousands of frames, `state.json`, `models/*.pt`).
   A public instance would be an empty second copy.

When the landing page has a real URL and the tool has a reachable one, point the landing page at it via
`02_web-app/.env`'s `VITE_TOOL_URL` (falls back to `http://localhost:8010`).

### Decisions still open (yours to make)

- **Whether to expose the tool publicly at all.** Recommendation: no — keep it local/LAN behind the
  login. Revisit only with a concrete need and a per-user auth model, not one shared password.
- **Domain.** Recommendation: a free subdomain from the static host for the landing page; don't buy a
  domain yet.
- **If the tool must be public:** cheapest CPU VPS with ≥4 GB RAM, and only after auth is in place.

Create any hosting account and enter any credentials yourself — those steps are not automated here.
