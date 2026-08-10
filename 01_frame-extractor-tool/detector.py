"""
YOLOv11 Detector Wrapper
========================
Wrapper สำหรับโมเดล YOLOv11 ตรวจจับอุปกรณ์เย็บแผล

Classes  : finger | forcep | needle | needle_holder | wound
Framework: Ultralytics YOLO (รองรับ YOLOv8–v11)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import cv2
import numpy as np

# ultralytics' torch_safe_load() defaults to UNRESTRICTED torch.load() (arbitrary pickled code can
# execute on load) unless this env var is set. Must be set before ultralytics is ever imported (its
# SAFE_LOAD constant is read once at import time) — set here, at module load, since YOLOv11Detector
# below imports ultralytics lazily. setdefault() so an operator can still explicitly opt out.
os.environ.setdefault("ULTRALYTICS_SAFE_LOAD", "1")


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


def polygon_bbox(points: list[list[float]]) -> tuple[float, float, float, float]:
    """Normalized polygon vertices -> derived (x_center, y_center, width, height), all normalized [0,1].
    Mirrors the JS `polygonToNormalizedBBox` in app.js exactly — keep both in sync if either changes."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    return (
        min(1.0, max(0.0, (x1 + x2) / 2)),
        min(1.0, max(0.0, (y1 + y2) / 2)),
        min(1.0, max(0.001, x2 - x1)),   # 0.001 floor mirrors clampPos() in app.js / DetectionIn's gt=0.0
        min(1.0, max(0.001, y2 - y1)),
    )


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
    # "model"        raw detector output
    # "manual"       human-drawn/edited at save time
    # "interpolated" geometry synthesised between two human keyframes; no detector and no human ever
    #                saw this exact box, so it is kept distinct from both — the Analytics accept-rate
    #                counts only "model", and a human confirming one does not rewrite it to "manual".
    source:     str = "model"
    points:     list[list[float]] | None = None  # normalized [[x,y], ...] polygon vertices; None = plain bbox
    keypoints:  list[list[float]] | None = None  # normalized [[x,y,v], ...] pose keypoints; v: 0=unlabeled,1=occluded,2=visible
    # Human-only annotation attributes. The YOLO label line has nowhere to put them, so they never
    # reach a .txt — dataset_exporter writes them to a separate attributes.json instead. A model
    # cannot know either of these, so the detectors leave them at their defaults.
    occluded:   bool = False  # partly hidden behind another object
    truncated:  bool = False  # runs off the edge of the frame

    def __post_init__(self):
        # Server is authoritative: whenever a real polygon/keypoint set is present, the bbox fields are
        # always derived from it — never whatever the caller happened to pass in.
        if self.points and len(self.points) >= 3:
            self.x_center, self.y_center, self.width, self.height = polygon_bbox(self.points)
        elif self.keypoints and len(self.keypoints) >= 1:
            self.x_center, self.y_center, self.width, self.height = polygon_bbox(
                [[p[0], p[1]] for p in self.keypoints]
            )

    # ── YOLO label string ──────────────────────
    def to_yolo_str(self) -> str:
        """คืน 1 บรรทัดสำหรับเขียนลงไฟล์ .txt (bbox format เท่านั้น — ดู to_yolo_seg_str() สำหรับ polygon)"""
        return (
            f"{self.class_id} "
            f"{self.x_center:.6f} {self.y_center:.6f} "
            f"{self.width:.6f} {self.height:.6f}"
        )

    def _bbox_corners(self) -> list[tuple[float, float]]:
        x1 = self.x_center - self.width / 2
        y1 = self.y_center - self.height / 2
        x2 = self.x_center + self.width / 2
        y2 = self.y_center + self.height / 2
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    def to_yolo_seg_str(self) -> str:
        """Ultralytics segmentation label line: 'class x1 y1 x2 y2 ... xn yn'.
        Falls back to the bbox's own 4 corners when no real polygon was drawn, so a bbox-only
        Detection still exports as a valid (rectangular) segmentation instance."""
        pts = self.points if self.points and len(self.points) >= 3 else self._bbox_corners()
        coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in pts)
        return f"{self.class_id} {coords}"

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
            "source":     self.source,
            "points":     [[round(x, 6), round(y, 6)] for x, y in self.points] if self.points else None,
            "keypoints":  [[round(x, 6), round(y, 6), int(v)] for x, y, v in self.keypoints] if self.keypoints else None,
            "occluded":   bool(self.occluded),
            "truncated":  bool(self.truncated),
        }


# ─────────────────────────────────────────────
#  Base Detector  (shared label/draw logic)
# ─────────────────────────────────────────────
class BaseDetector:
    """
    Interface ร่วมของทุก detector backend:
      predict()        → list[Detection]   (implement ใน subclass)
      to_yolo_label()  → str  (เขียนลงไฟล์ .txt ได้เลย)
      draw_boxes()     → np.ndarray  (BGR image พร้อม BBox)
    """

    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        raise NotImplementedError

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
        """วาด BBox/Polygon + label บนภาพ (คืน copy — ไม่แก้ไขต้นฉบับ)"""
        img = image_bgr.copy()
        h, w = img.shape[:2]
        for det in detections:
            color = CLASS_COLORS_BGR.get(det.class_name, _DEFAULT_BGR)

            if det.points and len(det.points) >= 3:
                pts = np.array([[int(x * w), int(y * h)] for x, y in det.points], dtype=np.int32)
                cv2.polylines(img, [pts], isClosed=True, color=color, thickness=thickness)
                x1, y1 = int(pts[:, 0].min()), int(pts[:, 1].min())  # label anchor = polygon's own top-left
            elif det.keypoints:
                xs, ys = [], []
                for px, py, v in det.keypoints:
                    cx, cy = int(px * w), int(py * h)
                    xs.append(cx); ys.append(cy)
                    if v == 2:
                        cv2.circle(img, (cx, cy), 4, color, -1)          # solid = visible
                    elif v == 1:
                        cv2.circle(img, (cx, cy), 4, color, thickness)   # hollow = occluded
                    else:
                        cv2.circle(img, (cx, cy), 2, _DEFAULT_BGR, -1)   # small/grey = not-labeled
                x1, y1 = min(xs), min(ys)  # label anchor = keypoints' own top-left
            else:
                x1, y1, x2, y2 = det.pixel_bbox(w, h)
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


def _threshold_for(class_name: str, conf: float, class_conf: dict[str, float] | None) -> float:
    """Confidence a detection of this class must reach to be kept: the per-class override when one
    was given, otherwise the run's single `conf`. Lives here so both detectors below apply the same
    rule — a class the model finds but scores too low (needle, on the models trained so far) can be
    let through without dropping the threshold for every other class and drowning the user in boxes
    to reject."""
    return (class_conf or {}).get(class_name, conf)


# ─────────────────────────────────────────────
#  YOLOv11 Detector  (local .pt weights)
# ─────────────────────────────────────────────
class YOLOv11Detector(BaseDetector):
    """โหลดโมเดล YOLOv11 ในเครื่องผ่าน ultralytics"""

    def __init__(
        self,
        model_path: str,
        conf:   float = 0.25,
        iou:    float = 0.45,
        device: str   = "cpu",
        class_conf: dict[str, float] | None = None,
    ):
        from ultralytics import YOLO  # lazy import (หลีกเลี่ยงหน้าจอช้า)
        self.model       = YOLO(model_path)
        self.conf        = conf
        self.iou         = iou
        self.device      = device
        self.class_conf  = dict(class_conf or {})
        self.class_names: list[str] = list(self.model.names.values())

    # ── Inference ─────────────────────────────
    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        """รัน inference บน 1 frame (BGR ndarray)"""
        h, w = image_bgr.shape[:2]
        # Ultralytics drops anything under `conf` before we ever see it, so ask it for the LOWEST
        # threshold any class wants and enforce the real per-class ones below. NMS is class-wise by
        # default (agnostic_nms=False), so the extra low-confidence boxes this admits for one class
        # cannot suppress another class's box.
        floor = min([self.conf, *self.class_conf.values()])
        results = self.model.predict(
            image_bgr,
            conf=floor,
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
                confidence = float(box.conf[0])
                if confidence < _threshold_for(name, self.conf, self.class_conf):
                    continue
                x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
                dets.append(Detection(
                    class_id   = cid,
                    class_name = name,
                    confidence = confidence,
                    x_center   = ((x1 + x2) / 2) / w,
                    y_center   = ((y1 + y2) / 2) / h,
                    width      = (x2 - x1) / w,
                    height     = (y2 - y1) / h,
                ))
        return dets


# ─────────────────────────────────────────────
#  Roboflow Cloud Detector  (hosted workflow API)
# ─────────────────────────────────────────────
def _extract_predictions(result) -> list[dict]:
    """
    ผลลัพธ์ของ Roboflow run_workflow() หน้าตาต่างกันได้ตามชนิด workflow
    ลองดึงจากโครงสร้างที่พบบ่อยที่สุดก่อน ถ้าไม่เจอเลยให้ print raw response
    ออก console เพื่อ debug แล้ว raise ให้เห็นชัดว่า parse ไม่ได้
    """
    candidates = result
    if isinstance(result, list) and result:
        candidates = result[0]

    if isinstance(candidates, dict):
        preds = candidates.get("predictions")
        if isinstance(preds, dict):
            preds = preds.get("predictions")
        if isinstance(preds, list):
            return preds

    print("[RoboflowDetector] ไม่รู้จักโครงสร้าง response — raw result:")
    print(result)
    raise ValueError(
        "ไม่สามารถอ่านผลลัพธ์จาก Roboflow workflow ได้ "
        "(ดู raw response ใน console แล้วปรับ _extract_predictions ให้ตรง schema จริง)"
    )


class RoboflowDetector(BaseDetector):
    """เรียกโมเดลผ่าน Roboflow Cloud workflow API (inference-sdk)"""

    def __init__(
        self,
        api_key:        str,
        workspace_name: str = "fhasai-khuanpan",
        workflow_id:    str = "ssid-v5-logic",
        api_url:        str = "https://serverless.roboflow.com",
        conf:           float = 0.25,
        class_conf:     dict[str, float] | None = None,
    ):
        from inference_sdk import InferenceHTTPClient  # lazy import
        self.client = InferenceHTTPClient(api_url=api_url, api_key=api_key)
        self.workspace_name = workspace_name
        self.workflow_id    = workflow_id
        self.conf           = conf
        self.class_conf     = dict(class_conf or {})
        self.class_names: list[str] = CLASS_NAMES

    # ── Inference ─────────────────────────────
    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        """รัน inference บน 1 frame (BGR ndarray) ผ่าน Roboflow cloud"""
        h, w = image_bgr.shape[:2]
        result = self.client.run_workflow(
            workspace_name=self.workspace_name,
            workflow_id=self.workflow_id,
            images={"image": image_bgr},
            use_cache=True,
        )
        preds = _extract_predictions(result)

        dets: list[Detection] = []
        for p in preds:
            confidence = float(p.get("confidence", 0.0))
            name = p.get("class") or p.get("class_name") or "unknown"
            if confidence < _threshold_for(name, self.conf, self.class_conf):
                continue
            cid  = p.get("class_id")
            if cid is None:
                cid = CLASS_NAMES.index(name) if name in CLASS_NAMES else -1
            dets.append(Detection(
                class_id   = int(cid),
                class_name = name,
                confidence = confidence,
                x_center   = float(p["x"]) / w,
                y_center   = float(p["y"]) / h,
                width      = float(p["width"]) / w,
                height     = float(p["height"]) / h,
            ))
        return dets
