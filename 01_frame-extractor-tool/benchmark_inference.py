# -*- coding: utf-8 -*-
"""วัดความเร็วการอนุมาน (inference) ของโมเดลที่ใช้จริง ผ่านโค้ดเส้นทางเดียวกับที่เว็บแอปเรียก

จงใจวัดผ่าน `YOLOv11Detector.predict()` ไม่ใช่เรียก ultralytics ตรง ๆ เพราะสิ่งที่ต้องตอบให้ได้คือ
"ระบบนี้เร็วแค่ไหน" ไม่ใช่ "ไลบรารีเร็วแค่ไหน" ตัวเลขที่ได้จึงรวมการอ่านไฟล์ภาพ การกรองรายคลาส
และการแปลงผลเป็น Detection ตามที่เว็บแอปทำจริงทุกครั้ง

    python benchmark_inference.py                     # อุปกรณ์ตามค่าตั้งต้น (cpu)
    python benchmark_inference.py --device cuda:0     # ต้องใช้ venv ที่มี torch แบบ CUDA
    python benchmark_inference.py --warmup 3 -n 50

อ่านอย่างเดียว ไม่เขียนอะไรลงดิสก์ ไม่แตะ webapp/state.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_MODEL = HERE / "models" / "ssid9_960px_150ep_20260813_map50-716.pt"
DEFAULT_FRAMES = HERE.parent / "03_dataset" / "ssid.yolov11" / "valid" / "images"


def imread_unicode(path: Path) -> np.ndarray | None:
    """cv2.imread คืน None เงียบ ๆ กับ path ที่มีอักษรไทย — อ่านผ่าน np.fromfile แทน"""
    import cv2
    buf = np.fromfile(str(path), dtype=np.uint8)
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--frames", default=str(DEFAULT_FRAMES))
    ap.add_argument("--device", default="cpu")
    ap.add_argument("-n", "--count", type=int, default=40, help="จำนวนเฟรมที่วัด")
    ap.add_argument("--warmup", type=int, default=3, help="จำนวนเฟรมอุ่นเครื่อง ไม่นับเข้าสถิติ")
    ap.add_argument("--json", default=None, help="เขียนผลเป็น JSON ลงไฟล์นี้")
    args = ap.parse_args()

    frames_dir = Path(args.frames)
    paths = sorted(p for p in frames_dir.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not paths:
        print("ไม่พบไฟล์ภาพใน %s" % frames_dir)
        return 1
    need = args.count + args.warmup
    paths = paths[:need]
    if len(paths) < need:
        print("มีภาพแค่ %d ไฟล์ ขอ %d" % (len(paths), need))
        return 1

    from detector import YOLOv11Detector

    print("โมเดล : %s" % Path(args.model).name)
    print("อุปกรณ์: %s" % args.device)

    t0 = time.perf_counter()
    det = YOLOv11Detector(model_path=args.model, device=args.device)
    load_s = time.perf_counter() - t0
    print("ขนาดภาพที่โมเดลใช้จริง (imgsz): %s" % det.imgsz)
    print("เวลาโหลดโมเดลครั้งแรก: %.2f วินาที" % load_s)

    # อ่านภาพทั้งหมดเข้าหน่วยความจำก่อน แล้ววัดสองอย่างแยกกัน:
    # เวลาอ่านไฟล์ (ดิสก์) กับเวลาอนุมาน (โมเดล) — รวมกันคือเวลาต่อเฟรมที่ผู้ใช้รู้สึกได้
    read_ms, infer_ms, nbox = [], [], []
    for i, path in enumerate(paths):
        t = time.perf_counter()
        img = imread_unicode(path)
        r = (time.perf_counter() - t) * 1000
        if img is None:
            print("อ่านไม่ได้: %s" % path.name)
            return 1
        t = time.perf_counter()
        dets = det.predict(img)
        d = (time.perf_counter() - t) * 1000
        if i >= args.warmup:                     # ตัดรอบอุ่นเครื่องทิ้ง
            read_ms.append(r)
            infer_ms.append(d)
            nbox.append(len(dets))

    def q(vals, p):
        s = sorted(vals)
        return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]

    total = [r + d for r, d in zip(read_ms, infer_ms)]
    out = {
        "model": Path(args.model).name,
        "device": args.device,
        "imgsz": det.imgsz,
        "frames_measured": len(infer_ms),
        "warmup_frames": args.warmup,
        "model_load_s": round(load_s, 2),
        "read_ms_median": round(statistics.median(read_ms), 1),
        "infer_ms_median": round(statistics.median(infer_ms), 1),
        "infer_ms_p95": round(q(infer_ms, 0.95), 1),
        "total_ms_median": round(statistics.median(total), 1),
        "frames_per_sec": round(1000.0 / statistics.median(total), 2),
        "frames_per_min": int(round(60_000.0 / statistics.median(total))),
        "boxes_per_frame_median": statistics.median(nbox),
    }

    print("")
    print("วัดจาก %d เฟรม (อุ่นเครื่อง %d เฟรม ไม่นับ)" % (out["frames_measured"], args.warmup))
    print("  อ่านไฟล์ภาพ      มัธยฐาน %7.1f ms" % out["read_ms_median"])
    print("  อนุมาน           มัธยฐาน %7.1f ms   (p95 %.1f ms)" % (out["infer_ms_median"],
                                                                  out["infer_ms_p95"]))
    print("  รวมต่อเฟรม       มัธยฐาน %7.1f ms" % out["total_ms_median"])
    print("  อัตราการประมวลผล %.2f เฟรม/วินาที  =  %d เฟรม/นาที" % (out["frames_per_sec"],
                                                                    out["frames_per_min"]))
    print("  กล่องที่พบต่อเฟรม มัธยฐาน %s" % out["boxes_per_frame_median"])

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\nเขียน JSON ลง %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
