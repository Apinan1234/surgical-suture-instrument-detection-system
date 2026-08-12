#!/usr/bin/env python3
"""Normalize a YOLO dataset whose labels MIX bbox rows and polygon rows into one that is pure bbox.

Why this exists
---------------
The Roboflow project `ssid` is annotated with a mix of boxes and polygons (the webapp grew polygon
support part-way through labelling), so a single downloaded export contains both `cls xc yc w h` rows
and `cls x1 y1 x2 y2 ...` polygon rows -- often inside the SAME label file.

Ultralytics decides "is this a segment file?" per FILE, not per row
(`ultralytics/data/utils.py`: `if any(len(x) > 6 for x in lb) and (not keypoint)`). In a mixed file it
therefore reinterprets every plain bbox row as a 2-point polygon: `[xc, yc, w, h]` is read as the two
points (xc, yc) and (w, h), and `segments2boxes` returns the box spanning them. The result is a
silently wrong box, e.g.

    real row  : 8 0.5733 0.4782 0.1748 0.0357
    read as   : 8 0.3741 0.2569 0.3984 0.4425

Measured on the 2026-08-11 export that hits 8,047 of 14,733 boxes (train 5,642 / val 1,597 / test 808)
-- it would corrupt both training and evaluation. Converting each polygon to its own bounding box up
front removes the mixed-file condition entirely, so every file takes Ultralytics' plain-bbox path.

A polygon's bounding box IS the object's bounding box, so no information a detection model can use is
lost. The conversion is non-destructive: the source dataset is only ever read.

Usage
-----
    python polygons_to_bboxes.py --src <dataset-dir> --dst <output-dir>
    python polygons_to_bboxes.py --src <dataset-dir> --dst <output-dir> --labels-only  # audit, no images

Output is pure ASCII on purpose -- this project's console is cp874 (Thai) and any non-ASCII in print()
raises UnicodeEncodeError and aborts the run.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def polygon_to_bbox(coords: list[float]) -> tuple[float, float, float, float]:
    """(xc, yc, w, h) of the axis-aligned box spanning a flat [x1,y1,x2,y2,...] polygon, clamped to
    [0,1]. Clamping matters because Ultralytics asserts `points.max() <= 1.01` and a hand-drawn polygon
    can run a hair past the image edge."""
    xs = [min(max(v, 0.0), 1.0) for v in coords[0::2]]
    ys = [min(max(v, 0.0), 1.0) for v in coords[1::2]]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return (x_min + x_max) / 2, (y_min + y_max) / 2, x_max - x_min, y_max - y_min


def convert_label_file(src: Path, dst: Path) -> dict:
    """Rewrite one label file so every row is `cls xc yc w h`. bbox rows pass through byte-identical;
    polygon rows become their bounding box. Returns per-file counts for the summary."""
    stats = {"bbox": 0, "polygon": 0, "degenerate": 0, "malformed": 0}
    out_lines: list[str] = []
    for lineno, raw in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 5:
            out_lines.append(line)  # already a bbox -- leave exactly as-is
            stats["bbox"] += 1
            continue
        # A polygon needs a class + at least 3 (x,y) pairs; anything else we cannot interpret.
        if len(parts) < 7 or len(parts) % 2 == 0:
            print(f"[warn] {src.name}:{lineno}: {len(parts)} values - not a bbox or a polygon, dropping")
            stats["malformed"] += 1
            continue
        cls = parts[0]
        try:
            coords = [float(v) for v in parts[1:]]
        except ValueError:
            print(f"[warn] {src.name}:{lineno}: non-numeric coordinates, dropping")
            stats["malformed"] += 1
            continue
        xc, yc, w, h = polygon_to_bbox(coords)
        if w <= 0 or h <= 0:
            # A zero-area box would be a free false negative for the model to learn from.
            print(f"[warn] {src.name}:{lineno}: polygon has zero width/height, dropping")
            stats["degenerate"] += 1
            continue
        out_lines.append(f"{cls} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
        stats["polygon"] += 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    return stats


def convert_split(src_split: Path, dst_split: Path, copy_images: bool) -> dict:
    src_labels, src_images = src_split / "labels", src_split / "images"
    if not src_labels.is_dir():
        return {}
    totals = {"files": 0, "mixed_files": 0, "bbox": 0, "polygon": 0, "degenerate": 0, "malformed": 0}
    for lf in sorted(src_labels.glob("*.txt")):
        st = convert_label_file(lf, dst_split / "labels" / lf.name)
        totals["files"] += 1
        # A file that held both kinds is exactly the case Ultralytics would have mis-read.
        if st["bbox"] and st["polygon"]:
            totals["mixed_files"] += 1
        for k in ("bbox", "polygon", "degenerate", "malformed"):
            totals[k] += st[k]

    if copy_images and src_images.is_dir():
        dst_images = dst_split / "images"
        dst_images.mkdir(parents=True, exist_ok=True)
        for img in sorted(src_images.iterdir()):
            if img.suffix.lower() in IMAGE_EXTS:
                shutil.copy2(img, dst_images / img.name)
    return totals


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert mixed bbox/polygon YOLO labels to pure bbox.")
    ap.add_argument("--src", required=True, help="source dataset dir (contains data.yaml + train/valid/test)")
    ap.add_argument("--dst", required=True, help="output dir; created if absent, must not be inside --src")
    ap.add_argument("--splits", nargs="*", default=["train", "valid", "test"])
    ap.add_argument("--labels-only", action="store_true",
                    help="convert labels but do not copy images (fast audit run)")
    args = ap.parse_args()

    src, dst = Path(args.src).resolve(), Path(args.dst).resolve()
    if not (src / "data.yaml").exists():
        print(f"[error] {src}/data.yaml not found", file=sys.stderr)
        sys.exit(1)
    # Writing inside the source would let a re-run read its own output and double-convert.
    if dst == src or str(dst).startswith(str(src) + "\\") or str(dst).startswith(str(src) + "/"):
        print(f"[error] --dst must not be inside --src (source is read-only by design)", file=sys.stderr)
        sys.exit(1)
    dst.mkdir(parents=True, exist_ok=True)

    grand = {"files": 0, "mixed_files": 0, "bbox": 0, "polygon": 0, "degenerate": 0, "malformed": 0}
    for split in args.splits:
        t = convert_split(src / split, dst / split, copy_images=not args.labels_only)
        if not t:
            print(f"[info] split '{split}' not present, skipping")
            continue
        print(f"[{split}] files={t['files']} mixed={t['mixed_files']} bbox_rows={t['bbox']} "
              f"polygon_rows_converted={t['polygon']} dropped={t['degenerate'] + t['malformed']}")
        for k in grand:
            grand[k] += t[k]

    # data.yaml is copied verbatim: its relative ../<split>/images paths still resolve in the copy.
    shutil.copy2(src / "data.yaml", dst / "data.yaml")

    print("\n==== summary ====")
    print(f"  source (unmodified) : {src}")
    print(f"  converted copy      : {dst}")
    print(f"  label files         : {grand['files']}")
    print(f"  mixed files fixed   : {grand['mixed_files']}  <- these were the corrupting ones")
    print(f"  bbox rows kept      : {grand['bbox']}")
    print(f"  polygons -> bbox    : {grand['polygon']}")
    print(f"  rows dropped        : {grand['degenerate'] + grand['malformed']}")
    print(f"  total boxes out     : {grand['bbox'] + grand['polygon']}")
    if args.labels_only:
        print("  NOTE: --labels-only, images were NOT copied; this copy cannot be trained on yet.")
    print("=================")


if __name__ == "__main__":
    main()
