#!/usr/bin/env python3
"""Measure how big each class's boxes actually are, straight from the YOLO label files.

Why this exists: `needle` recall sat at 0.2268 after 50 epochs and 0.249 after 150. Training longer
barely moved it, and the confusion matrix says roughly half of all real needles are predicted as
background. That pattern points at object size rather than undertraining -- but "points at" is not
evidence, so this measures it before anyone spends another 2.5 hours on the GPU.

The number that decides the next step is the COCO small-object fraction. COCO calls a box small when
its area is under 32x32 px. Labels are normalised, so at the training resolution of 640 that
threshold is 1024 / 640**2 = 0.0025 of the image. If `needle` is mostly under it while the classes
that score well are not, the fix is resolution (imgsz 640 -> 960) rather than more data or more
epochs -- a detector cannot recover a signal its stride has already thrown away.

Reads labels only: no model, no GPU, no ultralytics. Pure stdlib.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# COCO's small/medium/large cut-offs in pixels, converted to normalised area at a given imgsz.
COCO_SMALL_PX2 = 32 * 32
COCO_MEDIUM_PX2 = 96 * 96


def read_names(data_yaml: Path) -> list[str]:
    """Class names in id order. Hand-parsed: the yaml here is a flat `names:` list and adding a
    dependency for six lines of text would be silly."""
    names, in_names = [], False
    for line in data_yaml.read_text(encoding="utf-8").splitlines():
        if line.startswith("names:"):
            in_names = True
            continue
        if in_names:
            if line.startswith("- "):
                names.append(line[2:].strip())
            elif line.strip() and not line.startswith(" "):
                break
    return names


def collect(labels_dir: Path, n_classes: int) -> dict[int, list[tuple[float, float]]]:
    """{class_id: [(w, h), ...]} in normalised units, over every .txt in the directory."""
    out: dict[int, list[tuple[float, float]]] = {i: [] for i in range(n_classes)}
    for lf in sorted(labels_dir.glob("*.txt")):
        for line in lf.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            # 5 fields is a box. Anything longer is a polygon row, which this project's
            # polygons_to_bboxes.py is supposed to have converted already - if one shows up here the
            # dataset was not cleaned, and silently averaging it in would hide that.
            if len(parts) != 5:
                continue
            try:
                cid = int(parts[0])
                w, h = float(parts[3]), float(parts[4])
            except ValueError:
                continue
            if 0 <= cid < n_classes and w > 0 and h > 0:
                out[cid].append((w, h))
    return out


def pct(values: list[float], q: float) -> float:
    """Percentile by nearest rank. numpy is available in the training venv but not the webapp one,
    and this script should run in either."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(math.ceil(q / 100 * len(s))) - 1))
    return s[k]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=r"D:\ml\data\ssid9.yaml")
    ap.add_argument("--splits", nargs="+", default=["train", "valid", "test"])
    ap.add_argument("--imgsz", type=int, default=640, help="resolution the model trained at")
    ap.add_argument("--out", default="results_boxsize", help="directory for the .md/.csv tables")
    args = ap.parse_args()

    data_yaml = Path(args.data)
    names = read_names(data_yaml)
    if not names:
        print(f"[error] no class names in {data_yaml}", file=sys.stderr)
        sys.exit(1)
    root = Path(str(data_yaml).replace(".yaml", "_bbox"))
    if not root.is_dir():
        # ssid9.yaml points at ssid9_bbox/<split>/images; derive the root from the yaml's own entries
        for line in data_yaml.read_text(encoding="utf-8").splitlines():
            if line.startswith("train:"):
                root = Path(line.split(":", 1)[1].strip()).parent.parent
                break
    print(f"dataset root : {root}")
    print(f"classes      : {len(names)}")
    print(f"imgsz        : {args.imgsz}")

    small_thr = COCO_SMALL_PX2 / (args.imgsz ** 2)
    medium_thr = COCO_MEDIUM_PX2 / (args.imgsz ** 2)
    print(f"COCO small   : area < {small_thr:.5f} of the image ({COCO_SMALL_PX2} px2 at {args.imgsz})")
    print()

    boxes: dict[int, list[tuple[float, float]]] = {i: [] for i in range(len(names))}
    for sp in args.splits:
        d = root / sp / "labels"
        if not d.is_dir():
            print(f"[warn] missing {d} - split skipped", file=sys.stderr)
            continue
        got = collect(d, len(names))
        for cid, lst in got.items():
            boxes[cid].extend(lst)
        print(f"  {sp:6} {sum(len(v) for v in got.values()):>6,} boxes")

    rows = []
    for cid, name in enumerate(names):
        bs = boxes[cid]
        if not bs:
            continue
        areas = [w * h for w, h in bs]
        shorts = [min(w, h) for w, h in bs]
        n_small = sum(1 for a in areas if a < small_thr)
        n_med = sum(1 for a in areas if small_thr <= a < medium_thr)
        rows.append({
            "class": name,
            "boxes": len(bs),
            "median_area": pct(areas, 50),
            "p10_area": pct(areas, 10),
            "median_short_side_px": pct(shorts, 50) * args.imgsz,
            "pct_small": 100.0 * n_small / len(bs),
            "pct_medium": 100.0 * n_med / len(bs),
            "pct_large": 100.0 * (len(bs) - n_small - n_med) / len(bs),
        })

    rows.sort(key=lambda r: r["median_area"])

    hdr = ("class", "boxes", "median_area", "p10_area", "median_short_side_px",
           "pct_small", "pct_medium", "pct_large")
    print()
    print(f"{'class':<20}{'boxes':>8}{'med.area':>11}{'p10 area':>11}{'med.short px':>14}"
          f"{'% small':>9}{'% med':>8}{'% large':>9}")
    print("-" * 90)
    for r in rows:
        print(f"{r['class']:<20}{r['boxes']:>8,}{r['median_area']:>11.5f}{r['p10_area']:>11.5f}"
              f"{r['median_short_side_px']:>14.1f}{r['pct_small']:>9.1f}{r['pct_medium']:>8.1f}"
              f"{r['pct_large']:>9.1f}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import csv
    with open(out / "box_size_by_class.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)
    lines = ["# Box size per class (normalised area; small/medium/large use COCO cut-offs "
             f"at imgsz {args.imgsz})", "",
             "| " + " | ".join(hdr) + " |",
             "| " + " | ".join("---" if i == 0 else "---:" for i in range(len(hdr))) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(
            f"{r[k]:,}" if k == "boxes" else (r[k] if k == "class" else f"{r[k]:.5f}"
                                             if "area" in k else f"{r[k]:.1f}")
            for k in hdr) + " |")
    (out / "box_size_by_class.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {out / 'box_size_by_class.csv'} and .md")


if __name__ == "__main__":
    main()
