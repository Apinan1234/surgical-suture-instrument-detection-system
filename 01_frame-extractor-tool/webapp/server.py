"""
Web version of app.py — Phase 1 (Extract pipeline only).
FastAPI + in-memory state + threading.Thread jobs + HTTP polling, no DB, no framework frontend.
"""

import io
import json
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
from fastapi.responses import FileResponse, StreamingResponse
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

from frame_extractor import extract_frames  # noqa: E402  (needs sys.path set up first)
from detector import Detection, BaseDetector, YOLOv11Detector, RoboflowDetector, CLASS_NAMES, CLASS_COLORS_HEX  # noqa: E402
from dataset_exporter import export_dataset_pipeline, count_stats  # noqa: E402

DATA_DIR = Path(os.environ.get("DATA_DIR", WEBAPP_DIR / "data")).resolve()
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "8192"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_TOTAL_UPLOAD_MB = int(os.environ.get("MAX_TOTAL_UPLOAD_MB", "51200"))
MAX_TOTAL_UPLOAD_BYTES = MAX_TOTAL_UPLOAD_MB * 1024 * 1024
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
MAX_FRAMES_ALL_MODE = int(os.environ.get("MAX_FRAMES_ALL_MODE", "20000"))
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

VIDEOS_DIR = DATA_DIR / "videos"
FRAMES_DIR = DATA_DIR / "frames"
BACKUPS_DIR = DATA_DIR / "backups"
EXPORTS_DIR = DATA_DIR / "exports"
# Deliberately under TOOL_DIR, not DATA_DIR: _resolve_model_path()'s containment check (below) is
# anchored to TOOL_DIR, and DATA_DIR is env-overridable for deployment — keeping MODELS_DIR under the
# same root the security check already trusts means that check needs zero changes for uploaded models.
MODELS_DIR = TOOL_DIR / "models"
for d in (VIDEOS_DIR, FRAMES_DIR, BACKUPS_DIR, EXPORTS_DIR, MODELS_DIR):
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
_state: dict = {"videos": {}, "extract_jobs": {}, "frames": {}, "detect_jobs": {}, "export_jobs": {}, "ocr_jobs": {}, "assist_log": []}
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
    for key in ("videos", "extract_jobs", "frames", "detect_jobs", "export_jobs", "ocr_jobs"):
        _state.setdefault(key, {})
    _state.setdefault("assist_log", [])
    # Jobs are threads, so none of them survive the process. A status left at "running" by a
    # restart or a crash is therefore a lie, and one that costs something now that the client
    # persists job ids: restoring such a job disables Start and polls a job nothing will ever
    # finish, with no way out from the UI. Retire them here, where the fact is known.
    for key in ("extract_jobs", "detect_jobs", "export_jobs", "ocr_jobs"):
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


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


@app.get("/api/extract/{job_id}/zip")
def download_zip(job_id: str):
    with _state_lock:
        job = _state["extract_jobs"].get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        # Snapshot the paths under the lock; the zip building below is slow I/O and must not hold it.
        frames = [dict(_state["frames"][fid]) for fid in job.get("frame_ids", []) if fid in _state["frames"]]

    job_dir = FRAMES_DIR / job_id
    if not frames:
        raise HTTPException(status_code=404, detail="No frames to download for this job")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for frame in frames:
            path = Path(frame["path"])
            if not path.exists():
                continue
            try:
                arcname = str(path.relative_to(job_dir))
            except ValueError:
                arcname = path.name
            zf.write(path, arcname=arcname)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="frames_{job_id}.zip"'},
    )


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
    # MAX_TOTAL_UPLOAD_MB — a 50 GB default that a disk-filling upload stays under — so it would add a
    # limit the project has declined (see the 2026-08-01 review's accepted DoS-shaped gaps) while
    # returning a 413 the browser usually never sees (connection reset mid-upload → "Failed to
    # fetch"). This is now an authenticated route (S-1), which is the intended mitigation; the
    # incremental MAX_TOTAL_UPLOAD_BYTES guard inside _import_uploaded_frames remains the real cap on
    # what actually lands in the workspace.
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
            size = 0
            with open(dest_path, "wb") as out:
                while chunk := f.file.read(1024 * 1024):
                    size += len(chunk)
                    request_total += len(chunk)
                    if size > MAX_UPLOAD_SIZE_BYTES:
                        raise HTTPException(status_code=413, detail=f"File too large: {safe_name}")
                    # Bounds this request, where the video route's identical constant bounds total
                    # stored video. Frames carry no per-file size in state, and extracted frames are
                    # generated locally rather than uploaded, so there is no running total to add to.
                    if request_total > MAX_TOTAL_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Total upload size exceeded")
                    out.write(chunk)
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
            with _state_lock:
                record["detections"] = [d.to_dict() for d in dets]  # Detection.source defaults to "model"
                if record.get("reviewed"):
                    # Only reachable with the explicit skip_reviewed=false override — fresh unconfirmed
                    # model output shouldn't silently keep inheriting the frame's prior review status.
                    record["reviewed"] = False
                # Bulk detect replaces this frame's detections wholesale, so anyone editing it in a
                # browser is now holding a stale copy — bump so their next save gets a 409, not a
                # silent overwrite of what the model just wrote.
                _bump_rev(record)
            if dets:
                detected_total += 1
            job["log"].append(f"[{'detected' if dets else 'empty'}] {Path(record['path']).name}: {len(dets)} obj")
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
        job = _state["detect_jobs"].get(job_id)
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
        job = _state["detect_jobs"].get(job_id)
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


# ────────────────────────────── S-5 Annotation ──────────────────────────────


class DetectionIn(BaseModel):
    class_id: int
    class_name: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    x_center: float = Field(ge=0.0, le=1.0)
    y_center: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    source: Literal["model", "manual", "interpolated"] = "manual"
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
            if record.get("reviewed") and any(d.get("source") in ("model", "interpolated") for d in dets):
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

    with _state_lock:
        _state["assist_log"].append({
            "frame_id": frame_id,
            "backend": body.backend,
        "model_path": body.model_path if body.backend == "local" else None,
            "workspace_name": body.workspace_name if body.backend == "roboflow" else None,
            "workflow_id": body.workflow_id if body.backend == "roboflow" else None,
            "conf": body.conf,
            "class_conf": body.class_conf,
            "detected_count": len(dets),
            "created_at": datetime.now().isoformat(),
        })
    save_state()

    return {"detections": [d.to_dict() for d in dets]}


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


def _scan_models() -> list[str]:
    """Every .pt reachable for backend="local": top-level TOOL_DIR (pretrained convention, e.g.
    yolo11n.pt), MODELS_DIR (uploads), and runs/ (already-trained outputs from
    train_roboflow_yolo.py / experiment_tracking.py — surfaced automatically, no manual copying).
    Returned as relative-to-TOOL_DIR POSIX path strings, not bare names: once runs/ is included,
    multiple best.pt/last.pt share a filename across different run folders, so bare names would
    collide/be ambiguous. _resolve_model_path() already resolves values like this correctly."""
    paths = set(TOOL_DIR.glob("*.pt")) | set(MODELS_DIR.glob("*.pt")) | set((TOOL_DIR / "runs").rglob("*.pt"))
    return sorted(str(p.relative_to(TOOL_DIR)).replace("\\", "/") for p in paths)


@app.get("/api/models")
def list_models():
    return {"models": _scan_models()}


@app.post("/api/models")
def upload_model(file: UploadFile = File(...)):  # plain def: blocking writes belong on the threadpool
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

    suggested_total = sum(int(e.get("detected_count", 0)) for e in assist_log)

    accepted_total = sum(
        1
        for f in frames
        for d in f.get("detections", [])
        if d.get("source") == "model"
    )
    rate_pct = round(accepted_total / suggested_total * 100, 1) if suggested_total else 0.0

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
            "assist_call_count": len(assist_log),
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
    splits: SplitsIn = Field(default_factory=SplitsIn)
    preprocess: PreprocessIn = Field(default_factory=PreprocessIn)
    augment: AugmentIn = Field(default_factory=AugmentIn)


def _export_pool(detect_job_id: str, reviewed_only: bool) -> list[dict]:
    # The {**f} spread below copies each record, so the pool the export worker then spends minutes
    # writing to disk is a snapshot — annotations saved mid-export can't mutate it underneath.
    with _state_lock:
        job = _state["detect_jobs"].get(detect_job_id)
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
    return {**stats, "unreviewed": unreviewed, "class_count": len(CLASS_NAMES)}


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
