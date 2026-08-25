"""Core mining pipeline: sample frames from a source, run detection, stage matches.

This module has no argparse/CLI knowledge -- it's what both cli.py and any future UI
call directly.
"""
import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from frame_miner.classes import class_id_for_name, resolve_class_list
from frame_miner.detect import Detection, load_model, run_inference
from frame_miner.preview import draw_preview
from frame_miner.source import iter_source

logger = logging.getLogger(__name__)

MANIFEST_FIELDS = ["stem", "source", "frame_index", "timestamp_sec", "target_classes_matched", "n_detections"]


@dataclass
class MineSummary:
    candidates_seen: int
    frames_staged: int
    staging_dir: Path


def _write_image(path: Path, image: np.ndarray) -> None:
    ok, buf = cv2.imencode(".jpg", image)
    if not ok:
        raise IOError(f"failed to encode image for {path}")
    buf.tofile(str(path))


def _write_label(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def detections_to_label_lines(
    detections: list[Detection],
    class_list: list[str],
    img_w: int,
    img_h: int,
    frame_stem: str = "",
    class_list_path: str = "",
) -> list[str]:
    """Remap every detection's native class *name* to its id in `class_list` (never the
    checkpoint's own native class index -- see classes.py) and format as YOLO label lines.
    Pulled out of mine_source() so this -- the one correctness-critical step -- is testable
    without a real model.
    """
    lines = []
    for d in detections:
        class_id = class_id_for_name(class_list, d.class_name)
        if class_id is None:
            logger.warning(
                "class %r (frame %s) not in class list %s -- dropped from label output",
                d.class_name, frame_stem, class_list_path,
            )
            continue
        x, y, w, h = d.normalized_xywh(img_w, img_h)
        lines.append(f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
    return lines


def mine_source(
    source_path: str,
    model_path: str,
    target_classes: list[str],
    out_dir: str,
    class_list_path: str | None = None,
    conf: float = 0.25,
    iou: float = 0.45,
    interval_sec: float = 1.0,
    device: str = "cpu",
    progress_callback: Callable[[int, int], None] | None = None,
) -> MineSummary:
    """`class_list_path` is optional: if given, detections are remapped by name onto that
    pinned list (for merging into a specific existing dataset); if omitted, the loaded
    model's own native class order is used instead ("auto" mode). Either way the class
    order actually used is written to `<out_dir>/classes_used.txt`, and a second `mine`
    call into the same `out_dir` with a different model/class order raises rather than
    silently mixing two id schemes in one staging directory -- see resolve_class_list().

    `progress_callback(candidates_seen, frames_staged)`, if given, is called once per
    candidate frame. No progress-bar library dependency lives here (e.g. no tqdm/gradio
    import) -- a caller like the web UI wires this to its own progress widget.
    """
    target_set = set(target_classes)

    out = Path(out_dir)
    images_dir = out / "images"
    labels_dir = out / "labels"
    preview_dir = out / "preview"
    for d in (images_dir, labels_dir, preview_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = out / "manifest.csv"
    manifest_is_new = not manifest_path.exists()

    model = load_model(model_path, device=device)
    class_list = resolve_class_list(out, class_list_path, model.names)
    classes_used_path = out / "classes_used.txt"

    candidates_seen = 0
    frames_staged = 0

    with open(manifest_path, "a", newline="", encoding="utf-8") as mf:
        writer = csv.DictWriter(mf, fieldnames=MANIFEST_FIELDS)
        if manifest_is_new:
            writer.writeheader()

        for frame in iter_source(source_path, interval_sec):
            candidates_seen += 1
            detections = run_inference(model, frame.image, conf=conf, iou=iou, device=device)

            matched = {d.class_name for d in detections} & target_set
            if not matched:
                if progress_callback is not None:
                    progress_callback(candidates_seen, frames_staged)
                continue

            img_h, img_w = frame.image.shape[:2]
            label_lines = detections_to_label_lines(
                detections, class_list, img_w, img_h, frame_stem=frame.stem, class_list_path=str(classes_used_path),
            )

            _write_image(images_dir / f"{frame.stem}.jpg", frame.image)
            _write_label(labels_dir / f"{frame.stem}.txt", label_lines)
            _write_image(preview_dir / f"{frame.stem}.jpg", draw_preview(frame.image, detections, target_set))

            writer.writerow({
                "stem": frame.stem,
                "source": str(source_path),
                "frame_index": frame.index,
                "timestamp_sec": "" if frame.timestamp_sec is None else f"{frame.timestamp_sec:.3f}",
                "target_classes_matched": "|".join(sorted(matched)),
                "n_detections": len(label_lines),
            })
            frames_staged += 1

            if progress_callback is not None:
                progress_callback(candidates_seen, frames_staged)

    return MineSummary(candidates_seen=candidates_seen, frames_staged=frames_staged, staging_dir=out)
