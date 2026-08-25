import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from frame_miner.export import ExportSummary, export_dataset


class EmptyExportError(ValueError):
    """Picked classes yield zero stageable frames. Two distinguishable causes: nothing
    was picked (or a picked name doesn't match class_names), or a picked class has a
    nonzero results-grid count (seen on some non-candidate frame during live tracking)
    but was never staged in any interval-sampled candidate frame -- the exact
    rare-class scenario this product exists to help with. This module can only detect
    and report the situation clearly; avoiding it is the driver loop's concern
    (tracking/staging cadence)."""


@dataclass
class RunExportResult:
    summary: ExportSummary
    zip_path: Path
    labeled_classes: list[str]
    unlabeled_detected_classes: list[str]


def export_run(
    run_dir: str | Path,
    class_names: list[str],
    picked_classes: list[str],
    manifest: dict[str, set[int]],
    out_dir: str | Path,
    train: float = 0.8,
    val: float = 0.2,
    test: float = 0.0,
) -> RunExportResult:
    """Exports the picked classes' staged frames as a frame_miner-compatible dataset.

    class_names must be the exact native-order list originally used when staging wrote
    label ids -- passing a different order here silently mismatches data.yaml against
    the label ids already on disk. Always passes the FULL class_names to
    export_dataset(), never a picked subset, since frame_miner.merge requires an exact
    names-list match against the real merge target's data.yaml (which has all 9
    classes). Partial labeling happens by dropping label *lines* and excluding
    *frames*, never by shrinking the class list.
    """
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)

    unknown = [c for c in picked_classes if c not in class_names]
    if unknown:
        raise ValueError(f"picked_classes not in class_names: {unknown}")

    picked_ids = {class_names.index(c) for c in picked_classes}
    include_stems = sorted(stem for stem, ids in manifest.items() if ids & picked_ids)
    if not include_stems:
        raise EmptyExportError(
            f"No staged frame contains any of the picked classes {picked_classes!r}. "
            "Either nothing relevant was picked, or a picked class was only ever seen "
            "on non-candidate frames (never staged)."
        )

    all_present_ids: set[int] = set()
    for ids in manifest.values():
        all_present_ids |= ids
    unlabeled_detected_classes = sorted(
        class_names[i] for i in all_present_ids if i not in picked_ids
    )

    staging_images = run_dir / "staging" / "images"
    staging_preview = run_dir / "staging" / "preview"
    staging_labels = run_dir / "staging" / "labels"

    with tempfile.TemporaryDirectory(prefix="export_staging_") as tmp:
        filtered_dir = Path(tmp)
        filtered_images = filtered_dir / "images"
        filtered_preview = filtered_dir / "preview"
        filtered_labels = filtered_dir / "labels"
        for d in (filtered_images, filtered_preview, filtered_labels):
            d.mkdir(parents=True, exist_ok=True)

        for stem in include_stems:
            shutil.copy2(staging_images / f"{stem}.jpg", filtered_images / f"{stem}.jpg")
            shutil.copy2(staging_preview / f"{stem}.jpg", filtered_preview / f"{stem}.jpg")

            src_label = staging_labels / f"{stem}.txt"
            kept_lines = [
                line for line in src_label.read_text(encoding="utf-8").splitlines()
                if line.strip() and int(line.split()[0]) in picked_ids
            ]
            (filtered_labels / f"{stem}.txt").write_text(
                "\n".join(kept_lines) + "\n", encoding="utf-8"
            )

        summary = export_dataset(
            str(filtered_dir), str(out_dir), class_names,
            train=train, val=val, test=test,
        )

        # export_dataset() only reads preview/ for its stem-parity precondition -- it
        # never copies it into out_dir. Copy it ourselves for the QA folder.
        out_preview = out_dir / "preview"
        out_preview.mkdir(parents=True, exist_ok=True)
        for stem in include_stems:
            shutil.copy2(filtered_preview / f"{stem}.jpg", out_preview / f"{stem}.jpg")

    partial_labels_path = out_dir / "PARTIAL_LABELS.md"
    partial_labels_path.write_text(
        "# Partial label export\n\n"
        "This export labels ONLY the classes picked below, even though other real "
        "classes may be visible, unlabeled, in the same images. If merged into a "
        "dataset used for full multi-class training, the unlabeled-but-present "
        "classes below become false negatives for those classes.\n\n"
        f"**Labeled classes:** {', '.join(picked_classes)}\n\n"
        f"**Detected but not labeled in this export:** "
        f"{', '.join(unlabeled_detected_classes) if unlabeled_detected_classes else '(none)'}\n",
        encoding="utf-8",
    )

    summary_path = out_dir / "export_summary.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_data["labeled_classes"] = picked_classes
    summary_data["unlabeled_detected_classes"] = unlabeled_detected_classes
    summary_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    zip_base = run_dir / "export"
    zip_path_str = shutil.make_archive(str(zip_base), "zip", root_dir=str(out_dir))

    return RunExportResult(
        summary=summary,
        zip_path=Path(zip_path_str),
        labeled_classes=picked_classes,
        unlabeled_detected_classes=unlabeled_detected_classes,
    )
