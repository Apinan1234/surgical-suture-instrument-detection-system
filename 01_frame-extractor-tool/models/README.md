# models/

Two kinds of file live here, and git treats them differently (see `../.gitignore`):

- **Uploaded models** (`POST /api/models`) — user data, ignored by git.
- **Trained baselines** — committed on purpose, listed below.

## Why a baseline is copied here instead of left in `runs/`

`runs/` is gitignored, and `train_roboflow_yolo.py` trains with `exist_ok: true`, so the next
training run writes over `runs/roboflow_train/train/weights/best.pt` in place. A copy here is the
only durable record of a model that produced known numbers.

`server.py`'s `_scan_models()` already globs this directory, so a file dropped here shows up in the
Detect / Label Assist model pickers with no further wiring.

## Baselines

### `ssid_v6i_20260808_map50-557.pt`

Byte-identical copy (SHA-256 `c96f6e80…e54f95c`) of `runs/roboflow_train/train/weights/best.pt` as
it stood on 2026-08-08.

| | |
|---|---|
| Base | `yolo11n.pt`, `task=detect` |
| Dataset | `ssid.v6i.yolov11` (Roboflow `fhasai-khuanpan/ssid` v6, CC BY 4.0) — 564 train / 81 val / 80 test |
| Classes | `finger`, `forcep`, `needle`, `needle_holder`, `wound` |
| Training | 10 epochs, `imgsz 640`, `batch 16`, `device cpu`, `seed 42` — 1892 s |
| Results (epoch 10) | **mAP50 0.557**, mAP50-95 0.272, precision 0.579, recall 0.539 |

Measured behaviour on real footage (2726 frames of suturing practice, conf 0.25): 17151 boxes —
finger 12434, wound 2439, needle_holder 1707, forcep 565, **needle 6**. The `needle` class is
effectively blind at this checkpoint; needles are hand-drawn work until a later version fixes it.
Lowering conf to 0.15 only added low-confidence duplicates, so **use conf 0.25**.

The full run's curves, confusion matrix and `results.csv` stay in
`runs/roboflow_train/train/` — on this machine only.
