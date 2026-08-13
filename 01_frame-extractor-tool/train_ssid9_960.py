#!/usr/bin/env python3
"""Retrain the 9-class detector at imgsz 960 to test whether `needle` is a resolution problem.

Why this run exists: `needle` recall sat at 0.227 after 50 epochs and moved only to 0.2435 (val) /
0.2513 (test) after 150 -- three times the training budget bought almost nothing, while the
confusion matrix still puts 0.45 of all true needles in background. `analyze_box_sizes.py` then
measured why: needle has a median normalised area of 0.00092 and a median short side of **12.4 px at
imgsz 640**, with 80.9% of its boxes below COCO's small-object cut-off. The next smallest class,
wound, is nearly 3x larger. A detector cannot recover a signal its stride has already discarded, so
the lever is input resolution, not epochs and not more data.

This run is deliberately a copy of `D:\ml\runs\ssid9_aug_150ep` with imgsz raised 640 -> 960:
same weights, same data, same seed, same 150 epochs, same augmentation. Everything that could
explain a change other than resolution is held still.

`batch` stays at 8, which is worth saying because it looked like it could not. 960 costs ~2.25x the
activation memory of 640 and this machine has a 4 GB RTX 3050, so batch 4 seemed like the safe
assumption -- but a trial run at batch 4 reported only 1.36 GB reserved, leaving room to keep the
batch where the 150-epoch run had it. Measuring beat assuming: imgsz really is the only variable
that moves between the two runs.

Read the result off `needle` recall on the same val split, against 0.2435. If it moves, resolution
was the constraint. If it does not, stop buying GPU hours and go audit needle's label quality.

Run it with the GPU venv:

    D:\ml\ssid-gpu\Scripts\python.exe train_ssid9_960.py
    D:\ml\ssid-gpu\Scripts\python.exe train_ssid9_960.py --resume   # continue an interrupted run

Close Chrome first. This machine has a 28.7 GB commit limit and a pagefile Windows will not grow;
a dataloader worker that cannot be spawned surfaces as WinError 1455, which is why workers=0 here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DATA = Path(r"D:\ml\data\ssid9.yaml")
PROJECT = Path(r"D:\ml\runs\ssid9_aug_960")

# Held identical to ssid9_aug_150ep so that imgsz is the only difference between the two runs.
PARAMS = dict(
    data=str(DATA),
    epochs=150,
    imgsz=960,
    batch=8,
    device="0",
    workers=0,
    seed=42,
    deterministic=True,
    project=str(PROJECT),
    name="train",
    exist_ok=True,
    plots=True,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resume", action="store_true",
                    help="continue from the run's last.pt instead of starting over")
    args = ap.parse_args()

    if not DATA.exists():
        sys.exit(f"[error] dataset yaml not found: {DATA}")

    # The labels this reads must already be plain bboxes. A Roboflow export can carry boxes and
    # polygons in the same file, and ultralytics decides "is this a segment file?" per FILE rather
    # than per row -- so in a mixed file every plain bbox row is read as a 2-point polygon and
    # collapses to a wrong box. polygons_to_bboxes.py normalises that; ssid9_bbox is its output.
    if "ssid9_bbox" not in DATA.read_text(encoding="utf-8"):
        sys.exit(f"[error] {DATA} does not point at the normalised ssid9_bbox tree - "
                 f"run polygons_to_bboxes.py first")

    from ultralytics import YOLO

    if args.resume:
        # ultralytics reads epochs/imgsz/batch back out of the checkpoint's own args, so passing
        # PARAMS again here would be ignored at best and conflicting at worst. resume=True is the
        # whole instruction.
        last = PROJECT / "train" / "weights" / "last.pt"
        if not last.exists():
            sys.exit(f"[error] nothing to resume: {last} does not exist")
        print(f"[train] resuming from {last}")
        YOLO(str(last)).train(resume=True)
    else:
        print(f"[train] imgsz={PARAMS['imgsz']} batch={PARAMS['batch']} epochs={PARAMS['epochs']} "
              f"-> {PROJECT}")
        YOLO("yolo11n.pt").train(**PARAMS)

    # report_training_results.py refuses to run validation without a data.yaml at the RUN root, and
    # returns None quietly when it is missing -- which is how the 150-epoch run ended up with only
    # per-epoch curves and no per-class table. Put it there now rather than rediscovering that.
    PROJECT.mkdir(parents=True, exist_ok=True)
    (PROJECT / "data.yaml").write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[train] done. Next:\n"
          f"  python report_training_results.py --runs aug960={PROJECT} --out results_960 --split val --device 0")


if __name__ == "__main__":
    main()
