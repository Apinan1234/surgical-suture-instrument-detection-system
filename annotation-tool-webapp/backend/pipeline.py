"""Wires Phases 4-6 (model, frame extraction, detection/filter/export) into the two
calls Frontend needs: run_pipeline() for the automatic detect+stage pass,
export_picks() for the class-pick download. No gradio import here -- progress-callback
adaptation and gr.Error translation are Phase 3's job, matching frame_miner/mine.py's
own separation from web/app.py."""

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from backend import filter_and_storage, frame_extraction, model_loader, object_detection
from backend.dataset_export import RunExportResult, export_run

RUNS_ROOT = Path(__file__).resolve().parent.parent / "runs"  # project-root-relative,
# matching Phase 6 verification's own runs/phase6_verify* precedent, not system temp.
STALE_AFTER_SECONDS = 6 * 3600  # startup-sweep backstop, mirrors web/sessions.py

MAX_VIDEO_SECONDS = 180  # ~3 min upload cap. Reasoning (measured this session):
# Phase 6's verification video was 2726 frames at ~182ms/frame full-inference cost =
# ~495s processing for a video whose own duration (2726 frames / its fps) was ~90s --
# a ~5.4x realtime ratio. A 180s upload would take ~16 min to process. Tune this
# constant directly if that tradeoff needs to change; kept as a plain module constant,
# not derived dynamically, since the ms/frame cost is roughly fixed for this one
# bundled model/imgsz on CPU.


class VideoTooLongError(ValueError):
    """Raised by run_pipeline() before any inference starts. A ValueError subclass,
    matching dataset_export.EmptyExportError's pattern, so Phase 3 can catch a plain
    ValueError if it doesn't care about the distinction, or this specific type if it
    wants a tailored message."""


@dataclass
class RunResult:
    """Everything Phase 3 needs after the automatic detect+stage pass. Holds only what
    the results-grid UI and a later export_picks() call require -- not VideoMeta, not
    the original video_path (Frontend already has it from the upload widget), not
    frame/candidate counts (the last progress_callback call already told Frontend
    n_frames if it needs to display it)."""
    run_dir: Path
    class_names: list[str]
    output_video_path: Path
    counts: dict[str, int]
    best: dict[str, tuple[float, np.ndarray]]  # class_name -> (confidence, BGR crop),
    # passed through from ClassTracker.best as-is
    manifest: dict[str, set[int]]


def new_run_dir() -> Path:
    run_dir = RUNS_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def cleanup_run(run_dir: str | Path) -> None:
    """Best-effort delete. Caller's responsibility to only call this once the run's
    zip (which lives INSIDE run_dir -- see export_run()) has already been served/
    downloaded; never call this immediately after export_picks() returns."""
    shutil.rmtree(run_dir, ignore_errors=True)


def sweep_stale_runs(now: float | None = None) -> int:
    """Startup backstop for orphaned run_dirs (crashed process, closed tab before an
    explicit cleanup_run()). Not called from within this module -- Phase 3 calls it
    once at its own import time, same placement as sweep_stale_sessions() in
    yolo-frame-miner/web/app.py. Returns the count removed, for a log line."""
    if not RUNS_ROOT.exists():
        return 0
    now = time.time() if now is None else now
    removed = 0
    for entry in RUNS_ROOT.iterdir():
        if entry.is_dir() and now - entry.stat().st_mtime > STALE_AFTER_SECONDS:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed


def run_pipeline(
    video_path: str | Path,
    run_dir: str | Path | None = None,
    interval_sec: float = frame_extraction.DEFAULT_INTERVAL_SEC,
    max_video_seconds: float = MAX_VIDEO_SECONDS,
    progress_callback: Callable[[int, int], None] | None = None,
) -> RunResult:
    """Full automatic pass: reject videos over max_video_seconds up front (before
    loading the model or allocating a run_dir), then load the bundled model, decode
    every frame, detect+annotate with the fixed conf=0.25/iou=0.7 defaults (cut from
    the product entirely -- not exposed as parameters here), write the annotated
    output video, track live per-class counts/best crops, and stage every
    interval-sampled candidate frame with detections.

    `run_dir`: normally left None (allocates a fresh one via new_run_dir()); exposed
    for test harnesses that want a predictable, inspectable path, as Phase 6's own
    verification did.
    `max_video_seconds`: overridable per-call so Phase 7 tests can exercise the
    rejection path with a short synthetic video instead of monkeypatching a module
    constant or needing a real 3-minute file.
    `progress_callback(frames_done, n_frames)` is called once per decoded frame (every
    frame, not just candidates -- unlike frame_miner.mine_source, every frame gets
    inference here because the output video needs every frame boxed). No throttling:
    call rate is bounded by inference speed itself (~182ms/frame CPU => ~5-6 calls/sec),
    not chatty enough to need one.
    """
    meta, frames = frame_extraction.open_frame_source(video_path, interval_sec=interval_sec)
    duration_sec = meta.n_frames / meta.fps
    if duration_sec > max_video_seconds:
        frames.close()  # force the generator's `finally` to release cv2.VideoCapture
        # now rather than whenever GC gets to it -- we're not going to iterate it.
        raise VideoTooLongError(
            f"Video is {duration_sec:.0f}s -- this tool caps uploads at "
            f"{max_video_seconds:.0f}s because every frame gets a full inference pass "
            f"(~182ms/frame measured on CPU)."
        )

    model, class_names = model_loader.load_model()
    run_dir = Path(run_dir) if run_dir is not None else new_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)  # new_run_dir() already does this, but an
    # explicit run_dir passed by a caller (e.g. a test harness) might not exist yet --
    # cv2.VideoWriter fails silently (no exception, just a no-op writer) if the parent
    # directory is missing, which would otherwise surface only much later as a
    # confusing ffmpeg "no such file" error in finalize_output_video().

    raw_path = run_dir / "output_raw.mp4"
    out_path = run_dir / "output.mp4"
    writer = object_detection.open_raw_writer(raw_path, meta.fps, meta.width, meta.height)
    tracker = object_detection.ClassTracker(class_names)
    manifest: dict[str, set[int]] = {}

    try:
        for ef in frames:
            detections, annotated = object_detection.detect_and_annotate(model, class_names, ef.image)
            writer.write(annotated)
            tracker.update(ef.image, detections)
            if ef.is_candidate:
                stem = f"frame_{ef.index:06d}"
                class_ids = filter_and_storage.stage_candidate(
                    run_dir, stem, ef.image, annotated, detections, class_names,
                )
                if class_ids is not None:
                    manifest[stem] = class_ids
            if progress_callback is not None:
                progress_callback(ef.index + 1, meta.n_frames)
    finally:
        # Guarantee the OS file handle is released even if inference raises mid-loop --
        # cv2.VideoWriter holds the file open until release() is called explicitly;
        # without this a raised exception leaves a locked/corrupt raw_path on Windows.
        # The exception itself is never caught here -- it propagates raw to Phase 3,
        # same as frame_miner's web layer having no try/except around mine_source().
        writer.release()

    output_video_path = object_detection.finalize_output_video(raw_path, out_path)

    return RunResult(
        run_dir=run_dir,
        class_names=class_names,
        output_video_path=output_video_path,
        counts=tracker.counts,
        best=tracker.best,
        manifest=manifest,
    )


def export_picks(
    run_result: RunResult,
    picked_classes: list[str],
    out_dir: str | Path | None = None,
    train: float = 0.8,
    val: float = 0.2,
    test: float = 0.0,
) -> RunExportResult:
    """Thin wrapper so Phase 3 only ever imports backend.pipeline, never reaches into
    dataset_export directly. `out_dir` defaults to a scratch subdirectory of the run;
    the artifact Phase 3 actually serves via gr.File is result.zip_path, which
    export_run() always places at run_dir/export.zip regardless of out_dir."""
    if out_dir is None:
        out_dir = run_result.run_dir / "export_staged"
    return export_run(
        run_result.run_dir, run_result.class_names, picked_classes,
        run_result.manifest, out_dir, train=train, val=val, test=test,
    )
