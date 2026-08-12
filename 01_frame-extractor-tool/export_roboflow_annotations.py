#!/usr/bin/env python
"""
Export a Roboflow project's images + annotations to a local YOLO dataset WITHOUT creating a Version.

Why this exists
---------------
"Create New Version" hit "Credit Limit Reached", so the newly-labeled images are not in any Version
and cannot be downloaded the normal (version-based) way. This pulls the raw image + annotation records
straight from the project via the REST API and rebuilds a YOLO folder you can train locally with:

    python train_roboflow_yolo.py --skip-download --dataset-dir ./roboflow_raw \
        --imbalance-threshold 999 --model models/ssid_v6i_50ep_20260810_map50-608.pt --epochs 50

READ THIS BEFORE TRUSTING THE OUTPUT
------------------------------------
* Roboflow's API changes over time and this is written against its documented shapes as of writing.
  If a response looks different, run  --inspect  first: it dumps ONE raw image record so you can SEE
  the real field names, then adjust extract_boxes() / IMAGE_URL handling below. The script fails LOUD
  (raises with the offending record) rather than silently writing wrong labels.
* Run it yourself with YOUR key. It reads ROBOFLOW_API_KEY from webapp/.env (or the environment) and
  never prints it. Do not paste the key into chat or into this file.
* Read calls (project info, search) are normally NOT credit-consuming, but I can't see your account  -
  start with --count, which touches only the cheap project-info endpoint, and stop if anything warns
  about credits.

Usage
-----
    # 1) verify the project and the raw image count (do this first  - expect ~1150):
    python export_roboflow_annotations.py --project <PROJECT_SLUG> --count

    # 2) see the real shape of one image record (confirms how annotations are returned):
    python export_roboflow_annotations.py --project <PROJECT_SLUG> --inspect

    # 3) full export to a local YOLO dataset:
    python export_roboflow_annotations.py --project <PROJECT_SLUG> --out ./roboflow_raw

--workspace defaults to "fhasai-khuanpan" (this project's known workspace). Find both slugs in your
Roboflow project URL: app.roboflow.com/<workspace>/<project>/...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# This machine's console is the Thai code page (cp874); printing any non-ASCII char there raises
# UnicodeEncodeError and aborts mid-run. Force UTF-8 output so stray characters degrade to mojibake
# instead of crashing. Guarded: reconfigure() only exists on 3.7+ and only on real text streams.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

ENV_PATH = Path(__file__).resolve().parent / "webapp" / ".env"
# override=True on purpose (unlike train_roboflow_yolo.py): the whole job of this tool is to use the
# key you put in .env, so the file must win even if a stale ROBOFLOW_API_KEY is lingering in the OS
# environment (a very common cause of "I changed .env but it still uses the old key").
load_dotenv(ENV_PATH, override=True)

API_ROOT = "https://api.roboflow.com"
IMAGE_EXTS_KEEP = {".jpg", ".jpeg", ".png"}


# ────────────────────────────── low-level HTTP (stdlib only) ──────────────────────────────

_API_KEY_QS = re.compile(r"(api_key=)[^&\s]*", re.IGNORECASE)


def _redact(url: str) -> str:
    """Never let the api_key reach a log line.

    Scrubs the query parameter itself rather than substituting a known key string: the key can
    also arrive via --api-key, and keying off os.environ misses exactly that case -- the error
    paths below would then print the real key in full."""
    redacted = _API_KEY_QS.sub(r"\1<API_KEY>", url)
    env_key = os.environ.get("ROBOFLOW_API_KEY")
    return redacted.replace(env_key, "<API_KEY>") if env_key else redacted


def _get(url: str, timeout: int = 60) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"GET {_redact(url)} failed ({e.code}): {body}") from e


def _post(url: str, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"POST {_redact(url)} failed ({e.code}): {body}") from e


def _download(url: str, dest: Path, timeout: int = 120) -> int:
    import shutil
    with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)
    return dest.stat().st_size


# ────────────────────────────── Roboflow calls ──────────────────────────────

def list_projects(ws: str, key: str) -> dict:
    """Cheap read: the workspace and its projects. Lets you discover the project slug + image counts
    without knowing the slug up front. Shape (tolerated defensively):
    {"workspace": {"name":..., "projects": [{"id":"ws/proj","name":...,"images":N}, ...]}}."""
    return _get(f"{API_ROOT}/{ws}?api_key={urllib.parse.quote(key)}")


def get_project_info(ws: str, proj: str, key: str) -> dict:
    """Cheap read: project metadata. Used for the count check and to derive the class list.
    Documented shape: {"workspace":..., "project": {"images": N, "splits": {...}, "classes": {...}},
    "versions": [...]}. We tolerate small shape drift by .get()-ing defensively."""
    return _get(f"{API_ROOT}/{ws}/{proj}?api_key={urllib.parse.quote(key)}")


def search_images(ws: str, proj: str, key: str, offset: int, limit: int) -> dict:
    """One page of the project's images via the Search API (works WITHOUT a version). We ask for the
    fields we need to rebuild YOLO. If your Roboflow returns annotations under a different key, --inspect
    will show it and you adjust extract_boxes()."""
    # Field names are validated by the API; the valid set (from a 400 it returns) is: annotations,
    # aspectRatio, created, embedding, features, filename, height, id, labels, name, owner, projects,
    # score, split, tags, url, user_metadata, width. Note "annotations" (plural) carries the geometry.
    payload = {
        "api_key": key,
        "offset": offset,
        "limit": limit,
        "in_dataset": True,
        "fields": ["id", "name", "filename", "split", "width", "height", "annotations", "labels", "url"],
    }
    return _post(f"{API_ROOT}/{ws}/{proj}/search", payload)


def iter_all_images(ws: str, proj: str, key: str, page: int = 100):
    """Yield every image record, paging through search until a short page ends it."""
    offset = 0
    while True:
        res = search_images(ws, proj, key, offset, page)
        batch = res.get("results") or res.get("images") or []
        if not batch:
            break
        for rec in batch:
            yield rec
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.1)  # be gentle on the API


# ────────────────────────────── annotation -> YOLO ──────────────────────────────

def _find_boxes(record: dict) -> list[dict]:
    """Pull the list of boxes out of an image record, tolerant of the common Roboflow shapes.
    Returns a list of dicts each expected to carry a label + geometry; raises if none is found so a
    silent miswrite can't happen. --inspect shows you the real shape if this raises."""
    ann = record.get("annotation")
    if isinstance(ann, str):
        try:
            ann = json.loads(ann)
        except Exception:
            ann = None
    for container in (ann, record):
        if isinstance(container, dict):
            for key_name in ("boxes", "predictions", "objects", "annotations"):
                boxes = container.get(key_name)
                if isinstance(boxes, list):
                    return boxes
    # A legitimately unlabeled image is valid (background)  - signal that distinctly from "shape unknown".
    if isinstance(ann, dict) and not any(k in ann for k in ("boxes", "predictions", "objects", "annotations")):
        return []
    raise RuntimeError(
        "Could not locate a box list in this record. Run --inspect and adjust _find_boxes() to the "
        f"real shape. Record keys were: {list(record.keys())}"
    )


def extract_yolo_lines(record: dict, class_to_id: dict[str, int]) -> tuple[list[str], int]:
    """Convert one image record's boxes to YOLO label lines. ASSUMED geometry (Roboflow's usual):
    per box {"label"/"class": name, "x": center_x_px, "y": center_y_px, "width": w_px, "height": h_px},
    with the image's own width/height on the record. Confirm this against --inspect; if x/y turn out to
    be a corner rather than the center, change the two lines flagged below."""
    img_w = float(record.get("width") or 0)
    img_h = float(record.get("height") or 0)
    if not (img_w > 0 and img_h > 0):
        raise RuntimeError(f"Image record has no usable width/height: {record.get('name')!r}")

    lines, skipped = [], 0
    for box in _find_boxes(record):
        name = box.get("label") or box.get("class") or box.get("class_name")
        if name is None or name not in class_to_id:
            skipped += 1
            continue
        cx = float(box["x"]); cy = float(box["y"])           # <-- if x/y are a top-left corner, add w/2, h/2 here
        bw = float(box["width"]); bh = float(box["height"])
        # normalize to YOLO (all in [0,1], center form)
        nx, ny, nw, nh = cx / img_w, cy / img_h, bw / img_w, bh / img_h
        nx = min(max(nx, 0.0), 1.0); ny = min(max(ny, 0.0), 1.0)
        nw = min(max(nw, 0.0), 1.0); nh = min(max(nh, 0.0), 1.0)
        lines.append(f"{class_to_id[name]} {nx:.6f} {ny:.6f} {nw:.6f} {nh:.6f}")
    return lines, skipped


def image_download_url(record: dict, key: str) -> str | None:
    """Find a downloadable source-image URL on the record, appending the key if it's a Roboflow URL."""
    for field in ("image", "url", "source", "download"):
        val = record.get(field)
        if isinstance(val, dict):
            val = val.get("url") or val.get("original")
        if isinstance(val, str) and val.startswith("http"):
            if "api.roboflow.com" in val and "api_key=" not in val:
                sep = "&" if "?" in val else "?"
                return f"{val}{sep}api_key={urllib.parse.quote(key)}"
            return val
    return None


# ────────────────────────────── data.yaml ──────────────────────────────

def write_data_yaml(out: Path, class_names: list[str]) -> None:
    lines = [
        "train: images/train",
        "val: images/val",
        "test: images/test",
        f"nc: {len(class_names)}",
        "names:",
        *[f"  {i}: {n}" for i, n in enumerate(class_names)],
    ]
    (out / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ────────────────────────────── modes ──────────────────────────────

def do_check_key(effective: str | None) -> None:
    """Diagnose WHICH key is actually in effect, without exposing it. Compares the value the .env file
    holds against the value the process will send (which, after load_dotenv override=True, should be
    the file's). Only a short masked fragment is printed  - never the whole key."""
    from dotenv import dotenv_values

    def mask(k: str | None) -> str:
        if not k or not k.strip():
            return "MISSING / empty"
        k = k.strip()
        tail = k[-2:] if len(k) > 6 else ""
        return f"len={len(k)}, starts '{k[:3]}...{tail}'"

    file_key = (dotenv_values(ENV_PATH) or {}).get("ROBOFLOW_API_KEY")
    print(f".env file        : {ENV_PATH}")
    print(f".env key         : {mask(file_key)}")
    print(f"key in effect    : {mask(effective)}")
    fk = (file_key or "").strip()
    ek = (effective or "").strip()
    if not ek:
        print("\n>>> No key in effect. Put a valid PRIVATE API key in .env (ROBOFLOW_API_KEY=...).")
    elif fk and fk == ek:
        print("\n>>> The .env key IS the one being used. If Roboflow still returns 401, the key value")
        print(">>> itself is wrong: copy the PRIVATE API key (Settings > API Keys, not Publishable),")
        print(">>> paste with no surrounding quotes and no trailing space, and save the file.")
    else:
        print("\n>>> The key in effect does NOT match .env  - something else is overriding it.")
        print(">>> Re-run in a FRESH terminal (a stale OS env var only clears on a new shell).")


def do_list(ws: str, key: str) -> None:
    info = list_projects(ws, key)
    workspace = info.get("workspace", info)
    projects = workspace.get("projects") or []
    print(f"workspace: {ws}   ({workspace.get('name', '?')})")
    if not projects:
        print("no projects found  - check the workspace slug and the key. Raw response:")
        print(json.dumps(info, indent=2, ensure_ascii=False)[:2000])
        return
    print(f"{len(projects)} project(s):\n")
    for pr in projects:
        # "id" is usually "workspace/project-slug"; the slug is what --project wants.
        pid = pr.get("id", "")
        slug = pid.split("/", 1)[1] if "/" in pid else (pr.get("name") or pid)
        print(f"  slug: {slug:30}  images: {pr.get('images', '?'):>6}   name: {pr.get('name', '')}")
    print("\nPick the slug with ~1150 images, then run:")
    print("  ...export_roboflow_annotations.py --project <slug> --count")


def do_count(ws: str, proj: str, key: str) -> None:
    info = get_project_info(ws, proj, key)
    project = info.get("project", info)
    images = project.get("images")
    splits = project.get("splits") or {}
    classes = project.get("classes") or {}
    print(f"workspace/project : {ws}/{proj}")
    print(f"raw image count   : {images}   <-- expecting ~1150")
    if splits:
        print(f"splits            : {splits}")
    if classes:
        print(f"classes ({len(classes)})     : {classes}")
    else:
        print("classes           : (not in project info; will be derived from the images during export)")
    print("\nOK. If the count looks right, run --inspect next, then --out.")


def do_probe_annotation(ws: str, proj: str, key: str, image_id: str) -> None:
    """The Search API's `annotations` field is only a per-class count, not geometry. Try the likely
    per-image annotation endpoints and dump whichever returns real box data, so we can lock the export
    to the one that works (same discover-from-the-real-response approach that fixed the field names)."""
    qk = urllib.parse.quote(key)
    candidates = [
        f"{API_ROOT}/{ws}/{proj}/{image_id}/annotation?api_key={qk}",
        f"{API_ROOT}/{ws}/{proj}/{image_id}?api_key={qk}",
        f"{API_ROOT}/{ws}/{proj}/annotation/{image_id}?api_key={qk}",
    ]
    for url in candidates:
        base = _redact(url).split("?")[0]
        try:
            data = _get(url)
        except Exception as e:
            print(f"no  : {base}\n      -> {str(e)[:160]}")
            continue
        print(f"\nWORKS: {base}\n")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:4000])
        return
    print("\nNone of the candidate endpoints returned annotation geometry. Send this output and I'll try others.")


def do_inspect(ws: str, proj: str, key: str) -> None:
    for rec in iter_all_images(ws, proj, key, page=1):
        print("First image record (raw JSON)  - use this to confirm field names in extract_yolo_lines():\n")
        print(json.dumps(rec, indent=2, ensure_ascii=False)[:4000])
        return
    print("Search returned no images. Check the workspace/project slugs and the key.")


def do_export(ws: str, proj: str, key: str, out: Path, download_images: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    # Derive the class set from project info if present, else discover it while walking images.
    info = get_project_info(ws, proj, key)
    classes = (info.get("project", info).get("classes")) or {}
    class_names = sorted(classes.keys()) if classes else []
    discovered: set[str] = set()

    for split in ("train", "val", "test"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    # First pass only if we had to discover classes (keeps IDs stable regardless of image order).
    records = list(iter_all_images(ws, proj, key))
    if not class_names:
        for rec in records:
            for box in _find_boxes(rec):
                nm = box.get("label") or box.get("class") or box.get("class_name")
                if nm:
                    discovered.add(nm)
        class_names = sorted(discovered)
    class_to_id = {n: i for i, n in enumerate(class_names)}

    n_img = n_box = n_skip_class = n_no_img = n_collision = 0
    # Roboflow record names are not unique -- uploads from different videos routinely repeat one. Two
    # records sharing a stem used to write the same labels/<split>/<stem>.txt, so one image's boxes
    # vanished while the counter still reported both as exported.
    used_stems: set[tuple[str, str]] = set()
    for rec in records:
        # Roboflow split names vary ("valid" vs "val"); normalize to YOLO's train/val/test.
        split = (rec.get("split") or "train").lower()
        split = {"valid": "val", "validation": "val", "test": "test"}.get(split, "train" if split not in ("val", "test") else split)
        stem = Path(rec.get("name") or rec.get("id") or f"img{n_img}").stem
        if (split, stem) in used_stems:
            base, suffix = stem, 2
            while (split, f"{base}__{suffix}") in used_stems:
                suffix += 1
            stem = f"{base}__{suffix}"
            n_collision += 1
            print(f"  ! duplicate name '{base}' in split '{split}' - writing it as '{stem}'")
        used_stems.add((split, stem))
        lines, skipped = extract_yolo_lines(rec, class_to_id)
        n_box += len(lines); n_skip_class += skipped
        (out / "labels" / split / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        if download_images:
            url = image_download_url(rec, key)
            if not url:
                n_no_img += 1
            else:
                try:
                    _download(url, out / "images" / split / f"{stem}.jpg")
                except Exception as e:  # a single bad image shouldn't abort the whole pull
                    print(f"  ! image download failed for {stem}: {e}")
                    n_no_img += 1
        n_img += 1
        if n_img % 100 == 0:
            print(f"  ...{n_img} images")

    write_data_yaml(out, class_names)
    print(f"\nDone. images={n_img}  boxes={n_box}  classes={class_names}")
    if n_skip_class:
        print(f"  {n_skip_class} boxes skipped (label not in class list)")
    if n_collision:
        print(f"  {n_collision} duplicate filenames were renamed rather than overwritten")
    if download_images and n_no_img:
        print(f"  {n_no_img} images had no downloadable URL  - see note below")
    if not download_images:
        print("  labels only (--no-images): put the matching image files into images/<split>/ yourself,")
        print("  e.g. the frames you already extracted locally, matched by filename stem.")
    print(f"\nNext: python train_roboflow_yolo.py --skip-download --dataset-dir {out} "
          f"--imbalance-threshold 999 --epochs 50 --device cpu")


# ────────────────────────────── CLI ──────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Export a Roboflow project to local YOLO without a Version.")
    p.add_argument("--workspace", default="fhasai-khuanpan", help="Roboflow workspace slug (from the project URL)")
    p.add_argument("--project", default=None, help="Roboflow project slug (from the project URL); not needed for --list")
    p.add_argument("--api-key", default=os.environ.get("ROBOFLOW_API_KEY"),
                   help="defaults to ROBOFLOW_API_KEY in webapp/.env or the environment")
    p.add_argument("--out", default=None, help="output dataset dir for a full export")
    p.add_argument("--check-key", action="store_true", help="report (masked) which API key is actually in effect, then exit  - no network call")
    p.add_argument("--list", action="store_true", help="list all projects in the workspace (slug + image count), then exit")
    p.add_argument("--count", action="store_true", help="only print the project + raw image count, then exit")
    p.add_argument("--inspect", action="store_true", help="dump one raw image record and exit (to confirm field shapes)")
    p.add_argument("--anno", default=None, metavar="IMAGE_ID", help="probe per-image annotation endpoints for one image id, then exit")
    p.add_argument("--no-images", action="store_true", help="write labels + data.yaml only, skip downloading image files")
    args = p.parse_args()

    if not args.api_key:
        print("ERROR: no API key. Set ROBOFLOW_API_KEY in webapp/.env (it is gitignored) or pass --api-key.",
              file=sys.stderr)
        return 2

    if args.check_key:
        do_check_key(args.api_key)
        return 0
    if args.list:
        do_list(args.workspace, args.api_key)
        return 0
    if not args.project:
        print("ERROR: --project is required (run --list first to find the slug).", file=sys.stderr)
        return 2

    if args.anno:
        do_probe_annotation(args.workspace, args.project, args.api_key, args.anno)
    elif args.count:
        do_count(args.workspace, args.project, args.api_key)
    elif args.inspect:
        do_inspect(args.workspace, args.project, args.api_key)
    elif args.out:
        do_export(args.workspace, args.project, args.api_key, Path(args.out).resolve(), not args.no_images)
    else:
        print("Nothing to do. Pick one of --count / --inspect / --out <dir>. Start with --count.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
