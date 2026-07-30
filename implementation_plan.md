# แผนจัดระเบียบโฟลเดอร์ VideoFrameExtractor

## สรุปปัญหา

โฟลเดอร์ `VideoFrameExtractor` มีไฟล์และโฟลเดอร์กระจัดกระจาย ตั้งชื่อไม่ชัดเจน (เช่น "New folder", "New folder (2)") ทำให้ดูยุ่งเหยิง

## โครงสร้างใหม่ที่เสนอ

```
VideoFrameExtractor/
├── 01_frame-extractor-tool/        ← Python tool หลัก
│   ├── app.py
│   ├── frame_extractor.py
│   ├── detector.py
│   ├── dataset_exporter.py
│   ├── requirements.txt
│   ├── run_app.bat
│   ├── yolo11n.pt
│   ├── yolov8n.pt
│   ├── README.md
│   ├── frame_extractor_doc.md
│   └── .venv/
│
├── 02_web-app/                     ← React Web App (ai-surgical-instrument-detection-system)
│   └── (ทั้งหมดของ ai-surgical-instrument-detection-system)
│
├── 03_dataset/                     ← Dataset ที่ extract แล้ว
│   ├── raw-frames/                 ← (จาก "New folder" - frames จากวิดีโอ)
│   ├── ezgif-frames/               ← (จาก "ezgif-14d5a3887baf1d86-jpg")
│   └── test-output/                ← (จาก test_output_dataset)
│
├── 04_demos/                       ← Demo/prototype pages
│   └── scroll-demo/
│
└── _archive/                       ← ไฟล์เก่า/ไม่ใช้แล้ว
    ├── ai-surgical-instrument-detection-system.zip
    ├── ezgif-14d5a3887baf1d86-jpg.zip
    ├── New folder (2)/             ← โฟลเดอร์เปล่า
    ├── Deploy Workflow Images.txt
    ├── Deploy Workflow Video.txt
    ├── Handoff.txt
    ├── WORK_PLAN.md
    ├── scratchpad_tt1wdy7t.md
    └── __pycache__/
```

## สิ่งที่จะทำ

1. สร้างโฟลเดอร์ใหม่ทั้งหมด
2. ย้ายไฟล์ Python tool ไปยัง `01_frame-extractor-tool/`
3. ย้าย (rename) `ai-surgical-instrument-detection-system/` → `02_web-app/`
4. ย้าย dataset folders ไปยัง `03_dataset/`
5. ย้าย `scroll-demo/` ไปยัง `04_demos/`
6. รวมไฟล์เก่า/ไม่จำเป็นไว้ใน `_archive/`

## ข้อควรระวัง

> [!IMPORTANT]
>
> - **ไม่ลบ** ไฟล์ใดๆ — ย้ายเท่านั้น
> - `.git` และ `.claude` จะ**ไม่ย้าย** (เพราะเป็น repository root)
> - `Report-Phase-1-1 (1).pdf` จะถามก่อนว่าจะเก็บที่ไหน

## Open Questions

> [!IMPORTANT]
> ไฟล์ `Report-Phase-1-1 (1).pdf` ควรวางไว้ที่ไหน?
>
> - A) เก็บไว้ที่ root เลย
> - B) ย้ายไปที่ `_archive/`
> - C) สร้างโฟลเดอร์ใหม่ `05_reports/`
