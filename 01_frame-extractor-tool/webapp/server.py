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
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

WEBAPP_DIR = Path(__file__).resolve().parent
TOOL_DIR = WEBAPP_DIR.parent
sys.path.insert(0, str(TOOL_DIR))
from frame_extractor import extract_frames  # noqa: E402  (needs sys.path set up first)
from detector import Detection, BaseDetector, YOLOv11Detector, RoboflowDetector, CLASS_NAMES, CLASS_COLORS_HEX  # noqa: E402

load_dotenv(WEBAPP_DIR / ".env")

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

SNAPSHOT_INTERVAL_SEC = 15 * 60
SNAPSHOT_KEEP = 10

# ────────────────────────────── State (S-0) ──────────────────────────────

_state_lock = threading.Lock()
_state: dict = {"videos": {}, "extract_jobs": {}, "frames": {}, "detect_jobs": {}}
_last_snapshot_time = 0.0


def load_state():
    global _state
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            _state = json.load(f)
    for key in ("videos", "extract_jobs", "frames", "detect_jobs"):
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


# ────────────────────────────── S-2 Videos ──────────────────────────────


@app.post("/api/videos")
async def upload_videos(files: list[UploadFile] = File(...)):
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
def list_videos():
    return {"videos": list(_state["videos"].values())}


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
def start_extract(body: ExtractBody):
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
    return {"frames": frames}


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


class DetectBody(BaseModel):
    frame_ids: list[str]
    backend: Literal["local", "roboflow"] = "local"
    model_path: str = "yolo11n.pt"
    conf: float = Field(default=0.25, ge=0.01, le=0.99)
    iou: float = Field(default=0.45, ge=0.01, le=0.99)
    device: Literal["cpu", "cuda", "mps"] = "cpu"
    # TODO(Annotate): add skip_reviewed: bool = True here + filter logic once frames can be reviewed=true
    api_key: str | None = None
    workspace_name: str = "fhasai-khuanpan"
    workflow_id: str = "ssid-v5-logic"

    @model_validator(mode="after")
    def _check_backend(self):
        if self.backend == "roboflow" and not (self.api_key or "").strip():
            raise ValueError("api_key is required when backend=roboflow")
        return self


PRETRAINED_MODEL_PREFIXES = ("yolo", "rtdetr")


def _resolve_model_path(model_path: str) -> str:
    p = Path(model_path)
    if p.is_absolute() and p.exists():
        return str(p)
    candidate = TOOL_DIR / p
    return str(candidate) if candidate.exists() else model_path


def _validate_detect_backend(body: DetectBody):
    if body.backend == "roboflow":
        if not (body.api_key or "").strip():
            raise ValueError("api_key is required when backend=roboflow")
        return
    resolved = _resolve_model_path(body.model_path.strip())
    is_known_pretrained = body.model_path.startswith(PRETRAINED_MODEL_PREFIXES) and body.model_path.endswith(".pt")
    if not Path(resolved).exists() and not is_known_pretrained:
        raise ValueError(f"Model not found: {body.model_path}")


def build_detector(body: DetectBody):
    """Expensive (loads weights / imports ultralytics or inference_sdk) — call only from a worker thread."""
    if body.backend == "roboflow":
        return RoboflowDetector(
            api_key=body.api_key.strip(),
            workspace_name=body.workspace_name.strip(),
            workflow_id=body.workflow_id.strip(),
            conf=body.conf,
        )
    return YOLOv11Detector(
        model_path=_resolve_model_path(body.model_path.strip()),
        conf=body.conf,
        iou=body.iou,
        device=body.device,
    )


def _run_detect_job(job_id: str, body: DetectBody):
    job = _state["detect_jobs"][job_id]
    detected_total = 0

    try:
        det = build_detector(body)
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

        try:
            img = cv2.imread(record["path"])
            if img is None:
                job["log"].append(f"[error] cannot read {record['path']}")
                continue
            dets = det.predict(img)
            # กล่องที่เก็บที่นี่ทั้งหมดมาจากโมเดล — ถ้า Annotate ต้องแยก manual/model
            # ในอนาคต ให้ wrap เป็น {**d, "source": ...} ตอน PUT /api/frames/{id}/detections แทน
            record["detections"] = [d.to_dict() for d in dets]
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
        "conf": body.conf,
        "iou": body.iou,
        "device": body.device,
    }
    _job_stop_flags[job_id] = False
    threading.Thread(target=_run_detect_job, args=(job_id, body), daemon=True).start()
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
    return {"frames": frames}


@app.post("/api/detect/{job_id}/stop")
def stop_detect(job_id: str):
    if job_id not in _state["detect_jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    _job_stop_flags[job_id] = True
    return {"stopping": True}


@app.get("/api/frames/{frame_id}/preview.jpg")
def frame_preview(frame_id: str):
    record = _state["frames"].get(frame_id)
    if not record:
        raise HTTPException(status_code=404, detail="Frame not found")

    img = cv2.imread(record["path"])
    if img is None:
        raise HTTPException(status_code=404, detail="Frame image missing on disk")

    dets = [Detection(**d) for d in record.get("detections", [])]
    boxed = BaseDetector().draw_boxes(img, dets) if dets else img

    ok, buf = cv2.imencode(".jpg", boxed)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode image")

    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/jpeg")


@app.get("/api/models")
def list_models():
    return {"models": sorted(p.name for p in TOOL_DIR.glob("*.pt"))}


@app.get("/api/classes")
def list_classes():
    return {"class_names": CLASS_NAMES, "class_colors": CLASS_COLORS_HEX}


# ────────────────────────────── Static files (must be mounted last) ──────────────────────────────

app.mount("/", StaticFiles(directory=str(WEBAPP_DIR / "static"), html=True), name="static")
