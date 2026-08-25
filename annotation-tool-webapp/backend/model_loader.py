import os
os.environ.setdefault("ULTRALYTICS_SAFE_LOAD", "1")  # belt-and-suspenders vs. frontend/app.py's
# own guard, in case this module is ever imported standalone before that one runs

from pathlib import Path

from ultralytics import YOLO
from frame_miner.classes import native_order

# Relative to this repo, not a machine-specific absolute path: this checkpoint is the single
# tracked source of truth for the 9-class baseline (see 01_frame-extractor-tool/models/README.md) —
# reused here rather than duplicating a 5.4 MB weight file into this folder too.
MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "01_frame-extractor-tool" / "models" / "ssid9_960px_150ep_20260813_map50-716.pt"
)
_model = None
_class_names = None

def load_model(path: "str | Path" = MODEL_PATH):
    global _model, _class_names
    if _model is None:
        _model = YOLO(path)
        _class_names = native_order(_model.names)
    return _model, _class_names
