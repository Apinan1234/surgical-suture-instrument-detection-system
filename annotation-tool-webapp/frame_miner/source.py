"""Frame sources: a video file, sampled by time interval, or a folder of already-extracted
frame images, read exhaustively.

Thai/non-ASCII path handling: cv2.VideoCapture opens non-ASCII video paths fine on Windows,
but cv2.imread silently returns None on them -- so frame-folder images are decoded via
np.fromfile + cv2.imdecode instead, never cv2.imread.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass
class SourceFrame:
    index: int  # source frame index (video) or sorted ordinal position (folder)
    image: np.ndarray
    stem: str  # unique-within-source identifier used to key staged filenames
    timestamp_sec: float | None  # None for a frame-folder source


def iter_video_frames(path: str | Path, interval_sec: float) -> Iterator[SourceFrame]:
    path = Path(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"could not open video: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_step = max(1, int(fps * interval_sec))
    video_stem = path.stem

    try:
        i = 0
        while True:
            if i % frame_step == 0:
                ret, frame = cap.read()
                if not ret:
                    break
                yield SourceFrame(
                    index=i,
                    image=frame,
                    stem=f"{video_stem}_f{i:07d}",
                    timestamp_sec=i / fps,
                )
            else:
                ret = cap.grab()
                if not ret:
                    break
            i += 1
            if n_frames and i >= n_frames:
                break
    finally:
        cap.release()


def iter_frame_folder(path: str | Path) -> Iterator[SourceFrame]:
    path = Path(path)
    files = sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)

    for i, fp in enumerate(files):
        data = np.fromfile(str(fp), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            continue
        yield SourceFrame(index=i, image=image, stem=fp.stem, timestamp_sec=None)


def iter_source(path: str | Path, interval_sec: float) -> Iterator[SourceFrame]:
    path = Path(path)
    if path.is_dir():
        yield from iter_frame_folder(path)
    else:
        yield from iter_video_frames(path, interval_sec)
