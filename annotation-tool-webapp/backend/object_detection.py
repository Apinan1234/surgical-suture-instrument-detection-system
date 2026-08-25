import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe

CONF_DEFAULT = 0.25
IOU_DEFAULT = 0.7
IMGSZ = 960  # ssid9_960px_150ep's own training resolution. Omitting imgsz would let
# ultralytics inherit the checkpoint's own trained value anyway (YOLO._load sets
# self.overrides = self.model.args) -- see 01_frame-extractor-tool/detector.py:340-381,
# which verified this box-for-box on ultralytics 8.4.114. This project pins 8.4.127, a
# different version, so the value is pinned explicitly here rather than trusted to keep
# being inherited silently. Getting this wrong specifically hurts needle/wound recall
# (0.36 -> 0.24 at 640 vs 960, per results_960/inference_benchmark.md).

# Fixed, deterministic BGR colors, indexed by class_id -- reproducible across runs,
# unlike yolo_wv/app/utils.py's fresh random.randint() palette per run. Material Design's
# "A400" accent tier (max-saturation, not the muted "500" tier this used to use) -- picked to
# stay legible/eye-catching against real suturing-pad video (skin tones, blue/green cloth,
# stainless-steel instrument glare), not just to look bright in isolation.
_PALETTE_BGR: list[tuple[int, int, int]] = [
    (255, 121, 41),   # 0 -- electric blue
    (118, 230, 0),    # 1 -- neon green
    (68, 23, 255),    # 2 -- vivid red
    (0, 214, 255),    # 3 -- bright yellow
    (249, 0, 213),    # 4 -- vivid purple/magenta
    (255, 229, 0),    # 5 -- bright cyan
    (0, 109, 255),    # 6 -- hot orange -- needle, the class that matters most to spot
    (87, 0, 245),     # 7 -- vivid pink
    (0, 255, 198),    # 8 -- lime
]


@dataclass
class Detection:
    class_name: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float


def _color_for(class_names: list[str], class_name: str) -> tuple[int, int, int]:
    idx = class_names.index(class_name)
    return _PALETTE_BGR[idx % len(_PALETTE_BGR)]


def detect(
    model, class_names: list[str], frame: np.ndarray,
    conf: float = CONF_DEFAULT, iou: float = IOU_DEFAULT,
) -> list[Detection]:
    results = model.predict(frame, conf=conf, iou=iou, imgsz=IMGSZ, verbose=False)
    if not results:
        return []
    data = results[0].boxes.cpu().numpy().data
    detections = []
    for x1, y1, x2, y2, score, class_id in data:
        detections.append(Detection(
            class_name=class_names[int(class_id)],
            conf=float(score),
            x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2),
        ))
    return detections


def draw_detections(frame: np.ndarray, detections: list[Detection], class_names: list[str]) -> None:
    """Mutates `frame` in place. Caller must pass a copy if the original must stay
    clean -- prefer detect_and_annotate() unless there's an unusual need."""
    for d in detections:
        x1, y1, x2, y2 = int(d.x1), int(d.y1), int(d.x2), int(d.y2)
        color = _color_for(class_names, d.class_name)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d.class_name}: {d.conf:.2f}"
        label_y = max(y1 - 10, 10)
        cv2.putText(frame, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def detect_and_annotate(
    model, class_names: list[str], clean_frame: np.ndarray,
    conf: float = CONF_DEFAULT, iou: float = IOU_DEFAULT,
) -> tuple[list[Detection], np.ndarray]:
    """detect() then draw on a fresh copy of clean_frame. Guarantees clean_frame is
    never mutated -- the safe default entry point for callers that also need the
    clean frame intact (live tracking crops, staged clean images)."""
    detections = detect(model, class_names, clean_frame, conf=conf, iou=iou)
    annotated = clean_frame.copy()
    draw_detections(annotated, detections, class_names)
    return detections, annotated


class ClassTracker:
    def __init__(self, class_names: list[str]):
        self.class_names = class_names
        self.counts: dict[str, int] = {}
        self.best: dict[str, tuple[float, np.ndarray]] = {}

    def update(self, clean_frame: np.ndarray, detections: list[Detection]) -> None:
        height, width = clean_frame.shape[:2]
        for d in detections:
            self.counts[d.class_name] = self.counts.get(d.class_name, 0) + 1

            prev = self.best.get(d.class_name)
            if prev is not None and prev[0] >= d.conf:
                continue

            x1 = max(int(d.x1), 0)
            y1 = max(int(d.y1), 0)
            x2 = min(int(d.x2), width)
            y2 = min(int(d.y2), height)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = clean_frame[y1:y2, x1:x2].copy()
            self.best[d.class_name] = (d.conf, crop)


def open_raw_writer(path: str | Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(str(path), fourcc, fps, (width, height), isColor=True)


def finalize_output_video(raw_path: str | Path, out_path: str | Path) -> Path:
    """Transcodes the mp4v-encoded raw_path to real H.264 (browser/Gradio playable),
    since OpenCV's own build cannot encode H.264 directly. Deletes raw_path on success."""
    raw_path = Path(raw_path)
    out_path = Path(out_path)
    try:
        subprocess.run(
            [
                get_ffmpeg_exe(), "-y", "-i", str(raw_path),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(out_path),
            ],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else e.stderr
        raise RuntimeError(f"ffmpeg transcode failed (exit {e.returncode}): {stderr}") from e
    raw_path.unlink()
    return out_path
