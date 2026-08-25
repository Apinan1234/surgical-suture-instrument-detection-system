"""The explicit class-order file: one class name per line, index = output label id.

This is the compatibility linchpin with any downstream dataset this tool's output gets
merged into. A YOLO checkpoint's own `model.names` order is the checkpoint's business
and is NOT trusted for output ids -- every detection is translated by class *name*
through the list loaded here (see detect.py). See README for why.
"""
from pathlib import Path

CLASSES_USED_FILENAME = "classes_used.txt"


def load_class_list(path: str | Path) -> list[str]:
    """Read a class-order file: one name per line, blank lines ignored, order preserved.

    Raises ValueError on a duplicate name -- a duplicate would make `class_id_for_name`
    ambiguous and silently corrupt the id mapping.
    """
    names = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines()]
    names = [n for n in names if n]

    seen = set()
    for n in names:
        if n in seen:
            raise ValueError(f"duplicate class name {n!r} in {path} -- each name must appear once")
        seen.add(n)

    if not names:
        raise ValueError(f"{path} contains no class names")

    return names


def class_id_for_name(class_list: list[str], name: str) -> int | None:
    """This tool's output id for a class name, or None if the list has no such class."""
    try:
        return class_list.index(name)
    except ValueError:
        return None


def native_order(model_names: dict[int, str]) -> list[str]:
    """A model's own id-order class list, e.g. from `model.names`. Used as the output
    class order in "auto" mode, when no explicit --classes file was given -- see
    resolve_class_list().
    """
    return [model_names[i] for i in sorted(model_names)]


def resolve_class_list(staging_dir: str | Path, class_list_path: str | None, model_names: dict[int, str]) -> list[str]:
    """Decide the class-id order for a `mine` run, and keep it consistent with whatever
    a *previous* mine run into this same staging directory already recorded.

    If `class_list_path` is given, that pinned list is used (for merging into a specific
    existing dataset). If omitted, the loaded model's own native class order is used
    instead ("auto" mode -- e.g. a freshly uploaded model with no merge target yet).

    Either way, the resolved list is written to `<staging_dir>/classes_used.txt` the
    first time, and every later `mine` call into the same staging directory (even with a
    different model or a different --classes file) must resolve to the exact same list --
    mixing two different class orders in one staging directory would silently corrupt
    label ids for whichever run wrote second, since images/labels/ from both runs land in
    the same flat folder with no per-run tag.
    """
    class_list = load_class_list(class_list_path) if class_list_path else native_order(model_names)

    staging_dir = Path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    used_path = staging_dir / CLASSES_USED_FILENAME
    if used_path.exists():
        existing = load_class_list(used_path)
        if existing != class_list:
            raise ValueError(
                f"class order mismatch: {staging_dir} was already mined using this class order:\n"
                f"  {existing}\n"
                f"but this run resolved to:\n"
                f"  {class_list}\n"
                f"Mixing class orders in one staging directory would corrupt label ids for "
                f"whichever frames get labeled second -- use a fresh --out directory instead."
            )
    else:
        used_path.write_text("\n".join(class_list) + "\n", encoding="utf-8")

    return class_list


def class_list_for_export(staging_dir: str | Path, class_list_path: str | None) -> list[str]:
    """The class order `export` should use: `<staging_dir>/classes_used.txt`, written by
    whatever `mine` run(s) staged these frames -- that's the list the label ids in
    staging/labels/*.txt actually mean, so it's the only safe default. An explicit
    `--classes` override is allowed but must match exactly, or data.yaml would claim a
    names: order the label ids don't actually follow.
    """
    used_path = Path(staging_dir) / CLASSES_USED_FILENAME
    if not used_path.exists():
        if class_list_path:
            return load_class_list(class_list_path)
        raise FileNotFoundError(
            f"{used_path} not found -- run `mine` into this staging directory first, "
            f"or pass --classes explicitly"
        )

    used = load_class_list(used_path)
    if class_list_path:
        given = load_class_list(class_list_path)
        if given != used:
            raise ValueError(
                f"--classes does not match {used_path} (the order the staged labels actually "
                f"use):\n  staged:  {used}\n  given:   {given}"
            )
    return used
