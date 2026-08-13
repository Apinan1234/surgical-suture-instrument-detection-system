#!/usr/bin/env python3
r"""Parameterised training for the 9-class SSID detector -- the script for every run after the
imgsz 960 experiment.

`train_ssid9_960.py` stays as the record of that one experiment, with its settings hard-coded so the
run can be reproduced exactly. This script is the general one: model, resolution, batch and epochs
are all flags, and the run directory is named after the config, so a new experiment is a new command
rather than a new copy of the file.

Where this is starting from
---------------------------
Best model so far is `yolo11n` at imgsz 960, 150 epochs: val mAP50 **0.7160**, test 0.7015. The
target is a mean mAP50 of **0.80**, and the arithmetic says that needs every class to improve, not
just the weak one. Per-class val mAP50 at 960, with the training-set box count beside it:

    needle             0.360    1,387 boxes   <- a third of the entire gap to 0.80
    hand               0.618    1,339
    wound              0.661    1,742
    forcep             0.750    1,238
    needle_holder      0.773    1,947
    Tip_forcep         0.777      564
    finger             0.788    7,157
    Stitch Scissors    0.851       16         <- see the warning below
    Tip_needle_holder  0.866    1,031

Sum is 6.444 (mean 0.716); a mean of 0.80 needs 7.20. That is +0.756 spread across nine classes.

**`Stitch Scissors` makes the mean unstable.** Sixteen training boxes, ten in val, three in test. Its
score swings between 0.4314 and 0.9859 across runs and splits without anything real changing, and it
carries 1/9 of the headline number. It is currently scoring ABOVE the mean, so it is inflating the
figure being chased -- drop it and the eight-class mean is 0.6990, not 0.7160. Decide how to report
that class before reading any result from this script as progress.

The planned ladder
------------------
Phase A, hyperparameters only, one variable at a time:

    A1  yolo11n -> yolo11s at 960. The largest remaining lever: width 0.25 -> 0.50, 6.5 -> 21.5
        GFLOPs, and on COCO that is 39.5 -> 47.0 mAP50-95. Expect +0.02 to +0.05 here, not +0.08.

        python train_ssid9_v2.py --model yolo11s.pt --imgsz 960 --batch 4 --epochs 120 --name s960

    A3  the winner of A1 at imgsz 1280, for `needle` specifically -- 12.4 px at 640 is still only
        ~25 px at 1280.

        python train_ssid9_v2.py --model yolo11s.pt --imgsz 1280 --batch 2 --epochs 120 --name s1280

Then measure on the same val split and decide: >= 0.80 stop; 0.76-0.79 go add data for the classes
still dragging; < 0.76 stop training and go look at `needle`'s labels with your own eyes, because a
3x larger model that changes nothing is not a capacity problem.

Phase B is data work -- more `needle` frames, and a decision about `Stitch Scissors` -- and is
described in the plan file, not here.

VRAM on this machine
--------------------
One 4 GB RTX 3050. Measured: `yolo11n` at 960 with batch 8 reserves **2.65 GB**. `yolo11s` is twice
as wide, so batch 8 would land near 5.3 GB and will not fit; batch 4 should sit near 2.7 GB. That is
an estimate, not a measurement -- **watch the GPU_mem column ultralytics prints during epoch 1
before walking away**, and drop the batch if it climbs. Guessing this wrong once already cost a
restart on the 960 run.

Usage
-----
    D:\ml\ssid-gpu\Scripts\python.exe train_ssid9_v2.py --model yolo11s.pt --name s960
    D:\ml\ssid-gpu\Scripts\python.exe train_ssid9_v2.py --name s960 --resume

Close Chrome first: this machine has a 28.7 GB commit limit and a pagefile Windows will not grow, so
a dataloader worker that cannot spawn surfaces as WinError 1455. That is why workers=0 is fixed here
rather than exposed as a flag.
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
RUNS_ROOT = Path(r"D:\ml\runs")

# Held fixed across every experiment so that whatever the flags change is the only thing that
# changed. seed and dataset in particular: vary either and no two runs are comparable again.
FIXED = dict(
    device="0",
    workers=0,
    seed=42,
    deterministic=True,
    patience=50,
    plots=True,
    exist_ok=True,
    name="train",
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Train the 9-class SSID detector. See the module docstring for the plan.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--name", required=True,
                    help="short run id; the run lands in D:\\ml\\runs\\ssid9_<name>")
    ap.add_argument("--model", default="yolo11s.pt",
                    help="base checkpoint (yolo11n/s/m.pt), downloaded by ultralytics if absent")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--epochs", type=int, default=120,
                    help="the 960 run peaked at epoch 86 of 150, so 120 with patience 50 is enough")
    # BooleanOptionalAction, not store_true: store_true with default=True can never be switched off,
    # which would make the flag a lie. This gives --cos-lr and --no-cos-lr.
    ap.add_argument("--cos-lr", action=argparse.BooleanOptionalAction, default=True,
                    help="cosine LR decay; anneals to a cleaner minimum than the linear default")
    ap.add_argument("--close-mosaic", type=int, default=25,
                    help="epochs at the end trained on whole images with mosaic off, which is what "
                         "small objects are actually scored on")
    ap.add_argument("--resume", action="store_true",
                    help="continue from this run's last.pt instead of starting over")
    return ap.parse_args()


def write_run_data_yaml(project: Path) -> None:
    """report_training_results.py refuses to validate a run with no data.yaml at its ROOT, and
    returns None quietly when it is missing -- which is how the 150-epoch run sat for a day with
    per-epoch curves and no per-class table. Put it there as soon as the run exists."""
    project.mkdir(parents=True, exist_ok=True)
    (project / "data.yaml").write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    args = parse_args()
    project = RUNS_ROOT / f"ssid9_{args.name}"

    if not DATA.exists():
        sys.exit(f"[error] dataset yaml not found: {DATA}")

    # A Roboflow export can carry boxes and polygons in the same label file, and ultralytics decides
    # "is this a segment file?" per FILE rather than per row -- so in a mixed file every plain bbox
    # row is read as a 2-point polygon and collapses to a wrong box. polygons_to_bboxes.py
    # normalises that, and ssid9_bbox is its output.
    if "ssid9_bbox" not in DATA.read_text(encoding="utf-8"):
        sys.exit(f"[error] {DATA} does not point at the normalised ssid9_bbox tree - "
                 f"run polygons_to_bboxes.py first")

    from ultralytics import YOLO

    if args.resume:
        # ultralytics reads epochs/imgsz/batch back out of the checkpoint's own args, so re-supplying
        # them here would at best be ignored and at worst disagree with what it actually trained
        # under. resume=True is the whole instruction.
        last = project / "train" / "weights" / "last.pt"
        if not last.exists():
            sys.exit(f"[error] nothing to resume: {last} does not exist")
        print(f"[train] resuming from {last}")
        YOLO(str(last)).train(resume=True)
    else:
        if (project / "train" / "weights" / "last.pt").exists():
            sys.exit(f"[error] {project} already holds a run. Pass --resume to continue it, or pick "
                     f"another --name. (exist_ok=True would otherwise overwrite it in place.)")
        # No `model` key here on purpose: YOLO() takes the checkpoint, and train() must not also
        # receive one or ultralytics has two answers to which weights it is training.
        params = dict(
            FIXED,
            data=str(DATA),
            imgsz=args.imgsz,
            batch=args.batch,
            epochs=args.epochs,
            cos_lr=args.cos_lr,
            close_mosaic=args.close_mosaic,
            project=str(project),
        )
        print(f"[train] {args.model} imgsz={args.imgsz} batch={args.batch} epochs={args.epochs} "
              f"-> {project}")
        print("[train] watch the GPU_mem column in epoch 1: this card has 4 GB, and yolo11n at 960 "
              "batch 8 already used 2.65 GB of it")
        write_run_data_yaml(project)
        YOLO(args.model).train(**params)

    write_run_data_yaml(project)
    print(f"[train] done. Next:\n"
          f"  python report_training_results.py --runs {args.name}={project} "
          f"--out results_{args.name} --split val --device 0\n"
          f"  python report_training_results.py --runs {args.name}={project} "
          f"--out results_{args.name}_test --split test --device 0")


if __name__ == "__main__":
    main()
