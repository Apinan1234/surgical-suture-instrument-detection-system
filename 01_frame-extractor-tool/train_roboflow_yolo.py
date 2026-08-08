"""
Standalone CLI: download a Roboflow-annotated dataset, undersample an over-represented class in the
train split (whole-image removal, never partial-label edits), train a YOLOv11 model on CPU, and log
both ground-truth and model-predicted object positions to CSV.

The original --dataset-dir is NEVER modified: balancing operates only on a working copy of the train
split under --output-dir/train_balanced/ (see copy_train_split_for_balancing()), and every deletion is
runtime-asserted to fall outside --dataset-dir (see balance_train_split()'s protected_dir check). val/test
are read straight from the original (never copied, never written to).

Never touches webapp/server.py or static/app.js — fully independent of the annotation tool.
No credentials are ever hardcoded or requested interactively: the Roboflow API key must come from the
ROBOFLOW_API_KEY environment variable, --api-key, or webapp/.env (same gitignored file + python-dotenv
already used by webapp/server.py for its own secrets — reused here, not a new mechanism).

Usage:
    # One-time setup: add a line to webapp/.env (create it from webapp/.env.example if it doesn't exist)
    #   ROBOFLOW_API_KEY=rf_xxx
    python train_roboflow_yolo.py --workspace my-ws --project my-proj --version 3

    # Or pass it inline instead, without touching webapp/.env:
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
from dotenv import load_dotenv
from tqdm import tqdm

# Same webapp/.env file + python-dotenv already used by webapp/server.py — one shared place for
# secrets in this project, not a second convention. A missing file is fine (find_dotenv-less load_dotenv
# on a nonexistent path is a silent no-op); real env vars set before launch always take precedence
# since load_dotenv() never overrides an already-set os.environ value.
load_dotenv(Path(__file__).resolve().parent / "webapp" / ".env")

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
    if resolved.exists():
        return resolved
    # Fallback for Roboflow's plain "download zip to computer" export: its data.yaml has no `path:` key
    # and train/val/test values like "../train/images" that only resolve correctly when consumed via
    # Roboflow's own SDK (which injects a working `path:`). A manually-unzipped folder instead has
    # train/valid/test as direct children of dataset_dir — strip the ".." traversal and retry there.
    stripped_parts = [p for p in Path(raw).parts if p != ".."]
    if stripped_parts:
        fallback = (dataset_dir / Path(*stripped_parts)).resolve()
        if fallback.exists():
            return fallback
    return None


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


def copy_train_split_for_balancing(orig_images_dir: Path, orig_labels_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    """Copies the train split's images+labels into a fresh working directory under output_dir so every
    downstream balancing operation (which deletes files) only ever touches this copy — the original
    dataset directory is never opened in a write/delete mode anywhere in this script. Always starts from
    a clean copy (deletes any leftover copy from a prior run first) so re-running is deterministic and
    never compounds an already-balanced copy."""
    work_dir = output_dir / "train_balanced"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    images_copy = work_dir / "images"
    labels_copy = work_dir / "labels"
    shutil.copytree(orig_images_dir, images_copy)
    shutil.copytree(orig_labels_dir, labels_copy)
    return images_copy, labels_copy


def parse_labels_in_dir(images_dir: Path, labels_dir: Path, split: str, class_names: list[str]) -> list[dict]:
    """One dict per labeled instance: {split, image (full path str), class_id, class_name,
    x_center, y_center, width, height} — all normalized [0,1], read straight from the .txt files in a
    single images/labels directory pair. Split out of parse_yolo_labels() so callers can point it at
    either the original dataset's val/test dirs or the train_balanced working copy's dirs."""
    records: list[dict] = []
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


def parse_yolo_labels(dataset_dir: Path, yaml_data: dict) -> list[dict]:
    """All splits from the original dataset_dir, read-only. Used only for the pre-balance train count
    (always safe to read) — the post-balance ground-truth log reads train from the working copy instead,
    see main()."""
    class_names = yaml_data["names"]
    records: list[dict] = []
    for split in ("train", "val", "test"):
        images_dir = resolve_split_images_dir(dataset_dir, yaml_data, split)
        if images_dir is None:
            continue
        labels_dir = labels_dir_for(images_dir)
        records.extend(parse_labels_in_dir(images_dir, labels_dir, split, class_names))
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
    protected_dir: Path | None = None,
) -> dict:
    """Undersamples the single most over-represented class by DELETING WHOLE train images (image file
    + its .txt label file together) — never edits label lines inside a kept image, since that would
    leave any other real objects in that frame falsely unlabeled. val/test are never touched — kept
    exactly as downloaded, standard practice for a fair, representative evaluation.

    Explicit trade-off: an image containing BOTH the dominant class and other classes still loses
    those other classes' instances if it's selected for removal — an unavoidable cost of image-level
    (vs. instance-level) undersampling, accepted specifically to avoid the false-negative risk of
    partial in-image label edits.

    protected_dir, if given, is a hard runtime guarantee (not just a caller convention): every deletion
    is asserted to fall outside it. Callers must always pass the original --dataset-dir here and only
    ever hand this function records from the train_balanced working copy — this makes the "never touch
    the original dataset" contract fail loudly instead of silently, even if a future edit gets a call
    site wrong."""
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
        if protected_dir is not None:
            assert not str(img_path.resolve()).startswith(str(protected_dir.resolve())), (
                f"Refusing to delete {img_path} — it is inside the protected original dataset dir "
                f"{protected_dir}. This must only ever run against the train_balanced working copy."
            )
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


def write_working_data_yaml(yaml_data: dict, train_images_dir: Path, val_images_dir: Path | None,
                             test_images_dir: Path | None, output_dir: Path) -> Path:
    """A fresh data.yaml for model.train() that points train: at the balanced working copy and val:/test:
    straight at the ORIGINAL dataset's images — val/test are never copied (no need, they're never
    mutated), so training always evaluates against the real, untouched data."""
    data = {
        "train": str(train_images_dir),
        "nc": len(yaml_data["names"]),
        "names": yaml_data["names"],
    }
    if val_images_dir:
        data["val"] = str(val_images_dir)
    if test_images_dir:
        data["test"] = str(test_images_dir)
    path = output_dir / "data.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path


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


def verify_and_report_outputs(output_dir: Path) -> dict:
    """Confirms every artifact the user explicitly asked for is really on disk, and prints their exact
    absolute paths in one place — makes this an explicit, checked contract rather than an implicit side
    effect of however Ultralytics happens to be configured."""
    train_dir = output_dir / "train"
    checks = {
        "results.csv": train_dir / "results.csv",
        "results.png": train_dir / "results.png",
        "confusion_matrix.png": train_dir / "confusion_matrix.png",
        "best.pt": train_dir / "weights" / "best.pt",
    }
    gt_images = sorted(train_dir.glob("val_batch*_labels.jpg"))
    pred_images = sorted(train_dir.glob("val_batch*_pred.jpg"))

    print("\n==== Output manifest ====")
    missing = []
    for label, path in checks.items():
        ok = path.exists()
        print(f"  [{'OK' if ok else 'MISSING'}] {label}: {path}")
        if not ok:
            missing.append(label)
    print(f"  [{'OK' if gt_images else 'MISSING'}] ground-truth validation images: "
          f"{len(gt_images)} found" + (f" (e.g. {gt_images[0]})" if gt_images else ""))
    print(f"  [{'OK' if pred_images else 'MISSING'}] prediction validation images: "
          f"{len(pred_images)} found" + (f" (e.g. {pred_images[0]})" if pred_images else ""))
    if not gt_images:
        missing.append("ground-truth validation images")
    if not pred_images:
        missing.append("prediction validation images")
    print("==========================\n")

    if missing:
        print(f"[warn] expected output(s) not found: {', '.join(missing)} — training likely still "
              f"succeeded (this can happen with a very small/edge-case val set), but check {train_dir} "
              f"directly.", file=sys.stderr)
    return {"missing": missing, "gt_images": gt_images, "pred_images": pred_images}


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

        orig_train_images = resolve_split_images_dir(dataset_dir, yaml_data, "train")
        if orig_train_images is None:
            print("[error] could not resolve the train split's images directory from data.yaml", file=sys.stderr)
            sys.exit(1)
        orig_train_labels = labels_dir_for(orig_train_images)

        before_records = parse_labels_in_dir(orig_train_images, orig_train_labels, "train", class_names)
        print(f"[info] train class counts before balancing: {compute_class_counts(before_records)}")

        # Non-destructive: every mutation below targets this working copy only, never dataset_dir itself
        # (also enforced at runtime by balance_train_split's protected_dir assertion below).
        train_copy_images, train_copy_labels = copy_train_split_for_balancing(orig_train_images, orig_train_labels, output_dir)
        print(f"[info] original dataset untouched — balancing a working copy at {train_copy_images.parent}")

        copy_records = parse_labels_in_dir(train_copy_images, train_copy_labels, "train", class_names)
        report = balance_train_split(copy_records, seed=args.seed,
                                      max_drop_fraction=args.max_drop_fraction,
                                      imbalance_threshold=args.imbalance_threshold,
                                      protected_dir=dataset_dir)
        print(f"[balance] {report}")

        # Ground-truth log: re-parse the working copy (post-balance) for train, and the ORIGINAL for
        # val/test — val/test are never modified, so reading the original for them is always accurate.
        post_balance_train = parse_labels_in_dir(train_copy_images, train_copy_labels, "train", class_names)
        val_images = resolve_split_images_dir(dataset_dir, yaml_data, "val")
        test_images = resolve_split_images_dir(dataset_dir, yaml_data, "test")
        val_records = parse_labels_in_dir(val_images, labels_dir_for(val_images), "val", class_names) if val_images else []
        test_records = parse_labels_in_dir(test_images, labels_dir_for(test_images), "test", class_names) if test_images else []
        all_records = post_balance_train + val_records + test_records

        gt_path = output_dir / "ground_truth_positions.csv"
        n_gt = log_ground_truth_positions(all_records, gt_path)
        print(f"[log] wrote {n_gt} ground-truth instance rows to {gt_path}")

        if args.skip_train:
            print("[info] --skip-train set, stopping here.")
            return

        work_yaml = write_working_data_yaml(yaml_data, train_copy_images, val_images, test_images, output_dir)
        best_weights = train_model(work_yaml, args.model, args.epochs, args.imgsz,
                                    args.batch, args.device, args.seed, output_dir)
        print(f"[train] done — best weights at {best_weights}")

        verify_and_report_outputs(output_dir)

        pred_path = output_dir / "predicted_positions.csv"
        n_pred = log_predicted_positions(best_weights, [d for d in (val_images, test_images) if d],
                                          class_names, args.conf, args.device, pred_path)
        print(f"[log] wrote {n_pred} predicted instance rows to {pred_path}")

    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
