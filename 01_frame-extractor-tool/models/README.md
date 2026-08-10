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

### `ssid_v6i_50ep_20260810_map50-608.pt`  (current best)

Same data and hyperparameters as the 10-epoch baseline below, trained for **50 epochs** to test
whether that baseline was simply undertrained. It was. Copy of
`runs/roboflow_train_50ep/train/weights/best.pt`.

| | |
|---|---|
| Results (epoch 50) | **mAP50 0.608**, mAP50-95 0.311, precision 0.645, recall 0.598 |
| Per-class mAP50 | finger 0.857, needle_holder 0.877, forcep 0.736, wound 0.518, **needle 0.114** |

The point of the run was `needle`, which the baseline scored 0.008 on and never once produced on
real footage. Here it reaches 0.114 (precision 0.000 -> 0.415) and fires on **30 of 40 sampled real
frames at the ordinary 0.25 threshold**, where the baseline managed 0 of 40. It is still the weakest
class by a wide margin; needles from this footage are what the next round of annotation is for.

Inference stays at **imgsz 640**. Re-tested on this checkpoint: 1280 drops needle from 34 boxes to 6
and wound from 50 to 17, 1920 drops needle to 1 -- the model is trained at 640 and anything else is
off-distribution.

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
