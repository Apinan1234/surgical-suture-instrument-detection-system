"""Burn boxes+labels into a *copy* of a frame, for human review only.

The preview image is never read by export.py -- it exists purely to drive the
delete-to-reject review workflow (see review.py).
"""
import cv2
import numpy as np

from frame_miner.detect import Detection

TARGET_COLOR = (0, 0, 255)  # BGR red -- the class(es) that made this frame get staged
OTHER_COLOR = (255, 128, 0)  # BGR blue -- everything else detected on the frame


def draw_preview(image: np.ndarray, detections: list[Detection], target_classes: set[str]) -> np.ndarray:
    preview = image.copy()
    for d in detections:
        color = TARGET_COLOR if d.class_name in target_classes else OTHER_COLOR
        x1, y1, x2, y2 = int(d.x1), int(d.y1), int(d.x2), int(d.y2)
        cv2.rectangle(preview, (x1, y1), (x2, y2), color, 2)
        label = f"{d.class_name}: {d.confidence:.2f}"
        cv2.putText(preview, label, (x1, max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return preview
