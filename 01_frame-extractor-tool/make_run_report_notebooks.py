#!/usr/bin/env python3
"""Build ONE self-contained results notebook per training run, from the output of
report_training_results.py.

Why this exists
---------------
`ssid9_augmentation_ab_RESULTS.ipynb` is the A/B *comparison*: it puts both arms side by side, which
is the right shape for answering "does augmentation help?" but the wrong shape for reporting a single
model. This script writes one notebook per run instead, each covering that run alone across BOTH the
validation and the test split.

The figures are embedded as pre-populated cell outputs, so the notebook renders everywhere (GitHub,
nbviewer, VS Code, Jupyter) with nothing to execute and no GPU. Re-running the cells reproduces the
same images from `results*/` if those directories are present.

Inputs are the two report directories, which must already exist:
    python report_training_results.py --runs noaug=... aug=... --out results      --split val
    python report_training_results.py --runs noaug=... aug=... --out results_test --split test

Usage
-----
    python make_run_report_notebooks.py
    python make_run_report_notebooks.py --runs noaug aug --val-dir results --test-dir results_test

Output is pure ASCII on purpose -- this project's console is cp874 (Thai) and non-ASCII in print()
raises UnicodeEncodeError.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RUN_TITLES = {
    "noaug": ("Run A - augmentation OFF",
              "Every Ultralytics augmentation hyperparameter zeroed: no mosaic, no mixup, no HSV "
              "jitter, no flips, no scale/translate. This is the control arm."),
    "aug": ("Run B - augmentation ON",
            "Ultralytics' default augmentation pipeline (mosaic, HSV, scale, translate, horizontal "
            "flip). Everything else is identical to Run A, including the seed."),
    "aug150": ("Run C - 640 px, trained to convergence",
               "Run B's settings carried to 150 epochs instead of 50, to find out whether that arm "
               "was simply still climbing when it ran out. It was: the best epoch moved from 50 to "
               "120. This is the 640 px ceiling."),
    "aug960": ("Run D - 960 px",
               "Run C with one thing changed: imgsz 640 -> 960. Same weights, data, seed, epochs "
               "and augmentation, and the batch stayed at 8. It exists to test whether `needle` was "
               "failing because its boxes are too small to survive the network's stride -- the "
               "label files put its median short side at 12.4 px at 640, with 80.9% of its boxes "
               "below COCO's small-object cut-off."),
}


_ID_SEQ = [0]


def _next_id() -> str:
    """nbformat 4.5 requires a unique id per cell; a plain counter keeps regenerated notebooks
    byte-comparable instead of churning random uuids on every run."""
    _ID_SEQ[0] += 1
    return f"cell-{_ID_SEQ[0]:03d}"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "id": _next_id(), "metadata": {},
            "source": text.splitlines(keepends=True)}


def figure(png: Path, caption: str, counter: list[int]) -> list[dict]:
    """A caption cell plus a code cell carrying the PNG as a pre-rendered output."""
    if not png.exists():
        return [md(f"> _Figure missing: `{png.name}` was not produced by the report run._\n")]
    counter[0] += 1
    b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    rel = f"{png.parent.name}/{png.name}"
    code = {
        "cell_type": "code",
        "id": _next_id(),
        "execution_count": counter[0],
        "metadata": {},
        "source": [f"display(Image(filename={rel!r}))"],
        "outputs": [{"output_type": "display_data",
                     "data": {"image/png": b64},
                     "metadata": {}}],
    }
    return [md(f"**{caption}**\n"), code]


def load_metrics(report_dir: Path, label: str, split: str) -> dict | None:
    path = report_dir / f".metrics_{label}_{split}.json"
    if not path.exists():
        print(f"  [warn] {path} not found - that split is omitted", file=sys.stderr)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def f1_of(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if (p + r) else 0.0


def pct(v) -> str:
    return f"{v * 100:.2f}%"


def overall_table(val: dict | None, test: dict | None) -> str:
    """The headline table: one row per metric, one column per split."""
    cols, data = [], []
    for name, m in (("Validation Set", val), ("Test Set", test)):
        if not m:
            continue
        o = m["overall"]
        cols.append(name)
        data.append({"mAP@50": o["mAP50"], "mAP@50-95": o["mAP50_95"],
                     "Precision": o["precision"], "Recall": o["recall"],
                     "F1": f1_of(o["precision"], o["recall"])})
    if not cols:
        return "_No validation metrics available._\n"
    lines = ["| Metric | " + " | ".join(cols) + " |",
             "| --- | " + " | ".join("---:" for _ in cols) + " |"]
    for metric in ("mAP@50", "Precision", "Recall", "F1", "mAP@50-95"):
        lines.append(f"| {metric} | " + " | ".join(pct(d[metric]) for d in data) + " |")
    return "\n".join(lines) + "\n"


def per_class_table(val: dict | None, test: dict | None) -> str:
    """Average precision by class, both splits in one table so they can be read against each other."""
    base = val or test
    if not base:
        return "_No per-class metrics available._\n"
    by_split = {}
    for name, m in (("val", val), ("test", test)):
        if m:
            by_split[name] = {c["class"]: c for c in m["per_class"]}
    header = ["| Class |"]
    align = ["| --- |"]
    for name in by_split:
        pretty = "Validation" if name == "val" else "Test"
        header.append(f" {pretty} instances | {pretty} mAP@50 | {pretty} Precision |"
                      f" {pretty} Recall |")
        align.append(" ---: | ---: | ---: | ---: |")
    lines = ["".join(header), "".join(align)]
    order = sorted(base["per_class"], key=lambda c: -c["mAP50"])
    for row in order:
        cls = row["class"]
        cells = [f"| {cls} |"]
        for name, lut in by_split.items():
            c = lut.get(cls)
            if not c:
                cells.append(" - | - | - | - |")
                continue
            cells.append(f" {c['instances']} | {pct(c['mAP50'])} | {pct(c['precision'])} |"
                         f" {pct(c['recall'])} |")
        lines.append("".join(cells))
    return "\n".join(lines) + "\n"


def build_notebook(label: str, val_dir: Path, test_dir: Path) -> dict:
    title, blurb = RUN_TITLES.get(label, (f"Run {label}", ""))
    val = load_metrics(val_dir, label, "val")
    test = load_metrics(test_dir, label, "test")
    counter = [0]
    _ID_SEQ[0] = 0  # ids restart per notebook; they only have to be unique within one file
    cells: list[dict] = []

    cells.append(md(
        f"# SSID 9-class detector - {title}\n"
        f"\n"
        f"{blurb}\n"
        f"\n"
        f"Model: YOLO11n | 50 epochs | imgsz 640 | batch 8 | seed fixed | RTX 3050 Laptop 4 GB\n"
        f"\n"
        f"Dataset: 2,190 images (train 1,575 / val 400 / test 215), 22,957 boxes, 9 classes.\n"
        f"Every label row is a plain bounding box: the Roboflow export mixed bbox and polygon rows,\n"
        f"which Ultralytics mis-reads per file, so it was normalised with `polygons_to_bboxes.py`\n"
        f"first. Training a fresh export without that step corrupts thousands of boxes silently.\n"
        f"\n"
        f"**No class rebalancing was applied.** `finger` really does carry 7,157 of the 16,421\n"
        f"training boxes; downsampling it would have deleted whole images, taking the other classes\n"
        f"in those frames with them. The imbalance is a property of the reported result, not a bug.\n"))

    cells.append(md("## 1. Metrics\n\nAll figures are for this run only, at the default confidence "
                    "threshold used by the validator.\n\n" + overall_table(val, test)))

    cells.append(md("## 2. Average precision by class (mAP@50)\n\n" + per_class_table(val, test)))
    cells += figure(val_dir / f"{label}_per_class_map50.png",
                    "Per-class detection quality - validation set", counter)
    cells += figure(test_dir / f"{label}_per_class_map50.png",
                    "Per-class detection quality - test set", counter)

    cells.append(md(
        "## 3. Training graphs\n"
        "\n"
        "YOLO11 optimises **three** losses. There is no objectness loss - that belonged to YOLOv5 and\n"
        "v7; distribution focal loss (DFL) is what replaced it. Each component is plotted on its own\n"
        "axes because `cls_loss` starts an order of magnitude above `box_loss` and flattens the\n"
        "smaller curve when they share a scale.\n"))
    cells += figure(val_dir / f"{label}_box_loss.png", "Box loss (localisation)", counter)
    cells += figure(val_dir / f"{label}_cls_loss.png", "Class loss (classification)", counter)
    cells += figure(val_dir / f"{label}_dfl_loss.png", "DFL loss (replaces objectness)", counter)
    cells += figure(val_dir / f"{label}_loss_curve.png", "Total loss, train vs validation", counter)
    cells += figure(val_dir / f"{label}_learning_curve_map.png", "mAP per epoch", counter)
    cells += figure(val_dir / f"{label}_precision_recall_per_epoch.png",
                    "Precision and recall per epoch", counter)
    cells += figure(val_dir / f"{label}_lr_schedule.png", "Learning rate schedule", counter)

    cells.append(md(
        "## 4. Confusion matrix\n"
        "\n"
        "Columns are the true class, rows are what the model predicted, and the extra `background`\n"
        "row/column is the one that matters most: the background **row** counts detections that\n"
        "matched no object (false positives), and the background **column** counts real objects the\n"
        "model missed entirely (false negatives). Normalisation is per true class, so each column\n"
        "reads as \"of all the real X in this split, what did the model call them?\"\n"))
    cells += figure(val_dir / f"{label}_confusion_matrix_normalized.png",
                    "Confusion matrix, normalised per true class - validation set", counter)
    cells += figure(val_dir / f"{label}_confusion_matrix_raw.png",
                    "Confusion matrix, raw counts - validation set", counter)
    cells += figure(test_dir / f"{label}_confusion_matrix_normalized.png",
                    "Confusion matrix, normalised per true class - test set", counter)

    cells.append(md("## 5. Threshold behaviour\n\nHow precision, recall and F1 move as the confidence "
                    "threshold changes - the curves to consult before picking an operating point.\n"))
    cells += figure(val_dir / f"{label}_pr_curve_per_class.png", "Precision-recall per class", counter)
    cells += figure(val_dir / f"{label}_f1_confidence_curve.png", "F1 vs confidence", counter)
    cells += figure(val_dir / f"{label}_precision_confidence_curve.png",
                    "Precision vs confidence", counter)
    cells += figure(val_dir / f"{label}_recall_confidence_curve.png", "Recall vs confidence", counter)

    cells.append(md("## 6. Error analysis\n\nThe easiest and hardest validation frames, ranked by "
                    "false positives plus false negatives at IoU 0.5. Green solid is ground truth, "
                    "orange dashed is the prediction.\n"))
    cells += figure(val_dir / f"{label}_error_analysis_grid.png",
                    "Best and worst validation frames", counter)

    cells.append(md("## 7. Class distribution\n\nInstances (boxes), not images: one frame routinely "
                    "holds several objects, so image counts would understate the imbalance.\n"))
    cells += figure(val_dir / "class_distribution.png", "Instances per class per split", counter)

    # The imports the display cells rely on, placed first so a top-to-bottom re-run works.
    cells.insert(1, {"cell_type": "code", "id": _next_id(), "execution_count": None,
                     "metadata": {},
                     "source": ["from IPython.display import Image, display"],
                     "outputs": []})

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="One results notebook per training run.")
    ap.add_argument("--runs", nargs="+", default=["noaug", "aug"])
    ap.add_argument("--val-dir", default="results")
    ap.add_argument("--test-dir", default="results_test")
    ap.add_argument("--out-prefix", default="ssid9")
    args = ap.parse_args()

    val_dir, test_dir = Path(args.val_dir), Path(args.test_dir)
    if not val_dir.is_dir():
        print(f"[error] {val_dir} not found - run report_training_results.py first", file=sys.stderr)
        sys.exit(1)

    for label in args.runs:
        nb = build_notebook(label, val_dir, test_dir)
        out = Path(f"{args.out_prefix}_{label}_RESULTS.ipynb")
        out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
        figs = sum(1 for c in nb["cells"] if c["cell_type"] == "code" and c.get("outputs"))
        print(f"[ok] {out}  ({figs} figures, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
