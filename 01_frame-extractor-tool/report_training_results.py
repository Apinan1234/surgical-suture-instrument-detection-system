#!/usr/bin/env python3
"""Build the full plot + table report for one or more Ultralytics detection runs.

Every figure is written as its OWN file (no subplot grids) into --out, and every table is written twice,
as .csv and as a GitHub-flavoured markdown .md, so the numbers can be pasted straight into a report.

Scope: this is an OBJECT DETECTION project (Ultralytics YOLO), so the classification-only and
regression-only outputs (ROC/AUC one-vs-rest, classification report, predicted-vs-actual scatter,
residuals, MAE/RMSE/R2) are deliberately NOT produced -- they have no meaning for a detector. The
detection equivalents (PR curve per class, F1-confidence, mAP curves, per-class AP table) are produced
instead.

Usage
-----
    python report_training_results.py --runs noaug=D:\\ml\\runs\\ssid9_noaug aug=D:\\ml\\runs\\ssid9_aug
    python report_training_results.py --runs noaug=... --out results --split val --device 0
    python report_training_results.py --runs noaug=... --reuse-cached   # re-plot without re-running val

Only matplotlib + numpy + ultralytics are used (no pandas, no seaborn) -- everything else is stdlib.
All console output is pure ASCII: this project's console is cp874 (Thai) and non-ASCII in print()
raises UnicodeEncodeError.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")  # file output only, never a GUI window
import matplotlib.pyplot as plt

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# A .pt is a pickle: loading one can execute code. This script loads best.pt from whatever --runs
# points at, so it needs the same restricted-load default detector.py sets for the app. Must happen
# before ultralytics is ever imported (it reads SAFE_LOAD once, at import time); every import of it
# here is lazy, inside the functions below. Blank counts as unset -- same reasoning as detector.py.
if not (os.environ.get("ULTRALYTICS_SAFE_LOAD") or "").strip():
    os.environ["ULTRALYTICS_SAFE_LOAD"] = "true"


# ────────────────────────────── One shared visual theme ──────────────────────────────
# Every figure in the report goes through apply_theme() so colours, fonts, grid and DPI are identical
# across all of them. PALETTE is Okabe-Ito, which stays distinguishable in greyscale print and for the
# common forms of colour blindness -- worth it for a report with 9 classes on one axis.
PALETTE = [
    "#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00",
    "#56B4E9", "#F0E442", "#000000", "#8C564B",
]
RUN_COLORS = {0: "#0072B2", 1: "#D55E00", 2: "#009E73", 3: "#CC79A7"}
FIGSIZE = (9, 5.5)
DPI = 150


def apply_theme() -> None:
    plt.rcParams.update({
        "figure.figsize": FIGSIZE,
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
        "legend.frameon": False,
        "lines.linewidth": 2.0,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def save_fig(fig, out_dir: Path, name: str, produced: list[str]) -> None:
    path = out_dir / name
    fig.savefig(path)
    plt.close(fig)
    produced.append(name)
    print(f"  [fig] {name}")


# ────────────────────────────── Tables: always .csv AND .md ──────────────────────────────

def write_table(rows: list[dict], out_dir: Path, stem: str, produced: list[str],
                title: str | None = None, float_fmt: str = "{:.4f}") -> None:
    """One table -> two files. Callers pass a list of uniform dicts; column order follows the first row."""
    if not rows:
        print(f"  [skip] {stem}: no rows")
        return
    cols = list(rows[0].keys())

    with open(out_dir / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    def cell(v) -> str:
        if isinstance(v, float):
            return "n/a" if (math.isnan(v) or math.isinf(v)) else float_fmt.format(v)
        return str(v)

    lines = []
    if title:
        lines += [f"# {title}", ""]
    lines.append("| " + " | ".join(cols) + " |")
    # Numeric columns right-align; the first column is almost always a label, so left-align it.
    aligns = ["---" if i == 0 else "---:" for i in range(len(cols))]
    lines.append("| " + " | ".join(aligns) + " |")
    for r in rows:
        lines.append("| " + " | ".join(cell(r[c]) for c in cols) + " |")
    (out_dir / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    produced.extend([f"{stem}.csv", f"{stem}.md"])
    print(f"  [tbl] {stem}.csv + {stem}.md")


# ────────────────────────────── Reading a run off disk ──────────────────────────────

def read_results_csv(run_dir: Path) -> dict[str, np.ndarray]:
    """Ultralytics' per-epoch log as {column_name: float array}. Headers carry stray spaces in some
    versions, hence the strip()."""
    path = run_dir / "train" / "results.csv"
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        cols: list[list[float]] = [[] for _ in header]
        for row in reader:
            if len(row) != len(header):
                continue
            for i, v in enumerate(row):
                try:
                    cols[i].append(float(v))
                except ValueError:
                    cols[i].append(float("nan"))
    return {h: np.array(c, dtype=float) for h, c in zip(header, cols)}


def read_args_yaml(run_dir: Path) -> dict:
    """args.yaml holds the RESOLVED training config -- the ground truth for what a run actually did.
    Parsed with a tiny scalar reader so this script needs no yaml dependency beyond what is present."""
    path = run_dir / "train" / "args.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        out = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip()
        return out


def resolve_split_dir(data_yaml: Path, cfg: dict, value) -> Path | None:
    """A data.yaml split entry -> a real directory, or None if it cannot be found.

    Absolute wins. A relative entry is resolved the way ultralytics does (against `path:`, itself
    relative to the yaml's own directory) and then, if that misses, with any `..` stripped: Roboflow
    exports ship `../train/images` beside a yaml that already sits at the dataset root. Returning
    None rather than a non-existent path is the point -- a caller that accepts a missing directory
    publishes an all-zero table as if it had been measured."""
    p = Path(str(value))
    if p.is_absolute():
        return p if p.is_dir() else None
    root = Path(str(cfg.get("path", ".")))
    if not root.is_absolute():
        root = data_yaml.parent / root
    stripped = Path(*[part for part in p.parts if part != ".."]) if ".." in p.parts else p
    for cand in ((root / p), (data_yaml.parent / p), (data_yaml.parent / stripped)):
        if cand.is_dir():
            return cand.resolve()
    return None


def count_split_classes(images_dir: Path, n_classes: int) -> np.ndarray:
    """Instances per class id in one split, read from its YOLO .txt labels."""
    counts = np.zeros(n_classes, dtype=int)
    labels_dir = images_dir.parent / "labels"
    if not labels_dir.is_dir():
        print(f"  [warn] no labels dir beside {images_dir} - this split is not measured",
              file=sys.stderr)
        return counts
    for lf in labels_dir.glob("*.txt"):
        for line in lf.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue
            try:
                cid = int(parts[0])
            except ValueError:
                continue
            if 0 <= cid < n_classes:
                counts[cid] += 1
    return counts


# ────────────────────────────── Validation (the source of per-class numbers) ──────────────────────────────

def run_validation(run_dir: Path, split: str, device: str, cache: Path, reuse: bool) -> dict | None:
    """Run `model.val()` once per run and reduce it to plain JSON-able arrays.

    Cached because validation is the slow part of this script and the plots get iterated on far more
    often than the numbers change."""
    if reuse and cache.exists():
        print(f"  [val] reusing cached metrics {cache.name}")
        with open(cache, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("curves", "confusion_matrix"):
            if k in d and d[k] is not None:
                if k == "confusion_matrix":
                    d[k] = np.array(d[k])
                else:
                    for c in d[k]:
                        c["x"] = np.array(c["x"])
                        c["y"] = np.array(c["y"])
        return d

    weights = run_dir / "train" / "weights" / "best.pt"
    data_yaml = run_dir / "data.yaml"
    if not weights.exists():
        print(f"  [warn] no best.pt in {run_dir} - skipping validation-derived outputs", file=sys.stderr)
        return None
    if not data_yaml.exists():
        print(f"  [warn] no data.yaml in {run_dir} - skipping validation-derived outputs", file=sys.stderr)
        return None

    from ultralytics import YOLO
    print(f"  [val] running {split} validation on {weights.name} (device={device})")
    try:
        model = YOLO(str(weights))
        # plots=True is NOT cosmetic here: ultralytics only fills the confusion matrix inside
        # `if self.args.plots:` (models/yolo/detect/val.py), so plots=False silently hands back an
        # all-zero matrix -- which is what produced four blank confusion-matrix figures. It also
        # writes ultralytics' own PNGs into the run dir, which this report simply ignores.
        # project/name pin ultralytics' own plot output beside the run instead of letting it invent a
        # runs/detect/val* tree under whatever the current working directory happens to be.
        m = model.val(data=str(data_yaml), split=split, device=device, plots=True, verbose=False,
                      project=str(run_dir), name=f"val_{split}", exist_ok=True)
    except Exception as e:
        # Most often the run's data.yaml points at a dataset that has since moved. One run failing to
        # validate must not cost the report every other run's figures.
        print(f"  [warn] validation failed ({type(e).__name__}: {e}) - validation-derived outputs "
              f"skipped for this run", file=sys.stderr)
        return None

    names = m.names if isinstance(m.names, dict) else {i: n for i, n in enumerate(m.names)}
    ap_idx = list(np.array(m.ap_class_index).tolist())

    per_class = []
    for i, cid in enumerate(ap_idx):
        p, r, ap50, ap = m.box.class_result(i)
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        support = int(m.nt_per_class[cid]) if m.nt_per_class is not None else -1
        images = int(m.nt_per_image[cid]) if m.nt_per_image is not None else -1
        per_class.append({"class_id": int(cid), "class": names[int(cid)], "images": images,
                          "instances": support, "precision": float(p), "recall": float(r),
                          "f1": float(f1), "mAP50": float(ap50), "mAP50_95": float(ap)})

    mp, mr, map50, map5095 = m.mean_results()
    overall = {"precision": float(mp), "recall": float(mr),
               "mAP50": float(map50), "mAP50_95": float(map5095), "fitness": float(m.fitness)}

    curves = []
    try:
        for (x, y, xlabel, ylabel), label in zip(m.curves_results, m.curves):
            curves.append({"x": np.asarray(x), "y": np.asarray(y),
                           "xlabel": str(xlabel), "ylabel": str(ylabel), "name": str(label)})
    except Exception as e:  # curve export is a convenience, never worth failing the report over
        print(f"  [warn] could not read curves_results: {e}", file=sys.stderr)

    cm = None
    try:
        cm = np.asarray(m.confusion_matrix.matrix)
    except Exception as e:
        print(f"  [warn] could not read confusion matrix: {e}", file=sys.stderr)

    # curves_results rows are ordered by ap_class_index (only the classes PRESENT in this split), not
    # by class id -- without carrying it, a split missing one class shifts every later curve's legend.
    out = {"names": {int(k): v for k, v in names.items()}, "per_class": per_class,
           "overall": overall, "curves": curves, "confusion_matrix": cm, "split": split,
           "ap_class_index": [int(c) for c in ap_idx]}

    serializable = dict(out)
    serializable["curves"] = [{**c, "x": c["x"].tolist(), "y": c["y"].tolist()} for c in curves]
    serializable["confusion_matrix"] = cm.tolist() if cm is not None else None
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=1)
    return out


# ────────────────────────────── Per-run figures ──────────────────────────────

def plot_loss_curves(res: dict, label: str, out: Path, produced: list[str]) -> None:
    """Item 1 -- train vs val loss. Ultralytics logs three components; their sum is the comparable
    'total loss' and the clearest single overfitting signal."""
    ep = res.get("epoch")
    if ep is None:
        return
    tr_keys = ["train/box_loss", "train/cls_loss", "train/dfl_loss"]
    va_keys = ["val/box_loss", "val/cls_loss", "val/dfl_loss"]
    if not all(k in res for k in tr_keys + va_keys):
        return
    train_total = sum(res[k] for k in tr_keys)
    val_total = sum(res[k] for k in va_keys)
    # read_results_csv turns unparseable cells into NaN, so a present-but-empty loss column clears the
    # membership check above and then blows up nanargmin, killing every figure after this one.
    if not np.isfinite(val_total).any():
        print(f"  [skip] {label}_loss_curve: val loss column has no usable values", file=sys.stderr)
        return

    fig, ax = plt.subplots()
    ax.plot(ep, train_total, label="train loss (box+cls+dfl)", color=PALETTE[0])
    ax.plot(ep, val_total, label="val loss (box+cls+dfl)", color=PALETTE[1])
    best = int(np.nanargmin(val_total))
    ax.axvline(ep[best], color="grey", ls=":", lw=1.5)
    ax.annotate(f"min val loss\nepoch {int(ep[best])}", (ep[best], val_total[best]),
                textcoords="offset points", xytext=(8, 14), fontsize=9, color="grey")
    ax.set_xlabel("epoch"); ax.set_ylabel("loss")
    ax.set_title(f"Training vs validation loss - {label}")
    ax.legend()
    save_fig(fig, out, f"{label}_loss_curve.png", produced)


def plot_loss_breakdown(res: dict, label: str, out: Path, produced: list[str]) -> None:
    """Item 15 -- box / cls / dfl separately. YOLO has no objectness loss (that was v5/v7); dfl is its
    modern replacement, so the breakdown is box+cls+dfl."""
    ep = res.get("epoch")
    if ep is None:
        return
    parts = [("box_loss", "box"), ("cls_loss", "classification"), ("dfl_loss", "dfl (distribution focal)")]
    fig, ax = plt.subplots()
    for i, (key, nice) in enumerate(parts):
        if f"train/{key}" in res:
            ax.plot(ep, res[f"train/{key}"], color=PALETTE[i], label=f"train {nice}")
        if f"val/{key}" in res:
            ax.plot(ep, res[f"val/{key}"], color=PALETTE[i], ls="--", label=f"val {nice}")
    ax.set_xlabel("epoch"); ax.set_ylabel("loss component")
    ax.set_title(f"Loss breakdown by component - {label}")
    ax.legend(ncol=2, fontsize=9)
    save_fig(fig, out, f"{label}_loss_breakdown.png", produced)


def plot_loss_components_separately(res: dict, label: str, out: Path, produced: list[str]) -> None:
    """One figure per loss component, on top of the combined breakdown.

    A report that walks the reader through box / class / dfl one at a time needs them on their own
    axes: sharing one chart forces a single y-scale, and cls_loss starts an order of magnitude above
    box_loss, so the smaller curve reads as a flat line.

    Note for whoever writes that report: YOLO11 has **no objectness loss**. That was YOLOv5/v7. The
    three components here are box (localisation), cls (classification) and dfl (distribution focal,
    which is what replaced objectness).
    """
    ep = res.get("epoch")
    if ep is None:
        return
    for key, nice, fname in (("box_loss", "Box loss (localisation)", "box_loss"),
                             ("cls_loss", "Class loss (classification)", "cls_loss"),
                             ("dfl_loss", "DFL loss (distribution focal)", "dfl_loss")):
        if f"train/{key}" not in res and f"val/{key}" not in res:
            continue
        fig, ax = plt.subplots()
        if f"train/{key}" in res:
            ax.plot(ep, res[f"train/{key}"], color=PALETTE[0], label="train")
        if f"val/{key}" in res:
            ax.plot(ep, res[f"val/{key}"], color=PALETTE[1], label="validation")
        ax.set_xlabel("epoch"); ax.set_ylabel(nice.split(" (")[0].lower())
        ax.set_title(f"{nice} - {label}")
        ax.legend()
        save_fig(fig, out, f"{label}_{fname}.png", produced)


def plot_map_curves(res: dict, label: str, out: Path, produced: list[str]) -> None:
    """Items 2 + 12 -- the headline detection metrics per epoch. A detector has no 'train mAP' (it is
    never evaluated on the augmented train stream), so this is validation-only by construction."""
    ep = res.get("epoch")
    if ep is None or "metrics/mAP50(B)" not in res:
        return
    fig, ax = plt.subplots()
    ax.plot(ep, res["metrics/mAP50(B)"], label="mAP@50 (val)", color=PALETTE[0])
    if "metrics/mAP50-95(B)" in res:
        ax.plot(ep, res["metrics/mAP50-95(B)"], label="mAP@50-95 (val)", color=PALETTE[1])
    m = res["metrics/mAP50(B)"]
    if not np.isfinite(m).any():
        print(f"  [skip] {label}_learning_curve_map: mAP column is unusable", file=sys.stderr)
        plt.close(fig)
        return
    b = int(np.nanargmax(m))
    ax.scatter([ep[b]], [m[b]], color=PALETTE[0], zorder=5, s=45)
    ax.annotate(f"best {m[b]:.3f} @ epoch {int(ep[b])}", (ep[b], m[b]),
                textcoords="offset points", xytext=(-10, -20), fontsize=9)
    ax.set_xlabel("epoch"); ax.set_ylabel("mAP")
    ax.set_ylim(0, 1)
    ax.set_title(f"Learning curve - mAP per epoch - {label}")
    ax.legend()
    save_fig(fig, out, f"{label}_learning_curve_map.png", produced)


def plot_precision_recall_epochs(res: dict, label: str, out: Path, produced: list[str]) -> None:
    ep = res.get("epoch")
    if ep is None or "metrics/precision(B)" not in res:
        return
    fig, ax = plt.subplots()
    ax.plot(ep, res["metrics/precision(B)"], label="precision (val)", color=PALETTE[2])
    if "metrics/recall(B)" in res:
        ax.plot(ep, res["metrics/recall(B)"], label="recall (val)", color=PALETTE[3])
    ax.set_xlabel("epoch"); ax.set_ylabel("score"); ax.set_ylim(0, 1)
    ax.set_title(f"Precision and recall per epoch - {label}")
    ax.legend()
    save_fig(fig, out, f"{label}_precision_recall_per_epoch.png", produced)


def plot_lr_schedule(res: dict, label: str, out: Path, produced: list[str]) -> None:
    """Item 3 -- Ultralytics logs one LR per param group (pg0 bias / pg1 weights / pg2 norm)."""
    ep = res.get("epoch")
    lr_keys = [k for k in res if k.startswith("lr/")]
    if ep is None or not lr_keys:
        return
    fig, ax = plt.subplots()
    for i, k in enumerate(sorted(lr_keys)):
        ax.plot(ep, res[k], color=PALETTE[i % len(PALETTE)], label=k)
    ax.set_xlabel("epoch"); ax.set_ylabel("learning rate")
    ax.set_title(f"Learning rate schedule - {label}")
    ax.legend()
    save_fig(fig, out, f"{label}_lr_schedule.png", produced)


def _plot_confusion(matrix: np.ndarray, names: dict, label: str, out: Path, produced: list[str],
                    normalized: bool) -> None:
    """Item 4 -- both variants. Ultralytics' matrix is (nc+1, nc+1) indexed [predicted][true], where the
    extra row/column is 'background': the last column counts missed ground truths (FN) and the last row
    counts detections that matched nothing (FP). Normalization is per TRUE class (column), so each
    column reads as 'of all real X, what did the model call them'."""
    n = matrix.shape[0]
    labels = [names.get(i, str(i)) for i in range(n - 1)] + ["background"]
    m = matrix.astype(float)
    if not m.any():
        # An all-zero matrix means it was never populated (see the plots=True note in run_validation),
        # not that the model predicted nothing. Refuse to publish a blank grid as a result.
        print(f"  [skip] {label} confusion matrix is entirely zero - not plotting an empty grid",
              file=sys.stderr)
        return
    if normalized:
        col = m.sum(axis=0, keepdims=True)
        m = np.divide(m, col, out=np.zeros_like(m), where=col > 0)

    size = max(7.0, 0.75 * n + 3)
    fig, ax = plt.subplots(figsize=(size, size * 0.85))
    im = ax.imshow(m, cmap="Blues", vmin=0, vmax=1 if normalized else None)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04,
                 label="fraction of true class" if normalized else "count")
    ax.set_xticks(range(n)); ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(n)); ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("true"); ax.set_ylabel("predicted")
    kind = "normalized" if normalized else "raw counts"
    ax.set_title(f"Confusion matrix ({kind}) - {label}")
    thresh = (m.max() or 1) / 2
    for i in range(n):
        for j in range(n):
            v = m[i, j]
            if normalized and v < 0.005:
                continue
            if not normalized and v == 0:
                continue
            ax.text(j, i, f"{v:.2f}" if normalized else f"{int(v)}",
                    ha="center", va="center", fontsize=8,
                    color="white" if v > thresh else "black")
    ax.grid(False)
    suffix = "normalized" if normalized else "raw"
    save_fig(fig, out, f"{label}_confusion_matrix_{suffix}.png", produced)


def plot_curve_family(curves: list[dict], want: str, names: dict, label: str, out: Path,
                      produced: list[str], fname: str, title: str,
                      ap_class_index: list[int] | None = None) -> None:
    """Items 13 + 14 -- per-class PR / F1-conf / P-conf / R-conf, straight out of the validator."""
    c = next((c for c in curves if want.lower() in c["name"].lower()), None)
    if c is None:
        return
    x, y = np.asarray(c["x"]), np.asarray(c["y"])
    if y.ndim == 1:
        y = y[None, :]
    fig, ax = plt.subplots()
    # Row i of y is class row_cls[i]; the range() fallback is only for caches written before
    # ap_class_index was stored.
    row_cls = list(ap_class_index) if ap_class_index else list(range(y.shape[0]))
    ordered = sorted(range(y.shape[0]), key=lambda i: -float(np.nanmean(y[i])))
    for rank, i in enumerate(ordered):
        cid = row_cls[i] if i < len(row_cls) else i
        nm = names.get(cid, str(cid))
        ax.plot(x, y[i], color=PALETTE[rank % len(PALETTE)], label=nm, alpha=0.9)
    if y.shape[0] > 1:
        ax.plot(x, np.nanmean(y, axis=0), color="black", lw=2.8, ls="--", label="all classes (mean)")
    ax.set_xlabel(c["xlabel"]); ax.set_ylabel(c["ylabel"])
    ax.set_ylim(0, 1.02)
    ax.set_title(f"{title} - {label}")
    ax.legend(fontsize=8, ncol=2)
    save_fig(fig, out, f"{label}_{fname}.png", produced)


def plot_per_class_bar(per_class: list[dict], label: str, out: Path, produced: list[str]) -> None:
    if not per_class:
        return
    rows = sorted(per_class, key=lambda r: -r["mAP50"])
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(9, max(4.0, 0.45 * len(rows) + 2)))
    ax.barh(y, [r["mAP50"] for r in rows], color=PALETTE[0], label="mAP@50")
    ax.barh(y, [r["mAP50_95"] for r in rows], color=PALETTE[1], height=0.45, label="mAP@50-95")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['class']} (n={r['instances']})" for r in rows], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 1); ax.set_xlabel("mAP")
    ax.set_title(f"Per-class detection quality - {label}")
    ax.legend()
    for i, r in enumerate(rows):
        ax.text(r["mAP50"] + 0.01, i, f"{r['mAP50']:.3f}", va="center", fontsize=8)
    save_fig(fig, out, f"{label}_per_class_map50.png", produced)


def plot_class_distribution(dist: dict[str, np.ndarray], names: dict, out: Path,
                            produced: list[str]) -> None:
    """Item 8 -- class balance across splits. For detection this counts INSTANCES (boxes), not images:
    one frame routinely holds several objects, so image counts would understate the imbalance."""
    if not dist:
        return
    n = len(names)
    idx = np.arange(n)
    order = np.argsort(-dist.get("train", np.zeros(n)))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    width = 0.8 / max(1, len(dist))
    for i, (split, counts) in enumerate(dist.items()):
        ax.bar(idx + i * width, counts[order], width=width,
               color=PALETTE[i], label=f"{split} (n={int(counts.sum())})")
    ax.set_xticks(idx + width * (len(dist) - 1) / 2)
    ax.set_xticklabels([names[int(j)] for j in order], rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("instances (boxes)")
    ax.set_yscale("log")  # finger vs Stitch Scissors spans ~3 orders of magnitude
    ax.set_title("Class distribution per split (log scale)")
    ax.legend()
    save_fig(fig, out, "class_distribution.png", produced)


# ────────────────────────────── Error analysis grid (item 16) ──────────────────────────────

def _iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU of every box in a (N,4 xyxy) against every box in b (M,4 xyxy)."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-9)


def plot_error_grid(run_dir: Path, split_images: Path, names: dict, label: str, out: Path,
                    produced: list[str], device: str, conf: float = 0.25,
                    sample: int = 120, n_show: int = 4) -> None:
    """Item 16 -- the best and worst validation frames side by side, ground truth in green and
    predictions in red, so a reader can see WHAT the model gets wrong rather than only how much.

    Frames are ranked by (false positives + false negatives) at IoU 0.5, matching greedily by IoU.
    Only `sample` images are scored: this is an illustrative panel, not a metric."""
    weights = run_dir / "train" / "weights" / "best.pt"
    if not weights.exists() or not split_images.is_dir():
        return
    from ultralytics import YOLO
    from PIL import Image

    imgs = sorted([p for p in split_images.iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}])[:sample]
    if not imgs:
        return
    labels_dir = split_images.parent / "labels"
    model = YOLO(str(weights))
    scored = []
    for p in imgs:
        lf = labels_dir / (p.stem + ".txt")
        if not lf.exists():
            continue
        with Image.open(p) as im:
            W, H = im.size
        gt, gt_cls = [], []
        for line in lf.read_text(encoding="utf-8").splitlines():
            q = line.split()
            if len(q) != 5:
                continue
            c, xc, yc, w, h = int(q[0]), *(float(v) for v in q[1:])
            gt.append([(xc - w / 2) * W, (yc - h / 2) * H, (xc + w / 2) * W, (yc + h / 2) * H])
            gt_cls.append(c)
        gt = np.array(gt, dtype=float).reshape(-1, 4)

        r = model.predict(str(p), conf=conf, device=device, verbose=False)[0]
        pb = r.boxes.xyxy.cpu().numpy().reshape(-1, 4)
        pc = r.boxes.cls.cpu().numpy().astype(int)

        ious = _iou(pb, gt)
        matched_gt, matched_pred = set(), set()
        if ious.size:
            for pi, gi in sorted(((i, j) for i in range(ious.shape[0]) for j in range(ious.shape[1])),
                                 key=lambda t: -ious[t[0], t[1]]):
                if ious[pi, gi] < 0.5:
                    break
                if pi in matched_pred or gi in matched_gt:
                    continue
                if pc[pi] == gt_cls[gi]:
                    matched_pred.add(pi); matched_gt.add(gi)
        fp = len(pb) - len(matched_pred)
        fn = len(gt) - len(matched_gt)
        scored.append((fp + fn, p, gt, gt_cls, pb, pc, fp, fn))

    if not scored:
        return
    scored.sort(key=lambda t: t[0])
    # The halves must not overlap: with fewer than 2*n_show scored frames, scored[:k] + scored[-k:]
    # renders the same image twice, once titled "best" and once "worst".
    k = min(n_show, len(scored) // 2) or min(n_show, len(scored))
    picks = scored[:k] + scored[max(k, len(scored) - k):]
    titles = ["best"] * k + ["worst"] * (len(picks) - k)

    cols = 4
    rows = int(math.ceil(len(picks) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.4 * rows))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.axis("off")
    for ax, (err, p, gt, gt_cls, pb, pc, fp, fn), kind in zip(axes, picks, titles):
        with Image.open(p) as im:
            ax.imshow(im.convert("RGB"))
        for b, c in zip(gt, gt_cls):
            ax.add_patch(plt.Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1],
                                       fill=False, edgecolor="#009E73", lw=2))
            ax.text(b[0], b[1] - 4, names.get(int(c), str(c)), color="#009E73", fontsize=7,
                    bbox=dict(facecolor="white", alpha=0.65, pad=0.5, edgecolor="none"))
        for b, c in zip(pb, pc):
            ax.add_patch(plt.Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1],
                                       fill=False, edgecolor="#D55E00", lw=1.6, ls="--"))
            ax.text(b[0], b[3] + 12, names.get(int(c), str(c)), color="#D55E00", fontsize=7,
                    bbox=dict(facecolor="white", alpha=0.65, pad=0.5, edgecolor="none"))
        ax.set_title(f"{kind}: FP={fp} FN={fn}", fontsize=9)
    fig.suptitle(f"Error analysis - {label}   (green solid = ground truth, orange dashed = prediction)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    save_fig(fig, out, f"{label}_error_analysis_grid.png", produced)


# ────────────────────────────── Cross-run comparison (items 17 + 18) ──────────────────────────────

def plot_comparison_curves(runs: dict[str, dict], key: str, ylabel: str, title: str,
                           fname: str, out: Path, produced: list[str], ylim=(0, 1)) -> None:
    have = {lab: r for lab, r in runs.items() if r.get("results") and key in r["results"]}
    if len(have) < 2:
        return
    fig, ax = plt.subplots()
    for i, (lab, r) in enumerate(have.items()):
        ax.plot(r["results"]["epoch"], r["results"][key], color=RUN_COLORS[i % 4], label=lab)
    ax.set_xlabel("epoch"); ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_title(title)
    ax.legend()
    save_fig(fig, out, fname, produced)


def plot_comparison_total_loss(runs: dict[str, dict], out: Path, produced: list[str]) -> None:
    have = {lab: r for lab, r in runs.items() if r.get("results")}
    if len(have) < 2:
        return
    fig, ax = plt.subplots()
    for i, (lab, r) in enumerate(have.items()):
        res = r["results"]
        if not all(f"{p}/{c}_loss" in res for p in ("train", "val") for c in ("box", "cls", "dfl")):
            continue
        tr = sum(res[f"train/{c}_loss"] for c in ("box", "cls", "dfl"))
        va = sum(res[f"val/{c}_loss"] for c in ("box", "cls", "dfl"))
        ax.plot(res["epoch"], tr, color=RUN_COLORS[i % 4], label=f"{lab} train")
        ax.plot(res["epoch"], va, color=RUN_COLORS[i % 4], ls="--", label=f"{lab} val")
    ax.set_xlabel("epoch"); ax.set_ylabel("total loss (box+cls+dfl)")
    ax.set_title("Train vs validation loss - all runs")
    ax.legend(ncol=2, fontsize=9)
    save_fig(fig, out, "comparison_loss_curves.png", produced)


def plot_comparison_per_class(runs: dict[str, dict], out: Path, produced: list[str]) -> None:
    have = {lab: r for lab, r in runs.items() if r.get("val")}
    if len(have) < 2:
        return
    first = next(iter(have.values()))["val"]
    classes = [c["class"] for c in sorted(first["per_class"], key=lambda r: -r["mAP50"])]
    idx = np.arange(len(classes))
    width = 0.8 / len(have)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, (lab, r) in enumerate(have.items()):
        lut = {c["class"]: c["mAP50"] for c in r["val"]["per_class"]}
        ax.bar(idx + i * width, [lut.get(c, 0.0) for c in classes], width=width,
               color=RUN_COLORS[i % 4], label=lab)
    ax.set_xticks(idx + width * (len(have) - 1) / 2)
    ax.set_xticklabels(classes, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("mAP@50"); ax.set_ylim(0, 1)
    ax.set_title("Per-class mAP@50 by run")
    ax.legend()
    save_fig(fig, out, "comparison_per_class_map50.png", produced)


def build_benchmark_table(runs: dict[str, dict]) -> list[dict]:
    rows = []
    for lab, r in runs.items():
        v, res = r.get("val"), r.get("results")
        row = {"run": lab}
        if v:
            row.update({"mAP50": v["overall"]["mAP50"], "mAP50_95": v["overall"]["mAP50_95"],
                        "precision": v["overall"]["precision"], "recall": v["overall"]["recall"],
                        "fitness": v["overall"]["fitness"]})
        if res and "epoch" in res:
            row["epochs"] = int(res["epoch"][-1])
            if "metrics/mAP50(B)" in res:
                m = res["metrics/mAP50(B)"]
                row["best_epoch"] = int(np.nanargmax(m)) + 1
            for c in ("box", "cls", "dfl"):
                if f"val/{c}_loss" in res:
                    row[f"final_val_{c}_loss"] = float(res[f"val/{c}_loss"][-1])
            if "time" in res:
                row["train_time_min"] = float(res["time"][-1]) / 60.0
        rows.append(row)
    return rows


def build_hyperparam_table(runs: dict[str, dict]) -> list[dict]:
    """Item 18. Only the keys that actually differentiate these experiments -- dumping all ~100
    Ultralytics args would bury the two or three that matter."""
    keys = ["model", "epochs", "batch", "imgsz", "seed", "device", "workers", "optimizer", "lr0",
            "lrf", "momentum", "weight_decay", "warmup_epochs", "patience", "close_mosaic", "amp",
            "deterministic", "hsv_h", "hsv_s", "hsv_v", "degrees", "translate", "scale", "shear",
            "perspective", "flipud", "fliplr", "bgr", "mosaic", "mixup", "cutmix", "copy_paste"]
    run_args = [(lab, r.get("args", {})) for lab, r in runs.items()]
    table = []
    for k in keys:
        if not any(k in a for _, a in run_args):
            continue
        entry = {"hyperparameter": k}
        for lab, a in run_args:
            entry[lab] = a.get(k, "")
        table.append(entry)
    # A reader's first question is "what actually differed?" -- answer it in the table itself. The
    # same list goes in every run column: filling only the first leaves the rest blank as soon as
    # there are three or more runs.
    if len(run_args) > 1:
        changed = [e["hyperparameter"] for e in table
                   if len({str(e[lab]) for lab, _ in run_args}) > 1]
        summary = ", ".join(changed) if changed else "(nothing)"
        table.append({"hyperparameter": "** DIFFERS **", **{lab: summary for lab, _ in run_args}})
    return table


# ────────────────────────────── main ──────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Plots + tables for Ultralytics detection runs.")
    ap.add_argument("--runs", nargs="+", required=True,
                    help="one or more LABEL=PATH_TO_RUN_DIR (the dir holding train/ and data.yaml)")
    ap.add_argument("--out", default="results", help="output directory (default: results)")
    ap.add_argument("--split", default="val", choices=["val", "test"])
    ap.add_argument("--device", default="0")
    ap.add_argument("--conf", type=float, default=0.25, help="confidence threshold for the error grid")
    ap.add_argument("--reuse-cached", action="store_true",
                    help="reuse cached validation metrics instead of re-running model.val()")
    ap.add_argument("--skip-error-grid", action="store_true",
                    help="skip the error-analysis panel (it runs per-image inference)")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    apply_theme()
    produced: list[str] = []

    runs: dict[str, dict] = {}
    for spec in args.runs:
        if "=" not in spec:
            print(f"[error] --runs entries must be LABEL=PATH, got '{spec}'", file=sys.stderr)
            sys.exit(1)
        label, _, path = spec.partition("=")
        run_dir = Path(path).resolve()
        if not run_dir.is_dir():
            print(f"[error] run dir not found: {run_dir}", file=sys.stderr)
            sys.exit(1)
        runs[label] = {"dir": run_dir}

    for label, r in runs.items():
        print(f"\n[run] {label}  ({r['dir']})")
        r["results"] = read_results_csv(r["dir"])
        r["args"] = read_args_yaml(r["dir"])
        r["val"] = run_validation(r["dir"], args.split, args.device,
                                  out / f".metrics_{label}_{args.split}.json", args.reuse_cached)

        res = r["results"]
        if res:
            plot_loss_curves(res, label, out, produced)
            plot_loss_breakdown(res, label, out, produced)
            plot_loss_components_separately(res, label, out, produced)
            plot_map_curves(res, label, out, produced)
            plot_precision_recall_epochs(res, label, out, produced)
            plot_lr_schedule(res, label, out, produced)
        else:
            print("  [warn] no results.csv - per-epoch figures skipped", file=sys.stderr)

        v = r["val"]
        if v:
            names = {int(k): val for k, val in v["names"].items()}
            if v["confusion_matrix"] is not None:
                _plot_confusion(np.asarray(v["confusion_matrix"]), names, label, out, produced, False)
                _plot_confusion(np.asarray(v["confusion_matrix"]), names, label, out, produced, True)
            plot_curve_family(v["curves"], "Precision-Recall", names, label, out, produced,
                              "pr_curve_per_class", "Precision-Recall curve per class",
                              v.get("ap_class_index"))
            plot_curve_family(v["curves"], "F1-Confidence", names, label, out, produced,
                              "f1_confidence_curve", "F1 vs confidence",
                              v.get("ap_class_index"))
            plot_curve_family(v["curves"], "Precision-Confidence", names, label, out, produced,
                              "precision_confidence_curve", "Precision vs confidence",
                              v.get("ap_class_index"))
            plot_curve_family(v["curves"], "Recall-Confidence", names, label, out, produced,
                              "recall_confidence_curve", "Recall vs confidence",
                              v.get("ap_class_index"))
            plot_per_class_bar(v["per_class"], label, out, produced)

            write_table(v["per_class"], out, f"{label}_per_class_metrics", produced,
                        title=f"Per-class detection metrics ({args.split}) - {label}")
            write_table([{"metric": k, "value": val} for k, val in v["overall"].items()],
                        out, f"{label}_overall_metrics", produced,
                        title=f"Overall metrics ({args.split}) - {label}")

            if not args.skip_error_grid:
                data_yaml = r["dir"] / "data.yaml"
                try:
                    import yaml
                    d = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
                    split_dir = resolve_split_dir(data_yaml, d, d.get(args.split) or d.get("val"))
                    if split_dir is None:
                        print(f"  [warn] error grid skipped: the '{args.split}' images dir in "
                              f"{data_yaml} does not resolve to a real directory", file=sys.stderr)
                    else:
                        plot_error_grid(r["dir"], split_dir, names, label, out, produced,
                                        args.device, args.conf)
                except Exception as e:
                    print(f"  [warn] error grid skipped: {e}", file=sys.stderr)

    # Class distribution: read once, from the first run that exposes a usable data.yaml.
    for label, r in runs.items():
        v = r.get("val")
        if not v:
            continue
        try:
            import yaml
            data_yaml = r["dir"] / "data.yaml"
            d = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
            names = {int(k): val for k, val in v["names"].items()}
            dist = {}
            for split_key in ("train", "val", "test"):
                raw = d.get(split_key)
                if not raw:
                    continue
                sp = resolve_split_dir(data_yaml, d, raw)
                if sp is None:
                    print(f"[warn] class distribution: {split_key} path {raw!r} does not resolve - "
                          f"split omitted rather than published as zeros", file=sys.stderr)
                    continue
                dist[split_key] = count_split_classes(sp, len(names))
            plot_class_distribution(dist, names, out, produced)
            rows = [{"class": names[i],
                     **{s: int(c[i]) for s, c in dist.items()},
                     "total": int(sum(c[i] for c in dist.values()))}
                    for i in range(len(names))]
            rows.sort(key=lambda x: -x["total"])
            write_table(rows, out, "class_distribution", produced,
                        title="Instances (boxes) per class per split", float_fmt="{:.0f}")
        except Exception as e:
            print(f"[warn] class distribution skipped: {e}", file=sys.stderr)
        break

    if len(runs) > 1:
        print("\n[comparison]")
        plot_comparison_curves(runs, "metrics/mAP50(B)", "mAP@50", "mAP@50 per epoch - all runs",
                               "comparison_map50_curves.png", out, produced)
        plot_comparison_curves(runs, "metrics/mAP50-95(B)", "mAP@50-95",
                               "mAP@50-95 per epoch - all runs",
                               "comparison_map50-95_curves.png", out, produced)
        plot_comparison_total_loss(runs, out, produced)
        plot_comparison_per_class(runs, out, produced)
        write_table(build_benchmark_table(runs), out, "benchmark_comparison", produced,
                    title=f"Benchmark comparison ({args.split} split)")
        write_table(build_hyperparam_table(runs), out, "hyperparameter_summary", produced,
                    title="Hyperparameter summary per run")

    print("\n==== report complete ====")
    print(f"  output directory : {out}")
    print(f"  files written    : {len(produced)}")
    for f in sorted(produced):
        print(f"    - {f}")
    print("=========================")


if __name__ == "__main__":
    main()
