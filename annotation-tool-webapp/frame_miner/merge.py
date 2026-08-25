"""Merge an exported dataset (this tool's own `export` output, or any other dataset in
Roboflow's layout) into an existing Roboflow-layout dataset, by copying files only --
never overwriting.

Two-step by design: `plan_merge()` is read-only and always safe to run; `apply_merge()`
only proceeds if the plan has zero class-order mismatches and zero filename collisions
-- a partial merge that silently overwrote half of one split is exactly the kind of
mistake that's hard to notice and (for a dataset with no git history behind it) hard to
undo, so this refuses all-or-nothing rather than best-effort.
"""
import shutil
from dataclasses import dataclass, field
from pathlib import Path

SPLITS = ("train", "valid", "test")


def read_names(data_yaml_path: str | Path) -> list[str]:
    """Parse the `names: ['a', 'b', ...]` single-line list from a Roboflow-layout
    data.yaml. Deliberately not a general YAML parser -- this tool's own write_yaml()
    and real Roboflow exports both use exactly this single-line-list convention, so a
    small targeted parser is enough (same no-PyYAML reasoning as export.py).
    """
    text = Path(data_yaml_path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("names:"):
            bracket = line.split(":", 1)[1].strip()
            if not (bracket.startswith("[") and bracket.endswith("]")):
                raise ValueError(f"names: line in {data_yaml_path} is not a single-line list: {line!r}")
            inner = bracket[1:-1]
            return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    raise ValueError(f"no names: line found in {data_yaml_path}")


@dataclass
class MergePlan:
    class_list: list[str]
    to_copy: dict[str, list[str]] = field(default_factory=dict)  # split -> stems safe to copy
    collisions: dict[str, list[str]] = field(default_factory=dict)  # split -> stems already in target


def plan_merge(from_dir: str, into_dir: str) -> MergePlan:
    from_dir = Path(from_dir)
    into_dir = Path(into_dir)

    source_names = read_names(from_dir / "data.yaml")
    target_names = read_names(into_dir / "data.yaml")
    if source_names != target_names:
        raise ValueError(
            f"class order mismatch -- refusing to merge:\n"
            f"  {from_dir / 'data.yaml'}: {source_names}\n"
            f"  {into_dir / 'data.yaml'}: {target_names}"
        )

    plan = MergePlan(class_list=source_names)
    for split in SPLITS:
        src_images = from_dir / split / "images"
        if not src_images.exists():
            continue

        stems = sorted(p.stem for p in src_images.glob("*.jpg"))
        dst_images = into_dir / split / "images"
        existing = {p.stem for p in dst_images.glob("*.jpg")} if dst_images.exists() else set()

        clash = [s for s in stems if s in existing]
        if clash:
            plan.collisions[split] = clash
        else:
            plan.to_copy[split] = stems

    return plan


def apply_merge(from_dir: str, into_dir: str, plan: MergePlan) -> dict[str, int]:
    if plan.collisions:
        raise RuntimeError(f"refusing to apply a merge plan with collisions: {plan.collisions}")

    from_dir = Path(from_dir)
    into_dir = Path(into_dir)
    counts: dict[str, int] = {}

    for split, stems in plan.to_copy.items():
        dst_images = into_dir / split / "images"
        dst_labels = into_dir / split / "labels"
        dst_images.mkdir(parents=True, exist_ok=True)
        dst_labels.mkdir(parents=True, exist_ok=True)

        for stem in stems:
            shutil.copy2(from_dir / split / "images" / f"{stem}.jpg", dst_images / f"{stem}.jpg")
            shutil.copy2(from_dir / split / "labels" / f"{stem}.txt", dst_labels / f"{stem}.txt")

        counts[split] = len(stems)

    return counts
