"""Export surviving staged image+label pairs into a YOLO dataset in Roboflow's own
export layout -- <split>/images/, <split>/labels/, data.yaml with no `path:` key and
`../<split>/images` relative paths -- so the result can be merged into an existing
Roboflow-exported dataset (e.g. `03_dataset/ssid.yolov11new`) by copying files across.

Note the val split's *folder* is named `valid` (Roboflow's convention), even though the
data.yaml *key* for it is still `val:` -- that mismatch is Roboflow's own convention,
reproduced here deliberately, not a bug.
"""
import json
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# ratio-name (used for --train/--val/--test and data.yaml keys) -> actual folder name
SPLIT_DIR_NAMES = {"train": "train", "val": "valid", "test": "test"}


@dataclass
class ExportSummary:
    counts: dict[str, int]
    dataset_dir: Path


def _stems(dir_path: Path, suffix: str) -> set[str]:
    if not dir_path.exists():
        return set()
    return {p.stem for p in dir_path.glob(f"*{suffix}")}


def _split_counts(n: int, ratios: dict[str, float]) -> dict[str, int]:
    """Largest-remainder allocation of n items across ratios that sum to 1.0.

    A split with ratio exactly 0.0 always gets exactly 0 items -- flooring error from
    the *other* splits is never allowed to leak into it. (An earlier version used plain
    int(n*ratio) slicing, which put any leftover from truncation into whichever split
    was sliced last regardless of its own ratio -- `--test 0.0` could still get 1 item.)
    """
    live = [name for name, r in ratios.items() if r > 0]
    counts = {name: 0 for name in ratios}

    raw = {name: n * ratios[name] for name in live}
    for name in live:
        counts[name] = int(raw[name])

    leftover = n - sum(counts[name] for name in live)
    by_remainder = sorted(live, key=lambda name: raw[name] - counts[name], reverse=True)
    for i in range(leftover):
        counts[by_remainder[i % len(by_remainder)]] += 1

    return counts


def _split_stems(stems: list[str], train: float, val: float, test: float, seed: int) -> dict[str, list[str]]:
    total = train + val + test
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"train+val+test must sum to 1.0, got {total}")

    shuffled = list(stems)
    random.Random(seed).shuffle(shuffled)

    counts = _split_counts(len(shuffled), {"train": train, "val": val, "test": test})

    result = {}
    idx = 0
    for name in ("train", "val", "test"):
        result[name] = shuffled[idx:idx + counts[name]]
        idx += counts[name]
    return result


def write_yaml(path: Path, class_list: list[str]) -> None:
    names_literal = "[" + ", ".join(f"'{name}'" for name in class_list) + "]"
    lines = [
        "train: ../train/images",
        "val: ../valid/images",
        "test: ../test/images",
        "",
        f"nc: {len(class_list)}",
        f"names: {names_literal}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_dataset(
    staging_dir: str,
    out_dir: str,
    class_list: list[str],
    train: float = 0.8,
    val: float = 0.2,
    test: float = 0.0,
    seed: int = 42,
) -> ExportSummary:
    staging = Path(staging_dir)
    images_dir = staging / "images"
    labels_dir = staging / "labels"
    preview_dir = staging / "preview"

    image_stems = _stems(images_dir, ".jpg")
    preview_stems = _stems(preview_dir, ".jpg")
    if image_stems != preview_stems:
        raise RuntimeError(
            "staging/images and staging/preview are out of sync -- run `frame-miner review` "
            "since the last edit to staging/preview before exporting"
        )

    stems = sorted(image_stems)
    splits = _split_stems(stems, train, val, test, seed)

    out = Path(out_dir)
    used_stems: set[str] = set()
    counts: dict[str, int] = {}

    for split_name, split_stems in splits.items():
        if not split_stems:
            continue

        split_dir = out / SPLIT_DIR_NAMES[split_name]
        split_images_dir = split_dir / "images"
        split_labels_dir = split_dir / "labels"
        split_images_dir.mkdir(parents=True, exist_ok=True)
        split_labels_dir.mkdir(parents=True, exist_ok=True)

        for stem in split_stems:
            dest_stem = stem
            suffix = 1
            while dest_stem in used_stems:
                dest_stem = f"{stem}_{suffix}"
                suffix += 1
            used_stems.add(dest_stem)

            shutil.copy2(images_dir / f"{stem}.jpg", split_images_dir / f"{dest_stem}.jpg")
            shutil.copy2(labels_dir / f"{stem}.txt", split_labels_dir / f"{dest_stem}.txt")

        counts[split_name] = len(split_stems)

    write_yaml(out / "data.yaml", class_list)

    summary = {
        "counts": counts,
        "class_names": class_list,
        "seed": seed,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return ExportSummary(counts=counts, dataset_dir=out)
