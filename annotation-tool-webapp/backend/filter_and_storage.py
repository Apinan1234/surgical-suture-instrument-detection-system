from pathlib import Path

import cv2
import numpy as np
from frame_miner.classes import class_id_for_name

from backend.object_detection import Detection


def _write_image(path: Path, image: np.ndarray) -> None:
    # cv2.imwrite() silently returns False (no exception) on non-ASCII Windows paths.
    # frame_miner.mine's own _write_image() avoids it the same way -- mirrored here.
    ok, buf = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError(f"Failed to encode image for {path}")
    path.write_bytes(buf.tobytes())


def stage_candidate(
    run_dir: str | Path,
    stem: str,
    clean_image: np.ndarray,
    annotated_image: np.ndarray,
    detections: list[Detection],
    class_names: list[str],
) -> set[int] | None:
    """Stages one candidate frame's clean image, boxed preview, and YOLO label file
    (all detected classes, not just a to-be-picked subset) into run_dir/staging/, in
    the exact images/labels/preview layout frame_miner.export.export_dataset()
    expects. Returns None (writes nothing) if detections is empty; otherwise the set
    of class-ids present, for the caller's in-memory manifest.
    """
    if not detections:
        return None

    run_dir = Path(run_dir)
    images_dir = run_dir / "staging" / "images"
    preview_dir = run_dir / "staging" / "preview"
    labels_dir = run_dir / "staging" / "labels"
    for d in (images_dir, preview_dir, labels_dir):
        d.mkdir(parents=True, exist_ok=True)

    _write_image(images_dir / f"{stem}.jpg", clean_image)
    _write_image(preview_dir / f"{stem}.jpg", annotated_image)

    height, width = clean_image.shape[:2]
    lines = []
    class_ids: set[int] = set()
    for d in detections:
        class_id = class_id_for_name(class_names, d.class_name)
        assert class_id is not None, (
            f"{d.class_name!r} not in class_names -- class_names must be the same "
            "native_order() list used to produce these detections"
        )
        class_ids.add(class_id)

        cx = ((d.x1 + d.x2) / 2) / width
        cy = ((d.y1 + d.y2) / 2) / height
        w = (d.x2 - d.x1) / width
        h = (d.y2 - d.y1) / height
        lines.append(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

    (labels_dir / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return class_ids
