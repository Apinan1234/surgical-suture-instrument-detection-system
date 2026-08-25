# เอกสารอ้างอิงโค้ด — สำหรับตอบคำถามกรรมการเรื่อง 5 ขั้นตอนที่สาธิต

ระบุ **โค้ดที่ใช้งานจริง** (ไม่ใช่ของทดลอง/ค้าง) ต่อขั้นตอนที่สาธิตในเว็บแอป พร้อมไฟล์:บรรทัดที่แม่นยำ
ตรวจสอบตรงจากซอร์สโค้ดจริงเมื่อ 17 ส.ค. 2569 — ถ้าโค้ดถูกแก้ไขหลังจากนี้ เลขบรรทัดอาจขยับได้

ทุก endpoint นับจากการรัน `grep` จริงบน `server.py` ได้ **38 เส้นทาง** (ตรงกับที่พูดในสไลด์ System Framework)

---

## 1. สกัดเฟรม (Extract Frames)

| ส่วน | ไฟล์:บรรทัด | หน้าที่ |
|---|---|---|
| ปุ่มกด UI | `static/app.js:312` | `extract-start-btn` click handler — รวบรวมค่าจากฟอร์ม (mode, threshold, prefix ฯลฯ) |
| เรียก API | `static/app.js:333` | `apiFetch("/api/extract", {method:"POST", ...})` |
| Route หลัก | `server.py:514-548` | `start_extract(body: ExtractBody)` |
| **ตรรกะหลัก** | `frame_extractor.py` → ฟังก์ชัน `extract_frames()` | import ที่ `server.py:38` — ทำ slot-based selection, กรอง Laplacian variance (เบลอ) + motion IoU (ซ้ำ) |
| อัปโหลดวิดีโอ | `server.py:276` (`upload_videos`), `server.py:327` (`list_videos`) | |
| ติดตามสถานะ/ผล | `server.py:549` (status), `server.py:576` (รายชื่อเฟรม), `server.py:589` (หยุด) | polling ระหว่างรัน |
| ดาวน์โหลด ZIP | `server.py:639` (เริ่มทำ zip), `server.py:669` (สถานะ), `server.py:678` (ดาวน์โหลด) | |

**ถ้าถูกถาม "อัลกอริทึมคัดเฟรมอยู่ตรงไหน":** ชี้ที่ `frame_extractor.py` (`extract_frames`) — ไม่ใช่ใน
`server.py`, `server.py` แค่เรียกใช้และจัดการ job/สถานะเท่านั้น

---

## 2. ตรวจจับ (Detect)

| ส่วน | ไฟล์:บรรทัด | หน้าที่ |
|---|---|---|
| ปุ่มกด UI | `static/app.js:945` | `detect-start-btn` click handler — อ่านค่า backend/model/conf/device |
| เรียก API | `static/app.js:972` | `apiFetch("/api/detect", ...)` |
| Route หลัก | `server.py:1083-1122` | `start_detect(body: DetectBody)` |
| **ตรรกะหลัก** | `detector.py` → คลาส `YOLOv11Detector`, `RoboflowDetector`, `BaseDetector` | import ที่ `server.py:39` — ตัวเลือก local `.pt` vs Roboflow Cloud API สลับกันได้ผ่าน `backend` param |
| โหลด/จัดการโมเดล | `server.py:1863` (list), `server.py:1868` (upload), `server.py:1901` (load) | `list_models`/`upload_model`/`load_model` |
| ติดตามสถานะ | `server.py:1123` (status), `server.py:1132` (รายชื่อเฟรม), `server.py:1145` (หยุด) | |

**ถ้าถูกถาม "ป้องกัน .pt อันตรายยังไง":** `ULTRALYTICS_SAFE_LOAD` (env var, ค่าเริ่มต้น `true`) —
บังคับใช้ restricted/weights_only loading ใน `detector.py` ตอนโหลดโมเดล ป้องกัน arbitrary code execution
จากไฟล์ `.pt` ที่อัปโหลดมา (นี่คือด่านป้องกันหลักตั้งแต่ตัดระบบ login ออก)

---

## 3. กำกับข้อมูล (Annotate)

ส่วนนี้ endpoint เยอะที่สุด (14 เส้นทาง) เพราะครอบคลุมทั้งวาดกรอบ/ตรวจทาน/AI-assist/OCR

| ส่วน | ไฟล์:บรรทัด | หน้าที่ |
|---|---|---|
| ปุ่ม Confirm ทั้งหมด | `static/app.js:3701` | `confirm-all-btn` click handler |
| ปุ่ม Confirm ตามช่วงที่แสดง | `static/app.js:3227` | `annotate-confirm-range-btn` → `confirmShownFrames` |
| บันทึกกรอบ (ทีละเฟรม) | `static/app.js:1414` → `server.py:1303-1357` | `API.postDetections` → `replace_frame_detections` |
| บันทึกกรอบ (หลายเฟรมพร้อมกัน) | `server.py:1358-1421` | `replace_frame_detections_bulk` |
| Label Assist (AI เสนอกรอบ) | `static/app.js:3633` (`runAssist`) → `static/app.js:1444` (`API.postAssist`) → `server.py:1523-1602` | `assist_frame` — เรียก detector ให้เสนอกรอบต่อเฟรมเดียว |
| ทำเครื่องหมายตรวจทานแล้ว | `server.py:1422` (ทีละเฟรม), `server.py:1439` (หลายเฟรม) | `mark_frame_reviewed`/`review_frames_bulk` |
| OCR อ่านข้อความในภาพ | `server.py:1603` (ทีละเฟรม), `server.py:1707` (เป็นชุด/job) | ใช้ `pytesseract` (import `server.py:21`) |
| แสดงภาพ/thumbnail | `server.py:1481`, `server.py:1496`, `server.py:1174` | |

**ถ้าถูกถาม "AI Suggestions เส้นประมาจากไหน":** สามทาง — (1) ผล bulk `/api/detect` ที่ยังไม่ยืนยัน
(2) ผล Label Assist จาก `assist_frame` (`server.py:1523`) (3) ผลจาก interpolate (เดากรอบระหว่าง
keyframe — โค้ด interpolation อยู่ใน `static/app.js` โมดูล `Interpolate`, ปุ่มเริ่มที่บรรทัด 3510)

---

## 4. ส่งออก (Export)

| ส่วน | ไฟล์:บรรทัด | หน้าที่ |
|---|---|---|
| ปุ่มกด UI | `static/app.js:3948` | `export-start-btn` click handler — อ่านค่า format/split/preprocessing/augmentation |
| เรียก API | `static/app.js:3972` | `apiFetch("/api/export", ...)` |
| Route หลัก | `server.py:2138-2173` | `start_export(body: ExportBody)` |
| **ตรรกะหลัก** | `dataset_exporter.py` → ฟังก์ชัน `export_dataset_pipeline()` | import ที่ `server.py:41` — แปลง bbox-only ให้ export ได้ทั้ง detect/segment/pose |
| ดูตัวอย่างก่อน export | `server.py:2085-2137` | `export_preview` — ใช้ `count_stats()` (import เดียวกันบรรทัด 41) |
| ติดตามสถานะ/ดาวน์โหลด | `server.py:2174` (status), `server.py:2183` (download) | |

**ถ้าถูกถาม "แปลง bbox เป็น segment/pose ยังไง":** ชี้ที่ `dataset_exporter.py` โดยตรง — bbox-only แปลง
เป็น 4 มุมสี่เหลี่ยม (segment) หรือ bbox พร้อม keypoint slot ว่าง (pose) ตามที่พูดในสไลด์

---

## 5. Analytics

| ส่วน | ไฟล์:บรรทัด | หน้าที่ |
|---|---|---|
| เปิดแท็บ → ดึงข้อมูล | `static/app.js:155-170` (`switchTab`) → `static/app.js:4066` (`refreshAnalytics`) | ไม่มี route ใน URL แยก ต้องคลิกแท็บจริงถึงดึงข้อมูล |
| Route หลัก | `server.py:1946-2028` | `analytics()` — คำนวณสดทุกครั้งที่เรียก ไม่ cache |
| สูตร accept rate | `server.py:1965-1976` | `tracked`/`suggested_total`/`accepted_total`/`rate_pct` — คอมเมนต์ในโค้ดอธิบายบั๊กเดิมไว้ตรงนี้เลย |

**ถ้าถูกถาม "ทำไมบั๊กเดิมถึงเกิด":** อ่านคอมเมนต์ตรง `server.py:1955-1964` ได้เลย อธิบายไว้ละเอียดว่า
ตัวหารกับตัวตั้งเคยนับข้อมูลคนละชุดกันยังไง

---

## หมายเหตุรวม

- **โมดูลหลัก 3 ตัวที่ทำงานจริงเบื้องหลัง 5 ขั้นตอน**: `frame_extractor.py` (สกัดเฟรม) · `detector.py`
  (ตรวจจับ, ทั้ง local YOLO และ Roboflow) · `dataset_exporter.py` (ส่งออก) — ทั้งสามอยู่ที่
  `01_frame-extractor-tool/` (ไม่ใช่ใต้ `webapp/`) เพราะออกแบบให้ใช้ร่วมกับสคริปต์เทรน/ประเมินผลได้ด้วย
  ไม่ใช่โค้ดเฉพาะเว็บแอป
- **`server.py` เป็นแค่ตัวประสาน (orchestration layer)** — รับ request, จัดการ background job/thread,
  เขียน `state.json`, เรียกสามโมดูลข้างบน ไม่มีตรรกะ ML/image-processing อยู่ในตัวมันเอง (ยกเว้น OCR ที่
  เรียก `pytesseract` ตรงๆ เพราะเป็นงานเบา ไม่คุ้มแยกโมดูล)
- ถ้ากรรมการถามหาโค้ดที่ **ไม่ได้ใช้จริง/เป็นของทดลอง** — ให้ตอบตรงๆ ว่าอยู่นอกเว็บแอป เช่น
  `01_frame-extractor-tool/results_reannot_screening/` (สคริปต์ทดลอง class-balancing ที่คุยกันไปก่อนหน้า)
  หรือสคริปต์เทรนโมเดล (`train_ssid9_960.py` ฯลฯ) — เหล่านี้รันแยกจากเว็บแอป ไม่ได้ import เข้ามาใน
  `server.py`
