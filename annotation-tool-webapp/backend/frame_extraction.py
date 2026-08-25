from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

DEFAULT_INTERVAL_SEC = 1.0  # matches frame_miner's own default (web/app.py) — one candidate
# frame per second of video; a plain constant, safe to retune later without a redesign


@dataclass
class VideoMeta:
    fps: float
    n_frames: int
    width: int
    height: int
    frame_step: int  # max(1, int(fps * interval_sec)) -- same formula as frame_miner.source


@dataclass
class ExtractedFrame:
    index: int
    image: np.ndarray  # BGR, from cv2.VideoCapture.read()
    timestamp_sec: float
    is_candidate: bool  # True when index % frame_step == 0


def open_frame_source(
    path: str | Path, interval_sec: float = DEFAULT_INTERVAL_SEC
) -> tuple[VideoMeta, Iterator[ExtractedFrame]]:
    """
    One full decode pass over the video, single cv2.VideoCapture open. Does NOT call
    frame_miner.source.iter_video_frames() — that function grab()-skips (no decode) frames
    outside the sample interval, which is incompatible with needing every frame decoded here
    for the annotated output video (Phase 6). Reuses only its frame_step formula, for sampling
    consistency with the rest of the workspace.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_step = max(1, int(fps * interval_sec))
    meta = VideoMeta(fps=fps, n_frames=n_frames, width=width, height=height, frame_step=frame_step)

    def _frames() -> Iterator[ExtractedFrame]:
        try:
            i = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                yield ExtractedFrame(
                    index=i,
                    image=frame,
                    timestamp_sec=i / fps,
                    is_candidate=(i % frame_step == 0),
                )
                i += 1
        finally:
            cap.release()

    return meta, _frames()
