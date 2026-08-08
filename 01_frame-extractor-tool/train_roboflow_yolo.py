"""
Standalone CLI: download a Roboflow-annotated dataset, undersample an over-represented class in the
train split (whole-image removal, never partial-label edits), train a YOLOv11 model on CPU, and log
both ground-truth and model-predicted object positions to CSV.

Never touches webapp/server.py or static/app.js — fully independent of the annotation tool.
No credentials are ever hardcoded or requested interactively: the Roboflow API key must come from the
ROBOFLOW_API_KEY environment variable or --api-key.

Usage:
    python train_roboflow_yolo.py --workspace my-ws --project my-proj --version 3
    ROBOFLOW_API_KEY=rf_xxx python train_roboflow_yolo.py --workspace my-ws --project my-proj --version 3

    # Reuse an already-downloaded dataset (also useful for a credential-free dry run):
    python train_roboflow_yolo.py --skip-download --dataset-dir ./my_dataset --skip-train
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
import zipfile
from pathlib import Path

import yaml
from tqdm import tqdm

IMAGE_EXTS = (".jpg", ".jpeg", ".png")


# ────────────────────────────── Download ──────────────────────────────

def download_roboflow_dataset(workspace: str, project: str, version: int, api_key: str, fmt: str, dest_dir: Path) -> None:
    """Two-step Roboflow REST download: GET the export-info JSON (returns a signed export.link URL),
    then GET that link for the actual ZIP bytes, then extract via stdlib zipfile.
    https://docs.roboflow.com/datasets/versions/dataset-versions/exporting-data"""
    import urllib.error
    import urllib.request

    info_url = f"https://api.roboflow.com/{workspace}/{project}/{version}/{fmt}?api_key={api_key}"
    print(f"[roboflow] requesting export info: format={fmt} workspace={workspace} project={project} version={version}")
    try:
        with urllib.request.urlopen(info_url, timeout=30) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(
            f"Roboflow export-info request failed ({e.code}): {body}\n"
            f"If format='{fmt}' is rejected, try --format yolov8 or --format yolov7pytorch instead."
        ) from e

    link = info.get("export", {}).get("link")
    if not link:
        raise RuntimeError(f"Unexpected Roboflow response shape (no export.link key): {info}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "_download.zip"
    print("[roboflow] downloading dataset zip...")
    with urllib.request.urlopen(link, timeout=300) as resp, open(zip_path, "wb") as f:
        shutil.copyfileobj(resp, f)

    print(f"[roboflow] extracting to {dest_dir} ...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()


# ────────────────────────────── data.yaml / label parsing ──────────────────────────────

def load_data_yaml(dataset_dir: Path) -> dict:
    yaml_path = dataset_dir / "data.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"data.yaml not found in {dataset_dir} — did the download/extract succeed?")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    names_raw = data.get("names", [])
    data["names"] = [names_raw[k] for k in sorted(names_raw, key=int)] if isinstance(names_raw, dict) else list(names_raw)
    return data


def resolve_split_images_dir(dataset_dir: Path, yaml_data: dict, split: str) -> Path | None:
    raw = yaml_data.get(split)
    if not raw:
        return None
    base = dataset_dir
    if yaml_data.get("path"):
        p = Path(yaml_data["path"])
        base = p if p.is_absolute() else (dataset_dir / p)
    resolved = (base / raw).resolve()
    return resolved if resolved.exists() else None


def labels_dir_for(images_dir: Path) -> Path:
    """Ultralytics and Roboflow both keep images/ and labels/ as sibling dirs at the same nesting
    depth (train/images + train/labels, OR images/train + labels/train) — swap the 'images' path
    segment rather than assuming a fixed folder-naming convention. Roboflow's own validation-split
    folder is named 'valid', not 'val' — verified via docs.roboflow.com — a hardcoded 'val' guess
    would silently find zero files."""
    parts = list(images_dir.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "images":
            parts[i] = "labels"
            return Path(*parts)
    raise ValueError(f"no 'images' path segment in {images_dir} to derive its labels dir")


def parse_yolo_labels(dataset_dir: Path, yaml_data: dict) -> list[dict]:
    """One dict per labeled instance: {split, image (full path str), class_id, class_name,
    x_center, y_center, width, height} — all normalized [0,1], read straight from the .txt files."""
    class_names = yaml_data["names"]
    records: list[dict] = []
    for split in ("train", "val", "test"):
        images_dir = resolve_split_images_dir(dataset_dir, yaml_data, split)
        if images_dir is None:
            continue
        labels_dir = labels_dir_for(images_dir)
        for img_path in sorted(images_dir.iterdir()):
            if img_path.suffix.lower() not in IMAGE_EXTS:
                continue
            label_path = labels_dir / (img_path.stem + ".txt")
            if not label_path.exists():
                continue
            for line in label_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                if len(parts) > 5:
                    print(f"[warn] {label_path.name}: {len(parts)} values (expected 5 for bbox format) — "
                          f"skipping; is --format a detection export, not segmentation/pose?")
                    continue
                cid = int(parts[0])
                x, y, w, h = (float(v) for v in parts[1:5])
                name = class_names[cid] if cid < len(class_names) else str(cid)
                records.append({
                    "split": split, "image": str(img_path), "class_id": cid, "class_name": name,
                    "x_center": x, "y_center": y, "width": w, "height": h,
                })
    return records


# ────────────────────────────── Class balancing (undersample the dominant class) ──────────────────────────────

def compute_class_counts(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        counts[r["class_name"]] = counts.get(r["class_name"], 0) + 1
    return counts


def find_dominant_class(train_counts: dict[str, int], imbalance_threshold: float) -> str | None:
    """The class whose instance count exceeds imbalance_threshold x the mean of the other classes'
    counts, or None if the dataset is already roughly balanced (or has <2 classes present)."""
    if len(train_counts) < 2:
        return None
    dominant = max(train_counts, key=train_counts.get)
    others = [c for name, c in train_counts.items() if name != dominant]
    others_mean = sum(others) / len(others) if others else 0
    if others_mean == 0 or train_counts[dominant] <= others_mean * imbalance_threshold:
        return None
    return dominant


def balance_train_split(
    train_records: list[dict],
    seed: int,
    max_drop_fraction: float = 0.9,
    imbalance_threshold: float = 1.5,
) -> dict:
    """Undersamples the single most over-represented class by DELETING WHOLE train images (image file
    + its .txt label file together) — never edits label lines inside a kept image, since that would
    leave any other real objects in that frame falsely unlabeled. val/test are never touched — kept
    exactly as downloaded, standard practice for a fair, representative evaluation.

    Explicit trade-off: an image containing BOTH the dominant class and other classes still loses
    those other classes' instances if it's selected for removal — an unavoidable cost of image-level
    (vs. instance-level) undersampling, accepted specifically to avoid the false-negative risk of
    partial in-image label edits."""
    random.seed(seed)
    counts = compute_class_counts(train_records)
    dominant = find_dominant_class(counts, imbalance_threshold)
    if dominant is None:
        return {"dominant_class": None, "removed_images": 0,
                "reason": "already balanced (within --imbalance-threshold) or <2 classes present"}

    others = [c for name, c in counts.items() if name != dominant]
    target = round(sum(others) / len(others))

    by_image: dict[str, list[dict]] = {}
    for r in train_records:
        by_image.setdefault(r["image"], []).append(r)

    dominant_images = [img for img, rs in by_image.items() if any(r["class_name"] == dominant for r in rs)]
    random.shuffle(dominant_images)  # random selection, reproducible via --seed

    max_removable = int(len(dominant_images) * max_drop_fraction)
    removed_images: list[str] = []
    current_count = counts[dominant]

    for img in dominant_images:
        if current_count <= target or len(removed_images) >= max_removable:
            break
        n_here = sum(1 for r in by_image[img] if r["class_name"] == dominant)
        removed_images.append(img)
        current_count -= n_here

    for img in removed_images:
        img_path = Path(img)
        label_path = labels_dir_for(img_path.parent) / (img_path.stem + ".txt")
        img_path.unlink(missing_ok=True)
        label_path.unlink(missing_ok=True)

    return {
        "dominant_class": dominant,
        "dominant_count_before": counts[dominant],
        "dominant_count_after": current_count,
        "target_count": target,
        "removed_images": len(removed_images),
        "eligible_images": len(dominant_images),
        "hit_max_drop_cap": len(removed_images) >= max_removable,
    }


# ────────────────────────────── Position logging ──────────────────────────────

def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def log_ground_truth_positions(records: list[dict], out_path: Path) -> int:
    rows = [{
        "split": r["split"], "image": Path(r["image"]).name, "class_id": r["class_id"],
        "class_name": r["class_name"], "x_center": round(r["x_center"], 6),
        "y_center": round(r["y_center"], 6), "width": round(r["width"], 6), "height": round(r["height"], 6),
    } for r in records]
    _write_csv(out_path, rows, ["split", "image", "class_id", "class_name", "x_center", "y_center", "width", "height"])
    return len(rows)


def log_predicted_positions(weights_path: Path, image_dirs: list[Path], class_names: list[str],
                             conf: float, device: str, out_path: Path) -> int:
    from ultralytics import YOLO
    model = YOLO(str(weights_path))

    image_paths: list[Path] = []
    for d in image_dirs:
        if d and d.exists():
            image_paths.extend(sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS))

    rows = []
    for img_path in tqdm(image_paths, desc="Predicting"):
        results = model.predict(str(img_path), conf=conf, device=device, verbose=False)
        for r in results:
            for box in r.boxes:
                cid = int(box.cls[0])
                name = class_names[cid] if cid < len(class_names) else str(cid)
                x, y, w, h = (float(v) for v in box.xywhn[0].tolist())
                rows.append({
                    "image": img_path.name, "class_id": cid, "class_name": name,
                    "confidence": round(float(box.conf[0]), 4),
                    "x_center": round(x, 6), "y_center": round(y, 6),
                    "width": round(w, 6), "height": round(h, 6),
                })
    _write_csv(out_path, rows, ["image", "class_id", "class_name", "confidence", "x_center", "y_center", "width", "height"])
    return len(rows)


# ────────────────────────────── Training ──────────────────────────────

def train_model(data_yaml: Path, model_weights: str, epochs: int, imgsz: int, batch: int,
                 device: str, seed: int, output_dir: Path) -> Path:
    from ultralytics import YOLO
    print(f"[train] {model_weights} on {data_yaml} — epochs={epochs} imgsz={imgsz} batch={batch} device={device}")
    model = YOLO(model_weights)
    model.train(
        data=str(data_yaml), epochs=epochs, imgsz=imgsz, batch=batch,
        device=device, seed=seed, project=str(output_dir), name="train", exist_ok=True,
    )
    best = output_dir / "train" / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError(f"Training finished but best.pt not found at {best}")
    return best


# ────────────────────────────── CLI ──────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download a Roboflow dataset, undersample an over-represented class in the train "
                    "split, train YOLOv11 on CPU, and log ground-truth + predicted object positions.")
    parser.add_argument("--workspace")
    parser.add_argument("--project")
    parser.add_argument("--version", type=int)
    parser.add_argument("--api-key", default=os.environ.get("ROBOFLOW_API_KEY"),
                         help="Roboflow API key — never hardcode; defaults to $ROBOFLOW_API_KEY")
    parser.add_argument("--format", dest="fmt", default="yolov5pytorch",
                         help="Roboflow export format string. Default 'yolov5pytorch' is confirmed by "
                              "Roboflow's own docs and produces the same plain YOLO txt/data.yaml format "
                              "Ultralytics YOLOv8/v11 trains on. Try 'yolov8' if you know your workspace "
                              "supports it.")
    parser.add_argument("--dataset-dir", default="./roboflow_dataset")
    parser.add_argument("--skip-download", action="store_true",
                         help="reuse an already-downloaded dataset at --dataset-dir (must contain data.yaml) "
                              "instead of fetching from Roboflow")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--imbalance-threshold", type=float, default=1.5,
                         help="a class is 'over-represented' if its count exceeds this multiple of the mean of the others")
    parser.add_argument("--max-drop-fraction", type=float, default=0.9,
                         help="never remove more than this fraction of eligible train images")
    parser.add_argument("--output-dir", default="./runs/roboflow_train")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--skip-train", action="store_true",
                         help="download + balance + log ground truth only; skip training/prediction (dry run)")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if not args.skip_download:
            if not (args.workspace and args.project and args.version and args.api_key):
                print("[error] --workspace, --project, --version and an API key (--api-key or "
                      "ROBOFLOW_API_KEY) are required unless --skip-download is set.", file=sys.stderr)
                sys.exit(1)
            download_roboflow_dataset(args.workspace, args.project, args.version, args.api_key, args.fmt, dataset_dir)
        elif not (dataset_dir / "data.yaml").exists():
            print(f"[error] --skip-download set but {dataset_dir}/data.yaml does not exist.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"[info] --skip-download set — reusing existing dataset at {dataset_dir}")

        yaml_data = load_data_yaml(dataset_dir)
        class_names = yaml_data["names"]
        print(f"[info] classes: {class_names}")

        train_records = [r for r in parse_yolo_labels(dataset_dir, yaml_data) if r["split"] == "train"]
        print(f"[info] train class counts before balancing: {compute_class_counts(train_records)}")

        report = balance_train_split(train_records, seed=args.seed,
                                      max_drop_fraction=args.max_drop_fraction,
                                      imbalance_threshold=args.imbalance_threshold)
        print(f"[balance] {report}")

        # Re-parse from disk so the ground-truth log reflects exactly what survived balancing.
        all_records = parse_yolo_labels(dataset_dir, yaml_data)
        gt_path = output_dir / "ground_truth_positions.csv"
        n_gt = log_ground_truth_positions(all_records, gt_path)
        print(f"[log] wrote {n_gt} ground-truth instance rows to {gt_path}")

        if args.skip_train:
            print("[info] --skip-train set, stopping here.")
            return

        best_weights = train_model(dataset_dir / "data.yaml", args.model, args.epochs, args.imgsz,
                                    args.batch, args.device, args.seed, output_dir)
        print(f"[train] done — best weights at {best_weights}")

        val_dir = resolve_split_images_dir(dataset_dir, yaml_data, "val")
        test_dir = resolve_split_images_dir(dataset_dir, yaml_data, "test")
        pred_path = output_dir / "predicted_positions.csv"
        n_pred = log_predicted_positions(best_weights, [d for d in (val_dir, test_dir) if d],
                                          class_names, args.conf, args.device, pred_path)
        print(f"[log] wrote {n_pred} predicted instance rows to {pred_path}")

    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
