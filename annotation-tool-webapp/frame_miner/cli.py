"""argparse only -- every other module is plain importable functions a future UI can call directly."""
import argparse
import logging
import sys

from frame_miner.classes import class_list_for_export
from frame_miner.export import export_dataset
from frame_miner.merge import apply_merge, plan_merge
from frame_miner.mine import mine_source
from frame_miner.review import prune


def _cmd_mine(args: argparse.Namespace) -> None:
    summary = mine_source(
        source_path=args.source,
        model_path=args.model,
        target_classes=args.target_class,
        class_list_path=args.classes,
        out_dir=args.out,
        conf=args.conf,
        iou=args.iou,
        interval_sec=args.interval_sec,
        device=args.device,
    )
    print(f"candidates seen: {summary.candidates_seen}")
    print(f"frames staged:   {summary.frames_staged}")
    print(f"staging dir:     {summary.staging_dir}")
    if not args.classes:
        print(f"class order (auto, from model): {summary.staging_dir / 'classes_used.txt'}")


def _cmd_review(args: argparse.Namespace) -> None:
    result = prune(args.staging)
    print(f"kept: {result.kept}, rejected: {result.rejected}")


def _cmd_export(args: argparse.Namespace) -> None:
    class_list = class_list_for_export(args.staging, args.classes)
    summary = export_dataset(
        staging_dir=args.staging,
        out_dir=args.out,
        class_list=class_list,
        train=args.train,
        val=args.val,
        test=args.test,
        seed=args.seed,
    )
    print(f"counts: {summary.counts}")
    print(f"dataset dir: {summary.dataset_dir}")


def _cmd_merge(args: argparse.Namespace) -> None:
    plan = plan_merge(args.from_dir, args.into)

    print(f"class list: {plan.class_list}")
    for split, stems in plan.to_copy.items():
        print(f"  {split}: {len(stems)} to add")

    if plan.collisions:
        print("COLLISIONS -- these already exist in --into, nothing was copied:")
        for split, stems in plan.collisions.items():
            print(f"  {split}: {stems}")
        return

    if not args.apply:
        print("dry-run only -- pass --apply to actually copy files")
        return

    counts = apply_merge(args.from_dir, args.into, plan)
    print(f"merged: {counts}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="frame-miner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_mine = sub.add_parser("mine", help="scan a video/frame-folder and stage matching frames")
    p_mine.add_argument("--source", required=True, help="video file or folder of frame images")
    p_mine.add_argument("--model", required=True, help="ultralytics .pt checkpoint")
    p_mine.add_argument("--target-class", required=True, nargs="+", help="class name(s) to mine for")
    p_mine.add_argument("--classes", default=None,
                         help="class-order file for merging into an existing dataset (see "
                              "examples/*.txt). Omit to auto-derive from the model's own "
                              "native class order instead.")
    p_mine.add_argument("--conf", type=float, default=0.25)
    p_mine.add_argument("--iou", type=float, default=0.45)
    p_mine.add_argument("--interval-sec", type=float, default=1.0)
    p_mine.add_argument("--out", default="staging")
    p_mine.add_argument("--device", default="cpu")
    p_mine.set_defaults(func=_cmd_mine)

    p_review = sub.add_parser("review", help="prune staged frames rejected by deleting their preview image")
    p_review.add_argument("--staging", default="staging")
    p_review.set_defaults(func=_cmd_review)

    p_export = sub.add_parser("export", help="split surviving staged pairs into a YOLO dataset")
    p_export.add_argument("--staging", default="staging")
    p_export.add_argument("--out", default="dataset")
    p_export.add_argument("--classes", default=None,
                           help="class-order file, defines data.yaml names: order. Omit to use "
                                "staging/classes_used.txt (written by `mine`).")
    p_export.add_argument("--train", type=float, default=0.8)
    p_export.add_argument("--val", type=float, default=0.2)
    p_export.add_argument("--test", type=float, default=0.0)
    p_export.add_argument("--seed", type=int, default=42)
    p_export.set_defaults(func=_cmd_export)

    p_merge = sub.add_parser("merge", help="merge an exported dataset into an existing Roboflow-layout dataset")
    p_merge.add_argument("--from", dest="from_dir", required=True, help="dataset to merge in (e.g. this tool's export/ output)")
    p_merge.add_argument("--into", required=True, help="existing Roboflow-layout dataset root to merge into")
    p_merge.add_argument("--apply", action="store_true",
                          help="actually copy files. Default is a dry-run that only reports the plan.")
    p_merge.set_defaults(func=_cmd_merge)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
