"""
YOLOv11 Detector Wrapper
========================
Wrapper สำหรับโมเดล YOLOv11 ตรวจจับอุปกรณ์เย็บแผล

Classes  : finger | forcep | needle | needle_holder | wound
Framework: Ultralytics YOLO (รองรับ YOLOv8–v11)
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


# ─────────────────────────────────────────────
#  Class Colour Map  (BGR for OpenCV)
# ─────────────────────────────────────────────
CLASS_COLORS_BGR: dict[str, tuple[int, int, int]] = {
    "finger":        ( 72, 107, 255),   # red-coral
    "forcep":        (196, 205,  78),   # teal
    "needle":        ( 50, 220, 255),   # yellow
    "needle_holder": (160, 230, 168),   # mint-green
    "wound":         (148, 100, 240),   # violet
}
_DEFAULT_BGR: tuple[int, int, int] = (180, 180, 180)

# Hex counterparts (for Tkinter widgets)
CLASS_COLORS_HEX: dict[str, str] = {
    "finger":        "#FF6B48",
    "forcep":        "#4ECDC4",
    "needle":        "#FFE032",
    "needle_holder": "#A8E6A0",
    "wound":         "#F064A0",
}
_DEFAULT_HEX = "#AAAAAA"

CLASS_NAMES: list[str] = ["finger", "forcep", "needle", "needle_holder", "wound"]


# ─────────────────────────────────────────────
#  Data class
# ─────────────────────────────────────────────
@dataclass
class Detection:
    """ผลลัพธ์ Detection 1 object"""
    class_id:   int
    class_name: str
    confidence: float
    x_center:   float   # normalised [0, 1]
    y_center:   float
    width:      float
    height:     float

    # ── YOLO label string ──────────────────────
    def to_yolo_str(self) -> str:
        """คืน 1 บรรทัดสำหรับเขียนลงไฟล์ .txt"""
        return (
            f"{self.class_id} "
            f"{self.x_center:.6f} {self.y_center:.6f} "
            f"{self.width:.6f} {self.height:.6f}"
        )

    # ── Pixel coordinates ──────────────────────
    def pixel_bbox(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """คืน (x1, y1, x2, y2) ในหน่วย pixel (clipped ไม่ออกขอบ)"""
        x1 = int((self.x_center - self.width  / 2) * img_w)
        y1 = int((self.y_center - self.height / 2) * img_h)
        x2 = int((self.x_center + self.width  / 2) * img_w)
        y2 = int((self.y_center + self.height / 2) * img_h)
        return (
            max(0, x1), max(0, y1),
            min(img_w - 1, x2), min(img_h - 1, y2),
        )

    def to_dict(self) -> dict:
        return {
            "class_id":   self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "x_center":   round(self.x_center, 6),
            "y_center":   round(self.y_center, 6),
            "width":      round(self.width,    6),
            "height":     round(self.height,   6),
        }


# ─────────────────────────────────────────────
#  YOLOv11 Detector
# ─────────────────────────────────────────────
class YOLOv11Detector:
    """
    โหลดโมเดล YOLOv11 และให้บริการ:
      predict()        → list[Detection]
      to_yolo_label()  → str  (เขียนลงไฟล์ .txt ได้เลย)
      draw_boxes()     → np.ndarray  (BGR image พร้อม BBox)
    """

    def __init__(
        self,
        model_path: str,
        conf:   float = 0.25,
        iou:    float = 0.45,
        device: str   = "cpu",
    ):
        from ultralytics import YOLO  # lazy import (หลีกเลี่ยงหน้าจอช้า)
        self.model       = YOLO(model_path)
        self.conf        = conf
        self.iou         = iou
        self.device      = device
        self.class_names: list[str] = list(self.model.names.values())

    # ── Inference ─────────────────────────────
    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        """รัน inference บน 1 frame (BGR ndarray)"""
        h, w = image_bgr.shape[:2]
        results = self.model.predict(
            image_bgr,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            verbose=False,
        )
        dets: list[Detection] = []
        for r in results:
            for box in r.boxes:
                cid  = int(box.cls[0])
                name = (self.class_names[cid]
                        if cid < len(self.class_names) else str(cid))
                x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
                dets.append(Detection(
                    class_id   = cid,
                    class_name = name,
                    confidence = float(box.conf[0]),
                    x_center   = ((x1 + x2) / 2) / w,
                    y_center   = ((y1 + y2) / 2) / h,
                    width      = (x2 - x1) / w,
                    height     = (y2 - y1) / h,
                ))
        return dets

    # ── Label export ──────────────────────────
    def to_yolo_label(self, detections: list[Detection]) -> str:
        """คืน string พร้อมเขียนลงไฟล์ .txt (หลาย object หลายบรรทัด)"""
        return "\n".join(d.to_yolo_str() for d in detections)

    # ── Visualisation ─────────────────────────
    def draw_boxes(
        self,
        image_bgr:  np.ndarray,
        detections: list[Detection],
        font_scale: float = 0.55,
        thickness:  int   = 2,
    ) -> np.ndarray:
        """วาด BBox + label บนภาพ (คืน copy — ไม่แก้ไขต้นฉบับ)"""
        img = image_bgr.copy()
        h, w = img.shape[:2]
        for det in detections:
            color = CLASS_COLORS_BGR.get(det.class_name, _DEFAULT_BGR)
            x1, y1, x2, y2 = det.pixel_bbox(w, h)

            # กรอบ
            cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

            # Label background
            label = f"{det.class_name}  {det.confidence:.2f}"
            (lw, lh), bl = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            cv2.rectangle(
                img,
                (x1, y1 - lh - bl - 6),
                (x1 + lw + 8, y1),
                color, -1,
            )
            cv2.putText(
                img, label, (x1 + 4, y1 - bl - 3),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                (10, 10, 10), 1, cv2.LINE_AA,
            )
        return img
