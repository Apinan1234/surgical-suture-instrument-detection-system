"""
Web version of app.py — Phase 1 (Extract pipeline only).
FastAPI + in-memory state + threading.Thread jobs + HTTP polling, no DB, no framework frontend.
"""

import io
import json
import importlib.util
import os
import shutil
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Literal

import cv2
import pytesseract
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

WEBAPP_DIR = Path(__file__).resolve().parent
TOOL_DIR = WEBAPP_DIR.parent
sys.path.insert(0, str(TOOL_DIR))
# Load .env BEFORE importing detector: detector does os.environ.setdefault("ULTRALYTICS_SAFE_LOAD",
# …) at import time, so a value set here from .env is what setdefault preserves. If this ran after
# the import, an operator's ULTRALYTICS_SAFE_LOAD override in .env — where every other tunable lives
# — would be silently ignored (the setdefault would already have won).
load_dotenv(WEBAPP_DIR / ".env")

from frame_extractor import extract_frames, compute_phash  # noqa: E402  (needs sys.path set up first)
from detector import (Detection, BaseDetector, YOLOv11Detector, RoboflowDetector, CLASS_NAMES,  # noqa: E402
                      CLASS_COLORS_HEX, app_class_id, ensure_safe_load_or_raise, _effective_imgsz)
from dataset_exporter import export_dataset_pipeline, count_stats  # noqa: E402

DATA_DIR = Path(os.environ.get("DATA_DIR", WEBAPP_DIR / "data")).resolve()
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "8192"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_TOTAL_UPLOAD_MB = int(os.environ.get("MAX_TOTAL_UPLOAD_MB", "51200"))
MAX_TOTAL_UPLOAD_BYTES = MAX_TOTAL_UPLOAD_MB * 1024 * 1024
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
MAX_FRAMES_ALL_MODE = int(os.environ.get("MAX_FRAMES_ALL_MODE", "20000"))
# Caps how many matched frames a single Find Class run will save. Unlike Extract's target_frames,
# Find Class's match count is driven by video content the caller does not control ahead of time — a
# loose match_conf/target_classes pair on a long video could otherwise write an unbounded number of
# frames to disk before anyone notices.
MAX_FINDCLASS_MATCHES = int(os.environ.get("MAX_FINDCLASS_MATCHES", "2000"))
# Upper bound on one bulk detections write, i.e. on how long an interpolated span may be. The whole
# batch is applied under a single _state_lock, so this is really a cap on how long that lock is held.
MAX_BULK_FRAMES = int(os.environ.get("MAX_BULK_FRAMES", "500"))
# Its own cap, deliberately far higher: MAX_BULK_FRAMES bounds a payload of box arrays, this one
# bounds a list of ids. Confirming a whole unfiltered workspace has to stay possible - this one is
# 2,726 frames and growing.
MAX_BULK_REVIEW_FRAMES = int(os.environ.get("MAX_BULK_REVIEW_FRAMES", "20000"))
# Starlette caps a multipart body at 1000 files and FastAPI never raises that cap, so a folder of
# extracted frames - this workspace alone is 2,726 - was refused before the handler even ran.
MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "20000"))
# Below this many free bytes on DATA_DIR's filesystem, write-heavy routes refuse new work with a
# clear 507 instead of failing mid-write (a truncated video, a half-written state.json snapshot).
MIN_FREE_DISK_MB = int(os.environ.get("MIN_FREE_DISK_MB", "2048"))
# Per-IP throttle for routes that run CPU inference/OCR synchronously in the request handler and
# therefore aren't covered by MAX_CONCURRENT_JOBS (which only gates the background-job routes).
RATE_LIMIT_EXPENSIVE_MAX = int(os.environ.get("RATE_LIMIT_EXPENSIVE_MAX", "20"))
RATE_LIMIT_EXPENSIVE_WINDOW_SEC = int(os.environ.get("RATE_LIMIT_EXPENSIVE_WINDOW_SEC", "300"))
# Ceiling on JSON request bodies, checked from Content-Length before Starlette reads the body.
# Multipart uploads (videos/frames/models) have their own, larger, already-enforced limits above.
MAX_REQUEST_BODY_MB = int(os.environ.get("MAX_REQUEST_BODY_MB", "64"))

VIDEOS_DIR = DATA_DIR / "videos"
FRAMES_DIR = DATA_DIR / "frames"
BACKUPS_DIR = DATA_DIR / "backups"
EXPORTS_DIR = DATA_DIR / "exports"
ZIPS_DIR = DATA_DIR / "zips"
# Deliberately under TOOL_DIR, not DATA_DIR: _resolve_model_path()'s containment check (below) is
# anchored to TOOL_DIR, and DATA_DIR is env-overridable for deployment — keeping MODELS_DIR under the
# same root the security check already trusts means that check needs zero changes for uploaded models.
MODELS_DIR = TOOL_DIR / "models"
for d in (VIDEOS_DIR, FRAMES_DIR, BACKUPS_DIR, EXPORTS_DIR, ZIPS_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)

STATE_PATH = WEBAPP_DIR / "state.json"
STATE_BAK_PATH = WEBAPP_DIR / "state.json.bak"
STATE_TMP_PATH = WEBAPP_DIR / "state.json.tmp"

ALLOWED_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}

SNAPSHOT_INTERVAL_SEC = 15 * 60
SNAPSHOT_KEEP = 10

# ────────────────────────────── State (S-0) ──────────────────────────────

# Guards every mutation of, and every iteration over, the _state containers. Job workers run in
# their own threads and all non-async route handlers run in Starlette's threadpool, so both really do
# run concurrently: without this, a worker inserting into _state["frames"] while save_state() walks
# the same dict raises "RuntimeError: dictionary changed size during iteration".
# RLock, not Lock: a few call sites mutate and persist inside the same `with` block, and save_state()
# takes the lock itself — a plain Lock would self-deadlock.
_state_lock = threading.RLock()
# Serialises only the DISK half of save_state(). Deliberately separate so a slow copy/write/replace
# never blocks annotation requests. Lock order is always _state_lock -> _save_io_lock, never reversed.
_save_io_lock = threading.Lock()
_state: dict = {"videos": {}, "extract_jobs": {}, "frames": {}, "detect_jobs": {}, "findclass_jobs": {}, "export_jobs": {}, "zip_jobs": {}, "ocr_jobs": {}, "assist_log": []}
_last_snapshot_time = 0.0
# Serialising and writing are no longer one atomic step, so two concurrent saves could reach the disk
# out of order and let an older snapshot overwrite a newer one. Stamp each payload and skip any write
# that has already been superseded.
_save_seq = 0
_last_written_seq = 0


def load_state():
    global _state
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            _state = json.load(f)
    for key in ("videos", "extract_jobs", "frames", "detect_jobs", "findclass_jobs", "export_jobs", "zip_jobs", "ocr_jobs"):
        _state.setdefault(key, {})
    _state.setdefault("assist_log", [])
    # Jobs are threads, so none of them survive the process. A status left at "running" by a
    # restart or a crash is therefore a lie, and one that costs something now that the client
    # persists job ids: restoring such a job disables Start and polls a job nothing will ever
    # finish, with no way out from the UI. Retire them here, where the fact is known.
    for key in ("extract_jobs", "detect_jobs", "findclass_jobs", "export_jobs", "zip_jobs", "ocr_jobs"):
        for job in _state[key].values():
            if job.get("status") == "running":
                job["status"] = "error"
                job["error"] = "Interrupted by a server restart"
                if isinstance(job.get("log"), list):
                    job["log"].append("[error] Interrupted by a server restart")
    # Frames written before optimistic locking existed carry no "rev". Backfilling here makes
    # "every frame record has an int rev" true immediately after load, so no read path needs a default.
    for record in _state["frames"].values():
        record.setdefault("rev", 0)


def save_state():
    global _last_snapshot_time, _save_seq, _last_written_seq
    with _state_lock:
        # Serialise INSIDE the lock — this is the step that walks _state["frames"] and races the job
        # workers' inserts. Do the file I/O OUTSIDE it: a 20k-frame state is several MB, and holding
        # _state_lock across copy + write + replace would stall every concurrent annotation request.
        _save_seq += 1
        seq = _save_seq
        payload = json.dumps(_state, ensure_ascii=False, indent=2)

    with _save_io_lock:
        if seq < _last_written_seq:
            return  # a newer payload already reached disk; writing ours would roll it back

        if STATE_PATH.exists():
            shutil.copy(STATE_PATH, STATE_BAK_PATH)

        with open(STATE_TMP_PATH, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(STATE_TMP_PATH, STATE_PATH)
        # Advanced only once the payload is actually on disk. Stamping it before the write means a
        # failed write (full disk, unwritable backups dir) still marks this generation as written, so
        # a queued older-but-complete payload gets skipped as "superseded" and nothing lands at all.
        _last_written_seq = seq

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


def _client_ip(request: Request) -> str:
    # This is the peer address as the ASGI server reports it, which is the rate-limiter's bucket key
    # (see the expensive-route limiter below). Behind a reverse proxy that is the PROXY's address
    # unless uvicorn is run with --proxy-headers --forwarded-allow-ips=<proxy> (documented in
    # README.md), which rewrites it to the real client from X-Forwarded-For. Parsing XFF here in app
    # code instead would be worse: it is trivially spoofable unless the trusted-hop count is
    # configured, which is exactly what --forwarded-allow-ips exists to handle at the server layer.
    return request.client.host if request.client else "unknown"


# ────────────────────────────── Abuse mitigation ──────────────────────────────
# No login gate (removed — the tool is now open to the public), so these two middlewares are what
# stand between an anonymous visitor and unbounded CPU/bandwidth use. Multipart upload routes
# (/api/videos, /api/frames/upload, /api/models) already stream-check their own, larger limits
# (MAX_UPLOAD_SIZE_MB etc., enforced where the body is actually read) and are exempted here.

_EXPENSIVE_PATH_PREFIXES = ("/api/detect", "/api/extract", "/api/export", "/api/ocr", "/api/findclass")
_EXPENSIVE_PATH_SUFFIXES = ("/assist", "/ocr")

_rate_limit_hits: dict[str, list[float]] = {}
_rate_limit_lock = threading.Lock()


def _is_expensive_path(path: str) -> bool:
    return path.startswith(_EXPENSIVE_PATH_PREFIXES) or path.endswith(_EXPENSIVE_PATH_SUFFIXES)


@app.middleware("http")
async def expensive_route_rate_limit(request: Request, call_next):
    path = request.url.path
    if request.method in ("POST", "PUT") and _is_expensive_path(path):
        ip = _client_ip(request)
        now = time.time()
        with _rate_limit_lock:
            # Same stale-entry sweep pattern the old login limiter used: drop IPs with nothing left
            # in the window so the dict cannot grow without bound over a long-running process.
            for k in [k for k, v in _rate_limit_hits.items()
                      if not any(now - t < RATE_LIMIT_EXPENSIVE_WINDOW_SEC for t in v)]:
                _rate_limit_hits.pop(k, None)
            recent = [t for t in _rate_limit_hits.get(ip, []) if now - t < RATE_LIMIT_EXPENSIVE_WINDOW_SEC]
            if len(recent) >= RATE_LIMIT_EXPENSIVE_MAX:
                return JSONResponse({"detail": "Too many requests, slow down and try again shortly"},
                                     status_code=429)
            recent.append(now)
            _rate_limit_hits[ip] = recent
    return await call_next(request)


_BODY_SIZE_EXEMPT_PATHS = frozenset({"/api/videos", "/api/frames/upload", "/api/models"})


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    # Content-Length is checked, not the body itself, so an oversized request is rejected before
    # Starlette reads any of it into memory.
    if request.method in ("POST", "PUT") and request.url.path not in _BODY_SIZE_EXEMPT_PATHS:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_big = int(content_length) > MAX_REQUEST_BODY_MB * 1024 * 1024
            except ValueError:
                too_big = False
            if too_big:
                return JSONResponse({"detail": f"Request body exceeds {MAX_REQUEST_BODY_MB}MB limit"},
                                     status_code=413)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def _check_disk_headroom() -> None:
    """Raises 507 if DATA_DIR's filesystem is below MIN_FREE_DISK_MB free. Called explicitly at each
    write-heavy entry point (not as global middleware) so cheap/read-only routes are never slowed by
    a disk_usage() syscall that only matters right before new bytes hit disk."""
    free_mb = shutil.disk_usage(DATA_DIR).free / 1_000_000
    if free_mb < MIN_FREE_DISK_MB:
        raise HTTPException(status_code=507,
                             detail=f"Server disk space low ({free_mb:.0f}MB free), try again later")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ────────────────────────────── S-2 Videos ──────────────────────────────


# Plain `def`, not `async def`: this handler does blocking disk writes and calls save_state(), which
# serialises the whole state and writes several MB. On the event loop that stalls every other request
# (including the 1 Hz job polls); on Starlette's threadpool — where every other route here already
# runs — it doesn't.
@app.post("/api/videos")
def upload_videos(files: list[UploadFile] = File(...)):
    _check_disk_headroom()
    uploaded = []
    with _state_lock:
        current_total = sum(v.get("size_bytes", 0) for v in _state["videos"].values())
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or '(none)'}")

        video_id = uuid.uuid4().hex
        dest_path = VIDEOS_DIR / f"{video_id}{ext}"

        size = 0
        with open(dest_path, "wb") as out:
            while chunk := f.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_BYTES:
                    out.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large")
                if current_total + size > MAX_TOTAL_UPLOAD_BYTES:
                    out.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Total storage quota exceeded")
                out.write(chunk)
        current_total += size

        record = {
            "id": video_id,
            "filename": f.filename,
            "path": str(dest_path),
            "size_bytes": size,
            "uploaded_at": datetime.now().isoformat(),
        }
        with _state_lock:
            _state["videos"][video_id] = record
        uploaded.append(record)

    save_state()
    return {"videos": [_public(r) for r in uploaded]}


def _public(record: dict) -> dict:
    """Strip the absolute server filesystem path before a record goes into an API response —
    clients only ever need id-based media routes (image.jpg/thumbnail.jpg/preview.jpg) or the
    filename, never the real on-disk location."""
    return {k: v for k, v in record.items() if k != "path"}


@app.get("/api/videos")
def list_videos():
    with _state_lock:
        return {"videos": [_public(r) for r in _state["videos"].values()]}


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
    # Whole read-modify-write under the lock, so two concurrent DELETEs of the same id can't both
    # get past the 404 check and race on the unlink/del.
    with _state_lock:
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
    start_sec: float = Field(default=0.0, ge=0)
    end_sec: float | None = Field(default=None, gt=0)
    resize_max_px: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_time_range(self):
        if self.end_sec is not None and self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return self


_job_stop_flags: dict[str, bool] = {}
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

_running_jobs_lock = threading.Lock()
_running_jobs = 0


def _acquire_job_slot() -> bool:
    """Admission control for extract_jobs/detect_jobs/ocr_jobs — caps how many run at once
    (MAX_CONCURRENT_JOBS) so one operator can't exhaust CPU/GPU by starting many jobs back-to-back."""
    global _running_jobs
    with _running_jobs_lock:
        if _running_jobs >= MAX_CONCURRENT_JOBS:
            return False
        _running_jobs += 1
        return True


def _run_job_and_release(fn, *args):
    global _running_jobs
    try:
        fn(*args)
    finally:
        with _running_jobs_lock:
            _running_jobs -= 1


def _run_extract_job(job_id: str, body: ExtractBody):
    with _state_lock:
        job = _state["extract_jobs"][job_id]
    saved_total = 0
    frame_ids: list[str] = []

    for video_id in body.video_ids:
        if _job_stop_flags.get(job_id):
            break

        with _state_lock:
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
                full_duration = total_frames / fps if fps else 0
                end_bound = min(body.end_sec, full_duration) if body.end_sec is not None else full_duration
                duration = max(0.0, end_bound - body.start_sec)
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
                # No lock around the append: list.append is atomic under the GIL, and this fires per
                # extracted frame — taking the lock that often would contend with every save_state().
                # The trim is the one step a concurrent reader can actually be hurt by, so lock that.
                job["log"].append(msg)
                if len(job["log"]) > 500:
                    with _state_lock:
                        del job["log"][: len(job["log"]) - 500]

            user_prefix = (body.prefix or "").strip()
            file_prefix = f"{user_prefix}_frame" if user_prefix else "frame"

            # เมื่อทุกวิดีโอลงโฟลเดอร์เดียวกัน ต้องนับเลขต่อจากวิดีโอก่อนหน้า
            # (ไม่งั้นวิดีโอถัดไปจะเริ่มที่ _00000 แล้วเขียนทับภาพของวิดีโอแรก)
            stats = extract_frames(
                video_path=video_path,
                output_folder=str(out_dir),
                interval_sec=interval,
                compare_method="none" if is_all else body.compare_method,
                similarity_threshold=body.similarity_threshold,
                blur_threshold=body.blur_threshold,
                filter_blur=False if is_all else body.filter_blur,
                max_attempts_per_slot=999_999 if is_all else body.max_attempts_per_slot,
                prefix=file_prefix,
                start_sec=body.start_sec,
                end_sec=body.end_sec,
                resize_max_px=body.resize_max_px,
                start_index=0 if body.separate_per_video else saved_total,
                log_name=(
                    "extraction_log.json"
                    if body.separate_per_video
                    else f"extraction_log_{video_stem}.json"
                ),
                progress_callback=prog,
                log_callback=log_cb,
                max_frames=MAX_FRAMES_ALL_MODE if is_all else None,
            )
            saved_total += stats["saved"]

            if out_dir.exists():
                # Walk the directory OUTSIDE the lock (filesystem I/O), then take it only for the
                # dict inserts — this is the write that used to crash a concurrent save_state().
                img_paths = [p for p in sorted(out_dir.iterdir()) if p.suffix.lower() in IMAGE_EXTS]
                with _state_lock:
                    for img_path in img_paths:
                        frame_id = uuid.uuid4().hex
                        _state["frames"][frame_id] = {
                            "id": frame_id,
                            "video_id": video_id,
                            "job_id": job_id,
                            "path": str(img_path),
                            "filename": img_path.name,
                            "reviewed": False,
                            "rev": 0,
                        }
                        frame_ids.append(frame_id)
        except Exception as e:
            job["log"].append(f"[error] {record['filename']}: {e}")

    with _state_lock:
        job["status"] = "stopped" if _job_stop_flags.get(job_id) else "done"
        if job["status"] == "done":
            job["progress"] = 100
        job["frame_ids"] = frame_ids
        job["saved_total"] = saved_total
    _job_stop_flags.pop(job_id, None)
    save_state()


@app.post("/api/extract")
def start_extract(body: ExtractBody):
    _check_disk_headroom()
    for video_id in body.video_ids:
        if video_id not in _state["videos"]:
            raise HTTPException(status_code=404, detail=f"Unknown video id: {video_id}")

    if not _acquire_job_slot():
        raise HTTPException(
            status_code=429,
            detail=f"Too many jobs running (max {MAX_CONCURRENT_JOBS}); wait for one to finish",
        )

    job_id = uuid.uuid4().hex
    with _state_lock:
        _state["extract_jobs"][job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "log": [],
            "frame_ids": [],
            "saved_total": 0,
        }
    _job_stop_flags[job_id] = False
    threading.Thread(target=_run_job_and_release, args=(_run_extract_job, job_id, body), daemon=True).start()
    return {"job_id": job_id}


def _job_snapshot(job: dict) -> dict:
    """Copy a job record for the response. FastAPI serialises the return value AFTER the handler
    returns — i.e. outside any lock — so returning the live dict hands the JSON encoder something a
    worker thread is still appending to. Caller must hold _state_lock."""
    return {**job, "log": list(job["log"])} if "log" in job else {**job}


@app.get("/api/extract/{job_id}")
def extract_status(job_id: str):
    with _state_lock:
        job = _state["extract_jobs"].get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_snapshot(job)


def _paged_frames(job: dict, limit: int | None, offset: int) -> dict:
    """Frame-list payload for a job, optionally windowed. Shared by the extract and detect routes.

    Omitting `limit` returns every frame, which is the pre-paging behaviour and what any existing
    client still expects. Takes _state_lock itself."""
    with _state_lock:
        ids = [fid for fid in job.get("frame_ids", []) if fid in _state["frames"]]
        window = ids[offset: offset + limit] if limit is not None else ids[offset:]
        return {
            "frames": [_public(_state["frames"][fid]) for fid in window],
            # Counted AFTER the existence filter, so a client paging until it has `total` always
            # terminates — len(job["frame_ids"]) could exceed what the route can ever return.
            "total": len(ids),
            "offset": offset,
            "limit": limit,
        }


def _find_frame_job(job_id: str) -> dict | None:
    """A frame-producing job by id, whichever family made it. Detect and Find Class jobs are both
    shaped like {"frame_ids": [...], ...}, so Export/Annotate — which only need "the pool of frames
    this job id produced" — can treat a Find Class job id exactly like a Detect job id and gain both
    features with no code of their own. Caller must hold _state_lock (matches _paged_frames)."""
    return _state["detect_jobs"].get(job_id) or _state["findclass_jobs"].get(job_id)


@app.get("/api/extract/{job_id}/frames")
def extract_frames_list(
    job_id: str,
    limit: int | None = Query(None, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    with _state_lock:
        job = _state["extract_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _paged_frames(job, limit, offset)


@app.post("/api/extract/{job_id}/stop")
def stop_extract(job_id: str):
    if job_id not in _state["extract_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


def _run_zip_job(job_id: str, extract_job_id: str):
    """Build the zip on disk, updating job["progress"] per frame - mirrors _run_export_job's
    prog(done, total) closure. Building in memory (the old shape) meant no bytes at all left the
    server until the whole archive was done; a job the client can poll is what actually lets a
    progress bar be honest."""
    with _state_lock:
        job = _state["zip_jobs"][job_id]
    try:
        with _state_lock:
            src_job = _state["extract_jobs"].get(extract_job_id)
            if not src_job:
                raise ValueError(f"Unknown extract job: {extract_job_id}")
            frames = [dict(_state["frames"][fid]) for fid in src_job.get("frame_ids", []) if fid in _state["frames"]]
        if not frames:
            raise ValueError("No frames to download for this job")

        job_dir = FRAMES_DIR / extract_job_id
        zip_path = ZIPS_DIR / f"{job_id}.zip"
        total = len(frames)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, frame in enumerate(frames):
                path = Path(frame["path"])
                if path.exists():
                    try:
                        arcname = str(path.relative_to(job_dir))
                    except ValueError:
                        arcname = path.name
                    zf.write(path, arcname=arcname)
                with _state_lock:
                    job["progress"] = round((i + 1) / total * 100, 1)
        with _state_lock:
            job["zip_path"] = str(zip_path)
            job["status"] = "done"
            job["progress"] = 100
    except Exception as e:
        with _state_lock:
            job["status"] = "error"
            job["error"] = str(e)
        Path(ZIPS_DIR / f"{job_id}.zip").unlink(missing_ok=True)
    save_state()


@app.post("/api/extract/{job_id}/zip")
def start_zip(job_id: str):
    with _state_lock:
        src_job = _state["extract_jobs"].get(job_id)
        if not src_job:
            raise HTTPException(status_code=404, detail="Job not found")
        has_frames = any(fid in _state["frames"] for fid in src_job.get("frame_ids", []))
    if not has_frames:
        raise HTTPException(status_code=404, detail="No frames to download for this job")

    if not _acquire_job_slot():
        raise HTTPException(
            status_code=429,
            detail=f"Too many jobs running (max {MAX_CONCURRENT_JOBS}); wait for one to finish",
        )

    zip_job_id = uuid.uuid4().hex
    with _state_lock:
        _state["zip_jobs"][zip_job_id] = {
            "id": zip_job_id,
            "status": "running",
            "progress": 0,
            "extract_job_id": job_id,
            "zip_path": None,
            "error": None,
        }
    threading.Thread(target=_run_job_and_release, args=(_run_zip_job, zip_job_id, job_id), daemon=True).start()
    return {"job_id": zip_job_id}


@app.get("/api/extract/zip/{job_id}")
def zip_status(job_id: str):
    with _state_lock:
        job = _state["zip_jobs"].get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_snapshot(job)


@app.get("/api/extract/zip/{job_id}/download")
def download_zip_result(job_id: str):
    job = _state["zip_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done" or not job.get("zip_path"):
        raise HTTPException(status_code=400, detail="Zip not finished yet")
    zip_path = Path(job["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Zip file missing on disk")
    return FileResponse(zip_path, media_type="application/zip", filename=f"frames_{job['extract_job_id']}.zip")


# ────────────────────────────── S-4 Detection ──────────────────────────────


class DetectorConfigBody(BaseModel):
    backend: Literal["local", "roboflow"] = "local"
    model_path: str = "yolo11n.pt"
    conf: float = Field(default=0.25, ge=0.01, le=0.99)
    iou: float = Field(default=0.45, ge=0.01, le=0.99)
    device: Literal["cpu", "cuda", "mps"] = "cpu"
    # Per-class override for `conf`, e.g. {"needle": 0.10}. Absent classes keep `conf`. Exists
    # because a class the model finds but consistently scores low is otherwise invisible, and the
    # only alternative — lowering `conf` for everything — floods every other class with boxes the
    # user has to reject one by one.
    class_conf: dict[str, float] | None = None
    api_key: str | None = None
    workspace_name: str = "fhasai-khuanpan"
    workflow_id: str = "ssid-v5-logic"

    @model_validator(mode="after")
    def _check_class_conf(self):
        for name, value in (self.class_conf or {}).items():
            if name not in CLASS_NAMES:
                raise ValueError(f"Unknown class in class_conf: {name!r} (expected one of {CLASS_NAMES})")
            # Same bounds as the `conf` field above, so neither route can be talked past the other.
            if not 0.01 <= value <= 0.99:
                raise ValueError(f"class_conf[{name!r}] must be between 0.01 and 0.99, got {value}")
        return self

    @model_validator(mode="after")
    def _check_backend(self):
        if self.backend == "roboflow" and not (self.api_key or "").strip():
            raise ValueError("api_key is required when backend=roboflow")
        return self


class DetectBody(DetectorConfigBody):
    frame_ids: list[str]
    skip_reviewed: bool = True


PRETRAINED_MODEL_PREFIXES = ("yolo", "rtdetr")


@app.post("/api/frames/upload")
async def upload_frames(request: Request):
    """Adopt an already-extracted folder of images as a workspace.

    Until now the only way into this app was a video: POST /api/videos takes videos only, and frame
    records were created solely inside _run_extract_job. Anyone who had extracted frames elsewhere -
    ezgif, an earlier run, someone else's dataset - had nothing to point the tool at.

    The multipart body is parsed by hand rather than through File(...) for one reason: Starlette
    accepts at most 1000 files per request by default and FastAPI gives no way to raise that, so a
    real folder of frames was rejected before this function was ever entered. The blocking half -
    writing the files - then runs on the threadpool, which is where an async route must put it.
    """
    # Note on temp-disk use: Starlette spools every multipart part over 1 MB to a temp file as it
    # parses (SpooledTemporaryFile, formparsers.py), before _import_uploaded_frames checks a byte, so
    # a large body transiently occupies temp disk during the request (Starlette frees it when the
    # request ends). A Content-Length precheck was considered and rejected: it only catches an honest
    # client that declares an over-cap size (a chunked/lying client spools anyway), and only above
    # MAX_TOTAL_UPLOAD_MB — a 50 GB default that a disk-filling upload stays under. There is no auth
    # gate on this route anymore (removed — the tool is public now), so the checks that remain are:
    # _check_disk_headroom() below refuses new uploads once free space is already low, and the
    # incremental MAX_TOTAL_UPLOAD_BYTES guard inside _import_uploaded_frames is the real cap on what
    # actually lands permanently in the workspace. A single request can still transiently spool up to
    # MAX_UPLOAD_FILES worth of temp data before either check runs — an accepted gap, not a full fix.
    _check_disk_headroom()
    try:
        form = await request.form(max_files=MAX_UPLOAD_FILES, max_fields=MAX_UPLOAD_FILES)
    except Exception as e:  # starlette raises MultiPartException on a malformed or over-cap body
        raise HTTPException(status_code=400, detail=f"Could not read the upload: {e}")

    # Form values are starlette UploadFiles, not FastAPI's subclass of it, so this asks "not a plain
    # text field" rather than testing for a class.
    uploads = [v for v in form.getlist("files") if not isinstance(v, str)]
    if not uploads:
        raise HTTPException(status_code=400, detail="No files in the upload")
    return await run_in_threadpool(_import_uploaded_frames, uploads)


def _save_stream_capped(read_chunk, dest_path: Path, request_total: int, label: str) -> int:
    """Copy a readable stream to dest_path in 1MB chunks, enforcing MAX_UPLOAD_SIZE_BYTES per file and
    MAX_TOTAL_UPLOAD_BYTES across the whole request as bytes are actually read, never from a declared
    size. Shared by a plain uploaded file and a member pulled out of an uploaded .zip, so an extracted
    image is bound by the exact same caps as one uploaded directly - a zip's own file_size/compress_size
    metadata is never consulted, which is what defeats a zip bomb here."""
    size = 0
    with open(dest_path, "wb") as out:
        while chunk := read_chunk(1024 * 1024):
            size += len(chunk)
            request_total += len(chunk)
            if size > MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(status_code=413, detail=f"File too large: {label}")
            if request_total > MAX_TOTAL_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Total upload size exceeded")
            out.write(chunk)
    return request_total


def _import_uploaded_frames(uploads: list) -> dict:
    """Write uploaded images into a new job dir and register them. Blocking; threadpool only."""
    job_id = uuid.uuid4().hex
    job_dir = FRAMES_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved: list[tuple[str, Path]] = []
    skipped: list[str] = []
    request_total = 0
    used_names: set[str] = set()
    try:
        for f in uploads:
            # An <input webkitdirectory> hands over the whole directory, so the leaf name is where a
            # crafted path would hide - keep the leaf only (the traversal shape the 2026-08-01
            # security review found in the Extract prefix field).
            safe_name = os.path.basename(f.filename or "")
            ext = Path(safe_name).suffix.lower()

            if ext == ".zip":
                # A folder of frames zipped up before upload - handled inline rather than by
                # skipping/rejecting it, same rationale as accepting a bare folder below.
                f.file.seek(0)
                try:
                    zf = zipfile.ZipFile(f.file)
                except zipfile.BadZipFile:
                    skipped.append(safe_name or "unnamed file")
                    continue
                with zf:
                    members = [i for i in zf.infolist() if not i.is_dir()]
                    if len(members) > MAX_UPLOAD_FILES:
                        raise HTTPException(status_code=413, detail=f"Too many files inside {safe_name}")
                    for info in members:
                        # Zip-slip: never trust the member's stored path, only its basename - the same
                        # fix already applied to safe_name above and to the Extract prefix field
                        # (2026-08-01 security review).
                        member_name = os.path.basename(info.filename)
                        if Path(member_name).suffix.lower() not in IMAGE_EXTS:
                            skipped.append(member_name or "unnamed file")  # __MACOSX/, .DS_Store, etc.
                            continue
                        m_stem, m_suffix = Path(member_name).stem, Path(member_name).suffix
                        n = 2
                        while member_name in used_names:
                            member_name = f"{m_stem}_{n}{m_suffix}"
                            n += 1
                        used_names.add(member_name)
                        dest_path = job_dir / member_name
                        with zf.open(info) as member_fp:
                            request_total = _save_stream_capped(
                                member_fp.read, dest_path, request_total, member_name
                            )
                        saved.append((member_name, dest_path))
                continue

            if ext not in IMAGE_EXTS:
                # Skipped, not rejected. Every frames folder this tool produces holds an
                # extraction_log.json, and real folders carry .DS_Store / Thumbs.db / desktop.ini
                # besides; failing the whole import on those would break the one case this route
                # exists for.
                skipped.append(safe_name or "unnamed file")
                continue

            # Two subfolders can hold the same leaf name. Collisions must not overwrite each other,
            # and must not reach the exporter as duplicate filenames either - c1902a8 fixed exactly
            # that failure, where same-named frames silently dropped out of an export.
            stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
            n = 2
            while safe_name in used_names:
                safe_name = f"{stem}_{n}{suffix}"
                n += 1
            used_names.add(safe_name)

            dest_path = job_dir / safe_name
            request_total = _save_stream_capped(f.file.read, dest_path, request_total, safe_name)
            saved.append((safe_name, dest_path))

        if not saved:
            detail = "No images in the upload"
            if skipped:
                detail += f" ({len(skipped)} non-image file(s) ignored, e.g. {skipped[0]})"
            raise HTTPException(status_code=400, detail=detail)
    except BaseException:
        # Any failure, not only an HTTPException: a full disk or a client disconnect would otherwise
        # leave a half-imported folder that looks complete in the filmstrip and quietly becomes
        # training data.
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    frame_ids: list[str] = []
    with _state_lock:
        for name, path in saved:
            frame_id = uuid.uuid4().hex
            # Same key set an extracted frame gets (see _run_extract_job); video_id is None because
            # there is no source video, not because the field is optional.
            _state["frames"][frame_id] = {
                "id": frame_id,
                "video_id": None,
                "job_id": job_id,
                "path": str(path),
                "filename": name,
                "reviewed": False,
                "rev": 0,
            }
            frame_ids.append(frame_id)
        _state["extract_jobs"][job_id] = {
            "id": job_id,
            "status": "done",  # nothing to run - these frames arrived finished
            "progress": 100,
            "log": [f"[saved] {len(frame_ids)} frame(s) uploaded"]
            + ([f"[skip] {len(skipped)} non-image file(s) ignored"] if skipped else []),
            "frame_ids": frame_ids,
            "saved_total": len(frame_ids),
        }
    save_state()
    return {
        "job_id": job_id,
        "frame_ids": frame_ids,
        "count": len(frame_ids),
        "skipped": len(skipped),
    }


def _resolve_model_path(model_path: str) -> str | None:
    """Resolves model_path to an existing file strictly inside TOOL_DIR, or None."""
    p = Path(model_path.strip())
    candidate = p if p.is_absolute() else TOOL_DIR / p
    try:
        resolved = candidate.resolve()
        resolved.relative_to(TOOL_DIR.resolve())
    except ValueError:
        return None  # outside TOOL_DIR
    return str(resolved) if resolved.exists() else None


def _is_known_pretrained(model_path: str) -> bool:
    # Bare filename only (no path separators) — otherwise a crafted name like
    # "yolo/../../evil.pt" could pass the prefix/suffix check while still traversing.
    return (
        os.path.basename(model_path) == model_path
        and model_path.startswith(PRETRAINED_MODEL_PREFIXES)
        and model_path.endswith(".pt")
    )


def _validate_detect_backend(body: DetectorConfigBody):
    if body.backend == "roboflow":
        if not (body.api_key or "").strip():
            raise ValueError("api_key is required when backend=roboflow")
        return
    raw = body.model_path.strip()
    if _resolve_model_path(raw) is None and not _is_known_pretrained(raw):
        raise ValueError(f"Model not found: {body.model_path}")


def build_detector(body: DetectorConfigBody):
    """Expensive (loads weights / imports ultralytics or inference_sdk) — call only from a worker thread."""
    if body.backend == "roboflow":
        return RoboflowDetector(
            api_key=body.api_key.strip(),
            workspace_name=body.workspace_name.strip(),
            workflow_id=body.workflow_id.strip(),
            conf=body.conf,
            class_conf=body.class_conf,
        )
    raw_model_path = body.model_path.strip()
    return YOLOv11Detector(
        model_path=_resolve_model_path(raw_model_path) or raw_model_path,
        conf=body.conf,
        iou=body.iou,
        device=body.device,
        class_conf=body.class_conf,
    )


_detector_cache_lock = threading.Lock()
_detector_cache_key: tuple | None = None
_detector_cache_detector = None


def _get_cached_detector(body: DetectorConfigBody):
    """Single-slot cache keyed on (backend, model params), shared by bulk Detect jobs and Label
    Assist so neither reloads weights from disk when consecutive calls use the same model. Rebuilds
    only when the key tuple changes. Guarded by a lock since it's now reachable from a background
    job thread and the /assist request handler at the same time (bounded by MAX_CONCURRENT_JOBS)."""
    global _detector_cache_key, _detector_cache_detector
    # Sorted tuple, not the dict itself: the key has to be hashable, and two requests that set the
    # same thresholds in a different order are the same detector.
    class_conf_key = tuple(sorted((k, round(v, 4)) for k, v in (body.class_conf or {}).items()))
    if body.backend == "roboflow":
        key = ("roboflow", body.workspace_name.strip(), body.workflow_id.strip(), round(body.conf, 4), class_conf_key)
    else:
        key = ("local", body.model_path.strip(), round(body.conf, 4), round(body.iou, 4), body.device, class_conf_key)
    with _detector_cache_lock:
        if key != _detector_cache_key:
            _detector_cache_detector = build_detector(body)
            _detector_cache_key = key
        return _detector_cache_detector


def _run_detect_job(job_id: str, body: DetectBody):
    with _state_lock:
        job = _state["detect_jobs"][job_id]
    detected_total = 0

    try:
        det = _get_cached_detector(body)
    except Exception as e:
        with _state_lock:
            job["log"].append(f"[error] failed to load detector: {e}")
            job["status"] = "stopped"
        _job_stop_flags.pop(job_id, None)
        save_state()
        return

    # Recorded here rather than in the route: the job dict is built before any detector exists, and
    # the resolution is a property of the loaded checkpoint, not of the request. It goes in the log
    # too, because it is the one run parameter nobody chose — and because 960 is 2.25x the pixels of
    # 640, which on CPU is felt long before it is understood.
    imgsz = getattr(det, "imgsz", None)
    with _state_lock:
        job["imgsz"] = imgsz
        # Never name a resolution this app did not set. A Roboflow workflow resizes server-side and
        # reports none, and a local checkpoint that declares no imgsz leaves the choice inside
        # ultralytics — printing a number for either would be the silent mismatch this line exists
        # to prevent.
        job["log"].append(
            f"[info] inference resolution: {imgsz} px" if imgsz
            else "[info] inference resolution: chosen by the backend, not set by this app"
        )

    total = len(body.frame_ids)
    for idx, frame_id in enumerate(body.frame_ids):
        if _job_stop_flags.get(job_id):
            break

        with _state_lock:
            record = _state["frames"].get(frame_id)
        if not record:
            job["log"].append(f"[error] unknown frame id {frame_id}")
            continue

        if body.skip_reviewed and record.get("reviewed"):
            job["log"].append(f"[skip] {Path(record['path']).name}: already reviewed (skip_reviewed=true)")
            job["progress"] = round((idx + 1) / total * 100, 1) if total else 100
            if len(job["log"]) > 500:
                with _state_lock:
                    del job["log"][: len(job["log"]) - 500]
            continue

        try:
            img = cv2.imread(record["path"])
            if img is None:
                job["log"].append(f"[error] cannot read {record['path']}")
                continue
            dets = det.predict(img)
            records, dropped = _to_records(dets)  # Detection.source defaults to "model"
            if dropped:
                job["log"].append(
                    f"[skipped] {Path(record['path']).name}: {len(dropped)} box(es) from classes this "
                    f"project does not annotate ({', '.join(sorted(set(dropped)))}) - "
                    f"is this checkpoint the right one?"
                )
            with _state_lock:
                record["detections"] = records
                if record.get("reviewed"):
                    # Only reachable with the explicit skip_reviewed=false override — fresh unconfirmed
                    # model output shouldn't silently keep inheriting the frame's prior review status.
                    record["reviewed"] = False
                # Bulk detect replaces this frame's detections wholesale, so anyone editing it in a
                # browser is now holding a stale copy — bump so their next save gets a 409, not a
                # silent overwrite of what the model just wrote.
                _bump_rev(record)
            if records:
                detected_total += 1
            job["log"].append(f"[{'detected' if records else 'empty'}] {Path(record['path']).name}: {len(records)} obj")
        except Exception as e:
            job["log"].append(f"[error] {record['path']}: {e}")

        job["progress"] = round((idx + 1) / total * 100, 1) if total else 100
        if len(job["log"]) > 500:
            with _state_lock:
                del job["log"][: len(job["log"]) - 500]

    with _state_lock:
        job["status"] = "stopped" if _job_stop_flags.get(job_id) else "done"
        if job["status"] == "done":
            job["progress"] = 100
        job["frame_ids"] = body.frame_ids
        job["detected_total"] = detected_total
    _job_stop_flags.pop(job_id, None)
    save_state()


@app.post("/api/detect")
def start_detect(body: DetectBody):
    for frame_id in body.frame_ids:
        if frame_id not in _state["frames"]:
            raise HTTPException(status_code=404, detail=f"Unknown frame id: {frame_id}")

    try:
        _validate_detect_backend(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not _acquire_job_slot():
        raise HTTPException(
            status_code=429,
            detail=f"Too many jobs running (max {MAX_CONCURRENT_JOBS}); wait for one to finish",
        )

    job_id = uuid.uuid4().hex
    with _state_lock:
        _state["detect_jobs"][job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "log": [],
            "frame_ids": [],
            "detected_total": 0,
            "backend": body.backend,
            "model_path": body.model_path if body.backend == "local" else None,
            "workspace_name": body.workspace_name if body.backend == "roboflow" else None,
            "workflow_id": body.workflow_id if body.backend == "roboflow" else None,
            "conf": body.conf,
            "iou": body.iou,
            "device": body.device,
            "created_at": datetime.now().isoformat(),
        }
    _job_stop_flags[job_id] = False
    threading.Thread(target=_run_job_and_release, args=(_run_detect_job, job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/detect/{job_id}")
def detect_status(job_id: str):
    with _state_lock:
        job = _find_frame_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_snapshot(job)


@app.get("/api/detect/{job_id}/frames")
def detect_frames_list(
    job_id: str,
    limit: int | None = Query(None, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    with _state_lock:
        job = _find_frame_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _paged_frames(job, limit, offset)


@app.post("/api/detect/{job_id}/stop")
def stop_detect(job_id: str):
    if job_id not in _state["detect_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


def _get_frame_or_404(frame_id: str) -> dict:
    """Returns a LIVE reference into _state["frames"] — the caller must hold _state_lock for any
    read-modify-write on the returned record."""
    record = _state["frames"].get(frame_id)
    if not record:
        raise HTTPException(status_code=404, detail="Frame not found")
    return record


def _bump_rev(record: dict) -> int:
    """Version counter for a frame's DETECTIONS, used for optimistic locking on save.

    Deliberately not bumped by the review or OCR writers: those touch disjoint fields, so they can
    never cause a lost update of detections. If they bumped it, one batch-OCR run over a few hundred
    frames would 409 every in-flight annotation save — false conflicts that teach the user to click
    "overwrite" reflexively, which is exactly what this is meant to prevent.
    Caller must hold _state_lock."""
    record["rev"] = int(record.get("rev", 0)) + 1
    return record["rev"]


@app.get("/api/frames/{frame_id}/preview.jpg")
def frame_preview(frame_id: str):
    with _state_lock:
        record = _get_frame_or_404(frame_id)
        path = record["path"]
        stored_dets = list(record.get("detections", []))

    img = cv2.imread(path)
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    dets = [Detection(**d) for d in stored_dets]
    boxed = BaseDetector().draw_boxes(img, dets) if dets else img

    ok, buf = cv2.imencode(".jpg", boxed)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode image")

    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/jpeg")


# ────────────────────────────── S-4b Find Class ──────────────────────────────
# Given an already-trained model and a video, walk the video and keep only the frames where a
# user-chosen class actually appears — the tool for mining more examples of a rare/underrepresented
# class (e.g. `needle`) without scrubbing through the footage by hand. Deliberately its own job family
# rather than a Detect variant: Detect's input is frame_ids of frames that already exist on disk,
# Find Class's input is video_ids, like Extract — and unlike Extract, it never saves a frame to disk
# unless the model actually found the target class in it.


class FindClassBody(DetectorConfigBody):
    video_ids: list[str] = Field(min_length=1)
    target_classes: list[str] = Field(min_length=1)
    # Separate from `conf`/`class_conf` above: those control what predict() returns to us at all, this
    # controls which returned detections make a FRAME count as a match. Kept independent so a low
    # `conf` can be used to give a weak/rare class every chance to be seen, while match_conf still only
    # surfaces frames worth a human's time.
    match_conf: float = Field(default=0.25, ge=0.01, le=0.99)
    sample_interval_sec: float = Field(default=0.5, gt=0.0)
    start_sec: float = Field(default=0.0, ge=0)
    end_sec: float | None = Field(default=None, gt=0)
    # Hamming distance below which a new match is considered a near-duplicate of a recent one and
    # skipped. None disables dedup. Reuses frame_extractor.compute_phash — no new dependency.
    dedup_threshold: float | None = Field(default=8.0, ge=0.0)
    max_matches: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_target_classes(self):
        for name in self.target_classes:
            if name not in CLASS_NAMES:
                raise ValueError(f"Unknown class in target_classes: {name!r} (expected one of {CLASS_NAMES})")
        return self

    @model_validator(mode="after")
    def _check_time_range(self):
        if self.end_sec is not None and self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return self


# Bounded window of recently-accepted matches' pHashes to dedup against — comparing against every
# match ever saved this run would grow without bound on a long video; recent matches are the ones a
# near-duplicate is actually likely to follow.
_FINDCLASS_DEDUP_WINDOW = 5


def _run_findclass_job(job_id: str, body: FindClassBody):
    with _state_lock:
        job = _state["findclass_jobs"][job_id]

    def log_cb(msg):
        # No lock around the append — see the identical comment on _run_extract_job's log_cb.
        job["log"].append(msg)
        if len(job["log"]) > 500:
            with _state_lock:
                del job["log"][: len(job["log"]) - 500]

    try:
        det = _get_cached_detector(body)
    except Exception as e:
        with _state_lock:
            job["log"].append(f"[error] failed to load detector: {e}")
            job["status"] = "stopped"
        _job_stop_flags.pop(job_id, None)
        save_state()
        return

    imgsz = getattr(det, "imgsz", None)
    with _state_lock:
        job["imgsz"] = imgsz
        job["log"].append(
            f"[info] inference resolution: {imgsz} px" if imgsz
            else "[info] inference resolution: chosen by the backend, not set by this app"
        )

    frame_ids: list[str] = []
    matched_total = 0
    hit_cap = False

    for video_id in body.video_ids:
        if _job_stop_flags.get(job_id) or hit_cap:
            break

        with _state_lock:
            record = _state["videos"].get(video_id)
        if not record:
            log_cb(f"[error] unknown video id {video_id}")
            continue

        video_path = record["path"]
        video_stem = Path(record["filename"]).stem
        out_dir = FRAMES_DIR / job_id / video_stem

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            log_cb(f"[error] {record['filename']}: cannot open video")
            cap.release()
            continue

        recent_match_hashes: list = []
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            total_frames_full = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            start_frame = max(0, int(round(body.start_sec * fps)))
            end_frame = total_frames_full
            if body.end_sec is not None:
                end_frame = min(total_frames_full, int(round(body.end_sec * fps)))
            total_frames = max(0, end_frame - start_frame)
            frame_step = max(1, int(fps * body.sample_interval_sec))

            log_cb(
                f"[info] {record['filename']}: fps={fps:.1f} frames={total_frames_full} "
                f"sampling every {frame_step} frame(s) (~{body.sample_interval_sec:.2f}s)"
            )

            if total_frames <= 0:
                log_cb(f"[warn] {record['filename']}: start_sec is beyond the video's length — skipped")
                continue

            if start_frame > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            out_dir_created = False
            frame_idx = 0
            while frame_idx < total_frames:
                if _job_stop_flags.get(job_id):
                    break
                ret, frame = cap.read()
                if not ret:
                    break

                if total_frames:
                    job["progress"] = round(frame_idx / total_frames * 100, 1)

                if frame_idx % frame_step == 0:
                    abs_frame_idx = start_frame + frame_idx
                    time_sec = abs_frame_idx / fps if fps else 0.0
                    dets = det.predict(frame)
                    matches = [
                        d for d in dets
                        if d.class_name in body.target_classes and d.confidence >= body.match_conf
                    ]

                    if matches:
                        is_dup = False
                        h = None
                        if body.dedup_threshold is not None:
                            h = compute_phash(frame)
                            is_dup = any((h - prev) < body.dedup_threshold for prev in recent_match_hashes)

                        if is_dup:
                            log_cb(f"[dedup]   {record['filename']} @ {time_sec:.1f}s -> near-duplicate of a recent match, skipped")
                        else:
                            if h is not None:
                                recent_match_hashes.append(h)
                                if len(recent_match_hashes) > _FINDCLASS_DEDUP_WINDOW:
                                    recent_match_hashes.pop(0)

                            if not out_dir_created:
                                out_dir.mkdir(parents=True, exist_ok=True)
                                out_dir_created = True

                            filename = f"frame_{abs_frame_idx:06d}.jpg"
                            save_path = out_dir / filename
                            # Thai-filename-safe write, matching benchmark_inference.py's
                            # imread_unicode() pattern for reads: cv2.imwrite/imread silently fail on
                            # non-ASCII paths, and video_stem above comes straight from a user-uploaded
                            # filename that can contain them.
                            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                            if not ok:
                                log_cb(f"[error] {record['filename']} @ {time_sec:.1f}s: failed to encode frame")
                            else:
                                buf.tofile(str(save_path))
                                records, dropped = _to_records(dets)  # ALL detections on the frame, not just the matches
                                frame_id = uuid.uuid4().hex
                                with _state_lock:
                                    _state["frames"][frame_id] = {
                                        "id": frame_id,
                                        "video_id": video_id,
                                        "job_id": job_id,
                                        "path": str(save_path),
                                        "filename": filename,
                                        "reviewed": False,
                                        "rev": 0,
                                        "detections": records,
                                        "video_time_sec": round(time_sec, 2),
                                        "video_frame_index": abs_frame_idx,
                                        "target_match_conf": round(max(d.confidence for d in matches), 4),
                                    }
                                frame_ids.append(frame_id)
                                matched_total += 1
                                match_classes = ", ".join(sorted({d.class_name for d in matches}))
                                note = f" (+{len(dropped)} box(es) from unrecognised classes)" if dropped else ""
                                log_cb(f"[matched] {record['filename']} @ {time_sec:.1f}s -> {filename}: {match_classes}{note}")

                        if body.max_matches is not None and matched_total >= body.max_matches:
                            log_cb(f"[info] reached max_matches={body.max_matches} for this run, stopping")
                            hit_cap = True
                        elif matched_total >= MAX_FINDCLASS_MATCHES:
                            log_cb(f"[warn] reached server cap MAX_FINDCLASS_MATCHES={MAX_FINDCLASS_MATCHES}, stopping")
                            hit_cap = True
                        if hit_cap:
                            break

                frame_idx += 1
        except Exception as e:
            log_cb(f"[error] {record['filename']}: {e}")
        finally:
            cap.release()

    with _state_lock:
        job["status"] = "stopped" if _job_stop_flags.get(job_id) else "done"
        if job["status"] == "done":
            job["progress"] = 100
        job["frame_ids"] = frame_ids
        job["matched_total"] = matched_total
    _job_stop_flags.pop(job_id, None)
    save_state()


@app.post("/api/findclass")
def start_findclass(body: FindClassBody):
    _check_disk_headroom()
    for video_id in body.video_ids:
        if video_id not in _state["videos"]:
            raise HTTPException(status_code=404, detail=f"Unknown video id: {video_id}")

    try:
        _validate_detect_backend(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not _acquire_job_slot():
        raise HTTPException(
            status_code=429,
            detail=f"Too many jobs running (max {MAX_CONCURRENT_JOBS}); wait for one to finish",
        )

    job_id = uuid.uuid4().hex
    with _state_lock:
        _state["findclass_jobs"][job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "log": [],
            "frame_ids": [],
            "matched_total": 0,
            "target_classes": body.target_classes,
            "backend": body.backend,
            "model_path": body.model_path if body.backend == "local" else None,
            "workspace_name": body.workspace_name if body.backend == "roboflow" else None,
            "workflow_id": body.workflow_id if body.backend == "roboflow" else None,
            "conf": body.conf,
            "iou": body.iou,
            "device": body.device,
            "match_conf": body.match_conf,
            "sample_interval_sec": body.sample_interval_sec,
            "created_at": datetime.now().isoformat(),
        }
    _job_stop_flags[job_id] = False
    threading.Thread(target=_run_job_and_release, args=(_run_findclass_job, job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/findclass/{job_id}")
def findclass_status(job_id: str):
    with _state_lock:
        job = _state["findclass_jobs"].get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_snapshot(job)


@app.get("/api/findclass/{job_id}/frames")
def findclass_frames_list(
    job_id: str,
    limit: int | None = Query(None, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    with _state_lock:
        job = _state["findclass_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _paged_frames(job, limit, offset)


@app.post("/api/findclass/{job_id}/stop")
def stop_findclass(job_id: str):
    if job_id not in _state["findclass_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


# ────────────────────────────── S-5 Annotation ──────────────────────────────


def _to_records(dets: list[Detection]) -> tuple[list[dict], list[str]]:
    """Detections -> state records, with class ids renumbered into this app's scheme.

    A Detection reports the class id of the model that produced it. The 9-class checkpoints order
    their classes differently from CLASS_NAMES (which is pinned so that the boxes already in
    state.json keep their meaning), and dataset_exporter.py writes `class_id` verbatim into the YOLO
    label files -- so storing a model's own id would quietly relabel the dataset at export time.

    Detections whose class this app does not know are dropped rather than stored with a broken id:
    that is what a stock COCO checkpoint produces, and a `person` box with class_id -1 would export
    as an unparseable label. The names are returned so the caller can say so out loud.
    """
    records, dropped = [], []
    for d in dets:
        cid = app_class_id(d.class_name)
        if cid < 0:
            dropped.append(d.class_name)
            continue
        wire = d.to_dict()
        wire["class_id"] = cid
        records.append(wire)
    return records, dropped


# Sources that mean "a model produced this and a human has not confirmed it yet". hydrate() in
# app.js keeps its own copy of this list -- keep them in step.
MACHINE_SOURCES = ("model", "assist", "interpolated")


class DetectionIn(BaseModel):
    class_id: int
    class_name: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    x_center: float = Field(ge=0.0, le=1.0)
    y_center: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    # "model" is bulk /api/detect output, "assist" is an accepted Label Assist suggestion. They
    # were one value until the accept rate needed a numerator that matched its denominator; see
    # /api/analytics. Records written before the split carry "model" for both and stay that way.
    source: Literal["model", "assist", "manual", "interpolated"] = "manual"
    points: list[list[float]] | None = None
    keypoints: list[list[float]] | None = None
    # Set by a human in the Annotate tab only — never by the detectors (see Detection in detector.py).
    occluded: bool = False
    truncated: bool = False

    @model_validator(mode="after")
    def _check_class(self):
        if self.class_name not in CLASS_NAMES:
            raise ValueError(f"Unknown class_name: {self.class_name}")
        return self

    @model_validator(mode="after")
    def _check_points(self):
        if self.points is None:
            return self
        if len(self.points) < 3:
            raise ValueError("points must have at least 3 vertices")
        for p in self.points:
            if len(p) != 2:
                raise ValueError("each point must be [x, y]")
            x, y = p
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("point coordinates must be within [0, 1]")
        return self

    @model_validator(mode="after")
    def _check_keypoints(self):
        if self.keypoints is None:
            return self
        if self.points:
            raise ValueError("a detection cannot have both points (polygon) and keypoints (pose)")
        if len(self.keypoints) < 1:
            raise ValueError("keypoints must have at least 1 entry")
        for p in self.keypoints:
            if len(p) != 3:
                raise ValueError("each keypoint must be [x, y, v]")
            x, y, v = p
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("keypoint coordinates must be within [0, 1]")
            if v not in (0, 1, 2):
                raise ValueError("keypoint visibility v must be 0, 1, or 2")
        return self


class FrameDetectionsBody(BaseModel):
    detections: list[DetectionIn]
    # Present -> compare-and-swap against the frame's current rev, 409 on mismatch.
    # Absent  -> last-writer-wins, i.e. exactly the pre-optimistic-locking behaviour. Kept so curl
    # scripts and any other existing client keep working unchanged.
    rev: int | None = None


@app.get("/api/frames/{frame_id}/detections")
def get_frame_detections(frame_id: str):
    with _state_lock:
        record = _get_frame_or_404(frame_id)
        return {
            "frame_id": frame_id,
            "detections": record.get("detections", []),
            "rev": int(record.get("rev", 0)),
        }


@app.put("/api/frames/{frame_id}/detections")
def replace_frame_detections(frame_id: str, body: FrameDetectionsBody):
    # Built outside the lock: Detection.__post_init__ re-derives bboxes from polygons/keypoints, and
    # there is no reason to hold up other writers while that runs.
    new_dets = [Detection(**d.model_dump()).to_dict() for d in body.detections]

    with _state_lock:
        record = _get_frame_or_404(frame_id)
        current_rev = int(record.get("rev", 0))
        if body.rev is not None and body.rev != current_rev:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "stale_rev",
                    "message": "This frame was changed by someone else since you loaded it.",
                    "your_rev": body.rev,
                    "current_rev": current_rev,
                    "detections": record.get("detections", []),
                    "reviewed": bool(record.get("reviewed")),
                },
            )
        record["detections"] = new_dets
        rev = _bump_rev(record)

    save_state()
    return {"frame_id": frame_id, "detections": new_dets, "rev": rev}


class BulkItemIn(BaseModel):
    frame_id: str
    detections: list[DetectionIn]
    rev: int | None = None


class BulkDetectionsBody(BaseModel):
    items: list[BulkItemIn]

    @model_validator(mode="after")
    def _check_len(self):
        if not self.items:
            raise ValueError("items must not be empty")
        if len(self.items) > MAX_BULK_FRAMES:
            raise ValueError(f"at most {MAX_BULK_FRAMES} frames per bulk write")
        seen = set()
        for item in self.items:
            if item.frame_id in seen:
                # Two entries for one frame would make the second silently win, and the rev the
                # caller sent for it would already be stale from the first. Reject instead.
                raise ValueError(f"duplicate frame_id in items: {item.frame_id}")
            seen.add(item.frame_id)
        return self


# Note the path shape: "/api/frames/bulk/detections" would be swallowed by the route above with
# frame_id="bulk". This one cannot collide with it whatever order they are registered in.
@app.put("/api/frames/detections/bulk")
def replace_frame_detections_bulk(body: BulkDetectionsBody):
    """Replace detections on many frames as one all-or-nothing write.

    Exists because the single-frame route calls save_state() — a full serialisation of every frame in
    the app — once per frame. Filling a 300-frame interpolated span through it would mean 300 of
    those. It also could not be made atomic: a 409 partway through would leave the span half written
    with no way to tell how far it got.
    """
    # Built outside the lock for the same reason the single-frame route does it: Detection's
    # __post_init__ re-derives bboxes from polygons/keypoints, and this batch is far larger.
    prepared = [
        (item.frame_id, [Detection(**d.model_dump()).to_dict() for d in item.detections], item.rev)
        for item in body.items
    ]

    with _state_lock:
        # Pass 1 decides; pass 2 mutates. Nothing is written unless every item passes, so a caller
        # that gets a 409 knows the whole batch was rejected and can reload without reconciling.
        conflicts = []
        for frame_id, _dets, rev in prepared:
            record = _state["frames"].get(frame_id)
            if record is None:
                conflicts.append({"frame_id": frame_id, "error": "not_found"})
                continue
            current_rev = int(record.get("rev", 0))
            if rev is not None and rev != current_rev:
                conflicts.append({
                    "frame_id": frame_id,
                    "error": "stale_rev",
                    "your_rev": rev,
                    "current_rev": current_rev,
                })
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "bulk_rejected",
                    "message": "No frames were changed. Reload the frame list and try again.",
                    "conflicts": conflicts,
                },
            )

        results = []
        for frame_id, dets, _rev in prepared:
            record = _state["frames"][frame_id]
            record["detections"] = dets
            # Same rule as _run_detect_job: unconfirmed machine output must not inherit the frame's
            # prior review status. The frontend already keeps reviewed frames out of an interpolated
            # span, but this route is reachable on its own — and a frame left `reviewed` while holding
            # machine boxes is worse than it looks, because hydrate() only dashes them when the frame
            # is unreviewed, so they would never be presented for review at all.
            if record.get("reviewed") and any(d.get("source") in MACHINE_SOURCES for d in dets):
                record["reviewed"] = False
            results.append({"frame_id": frame_id, "rev": _bump_rev(record)})

    save_state()
    return {"results": results}


class ReviewBody(BaseModel):
    reviewed: bool = True


@app.post("/api/frames/{frame_id}/review")
def mark_frame_reviewed(frame_id: str, body: ReviewBody = ReviewBody()):
    with _state_lock:
        record = _get_frame_or_404(frame_id)
        record["reviewed"] = body.reviewed  # disjoint from detections — deliberately no rev bump
        reviewed = record["reviewed"]
    save_state()
    return {"frame_id": frame_id, "reviewed": reviewed}


class BulkReviewBody(BaseModel):
    frame_ids: list[str]
    reviewed: bool = True


# Path shape matches /api/frames/detections/bulk and for the same reason: "/api/frames/bulk/review"
# would be swallowed by the route above with frame_id="bulk".
@app.post("/api/frames/review/bulk")
def review_frames_bulk(body: BulkReviewBody):
    """Flip `reviewed` on many frames as one write.

    Reviewing frame by frame means one save_state() - a full serialisation of every frame in the app
    - per frame, which is why confirming a filtered range was not something the UI could offer.

    Deliberately does NOT bump `rev`: the single-frame route documents review as disjoint from
    detections, and if this one bumped it every bulk confirm would invalidate every open editor's
    optimistic-locking token for no reason.

    The two guards below raise HTTPException rather than living in a validator, because the client
    puts `detail` straight into an alert and a pydantic 422 body is a list of objects there.
    """
    if not body.frame_ids:
        raise HTTPException(status_code=400, detail="frame_ids must not be empty")
    # Order-preserving dedupe: the same id twice is harmless here (unlike the detections route, where
    # each entry carries data), but it would inflate the count reported back.
    frame_ids = list(dict.fromkeys(body.frame_ids))
    if len(frame_ids) > MAX_BULK_REVIEW_FRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_BULK_REVIEW_FRAMES} frames per bulk review (got {len(frame_ids)})",
        )

    with _state_lock:
        # Pass 1 decides, pass 2 mutates - same all-or-nothing shape as the bulk detections route, so
        # a rejected call leaves nothing half-applied.
        unknown = [fid for fid in frame_ids if fid not in _state["frames"]]
        if unknown:
            raise HTTPException(
                status_code=404,
                detail=f"No frames were changed. Unknown frame id(s): {', '.join(unknown[:5])}"
                + (f" and {len(unknown) - 5} more" if len(unknown) > 5 else ""),
            )
        for fid in frame_ids:
            _state["frames"][fid]["reviewed"] = body.reviewed

    save_state()
    return {"updated": len(frame_ids), "reviewed": body.reviewed}


@app.get("/api/frames/{frame_id}/image.jpg")
def frame_image(frame_id: str):
    record = _get_frame_or_404(frame_id)

    img = cv2.imread(record["path"])
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode image")

    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/jpeg")


@app.get("/api/frames/{frame_id}/thumbnail.jpg")
def frame_thumbnail(frame_id: str, max_side: int = Query(160, alias="max")):
    record = _get_frame_or_404(frame_id)

    img = cv2.imread(record["path"])
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    h, w = img.shape[:2]
    scale = max_side / float(h if h >= w else w)
    if scale < 1.0:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode thumbnail")

    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/jpeg")


# ────────────────────────────── S-8 Label Assist ──────────────────────────────


class AssistBody(DetectorConfigBody):
    pass


@app.post("/api/frames/{frame_id}/assist")
def assist_frame(frame_id: str, body: AssistBody):
    with _state_lock:
        path = _get_frame_or_404(frame_id)["path"]

    try:
        _validate_detect_backend(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    img = cv2.imread(path)
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    try:
        det = _get_cached_detector(body)
        dets = det.predict(img)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Assist failed: {e}")

    # Detection defaults to source="model"; re-stamping here is what lets /api/analytics count the
    # boxes this call had accepted without also sweeping in every box a bulk detect run produced.
    suggestions, dropped = _to_records(dets)
    for wire in suggestions:
        wire["source"] = "assist"

    with _state_lock:
        _state["assist_log"].append({
            "frame_id": frame_id,
            "backend": body.backend,
        "model_path": body.model_path if body.backend == "local" else None,
            "workspace_name": body.workspace_name if body.backend == "roboflow" else None,
            "workflow_id": body.workflow_id if body.backend == "roboflow" else None,
            "conf": body.conf,
            "class_conf": body.class_conf,
            # Counts what was actually offered to the user, not what the model emitted: a
            # suggestion dropped for being an unknown class was never a suggestion, and counting it
            # would make the accept rate unreachable by construction.
            "detected_count": len(suggestions),
            # Marks this call as one whose accepted boxes are identifiable (they will be saved as
            # source="assist"). Entries logged before the split have no such flag and are left out of
            # the accept-rate denominator rather than being compared against boxes that cannot be
            # told apart from bulk detect output.
            "tracks_accepts": True,
            "created_at": datetime.now().isoformat(),
        })
    save_state()

    return {"detections": suggestions, "skipped_unknown_classes": sorted(set(dropped))}


# ────────────────────────────── OCR (burned-in overlay text) ──────────────────────────────


def _resolve_tesseract_cmd() -> str:
    """Locate the Tesseract binary: PATH first (shutil.which), then the default UB-Mannheim
    Windows installer location (covers install-succeeded-but-server-predates-PATH-refresh).
    Raises with an actionable install hint if neither is found."""
    found = shutil.which("tesseract")
    if found:
        return found
    standard = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if standard.exists():
        return str(standard)
    raise RuntimeError(
        "Tesseract OCR binary not found. Install it (e.g. `winget install --id "
        "UB-Mannheim.TesseractOCR -e`), then restart this server."
    )


def run_ocr(img) -> str:
    """Run Tesseract against a full frame (BGR ndarray from cv2.imread) and return the extracted
    text, whitespace-trimmed. Full-frame only, Tesseract defaults only — no ROI/crop, no
    language/PSM config, per confirmed v1 scope."""
    pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract_cmd()
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # same BGR->RGB conversion app.py already does
    # (app.py:906, app.py:1091) before handing a cv2 frame to a non-cv2 library.
    return pytesseract.image_to_string(rgb).strip()


@app.post("/api/frames/{frame_id}/ocr")
def ocr_frame(frame_id: str):
    with _state_lock:
        record = _get_frame_or_404(frame_id)
        path = record["path"]

    img = cv2.imread(path)
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    try:
        text = run_ocr(img)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")

    with _state_lock:
        record["ocr_text"] = text  # disjoint from detections — deliberately no rev bump
    save_state()

    return {"frame_id": frame_id, "ocr_text": text}


class OcrBody(BaseModel):
    frame_ids: list[str]
    skip_existing: bool = True


def _run_ocr_job(job_id: str, body: OcrBody):
    """Batch OCR across a frame set — same job/progress/log/stop shape as _run_detect_job, so the
    frontend polls it identically. Writes straight to record["ocr_text"], matching the single-frame
    route: OCR has no accept/reject step, so it's settled metadata, not a pending suggestion."""
    with _state_lock:
        job = _state["ocr_jobs"][job_id]
    text_found_total = 0
    skipped_total = 0

    try:
        # Resolve the binary once up front. Doing it per frame would repeat the same "not installed"
        # failure for every frame in the job instead of failing fast with one actionable message.
        _resolve_tesseract_cmd()
    except Exception as e:
        with _state_lock:
            job["log"].append(f"[error] {e}")
            job["status"] = "stopped"
        _job_stop_flags.pop(job_id, None)
        save_state()
        return

    total = len(body.frame_ids)
    for idx, frame_id in enumerate(body.frame_ids):
        if _job_stop_flags.get(job_id):
            break

        with _state_lock:
            record = _state["frames"].get(frame_id)
        if not record:
            job["log"].append(f"[error] unknown frame id {frame_id}")
            continue

        if body.skip_existing and record.get("ocr_text") is not None:
            skipped_total += 1
            job["log"].append(f"[skip] {Path(record['path']).name}: already has OCR text")
            job["progress"] = round((idx + 1) / total * 100, 1) if total else 100
            if len(job["log"]) > 500:
                with _state_lock:
                    del job["log"][: len(job["log"]) - 500]
            continue

        try:
            img = cv2.imread(record["path"])
            if img is None:
                job["log"].append(f"[error] cannot read {record['path']}")
                continue
            text = run_ocr(img)
            with _state_lock:
                record["ocr_text"] = text  # disjoint from detections — deliberately no rev bump
            if text:
                text_found_total += 1
            preview = text.replace("\n", " ")[:60]
            job["log"].append(
                f"[text] {Path(record['path']).name}: {preview}" if text
                else f"[empty] {Path(record['path']).name}: no text"
            )
        except Exception as e:
            job["log"].append(f"[error] {record['path']}: {e}")

        job["progress"] = round((idx + 1) / total * 100, 1) if total else 100
        if len(job["log"]) > 500:
            with _state_lock:
                del job["log"][: len(job["log"]) - 500]

    with _state_lock:
        job["status"] = "stopped" if _job_stop_flags.get(job_id) else "done"
        if job["status"] == "done":
            job["progress"] = 100
        job["frame_ids"] = body.frame_ids
        # text_found_total counts only frames OCR'd by THIS run; skipped_total is reported separately
        # so a fully-skipped re-run doesn't read as "0 frames with text" when they all already have some.
        job["text_found_total"] = text_found_total
        job["skipped_total"] = skipped_total
    _job_stop_flags.pop(job_id, None)
    save_state()


@app.post("/api/ocr")
def start_ocr(body: OcrBody):
    for frame_id in body.frame_ids:
        if frame_id not in _state["frames"]:
            raise HTTPException(status_code=404, detail=f"Unknown frame id: {frame_id}")

    if not _acquire_job_slot():
        raise HTTPException(
            status_code=429,
            detail=f"Too many jobs running (max {MAX_CONCURRENT_JOBS}); wait for one to finish",
        )

    job_id = uuid.uuid4().hex
    with _state_lock:
        _state["ocr_jobs"][job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "log": [],
            "frame_ids": [],
            "text_found_total": 0,
            "skipped_total": 0,
            "skip_existing": body.skip_existing,
            "created_at": datetime.now().isoformat(),
        }
    _job_stop_flags[job_id] = False
    threading.Thread(target=_run_job_and_release, args=(_run_ocr_job, job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/ocr/{job_id}")
def ocr_status(job_id: str):
    with _state_lock:
        job = _state["ocr_jobs"].get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_snapshot(job)


@app.post("/api/ocr/{job_id}/stop")
def stop_ocr(job_id: str):
    if job_id not in _state["ocr_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


# The batch results need no dedicated GET route — ocr_text rides through _public() on the existing
# GET /api/detect/{job_id}/frames, which the Annotate frontend already fetches.


# ────────────────────────────── S-7 Models ──────────────────────────────


# What each checkpoint declares about itself, cached on (path, mtime, size). Reading it means
# unpickling a checkpoint, which costs the better part of a second, and the picker refreshes on every
# page load — nine of them in series would stall the UI. A background warm-up fills this at startup
# so the first render already has the numbers; anything not yet read reports null and the UI shows a
# dash.
#
# Class count and training resolution are cached together because they come off the same load. The
# resolution is here for the picker's sake: a model served at the wrong imgsz fails silently rather
# than loudly (see _effective_imgsz in detector.py), so the one place a user chooses a model is the place
# that has to say which resolution that choice implies.
_MODEL_META: dict[tuple[str, int, int], dict] = {}
# Serialises the reads. Without it the warm-up thread and a request thread can both be part-way
# through importing ultralytics, and the loser reports every checkpoint as unreadable.
_MODEL_META_LOCK = threading.Lock()

# Copied at every use rather than shared: a single dict handed out for every unreadable checkpoint is
# one accidental mutation away from rewriting them all.
_UNREADABLE_MODEL = {"classes": None, "imgsz": None}


def _model_meta(path: Path) -> dict:
    """{"classes": n, "imgsz": n} for a checkpoint; either value is None if it cannot be read."""
    try:
        st = path.stat()
    except OSError:
        return dict(_UNREADABLE_MODEL)
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in _MODEL_META:
        return _MODEL_META[key]
    with _MODEL_META_LOCK:
        if key in _MODEL_META:   # filled while this thread waited
            return _MODEL_META[key]
        return _read_model_meta(path, key)


def _read_model_meta(path: Path, key: tuple[str, int, int]) -> dict:
    meta = dict(_UNREADABLE_MODEL)
    try:
        ensure_safe_load_or_raise()  # a .pt is a pickle; same guard as every other load path
        from ultralytics import YOLO
        model = YOLO(str(path))
        names = model.names
        # The same helper the detector uses, so the picker cannot advertise a resolution the run
        # would not actually use.
        meta = {"classes": len(names) if names else None, "imgsz": _effective_imgsz(model)}
    except Exception as e:
        # A foreign or half-written .pt must not break the picker, but staying silent once hid a
        # plain NameError and made every model report "unreadable".
        print(f"[models] could not read metadata from {path.name}: {type(e).__name__}: {e}", flush=True)
        meta = dict(_UNREADABLE_MODEL)
    _MODEL_META[key] = meta
    return meta


def _model_kind(p: Path) -> str:
    """project = trained for this dataset, base = a stock COCO weight, checkpoint = a training run.

    The distinction is the whole point of this endpoint: a stock weight detects person/car/dog and
    is useless here, but sitting in a flat list it looks like any other option."""
    if p.parent == MODELS_DIR:
        return "project"
    if p.parent == TOOL_DIR:
        return "base"
    return "checkpoint"


def _scan_models() -> list[dict]:
    """Every .pt reachable for backend="local": top-level TOOL_DIR (pretrained convention, e.g.
    yolo11n.pt), MODELS_DIR (uploads), and runs/ (already-trained outputs from
    train_roboflow_yolo.py / experiment_tracking.py — surfaced automatically, no manual copying).

    `path` stays relative-to-TOOL_DIR POSIX, not a bare name: once runs/ is included, multiple
    best.pt/last.pt share a filename across different run folders, so bare names would collide.
    _resolve_model_path() already resolves values like this correctly."""
    paths = set(TOOL_DIR.glob("*.pt")) | set(MODELS_DIR.glob("*.pt")) | set((TOOL_DIR / "runs").rglob("*.pt"))
    out = []
    for p in sorted(paths):
        try:
            st = p.stat()
        except OSError:
            continue
        meta = _model_meta(p)
        out.append({
            "path": str(p.relative_to(TOOL_DIR)).replace("\\", "/"),
            "kind": _model_kind(p),
            "classes": meta["classes"],
            "imgsz": meta["imgsz"],
            "size_mb": round(st.st_size / 1_000_000, 1),
            "mtime": st.st_mtime,
        })
    return out


def _warm_model_meta_cache() -> None:
    paths = set(TOOL_DIR.glob("*.pt")) | set(MODELS_DIR.glob("*.pt")) | set((TOOL_DIR / "runs").rglob("*.pt"))
    for p in sorted(paths):
        _model_meta(p)


threading.Thread(target=_warm_model_meta_cache, daemon=True).start()


@app.get("/api/models")
def list_models():
    return {"models": _scan_models()}


@app.post("/api/models")
def upload_model(file: UploadFile = File(...)):  # plain def: blocking writes belong on the threadpool
    _check_disk_headroom()
    ext = Path(file.filename).suffix.lower()
    if ext != ".pt":
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or '(none)'}")

    # Strip any path components a crafted filename= could carry (same fix already applied to the
    # Extract prefix field during the 2026-08-01 security review).
    safe_name = os.path.basename(file.filename)
    dest_path = MODELS_DIR / safe_name
    if dest_path.exists():
        # Never silently overwrite an existing model file — dedupe instead.
        stem, suffix = dest_path.stem, dest_path.suffix
        n = 2
        while (MODELS_DIR / f"{stem}_{n}{suffix}").exists():
            n += 1
        dest_path = MODELS_DIR / f"{stem}_{n}{suffix}"

    size = 0
    with open(dest_path, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE_BYTES:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)

    relative_path = str(dest_path.relative_to(TOOL_DIR)).replace("\\", "/")
    return {"uploaded": relative_path, "models": _scan_models()}


@app.post("/api/models/load")
def load_model(body: DetectorConfigBody):  # plain def: build_detector blocks, and belongs on the threadpool
    """Build the detector the next Detect or Assist call will use, and report what it turned out to be.

    Without this there is no way to find out whether a model path is usable except to start a real
    job and wait for it to fail, which on this workspace is minutes. It deliberately goes through
    _get_cached_detector rather than build_detector: validating the path is only half the point, the
    other half is leaving the cache warm for the call that follows.

    Note what the answer does and does not mean. The cache holds ONE detector, keyed on the whole
    parameter tuple including class_conf, so a later request with different thresholds rebuilds it.
    A success here means "this model loads and these are its classes", never "pinned in memory".
    """
    try:
        _validate_detect_backend(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        det = _get_cached_detector(body)
    except Exception as e:  # torch.load / ultralytics raise a wide range on a corrupt or wrong-type file
        raise HTTPException(status_code=400, detail=f"Could not load model: {e}")

    return {
        "backend": body.backend,
        "model_path": body.model_path.strip() if body.backend == "local" else None,
        "class_names": list(getattr(det, "class_names", [])),
        # The resolution this detector will actually run at, inferred from the checkpoint. This
        # endpoint exists to answer "what will the next call do", and at the wrong imgsz a model
        # returns fewer small objects rather than an error — so it has to answer this too.
        "imgsz": getattr(det, "imgsz", None),
        # Only ultralytics models carry a task; a Roboflow workflow has none, hence None rather than
        # a guess. This is what tells the user a segment checkpoint was loaded for a detect job.
        "task": getattr(getattr(det, "model", None), "task", None),
    }


@app.get("/api/classes")
def list_classes():
    return {"class_names": CLASS_NAMES, "class_colors": CLASS_COLORS_HEX}


# ────────────────────────────── Analytics ──────────────────────────────


@app.get("/api/analytics")
def analytics():
    # Snapshot under the lock: this scans every frame in the app, so without it a job inserting
    # frames mid-scan would raise "dictionary changed size during iteration".
    with _state_lock:
        assist_log = list(_state.get("assist_log", []))
        frames = list(_state["frames"].values())
        detect_jobs = list(_state["detect_jobs"].values())

    # This ratio read 4834.6% because its two halves counted different things: the denominator
    # counted only suggestions made through /assist, while the numerator counted every model-sourced
    # box in the app -- including bulk /api/detect output that was never offered as a suggestion, and
    # boxes annotated before the assist log existed at all.
    #
    # Accepted assist suggestions now save as source="assist" (see assist_frame), so the numerator
    # can name exactly what the denominator offered. Assist calls logged before that split are
    # excluded from both halves: their accepted boxes were saved as "model" and cannot be picked out
    # of the bulk-detect population, so counting their suggestions would understate the rate as badly
    # as the old numerator overstated it.
    tracked = [e for e in assist_log if e.get("tracks_accepts")]
    suggested_total = sum(int(e.get("detected_count", 0)) for e in tracked)

    accepted_total = sum(
        1
        for f in frames
        for d in f.get("detections", [])
        if d.get("source") == "assist"
    )
    # None, not 0.0: before the first tracked assist call there is no rate to report, and 0% would
    # read as "the user rejects everything".
    rate_pct = round(accepted_total / suggested_total * 100, 1) if suggested_total else None

    # Reported beside the rate rather than divided into it. This is the quantity the old numerator
    # was actually measuring -- every box in the app that came from a model by any route.
    model_box_total = sum(
        1
        for f in frames
        for d in f.get("detections", [])
        if d.get("source") in ("model", "assist")
    )

    job_history = [
        {
            "id": job["id"],
            "backend": job.get("backend"),
            "model_path": job.get("model_path"),
            "workspace_name": job.get("workspace_name"),
            "workflow_id": job.get("workflow_id"),
            "conf": job.get("conf"),
            "status": job.get("status"),
            "frame_count": len(job.get("frame_ids", [])),
            "detected_total": job.get("detected_total", 0),
            "created_at": job.get("created_at"),  # None for jobs created before this field existed
        }
        for job in detect_jobs
    ]

    pool = [{"has_detection": bool(f.get("detections"))} for f in frames]
    dataset_stats = count_stats(pool)
    reviewed_count = sum(1 for f in frames if f.get("reviewed"))

    class_counts = {name: 0 for name in CLASS_NAMES}
    for f in frames:
        for d in f.get("detections", []):
            name = d.get("class_name")
            if name in class_counts:
                class_counts[name] += 1

    return {
        "accept_rate": {
            "suggested_total": suggested_total,
            "accepted_total": accepted_total,
            "rate_pct": rate_pct,
            "assist_call_count": len(tracked),
            # How many logged assist calls the rate had to leave out, so a small denominator beside a
            # large annotation count is self-explaining rather than suspicious.
            "untracked_call_count": len(assist_log) - len(tracked),
            "model_box_total": model_box_total,
        },
        "detect_jobs": job_history,
        "dataset": {**dataset_stats, "reviewed": reviewed_count},
        "class_counts": class_counts,
    }


# ────────────────────────────── S-6 Export ──────────────────────────────


class SplitsIn(BaseModel):
    train: float = Field(default=0.7, gt=0.0, lt=1.0)
    val: float = Field(default=0.2, ge=0.0, lt=1.0)
    test: float = Field(default=0.1, ge=0.0, lt=1.0)

    @model_validator(mode="after")
    def _check_sum(self):
        total = self.train + self.val + self.test
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"splits must sum to ~1.0 (got {total:.3f})")
        return self


class PreprocessIn(BaseModel):
    resize: bool = True
    resize_size: int = Field(default=640, gt=0)


class AugmentIn(BaseModel):
    multiplier: int = Field(default=1, ge=1, le=10)  # web default: 1 (no albumentations installed)
    flip: bool = True
    rotate: bool = True
    blur: bool = True
    brightness: bool = True
    crop: bool = True


class ExportBody(BaseModel):
    detect_job_id: str
    version_name: str = Field(default="v1", max_length=64)
    reviewed_only: bool = False
    task: Literal["detect", "segment", "pose"] = "detect"
    yolo_version: Literal["v8", "v11", "v26"] = "v11"
    splits: SplitsIn = Field(default_factory=SplitsIn)
    preprocess: PreprocessIn = Field(default_factory=PreprocessIn)
    augment: AugmentIn = Field(default_factory=AugmentIn)


def _export_pool(detect_job_id: str, reviewed_only: bool) -> list[dict]:
    # The {**f} spread below copies each record, so the pool the export worker then spends minutes
    # writing to disk is a snapshot — annotations saved mid-export can't mutate it underneath.
    with _state_lock:
        job = _find_frame_job(detect_job_id)
        if job is None:
            raise ValueError(f"Unknown detect_job_id: {detect_job_id}")
        frames = [_state["frames"][fid] for fid in job.get("frame_ids", []) if fid in _state["frames"]]
        if reviewed_only:
            frames = [f for f in frames if f.get("reviewed")]
        return [{**f, "image_path": f["path"], "has_detection": bool(f.get("detections"))} for f in frames]


@app.get("/api/export/preview")
def export_preview(detect_job_id: str, reviewed_only: bool = False):
    try:
        pool = _export_pool(detect_job_id, reviewed_only)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    stats = count_stats(pool)
    unreviewed = sum(1 for item in pool if not item.get("reviewed"))
    augment_available = importlib.util.find_spec("albumentations") is not None
    return {**stats, "unreviewed": unreviewed, "class_count": len(CLASS_NAMES), "augment_available": augment_available}


def _run_export_job(job_id: str, body: ExportBody):
    with _state_lock:
        job = _state["export_jobs"][job_id]
    try:
        pool = _export_pool(body.detect_job_id, body.reviewed_only)

        def prog(done, total):
            job["progress"] = round(done / total * 100, 1) if total else 100

        out_dir = EXPORTS_DIR / job_id
        # Segmentation-format datasets can't be augmented by the bbox-only albumentations pipeline —
        # force multiplier=1 here regardless of what the (also client-disabled) UI controls sent.
        augment_config = body.augment.model_dump() if body.task == "detect" else {"multiplier": 1}
        zip_path = export_dataset_pipeline(
            results=pool,
            output_dir=str(out_dir),
            class_names=CLASS_NAMES,
            splits={"train": body.splits.train, "val": body.splits.val, "test": body.splits.test},
            include_empty=True,
            as_zip=True,
            preprocess_config={"resize": body.preprocess.resize, "resize_size": body.preprocess.resize_size},
            augment_config=augment_config,
            progress_callback=prog,
            task=body.task,
            yolo_version=body.yolo_version,
        )
        summary_path = out_dir / "export_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
        with _state_lock:
            job["zip_path"] = zip_path
            if summary is not None:
                job["summary"] = summary
            job["status"] = "done"
            job["progress"] = 100
    except Exception as e:
        with _state_lock:
            job["status"] = "error"
            job["error"] = str(e)
    save_state()


@app.post("/api/export")
def start_export(body: ExportBody):
    try:
        pool = _export_pool(body.detect_job_id, body.reviewed_only)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not pool:
        raise HTTPException(status_code=400, detail="No frames available to export for this selection")

    # Acquired only after the 404/400 checks above, so a rejected request never leaks a slot.
    # Export was the one job family that skipped admission control; a large augmented export is as
    # CPU-hungry as a detect run, so it belongs under the same cap.
    if not _acquire_job_slot():
        raise HTTPException(
            status_code=429,
            detail=f"Too many jobs running (max {MAX_CONCURRENT_JOBS}); wait for one to finish",
        )

    job_id = uuid.uuid4().hex
    with _state_lock:
        _state["export_jobs"][job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "detect_job_id": body.detect_job_id,
            "version_name": body.version_name,
            "reviewed_only": body.reviewed_only,
            "pool_size": len(pool),
            "zip_path": None,
            "summary": None,
            "error": None,
        }
    threading.Thread(target=_run_job_and_release, args=(_run_export_job, job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/export/{job_id}")
def export_status(job_id: str):
    with _state_lock:
        job = _state["export_jobs"].get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_snapshot(job)


@app.get("/api/export/{job_id}/download")
def download_export(job_id: str):
    job = _state["export_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done" or not job.get("zip_path"):
        raise HTTPException(status_code=400, detail="Export not finished yet")
    zip_path = Path(job["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Export file missing on disk")
    safe_version = "".join(c for c in (job.get("version_name") or "v1") if c.isalnum() or c in "-_") or "v1"
    return FileResponse(zip_path, media_type="application/zip", filename=f"dataset_{safe_version}.zip")


# ────────────────────────────── Static files (must be mounted last) ──────────────────────────────

app.mount("/", StaticFiles(directory=str(WEBAPP_DIR / "static"), html=True), name="static")
