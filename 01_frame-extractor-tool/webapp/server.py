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
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

WEBAPP_DIR = Path(__file__).resolve().parent
TOOL_DIR = WEBAPP_DIR.parent
sys.path.insert(0, str(TOOL_DIR))
from frame_extractor import extract_frames  # noqa: E402  (needs sys.path set up first)
from detector import Detection, BaseDetector, YOLOv11Detector, RoboflowDetector, CLASS_NAMES, CLASS_COLORS_HEX  # noqa: E402
from dataset_exporter import export_dataset_pipeline, count_stats  # noqa: E402

load_dotenv(WEBAPP_DIR / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR", WEBAPP_DIR / "data")).resolve()
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "8192"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_TOTAL_UPLOAD_MB = int(os.environ.get("MAX_TOTAL_UPLOAD_MB", "51200"))
MAX_TOTAL_UPLOAD_BYTES = MAX_TOTAL_UPLOAD_MB * 1024 * 1024
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
MAX_FRAMES_ALL_MODE = int(os.environ.get("MAX_FRAMES_ALL_MODE", "20000"))

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

_state_lock = threading.Lock()
_state: dict = {"videos": {}, "extract_jobs": {}, "frames": {}, "detect_jobs": {}, "export_jobs": {}, "assist_log": []}
_last_snapshot_time = 0.0


def load_state():
    global _state
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            _state = json.load(f)
    for key in ("videos", "extract_jobs", "frames", "detect_jobs", "export_jobs"):
        _state.setdefault(key, {})
    _state.setdefault("assist_log", [])


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


# ────────────────────────────── S-2 Videos ──────────────────────────────


@app.post("/api/videos")
async def upload_videos(files: list[UploadFile] = File(...)):
    uploaded = []
    current_total = sum(v.get("size_bytes", 0) for v in _state["videos"].values())
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
    return {"videos": [_public(r) for r in _state["videos"].values()]}


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
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
    """Admission control for extract_jobs/detect_jobs — caps how many run at once
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
                job["log"].append(msg)
                if len(job["log"]) > 500:
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
                for img_path in sorted(out_dir.iterdir()):
                    if img_path.suffix.lower() not in IMAGE_EXTS:
                        continue
                    frame_id = uuid.uuid4().hex
                    _state["frames"][frame_id] = {
                        "id": frame_id,
                        "video_id": video_id,
                        "job_id": job_id,
                        "path": str(img_path),
                        "filename": img_path.name,
                        "reviewed": False,
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


@app.get("/api/extract/{job_id}")
def extract_status(job_id: str):
    job = _state["extract_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/extract/{job_id}/frames")
def extract_frames_list(job_id: str):
    job = _state["extract_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    frames = [_state["frames"][fid] for fid in job.get("frame_ids", []) if fid in _state["frames"]]
    return {"frames": [_public(f) for f in frames]}


@app.post("/api/extract/{job_id}/stop")
def stop_extract(job_id: str):
    if job_id not in _state["extract_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


@app.get("/api/extract/{job_id}/zip")
def download_zip(job_id: str):
    job = _state["extract_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dir = FRAMES_DIR / job_id
    frames = [_state["frames"][fid] for fid in job.get("frame_ids", []) if fid in _state["frames"]]
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
    api_key: str | None = None
    workspace_name: str = "fhasai-khuanpan"
    workflow_id: str = "ssid-v5-logic"

    @model_validator(mode="after")
    def _check_backend(self):
        if self.backend == "roboflow" and not (self.api_key or "").strip():
            raise ValueError("api_key is required when backend=roboflow")
        return self


class DetectBody(DetectorConfigBody):
    frame_ids: list[str]
    skip_reviewed: bool = True


PRETRAINED_MODEL_PREFIXES = ("yolo", "rtdetr")


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
        )
    raw_model_path = body.model_path.strip()
    return YOLOv11Detector(
        model_path=_resolve_model_path(raw_model_path) or raw_model_path,
        conf=body.conf,
        iou=body.iou,
        device=body.device,
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
    if body.backend == "roboflow":
        key = ("roboflow", body.workspace_name.strip(), body.workflow_id.strip(), round(body.conf, 4))
    else:
        key = ("local", body.model_path.strip(), round(body.conf, 4), round(body.iou, 4), body.device)
    with _detector_cache_lock:
        if key != _detector_cache_key:
            _detector_cache_detector = build_detector(body)
            _detector_cache_key = key
        return _detector_cache_detector


def _run_detect_job(job_id: str, body: DetectBody):
    job = _state["detect_jobs"][job_id]
    detected_total = 0

    try:
        det = _get_cached_detector(body)
    except Exception as e:
        job["log"].append(f"[error] failed to load detector: {e}")
        job["status"] = "stopped"
        _job_stop_flags.pop(job_id, None)
        save_state()
        return

    total = len(body.frame_ids)
    for idx, frame_id in enumerate(body.frame_ids):
        if _job_stop_flags.get(job_id):
            break

        record = _state["frames"].get(frame_id)
        if not record:
            job["log"].append(f"[error] unknown frame id {frame_id}")
            continue

        if body.skip_reviewed and record.get("reviewed"):
            job["log"].append(f"[skip] {Path(record['path']).name}: already reviewed (skip_reviewed=true)")
            job["progress"] = round((idx + 1) / total * 100, 1) if total else 100
            if len(job["log"]) > 500:
                del job["log"][: len(job["log"]) - 500]
            continue

        try:
            img = cv2.imread(record["path"])
            if img is None:
                job["log"].append(f"[error] cannot read {record['path']}")
                continue
            dets = det.predict(img)
            record["detections"] = [d.to_dict() for d in dets]  # Detection.source defaults to "model"
            if record.get("reviewed"):
                # Only reachable with the explicit skip_reviewed=false override — fresh unconfirmed
                # model output shouldn't silently keep inheriting the frame's prior review status.
                record["reviewed"] = False
            if dets:
                detected_total += 1
            job["log"].append(f"[{'detected' if dets else 'empty'}] {Path(record['path']).name}: {len(dets)} obj")
        except Exception as e:
            job["log"].append(f"[error] {record['path']}: {e}")

        job["progress"] = round((idx + 1) / total * 100, 1) if total else 100
        if len(job["log"]) > 500:
            del job["log"][: len(job["log"]) - 500]

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
    job = _state["detect_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/detect/{job_id}/frames")
def detect_frames_list(job_id: str):
    job = _state["detect_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    frames = [_state["frames"][fid] for fid in job.get("frame_ids", []) if fid in _state["frames"]]
    return {"frames": [_public(f) for f in frames]}


@app.post("/api/detect/{job_id}/stop")
def stop_detect(job_id: str):
    if job_id not in _state["detect_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


def _get_frame_or_404(frame_id: str) -> dict:
    record = _state["frames"].get(frame_id)
    if not record:
        raise HTTPException(status_code=404, detail="Frame not found")
    return record


@app.get("/api/frames/{frame_id}/preview.jpg")
def frame_preview(frame_id: str):
    record = _get_frame_or_404(frame_id)

    img = cv2.imread(record["path"])
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    dets = [Detection(**d) for d in record.get("detections", [])]
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
    source: Literal["model", "manual"] = "manual"
    points: list[list[float]] | None = None
    keypoints: list[list[float]] | None = None

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


@app.get("/api/frames/{frame_id}/detections")
def get_frame_detections(frame_id: str):
    record = _get_frame_or_404(frame_id)
    return {"frame_id": frame_id, "detections": record.get("detections", [])}


@app.put("/api/frames/{frame_id}/detections")
def replace_frame_detections(frame_id: str, body: FrameDetectionsBody):
    record = _get_frame_or_404(frame_id)
    record["detections"] = [Detection(**d.model_dump()).to_dict() for d in body.detections]
    save_state()
    return {"frame_id": frame_id, "detections": record["detections"]}


class ReviewBody(BaseModel):
    reviewed: bool = True


@app.post("/api/frames/{frame_id}/review")
def mark_frame_reviewed(frame_id: str, body: ReviewBody = ReviewBody()):
    record = _get_frame_or_404(frame_id)
    record["reviewed"] = body.reviewed
    save_state()
    return {"frame_id": frame_id, "reviewed": record["reviewed"]}


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
    record = _get_frame_or_404(frame_id)

    try:
        _validate_detect_backend(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    img = cv2.imread(record["path"])
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    try:
        det = _get_cached_detector(body)
        dets = det.predict(img)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Assist failed: {e}")

    _state["assist_log"].append({
        "frame_id": frame_id,
        "backend": body.backend,
        "model_path": body.model_path if body.backend == "local" else None,
        "workspace_name": body.workspace_name if body.backend == "roboflow" else None,
        "workflow_id": body.workflow_id if body.backend == "roboflow" else None,
        "conf": body.conf,
        "detected_count": len(dets),
        "created_at": datetime.now().isoformat(),
    })
    save_state()

    return {"detections": [d.to_dict() for d in dets]}


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
async def upload_model(file: UploadFile = File(...)):
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
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE_BYTES:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)

    relative_path = str(dest_path.relative_to(TOOL_DIR)).replace("\\", "/")
    return {"uploaded": relative_path, "models": _scan_models()}


@app.get("/api/classes")
def list_classes():
    return {"class_names": CLASS_NAMES, "class_colors": CLASS_COLORS_HEX}


# ────────────────────────────── Analytics ──────────────────────────────


@app.get("/api/analytics")
def analytics():
    assist_log = _state.get("assist_log", [])
    suggested_total = sum(int(e.get("detected_count", 0)) for e in assist_log)

    frames = list(_state["frames"].values())
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
        for job in _state["detect_jobs"].values()
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
        job["zip_path"] = zip_path
        summary_path = out_dir / "export_summary.json"
        if summary_path.exists():
            job["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        job["status"] = "done"
        job["progress"] = 100
    except Exception as e:
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

    job_id = uuid.uuid4().hex
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
    threading.Thread(target=_run_export_job, args=(job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/export/{job_id}")
def export_status(job_id: str):
    job = _state["export_jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
