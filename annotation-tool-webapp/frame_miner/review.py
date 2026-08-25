"""Review step: whatever survives in staging/preview/ is what gets kept.

A human deletes rejected frames' preview images (in Explorer, any viewer -- no custom
tool needed for v1). `prune()` then deletes the corresponding clean image+label and
drops the row from manifest.csv. Idempotent: running with no preview changes rejects 0.
"""
import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    kept: int
    rejected: int


def _stems(dir_path: Path, suffix: str) -> set[str]:
    if not dir_path.exists():
        return set()
    return {p.stem for p in dir_path.glob(f"*{suffix}")}


def prune(staging_dir: str) -> PruneResult:
    out = Path(staging_dir)
    images_dir = out / "images"
    labels_dir = out / "labels"
    preview_dir = out / "preview"
    manifest_path = out / "manifest.csv"

    preview_stems = _stems(preview_dir, ".jpg")
    image_stems = _stems(images_dir, ".jpg")

    rejected = image_stems - preview_stems
    orphaned_previews = preview_stems - image_stems
    for stem in orphaned_previews:
        logger.warning("preview/%s.jpg has no matching staged image/label -- left alone", stem)

    for stem in rejected:
        (images_dir / f"{stem}.jpg").unlink(missing_ok=True)
        (labels_dir / f"{stem}.txt").unlink(missing_ok=True)

    if manifest_path.exists():
        with open(manifest_path, newline="", encoding="utf-8") as mf:
            reader = csv.DictReader(mf)
            fieldnames = reader.fieldnames
            rows = [row for row in reader if row["stem"] not in rejected]
        with open(manifest_path, "w", newline="", encoding="utf-8") as mf:
            writer = csv.DictWriter(mf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    kept = len(image_stems) - len(rejected)
    return PruneResult(kept=kept, rejected=len(rejected))
