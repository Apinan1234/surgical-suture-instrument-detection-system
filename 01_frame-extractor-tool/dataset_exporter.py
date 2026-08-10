from __future__ import annotations

import json
import random
import shutil
import os
from pathlib import Path
import cv2
import numpy as np

# Per-instance annotation attributes carried in attributes.json alongside the dataset. Kept in sync
# with the same-named fields on detector.Detection; a YOLO label line has no column for them.
ATTRIBUTE_NAMES = ("occluded", "truncated")


def _label_line(d: dict, task: str, n_kpts: int = 0) -> str:
    """One YOLO label line for a single detection dict (Detection.to_dict()-shaped)."""
    if task == "segment":
        pts = d.get("points")
        if not pts or len(pts) < 3:
            # legacy / bbox-only detection on this frame — fall back to the bbox's own 4 corners so a
            # mixed dataset (some frames hand-polygoned, most still bbox-only) still exports as fully
            # valid, trainable segmentation labels throughout.
            x1 = d["x_center"] - d["width"] / 2
            y1 = d["y_center"] - d["height"] / 2
            x2 = d["x_center"] + d["width"] / 2
            y2 = d["y_center"] + d["height"] / 2
            pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in pts)
        return f"{d['class_id']} {coords}"
    if task == "pose":
        # Zero-pad every instance up to the pool-wide max keypoint count (n_kpts) so a mixed dataset
        # (varying point counts per instance, or none at all) exports as one valid, rectangular
        # kpt_shape=[n_kpts,3] Ultralytics pose dataset.
        kpts = (d.get("keypoints") or [])[:n_kpts]
        kpts = kpts + [[0.0, 0.0, 0]] * (n_kpts - len(kpts))
        kpt_str = " ".join(f"{x:.6f} {y:.6f} {int(v)}" for x, y, v in kpts)
        base = f"{d['class_id']} {d['x_center']:.6f} {d['y_center']:.6f} {d['width']:.6f} {d['height']:.6f}"
        return f"{base} {kpt_str}".rstrip()
    return f"{d['class_id']} {d['x_center']:.6f} {d['y_center']:.6f} {d['width']:.6f} {d['height']:.6f}"


def export_dataset_pipeline(
    results: list[dict],
    output_dir: str,
    class_names: list[str],
    splits: dict[str, float], # e.g., {"train": 0.7, "val": 0.2, "test": 0.1}
    include_empty: bool = True,
    as_zip: bool = False,
    seed: int = 42,
    preprocess_config: dict = None,
    augment_config: dict = None,
    progress_callback = None,
    task: str = "detect",   # "detect" (bbox) | "segment" (polygon) | "pose" (bbox + keypoints) — Ultralytics label formats
) -> str:
    random.seed(seed)

    # Filter
    pool = [r for r in results if r.get("has_detection") or include_empty]
    if not pool:
        raise ValueError("ไม่มีข้อมูลที่จะ export (pool ว่าง)")

    n_kpts = 0
    if task == "pose":
        for item in pool:
            for d in item.get("detections", []):
                n_kpts = max(n_kpts, len(d.get("keypoints") or []))
        if n_kpts == 0:
            raise ValueError("task='pose' but no detection in the export pool has any keypoints — "
                              "annotate at least one instance with the Keypoint tool first")

    random.shuffle(pool)
    
    total_len = len(pool)
    train_end = int(total_len * splits.get("train", 0.8))
    val_end = train_end + int(total_len * splits.get("val", 0.2))
    
    split_data = {
        "train": pool[:train_end],
        "val": pool[train_end:val_end],
        "test": pool[val_end:]
    }
    
    out = Path(output_dir)
    
    # Preprocessing pipeline
    # For now, just resize using cv2 if specified
    do_resize = preprocess_config and preprocess_config.get("resize", False)
    resize_size = preprocess_config.get("resize_size", 640) if do_resize else None
    
    # Augmentation pipeline using albumentations — bbox-only (BboxParams below), so it never applies
    # to a "segment" export even if a caller passed a stale multiplier > 1 in augment_config.
    do_augment = task == "detect" and augment_config and augment_config.get("multiplier", 1) > 1
    multiplier = augment_config.get("multiplier", 1) if do_augment else 1
    
    transform = None
    if do_augment:
        import albumentations as A
        aug_list = []
        if augment_config.get("flip"):
            aug_list.append(A.HorizontalFlip(p=0.5))
            aug_list.append(A.VerticalFlip(p=0.2))
        if augment_config.get("rotate"):
            aug_list.append(A.Rotate(limit=15, p=0.8, border_mode=cv2.BORDER_CONSTANT))
        if augment_config.get("blur"):
            aug_list.append(A.Blur(blur_limit=3, p=0.3))
        if augment_config.get("brightness"):
            aug_list.append(A.RandomBrightnessContrast(p=0.5))
        if augment_config.get("crop"):
            aug_list.append(A.RandomResizedCrop(size=(resize_size or 640, resize_size or 640) if do_resize else (1000, 1000), scale=(0.8, 1.0), p=0.5))
            
        if aug_list:
            # Albumentations requires BBox format, YOLO is [x_center, y_center, width, height] normalized
            transform = A.Compose(aug_list, bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))

    total_ops = 0
    for split_name, items in split_data.items():
        if split_name == "train":
            total_ops += len(items) * multiplier
        else:
            total_ops += len(items)
            
    done = 0
    total_exported = 0
    train_count = 0
    val_count = 0
    test_count = 0
    # Per-instance annotation attributes, keyed "<split>/<stem>" so an entry maps onto exactly one
    # labels/<split>/<stem>.txt. Written out as attributes.json below, and only if anything is set.
    attributes_index: dict[str, dict] = {}
    # Frame filenames are only unique within one Extract job: numbering restarts at 00000 each run,
    # so a second run with the same prefix yields a second "<prefix>_frame_00000.jpg". A Detect job
    # can span several Extract jobs, so two pool items can share a stem — and sharing a stem means
    # the later one overwrites the earlier one's image AND label, losing an annotated frame with no
    # error and leaving the summary counts overstated. Keep every exported stem distinct instead.
    used_stems: set[str] = set()

    for split_name, items in split_data.items():
        if not items: continue
        img_dir = out / "images" / split_name
        lbl_dir = out / "labels" / split_name
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        
        for item in items:
            src = Path(item["image_path"])
            img = cv2.imread(str(src))
            if img is None: continue
            
            orig_h, orig_w = img.shape[:2]
            
            # Load detections
            bboxes = []
            labels = []
            for d in item.get("detections", []):
                # YOLO format: [x_center, y_center, width, height]
                bboxes.append([d["x_center"], d["y_center"], d["width"], d["height"]])
                labels.append(d["class_id"])
                
            # Preprocess (Resize).
            # `and` binds tighter than `or`, so the do_resize guard has to wrap the whole condition —
            # without the outer parens the train split resized even with resize turned off, and
            # resize_size is None in that case.
            #
            # KNOWN GAP (pre-existing, deliberately left as-is): an augmented train split comes out at
            # mixed resolutions. The base copy is skipped here on the assumption that augmentation
            # resizes instead, but the only size-setting transform below is RandomResizedCrop — which
            # is added only when augment_config["crop"] is on, and even then fires at p=0.5. So with
            # Resize on and multiplier > 1, train images keep their original size while val/test are
            # resize_size square. Harmless for training (Ultralytics resizes to imgsz on load anyway);
            # it costs disk and makes the export look inconsistent. Fix the condition here and add an
            # explicit resize to the augmented branch if that ever matters.
            if do_resize and (split_name != "train" or not do_augment):
                img = cv2.resize(img, (resize_size, resize_size))
                
            # Base save
            stem = src.stem
            if stem in used_stems:
                n = 2
                while f"{stem}__{n}" in used_stems:
                    n += 1
                stem = f"{stem}__{n}"
            used_stems.add(stem)

            save_name = stem + "_0"
            cv2.imwrite(str(img_dir / f"{save_name}.jpg"), img)
            
            inst_attrs = {}
            with open(lbl_dir / f"{save_name}.txt", "w") as f:
                for i, d in enumerate(item.get("detections", [])):
                    f.write(_label_line(d, task, n_kpts) + "\n")
                    # Line i of this .txt is instance i — that index is the only handle a consumer
                    # has for tying an attribute back to a label the YOLO format can't carry it on.
                    flags = {k: True for k in ATTRIBUTE_NAMES if d.get(k)}
                    if flags:
                        inst_attrs[str(i)] = flags
            if inst_attrs:
                attributes_index[f"{split_name}/{save_name}"] = {
                    "split": split_name,
                    "source_image": src.name,
                    "instances": inst_attrs,
                }

            total_exported += 1
            if split_name == "train": train_count += 1
            elif split_name == "val": val_count += 1
            elif split_name == "test": test_count += 1
            
            done += 1
            if progress_callback: progress_callback(done, total_ops)
            
            # Augmentations (Only for Train)
            # NOTE: augmented copies are deliberately absent from attributes.json. Albumentations
            # drops and reorders boxes whose geometry leaves the crop, so an augmented .txt's
            # instance indices do NOT correspond to the base image's — carrying attributes across
            # would be actively wrong, not merely incomplete. (This path already loses
            # points/keypoints for the same reason.)
            if split_name == "train" and do_augment and transform:
                for i in range(1, multiplier):
                    try:
                        transformed = transform(image=img, bboxes=bboxes, class_labels=labels)
                        aug_img = transformed['image']
                        aug_bboxes = transformed['bboxes']
                        aug_labels = transformed['class_labels']
                        
                        aug_name = stem + f"_{i}"
                        cv2.imwrite(str(img_dir / f"{aug_name}.jpg"), aug_img)
                        with open(lbl_dir / f"{aug_name}.txt", "w") as f:
                            for b, l in zip(aug_bboxes, aug_labels):
                                f.write(f"{l} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}\n")
                                
                        total_exported += 1
                        train_count += 1
                    except Exception as e:
                        print(f"Augment error: {e}")
                    
                    done += 1
                    if progress_callback: progress_callback(done, total_ops)

    _write_yaml(out / "data.yaml", class_names, out, task, n_kpts)

    summary = {
        "total_exported":  total_exported,
        "train":           train_count,
        "val":             val_count,
        "test":            test_count,
        "class_names":     class_names,
        "task":            task,
        "kpt_shape":       [n_kpts, 3] if task == "pose" else None,
        "has_attributes":  bool(attributes_index),
    }
    (out / "export_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Must be written before the as_zip block below — make_archive zips `out` as it stands.
    if attributes_index:
        (out / "attributes.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "note": (
                        "Per-instance annotation attributes the YOLO label format cannot carry. "
                        'Keys under "images" are "<split>/<stem>", i.e. exactly '
                        "labels/<split>/<stem>.txt and images/<split>/<stem>.jpg. \"instances\" is "
                        "keyed by the 0-based line number within that .txt. Sparse: only instances "
                        "with at least one attribute set are listed, anything absent is false. "
                        "Augmented training copies are intentionally not covered."
                    ),
                    "attribute_names": list(ATTRIBUTE_NAMES),
                    "images": attributes_index,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    if as_zip:
        archive = shutil.make_archive(str(out), "zip", str(out.parent), out.name)
        return archive

    return str(out)

def _write_yaml(path: Path, class_names: list[str], dataset_root: Path, task: str = "detect", n_kpts: int = 0) -> None:
    # NOTE: Ultralytics data.yaml has no `task:` key — it infers detect/segment/pose from the model
    # checkpoint / CLI command used at train time, not from this file. This comment is informational
    # only, never a structural YAML key (a real `task:` key risks an "unknown key" warning). Pose is
    # the one exception that DOES need an extra structural key — `kpt_shape` — verified against
    # Ultralytics docs (https://docs.ultralytics.com/datasets/pose).
    comment = (
        "# Labels in this dataset are in Ultralytics segmentation polygon format "
        "(class x1 y1 x2 y2 ...). Train with the segment task/model, e.g. "
        "`yolo segment train data=data.yaml model=yolov8n-seg.pt` — Ultralytics infers the task "
        "from the model/CLI command, not from this file.\n"
        if task == "segment" else
        "# Labels in this dataset are in Ultralytics pose format (bbox + keypoints). Train with "
        "`yolo pose train data=data.yaml model=yolov8n-pose.pt` — Ultralytics infers the task from "
        "the model/CLI command, not from this file.\n"
        if task == "pose" else ""
    )
    try:
        import yaml  # type: ignore
        data = {
            "path":  str(dataset_root.resolve()),
            "train": "images/train",
            "val":   "images/val",
            "test":  "images/test",
            "nc":    len(class_names),
            "names": class_names,
        }
        if task == "pose":
            data["kpt_shape"] = [n_kpts, 3]   # ndim=3: (x, y, visibility)
        with open(path, "w", encoding="utf-8") as f:
            if comment:
                f.write(comment)
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)
    except ImportError:
        lines = ([comment.rstrip("\n")] if comment else []) + [
            f"path: {str(dataset_root.resolve())}",
            "train: images/train",
            "val:   images/val",
            "test:  images/test",
            f"nc: {len(class_names)}",
        ] + ([f"kpt_shape: [{n_kpts}, 3]"] if task == "pose" else []) + [
            "names:",
        ] + [f"  - {n}" for n in class_names]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def count_stats(results: list[dict]) -> dict:
    total = len(results)
    with_det = sum(1 for r in results if r.get("has_detection"))
    return {
        "total":          total,
        "with_detection": with_det,
        "empty":          total - with_det,
        "detection_rate": f"{with_det/total*100:.1f}%" if total else "0%",
    }
