"""
Experiment tracking helpers for train_yolo_experiment.ipynb — turns one training run into a
self-contained, browsable record (real prediction images, real ground-truth images, real metrics) saved
under runs/model_experiments/<mAP50>_percent/, instead of just a best.pt with no context.

Reuses train_roboflow_yolo.py's dataset/balancing machinery (already built + verified non-destructive
this session) and detector.py's Detection/BaseDetector.draw_boxes for visualization, so rendered boxes
use the exact same class-color convention as the rest of this project (webapp preview, app.py). No new
dependencies here beyond what the notebook itself needs (ipykernel) — this module only uses stdlib plus
opencv/ultralytics, both already installed.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import cv2

from detector import BaseDetector, Detection

IMAGE_EXTS = (".jpg", ".jpeg", ".png")

HISTORY_FIELDS = [
    "run_id", "model", "epochs", "imgsz", "batch", "device", "augmentation",
    "balancing_method", "precision", "recall", "mAP50", "mAP50_95",
    "training_time", "model_path",
]

# The balancing method itself doesn't currently vary run to run, so this is a fixed string rather than
# a free-text field callers have to remember to fill in correctly each time.
BALANCING_METHOD = "dominant-class undersampling (train_roboflow_yolo.balance_train_split)"

# Files Ultralytics itself writes into its training output dir — copied up flat into the final
# <score>_percent/ folder (not left nested under a train/ subfolder), matching the requested layout.
# Some (e.g. confusion_matrix.png) may legitimately be absent for edge-case val sets — silently skipped,
# not an error; callers that care can check the returned list.
_ULTRALYTICS_KNOWN_FILES = [
    "results.csv", "results.png", "confusion_matrix.png", "confusion_matrix_normalized.png",
    "BoxPR_curve.png", "BoxF1_curve.png", "BoxP_curve.png", "BoxR_curve.png", "labels.jpg",
]


# ────────────────────────────── Per-run folder naming ──────────────────────────────

def score_to_folder_name(map50: float) -> str:
    """0.8735 -> "87.35_percent" — 2 decimal places, matches the user's own example exactly."""
    return f"{round(map50 * 100, 2)}_percent"


def finalize_run_dir(tmp_run_dir: Path, experiments_root: Path, map50: float) -> Path:
    """Renames the temp training-output directory to its final <score>_percent/ name (mAP50 isn't known
    until after training+validation finish, so training always writes into a fixed temp dir first).
    Handles name collisions (two runs rounding to the same score) by appending _2, _3, ... rather than
    ever overwriting an existing run's folder."""
    base_name = score_to_folder_name(map50)
    candidate = experiments_root / base_name
    n = 2
    while candidate.exists():
        candidate = experiments_root / f"{base_name}_{n}"
        n += 1
    tmp_run_dir.rename(candidate)
    return candidate


def collect_run_artifacts(ultralytics_train_dir: Path, final_dir: Path) -> list[str]:
    """Copies the known Ultralytics-produced files (results.csv/png, confusion matrix, curves,
    labels.jpg, weights/best.pt+last.pt) up into final_dir directly, flat — matching the requested
    per-run layout, not nested under a train/ subfolder. Returns the filenames actually found+copied."""
    final_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in _ULTRALYTICS_KNOWN_FILES:
        src = ultralytics_train_dir / name
        if src.exists():
            shutil.copy2(src, final_dir / name)
            copied.append(name)
    weights_dir = ultralytics_train_dir / "weights"
    for name in ("best.pt", "last.pt"):
        src = weights_dir / name
        if src.exists():
            shutil.copy2(src, final_dir / name)
            copied.append(name)
    return copied


# ────────────────────────────── Visualization (ground truth + predictions) ──────────────────────────────

def _draw_gt_image(img, records: list[dict]) -> "cv2.typing.MatLike":
    dets = [
        Detection(class_id=r["class_id"], class_name=r["class_name"], confidence=1.0,
                  x_center=r["x_center"], y_center=r["y_center"], width=r["width"], height=r["height"])
        for r in records
    ]
    return BaseDetector().draw_boxes(img, dets) if dets else img


def _draw_pred_image(img, model, class_names: list[str], conf: float, device: str) -> "cv2.typing.MatLike":
    results = model.predict(img, conf=conf, device=device, verbose=False)
    dets = []
    for res in results:
        for box in res.boxes:
            cid = int(box.cls[0])
            name = class_names[cid] if cid < len(class_names) else str(cid)
            x, y, w, h = (float(v) for v in box.xywhn[0].tolist())
            dets.append(Detection(class_id=cid, class_name=name, confidence=float(box.conf[0]),
                                   x_center=x, y_center=y, width=w, height=h))
    return BaseDetector().draw_boxes(img, dets) if dets else img


def draw_sample_annotations(images_dir: Path, labels_dir: Path, class_names: list[str], n: int = 6) -> list[dict]:
    """Ground-truth visualizations for the first n images — used for the notebook's step-3 sanity check
    (real annotation examples before training even starts). Returns [{"name": ..., "image": np.ndarray}].
    Import-local to avoid a hard dependency on train_roboflow_yolo at module-import time."""
    from train_roboflow_yolo import parse_labels_in_dir

    records = parse_labels_in_dir(images_dir, labels_dir, "sample", class_names)
    by_image: dict[str, list[dict]] = {}
    for r in records:
        by_image.setdefault(Path(r["image"]).name, []).append(r)

    out = []
    for img_path in sorted(images_dir.iterdir())[:n]:
        if img_path.suffix.lower() not in IMAGE_EXTS:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        out.append({"name": img_path.name, "image": _draw_gt_image(img, by_image.get(img_path.name, []))})
    return out


def render_val_visualizations(best_weights: Path, val_images_dir: Path, val_labels_dir: Path,
                               class_names: list[str], out_dir: Path, conf: float = 0.25,
                               device: str = "cpu") -> tuple[int, int]:
    """For every real validation image: one full-size prediction-boxes image (val_predictions/) and one
    full-size ground-truth-boxes image (val_ground_truth/), both via detector.py's Detection/draw_boxes
    so styling matches the rest of the project. Returns (n_pred_images, n_gt_images)."""
    from ultralytics import YOLO
    from train_roboflow_yolo import parse_labels_in_dir

    pred_dir = out_dir / "val_predictions"
    gt_dir = out_dir / "val_ground_truth"
    pred_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(best_weights))
    gt_records = parse_labels_in_dir(val_images_dir, val_labels_dir, "val", class_names)
    gt_by_image: dict[str, list[dict]] = {}
    for r in gt_records:
        gt_by_image.setdefault(Path(r["image"]).name, []).append(r)

    n_pred, n_gt = 0, 0
    for img_path in sorted(val_images_dir.iterdir()):
        if img_path.suffix.lower() not in IMAGE_EXTS:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue

        cv2.imwrite(str(gt_dir / img_path.name), _draw_gt_image(img, gt_by_image.get(img_path.name, [])))
        n_gt += 1

        cv2.imwrite(str(pred_dir / img_path.name), _draw_pred_image(img, model, class_names, conf, device))
        n_pred += 1

    return n_pred, n_gt


# ────────────────────────────── metrics.json / config.json / training_time.json ──────────────────────────────

def write_metrics_json(metrics, out_dir: Path, class_names: list[str]) -> dict:
    """metrics is the DetMetrics object returned by YOLO(...).val(...) — real object-detection metrics
    (precision/recall/mAP50/mAP50-95, overall + per-class), NOT sklearn classification_report; this is
    detection, not single-label classification."""
    data = {
        "precision": float(metrics.box.mp),
        "recall": float(metrics.box.mr),
        "mAP50": float(metrics.box.map50),
        "mAP50_95": float(metrics.box.map),
        "per_class": {},
    }
    ap_class_index = getattr(metrics.box, "ap_class_index", [])
    for i, cid in enumerate(ap_class_index):
        name = class_names[int(cid)] if int(cid) < len(class_names) else str(cid)
        data["per_class"][name] = {
            "mAP50": float(metrics.box.ap50[i]) if i < len(metrics.box.ap50) else None,
            "mAP50_95": float(metrics.box.ap[i]) if i < len(metrics.box.ap) else None,
        }
    (out_dir / "metrics.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def write_config_json(config: dict, out_dir: Path) -> None:
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


def write_training_time_json(seconds: float, out_dir: Path) -> dict:
    data = {"seconds": round(seconds, 2), "human_readable": _format_duration(seconds)}
    (out_dir / "training_time.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


# ────────────────────────────── experiment_history.csv ──────────────────────────────

def append_experiment_history(experiments_root: Path, row: dict) -> Path:
    """Appends one row to experiment_history.csv, writing the header only if the file is new."""
    path = experiments_root / "experiment_history.csv"
    is_new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in HISTORY_FIELDS})
    return path


def read_experiment_history(experiments_root: Path) -> list[dict]:
    path = experiments_root / "experiment_history.csv"
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ────────────────────────────── Model selection / pruning ──────────────────────────────

def prune_low_scoring_runs(experiments_root: Path, threshold: float = 0.80) -> dict:
    """Reads every run's metrics.json under experiments_root. Deletes ONLY best.pt/last.pt (never any
    other file in the run's folder) for any run with mAP50 < threshold that is not the single
    highest-scoring run overall — if nothing has reached threshold yet, only the single best-so-far run
    keeps its weights. Every deletion is asserted to fall inside experiments_root: the mirror-image of
    balance_train_split's protected_dir check (there: never delete INSIDE a protected dir; here: never
    delete OUTSIDE the allowed dir) — same defensive pattern, opposite direction, given this session's
    established caution around any deletion at all."""
    experiments_root = experiments_root.resolve()
    run_scores: dict[Path, float] = {}
    for run_dir in sorted(p for p in experiments_root.iterdir() if p.is_dir()):
        metrics_path = run_dir / "metrics.json"
        if not metrics_path.exists():
            continue
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            run_scores[run_dir] = float(data["mAP50"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    if not run_scores:
        return {"pruned": [], "kept": [], "best_run": None, "best_score": None}

    best_run = max(run_scores, key=run_scores.get)
    pruned: list[str] = []
    kept: list[str] = []
    for run_dir, score in run_scores.items():
        keep_weights = score >= threshold or run_dir == best_run
        if keep_weights:
            kept.append(str(run_dir))
            continue
        for fname in ("best.pt", "last.pt"):
            fpath = run_dir / fname
            if not fpath.exists():
                continue
            resolved = fpath.resolve()
            assert str(resolved).startswith(str(experiments_root)), (
                f"Refusing to delete {resolved} — outside the experiments root {experiments_root}."
            )
            fpath.unlink()
            pruned.append(str(fpath))

    return {"pruned": pruned, "kept": kept, "best_run": str(best_run), "best_score": run_scores[best_run]}
