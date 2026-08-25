"""Thin wrapper around an ultralytics YOLO checkpoint.

Detections carry the class name (from the checkpoint's own model.names) rather than its
native numeric id -- callers must remap by name through an explicit class list (see
classes.py) before writing anything to disk. Never trust a checkpoint's own class index;
see README for why.
"""
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO


@dataclass
class Detection:
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    def normalized_xywh(self, img_w: int, img_h: int) -> tuple[float, float, float, float]:
        x_center = (self.x1 + self.x2) / 2 / img_w
        y_center = (self.y1 + self.y2) / 2 / img_h
        width = (self.x2 - self.x1) / img_w
        height = (self.y2 - self.y1) / img_h
        return x_center, y_center, width, height


def load_model(model_path: str, device: str = "cpu") -> YOLO:
    return YOLO(model_path)


def run_inference(model: YOLO, image: np.ndarray, conf: float, iou: float, device: str = "cpu") -> list[Detection]:
    results = model.predict(image, conf=conf, iou=iou, device=device, verbose=False)
    if not results:
        return []

    names = model.names
    boxes = results[0].boxes.cpu().numpy().data
    detections = []
    for box in boxes:
        x1, y1, x2, y2, confidence, class_id = box.tolist()
        detections.append(Detection(
            class_name=names[int(class_id)],
            confidence=confidence,
            x1=x1, y1=y1, x2=x2, y2=y2,
        ))
    return detections
