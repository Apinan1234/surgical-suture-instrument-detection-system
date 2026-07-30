"""
Web version of app.py — Phase 1 (Extract pipeline only).
FastAPI + in-memory state + threading.Thread jobs + HTTP polling, no DB, no framework frontend.
"""

import hmac
import json
import os
import secrets
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import cv2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

WEBAPP_DIR = Path(__file__).resolve().parent
TOOL_DIR = WEBAPP_DIR.parent
sys.path.insert(0, str(TOOL_DIR))
from frame_extractor import extract_frames  # noqa: E402  (needs sys.path set up first)

load_dotenv(WEBAPP_DIR / ".env")

APP_PASSWORD = os.environ.get("APP_PASSWORD")
if not APP_PASSWORD:
    raise RuntimeError("APP_PASSWORD environment variable is required (see webapp/.env.example)")

DATA_DIR = Path(os.environ.get("DATA_DIR", WEBAPP_DIR / "data")).resolve()
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "8192"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

VIDEOS_DIR = DATA_DIR / "videos"
FRAMES_DIR = DATA_DIR / "frames"
BACKUPS_DIR = DATA_DIR / "backups"
for d in (VIDEOS_DIR, FRAMES_DIR, BACKUPS_DIR):
    d.mkdir(parents=True, exist_ok=True)

STATE_PATH = WEBAPP_DIR / "state.json"
STATE_BAK_PATH = WEBAPP_DIR / "state.json.bak"
STATE_TMP_PATH = WEBAPP_DIR / "state.json.tmp"

ALLOWED_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}

SESSION_TTL = timedelta(hours=10)
RATE_LIMIT_WINDOW_SEC = 5 * 60
RATE_LIMIT_MAX_FAILURES = 5
SNAPSHOT_INTERVAL_SEC = 15 * 60
SNAPSHOT_KEEP = 10

# ────────────────────────────── State (S-0) ──────────────────────────────

_state_lock = threading.Lock()
_state: dict = {"videos": {}, "extract_jobs": {}, "frames": {}}
_last_snapshot_time = 0.0


def load_state():
    global _state
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            _state = json.load(f)
    for key in ("videos", "extract_jobs", "frames"):
        _state.setdefault(key, {})


def save_state():
    global _last_snapshot_time
    with _state_lock:
        if STATE_PATH.exists():
            shutil.copy(STATE_PATH, STATE_BAK_PATH)

        with open(STATE_TMP_PATH, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, indent=2)
        os.replace(STATE_TMP_PATH, STATE_PATH)

        now = time.time()
        if now - _last_snapshot_time >= SNAPSHOT_INTERVAL_SEC:
            _last_snapshot_time = now
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy(STATE_PATH, BACKUPS_DIR / f"state_{ts}.json")
            snapshots = sorted(BACKUPS_DIR.glob("state_*.json"))
            while len(snapshots) > SNAPSHOT_KEEP:
                snapshots.pop(0).unlink(missing_ok=True)


load_state()

app = FastAPI()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ────────────────────────────── S-1 Auth ──────────────────────────────

_sessions: dict[str, datetime] = {}
_login_failures: dict[str, list[float]] = {}


class LoginBody(BaseModel):
    password: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    ip = _client_ip(request)
    now = time.time()
    recent_failures = [t for t in _login_failures.get(ip, []) if now - t < RATE_LIMIT_WINDOW_SEC]

    if len(recent_failures) >= RATE_LIMIT_MAX_FAILURES:
        raise HTTPException(status_code=401, detail="Too many failed attempts, try again later")

    if not hmac.compare_digest(body.password, APP_PASSWORD):
        recent_failures.append(now)
        _login_failures[ip] = recent_failures
        raise HTTPException(status_code=401, detail="Invalid password")

    _login_failures.pop(ip, None)
    token = secrets.token_urlsafe(32)
    _sessions[token] = datetime.now() + SESSION_TTL
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=False,  # flip to True once served behind real HTTPS
        samesite="strict",
        max_age=int(SESSION_TTL.total_seconds()),
    )
    return {"authenticated": True}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session")
    if token:
        _sessions.pop(token, None)
    response.delete_cookie("session")
    return {"authenticated": False}


def require_auth(request: Request) -> str:
    token = request.cookies.get("session")
    if not token or token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if _sessions[token] < datetime.now():
        _sessions.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")
    return token


@app.get("/api/me")
def me(token: str = Depends(require_auth)):
    return {"authenticated": True}


# ────────────────────────────── S-2 Videos ──────────────────────────────


@app.post("/api/videos")
async def upload_videos(files: list[UploadFile] = File(...), token: str = Depends(require_auth)):
    uploaded = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or '(none)'}")

        video_id = uuid.uuid4().hex
        dest_path = VIDEOS_DIR / f"{video_id}{ext}"

        size = 0
        with open(dest_path, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_BYTES:
                    out.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)

        record = {
            "id": video_id,
            "filename": f.filename,
            "path": str(dest_path),
            "size_bytes": size,
            "uploaded_at": datetime.now().isoformat(),
        }
        _state["videos"][video_id] = record
        uploaded.append(record)

    save_state()
    return {"videos": uploaded}


@app.get("/api/videos")
def list_videos(token: str = Depends(require_auth)):
    return {"videos": list(_state["videos"].values())}


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str, token: str = Depends(require_auth)):
    record = _state["videos"].get(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    path = Path(record["path"])
    if path.exists():
        path.unlink()
    del _state["videos"][video_id]
    save_state()
    return {"deleted": video_id}


# ────────────────────────────── S-3 Extraction ──────────────────────────────


class ExtractBody(BaseModel):
    video_ids: list[str]
    mode: Literal["interval", "target", "all"] = "target"
    interval_sec: float = 1.0
    target_frames: int = Field(default=30, ge=1)
    compare_method: Literal["none", "motion_iou", "frame_diff", "phash"] = "motion_iou"
    similarity_threshold: float = 30.0
    filter_blur: bool = True
    blur_threshold: float = 50.0
    prefix: str = "frame"
    max_attempts_per_slot: int = Field(default=5, ge=1)
    separate_per_video: bool = True


_job_stop_flags: dict[str, bool] = {}
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def _run_extract_job(job_id: str, body: ExtractBody):
    job = _state["extract_jobs"][job_id]
    saved_total = 0
    frame_ids: list[str] = []

    for video_id in body.video_ids:
        if _job_stop_flags.get(job_id):
            break

        record = _state["videos"].get(video_id)
        if not record:
            job["log"].append(f"[error] unknown video id {video_id}")
            continue

        video_path = record["path"]
        video_stem = Path(record["filename"]).stem
        out_dir = FRAMES_DIR / job_id / video_stem if body.separate_per_video else FRAMES_DIR / job_id
        is_all = body.mode == "all"

        try:
            if body.mode == "target":
                cap = cv2.VideoCapture(video_path)
                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
                duration = total_frames / fps if fps else 0
                interval = max(0.1, duration / max(1, body.target_frames))
                job["log"].append(f"[info] {record['filename']}: {duration:.1f}s -> {interval:.2f}s/frame")
            elif is_all:
                interval = 0.0
                job["log"].append(f"[info] {record['filename']}: all-frames mode")
            else:
                interval = body.interval_sec

            def prog(cur, tot):
                if tot:
                    job["progress"] = round(cur / tot * 100, 1)

            def log_cb(msg):
                job["log"].append(msg)
                if len(job["log"]) > 500:
                    del job["log"][: len(job["log"]) - 500]

            stats = extract_frames(
                video_path=video_path,
                output_folder=str(out_dir),
                interval_sec=interval,
                compare_method="none" if is_all else body.compare_method,
                similarity_threshold=body.similarity_threshold,
                blur_threshold=body.blur_threshold,
                filter_blur=False if is_all else body.filter_blur,
                max_attempts_per_slot=999_999 if is_all else body.max_attempts_per_slot,
                prefix=body.prefix,
                progress_callback=prog,
                log_callback=log_cb,
            )
            saved_total += stats["saved"]

            if out_dir.exists():
                for img_path in sorted(out_dir.iterdir()):
                    if img_path.suffix.lower() not in IMAGE_EXTS:
                        continue
                    frame_id = uuid.uuid4().hex
                    _state["frames"][frame_id] = {
                        "id": frame_id,
                        "video_id": video_id,
                        "job_id": job_id,
                        "path": str(img_path),
                    }
                    frame_ids.append(frame_id)
        except Exception as e:
            job["log"].append(f"[error] {record['filename']}: {e}")

    job["status"] = "stopped" if _job_stop_flags.get(job_id) else "done"
    if job["status"] == "done":
        job["progress"] = 100
    job["frame_ids"] = frame_ids
    job["saved_total"] = saved_total
    _job_stop_flags.pop(job_id, None)
    save_state()


@app.post("/api/extract")
def start_extract(body: ExtractBody, token: str = Depends(require_auth)):
    for video_id in body.video_ids:
        if video_id not in _state["videos"]:
            raise HTTPException(status_code=404, detail=f"Unknown video id: {video_id}")

    job_id = uuid.uuid4().hex
    _state["extract_jobs"][job_id] = {
        "id": job_id,
        "status": "running",
        "progress": 0,
        "log": [],
        "frame_ids": [],
        "saved_total": 0,
    }
    _job_stop_flags[job_id] = False
    threading.Thread(target=_run_extract_job, args=(job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/extract/{job_id}")
def extract_status(job_id: str, token: str = Depends(require_auth)):
    job = _state["extract_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/extract/{job_id}/frames")
def extract_frames_list(job_id: str, token: str = Depends(require_auth)):
    job = _state["extract_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    frames = [_state["frames"][fid] for fid in job.get("frame_ids", []) if fid in _state["frames"]]
    return {"frames": frames}


@app.post("/api/extract/{job_id}/stop")
def stop_extract(job_id: str, token: str = Depends(require_auth)):
    if job_id not in _state["extract_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


# ────────────────────────────── Static files (must be mounted last) ──────────────────────────────

app.mount("/", StaticFiles(directory=str(WEBAPP_DIR / "static"), html=True), name="static")
