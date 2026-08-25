"""FastAPI backend serving the real rare-class-labeler frontend (frontend/static/index.html).
Only file with web-framework code in the project; calls into backend.pipeline and
backend.model_loader only (never backend.dataset_export/object_detection/frame_extraction/
filter_and_storage directly). Replaces the earlier Gradio-based Phase 3 build wholesale."""

import asyncio
import base64
import logging
import os
import re
import threading
import time
from pathlib import Path

os.environ.setdefault("ULTRALYTICS_SAFE_LOAD", "1")

import cv2
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import model_loader, pipeline

# Gap #1's Windows large-file Range-request fix. asyncio.set_event_loop_policy(...) alone has NO
# effect on which loop uvicorn actually uses (verified empirically against the installed
# uvicorn==0.52.4): uvicorn's default loop="auto" resolves to a loop_factory that gets called
# directly, bypassing whatever policy is set. Only loop="none" (passed to uvicorn.run() below)
# makes it fall through to asyncio.new_event_loop(), which DOES honor this policy.
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rare_class_labeler")

# Eager warm-up: loads the model once at import time (not on the first user's video) so every
# run_pipeline() call's own internal load_model() call is a guaranteed cache hit via
# model_loader's module-level globals -- the "loading model" progress stage is genuinely
# near-instant on every run, including the first.
_, CLASS_NAMES = model_loader.load_model()

_removed = pipeline.sweep_stale_runs()
if _removed:
    logger.info("swept %d stale run dir(s) on startup", _removed)

# Relative to this repo, not a machine-specific absolute path. The file itself isn't tracked in
# git (see this folder's .gitignore) -- the Quickstart/"Examples" button already fails with a clear
# Thai message below when it's missing, rather than crashing, so this only works on a machine that
# has the file placed here locally.
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
WIN_VIDEO = EXAMPLES_DIR / "WIN_20260525_14_47_12_Pro_muted.mp4"
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

RARE_MAX_FRACTION = 0.3
RARE_BALANCE_GUARD = 0.5


def rare_classes(counts: dict[str, int]) -> set[str]:
    """Classes at or below RARE_MAX_FRACTION of this run's max count -- but only if the run
    isn't already roughly balanced (skip entirely when the min count is already within
    RARE_BALANCE_GUARD of the max). Data-driven from this run's own counts, never hardcoded to
    "needle" -- generalizes to whichever class is actually scarce in a given video."""
    if len(counts) <= 1:
        return set()
    max_count = max(counts.values())
    min_count = min(counts.values())
    if min_count > RARE_BALANCE_GUARD * max_count:
        return set()
    threshold = max(1, round(RARE_MAX_FRACTION * max_count))
    return {c for c, n in counts.items() if n <= threshold}


def _thumbnail_data_uri(crop_bgr) -> str | None:
    if crop_bgr is None:
        return None
    ok, buf = cv2.imencode(".jpg", crop_bgr)
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


# ---- job tracking: plain in-memory dict, one background thread per job. No lock -- each
# entry is written only by its own worker thread, reads are simple atomic dict lookups under
# the GIL, and entries are never deleted or iterated. See plan doc for the full justification. ----
JOBS: dict[str, dict] = {}
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")  # matches uuid.uuid4().hex exactly -- a path-traversal guard


class JobNotFoundError(Exception):
    pass


def _new_job_entry(video_name: str, source_path: Path) -> dict:
    return {
        "status": "processing",  # "processing" | "done" | "error"
        "frac": 0.0,
        "message": "กำลังเตรียมวิดีโอ...",
        "video_name": video_name,
        "source_path": source_path,
        "created_at": time.time(),
        "result": None,
        "error_message": None,
    }


def _run_job(job_id: str, video_path: Path) -> None:
    def on_frame(done, total):
        if done >= total:
            # Last per-frame callback -- writer.release() + the real ffmpeg transcode still
            # run inside run_pipeline() after this, with no further callbacks possible, so this
            # message honestly holds here for the real transcode duration.
            JOBS[job_id].update(frac=0.92, message="กำลังประกอบวิดีโอผลลัพธ์ (H.264)...")
        else:
            frac = 0.03 + 0.87 * (done / max(total, 1))
            JOBS[job_id].update(frac=frac, message=f"กำลังตรวจจับวัตถุ... เฟรม {done}/{total}")

    try:
        result = pipeline.run_pipeline(
            video_path, run_dir=pipeline.RUNS_ROOT / job_id, progress_callback=on_frame,
        )
    except pipeline.VideoTooLongError:
        JOBS[job_id].update(status="error", error_message=(
            f"วิดีโอยาวเกินไป — รองรับไม่เกิน {pipeline.MAX_VIDEO_SECONDS:.0f} วินาที "
            "เนื่องจากระบบต้องตรวจจับวัตถุทุกเฟรม กรุณาอัปโหลดวิดีโอที่สั้นกว่านี้"
        ))
        return
    except Exception:
        logger.exception("run_pipeline failed for %s", video_path)
        JOBS[job_id].update(status="error", error_message=(
            "เกิดข้อผิดพลาดขณะประมวลผลวิดีโอ กรุณาลองใหม่อีกครั้ง หรือใช้ไฟล์วิดีโออื่น"
        ))
        return
    JOBS[job_id].update(status="done", frac=1.0, message="เสร็จสิ้น", result=result)


def get_job(job_id: str) -> dict:
    """For routes that need the in-memory JOBS entry (/status, /result, /source, /export)."""
    if not JOB_ID_RE.match(job_id) or job_id not in JOBS:
        raise JobNotFoundError()
    return JOBS[job_id]


def run_dir_for(job_id: str) -> Path:
    """For the two disk-only, restart-resilient routes (/video, /export/download) -- validates
    only the id shape, not JOBS membership, so these keep working across a server restart."""
    if not JOB_ID_RE.match(job_id):
        raise JobNotFoundError()
    return pipeline.RUNS_ROOT / job_id


app = FastAPI()


@app.exception_handler(JobNotFoundError)
def _job_not_found(request, exc):
    return JSONResponse(status_code=404, content={
        "error_message": "ไม่พบงานนี้ — อาจถูกลบไปแล้ว หรือเซิร์ฟเวอร์เพิ่งรีสตาร์ท กรุณาอัปโหลดวิดีโอใหม่อีกครั้ง"
    })


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX_HTML, media_type="text/html")


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles sends Last-Modified/ETag but no Cache-Control -- browsers then apply their own
    heuristic freshness window and can silently keep serving a stale css/js file after an edit,
    with no request even reaching the server (confirmed happening during this project's own
    edit-and-refresh workflow). no-cache forces a conditional GET (cheap, still a 304 when
    unchanged) instead of a blind cache hit, so a saved edit always shows up on next refresh."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Plain website layout (index.html + css/ + js/) instead of one monolithic HTML file --
# StaticFiles is stdlib-to-FastAPI, no new dependency. Mounted narrowly under /css and /js
# (not at "/") so it can never shadow the /api/* routes above regardless of registration order.
app.mount("/css", NoCacheStaticFiles(directory=STATIC_DIR / "css"), name="css")
app.mount("/js", NoCacheStaticFiles(directory=STATIC_DIR / "js"), name="js")


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse(status_code=400, content={"error_message": "กรุณาเลือกไฟล์วิดีโอ"})
    run_dir = pipeline.new_run_dir()
    job_id = run_dir.name
    suffix = Path(file.filename).suffix or ".mp4"
    input_path = run_dir / f"input{suffix}"
    with input_path.open("wb") as f:
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    await file.close()
    JOBS[job_id] = _new_job_entry(file.filename, input_path)
    threading.Thread(target=_run_job, args=(job_id, input_path), daemon=True).start()
    return {"job_id": job_id, "video_name": file.filename}


@app.post("/api/jobs/example", status_code=202)
def create_example_job():
    if not WIN_VIDEO.exists():
        return JSONResponse(status_code=500, content={"error_message": "ไม่พบไฟล์ตัวอย่างในเครื่อง server"})
    run_dir = pipeline.new_run_dir()
    job_id = run_dir.name
    JOBS[job_id] = _new_job_entry(WIN_VIDEO.name, WIN_VIDEO)
    threading.Thread(target=_run_job, args=(job_id, WIN_VIDEO), daemon=True).start()
    return {"job_id": job_id, "video_name": WIN_VIDEO.name, "size_bytes": WIN_VIDEO.stat().st_size}


@app.get("/api/jobs/{job_id}/status")
def get_status(job_id: str):
    job = get_job(job_id)
    payload = {"status": job["status"], "frac": job["frac"], "message": job["message"]}
    if job["status"] == "error":
        payload["error_message"] = job["error_message"]
    return payload


@app.get("/api/jobs/{job_id}/result")
def get_result(job_id: str):
    job = get_job(job_id)
    if job["status"] == "error":
        return JSONResponse(status_code=500, content={"error_message": job["error_message"]})
    if job["status"] != "done":
        return JSONResponse(status_code=409, content={"error_message": "ยังประมวลผลไม่เสร็จ"})

    result: pipeline.RunResult = job["result"]
    rare = rare_classes(result.counts)
    classes = []
    for name in result.class_names:
        count = result.counts.get(name, 0)
        if count <= 0:
            continue
        best = result.best.get(name)
        classes.append({
            "name": name,
            "count": count,
            "is_rare": name in rare,
            "thumbnail": _thumbnail_data_uri(best[1] if best is not None else None),
        })
    return {
        "job_id": job_id,
        "video_name": job["video_name"],
        "output_video_url": f"/api/jobs/{job_id}/video",
        "total_detected": len(classes),
        "classes": classes,
    }


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    path = run_dir_for(job_id) / "output.mp4"
    if not path.exists():
        raise JobNotFoundError()
    return FileResponse(path, media_type="video/mp4")  # no filename= -> inline playback, Range-enabled


@app.get("/api/jobs/{job_id}/source")
def get_source(job_id: str):
    job = get_job(job_id)
    path = Path(job["source_path"])
    if not path.exists():
        raise JobNotFoundError()
    return FileResponse(path)


class ExportRequest(BaseModel):
    classes: list[str]


@app.post("/api/jobs/{job_id}/export")
def export_job(job_id: str, body: ExportRequest):
    job = get_job(job_id)
    if job["status"] != "done":
        return JSONResponse(status_code=409, content={"error_message": "ยังประมวลผลไม่เสร็จ"})
    if not body.classes:
        return JSONResponse(status_code=400, content={"error_message": "กรุณาเลือกอย่างน้อย 1 คลาสก่อนดาวน์โหลด"})

    result: pipeline.RunResult = job["result"]
    try:
        export_result = pipeline.export_picks(result, body.classes)
    except ValueError as e:
        # Covers dataset_export.EmptyExportError (a ValueError subclass) -- the genuine
        # detected-but-never-staged rare-frame scenario this product exists to surface.
        return JSONResponse(status_code=422, content={"error_message": f"ไม่สามารถสร้างชุดข้อมูลได้: {e}"})
    except Exception:
        logger.exception("export_picks failed for job %s", job_id)
        return JSONResponse(status_code=500, content={
            "error_message": "เกิดข้อผิดพลาดขณะสร้างไฟล์ดาวน์โหลด กรุณาลองใหม่อีกครั้ง"
        })
    return {
        "download_url": f"/api/jobs/{job_id}/export/download",
        "labeled_classes": export_result.labeled_classes,
        "unlabeled_detected_classes": export_result.unlabeled_detected_classes,
    }


@app.get("/api/jobs/{job_id}/export/download")
def download_export(job_id: str):
    path = run_dir_for(job_id) / "export.zip"
    if not path.exists():
        raise JobNotFoundError()
    return FileResponse(path, media_type="application/zip", filename="rare_class_export.zip")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7860, loop="none")
