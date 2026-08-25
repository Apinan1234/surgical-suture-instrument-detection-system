# เนื้อหาที่แยกจากไฟล์ 66120361_real.pdf (24 หน้า)

โปรเจกต์: ระบบตรวจจับและจำแนกอุปกรณ์เย็บแผลด้วย YOLOv11 พร้อมเว็บแอปพลิเคชันสนับสนุนการเตรียมชุดข้อมูล
(หมายเหตุ: เลขหน้าที่ปรากฏในสไลด์คือเลขหน้าเอกสารต้นฉบับ/นำเสนอ ซึ่งอาจไม่ตรงกับลำดับหน้า PDF — เวอร์ชันนี้เป็นฉบับอัปเดต/ฉบับจริง มีเนื้อหาเพิ่มจากไฟล์ก่อนหน้ามาก โดยเฉพาะส่วน System Framework/Infrastructure และผลการทดลองเชิงลึก)

---

## หน้า 1 — Section Header
**WEB APPLICATION DEMONSTRATION**

---

## หน้า 2 (สไลด์ 18) — "1. สกัดเฟรม (Extract Frames)"

หน้าจอเว็บแอป แสดงส่วน **Videos** และ **Extract Frames**:

- **Videos**: อัปโหลดไฟล์วิดีโอ (ตัวอย่าง: `Video Project 3.mp4 (24.6 MB)`) มีปุ่ม Choose Files / Remove
- **Extract Frames**
  - Mode: Adaptive (Target frame count) [เลือกอยู่] / Fixed Interval / All Frames
  - Target frame count: `12`
  - TRIM (OPTIONAL): Start time (seconds) = `0`, End time (seconds) = `until end of video`
  - SIMILARITY & BLUR FILTERING
    - Similarity filter method: `Motion IoU`
    - Similarity threshold: `2`
    - ✅ Filter blurry frames
    - Blur threshold: `5`
  - OUTPUT
    - Output size (optional): `Up to 1280px (long edge)`
    - Filename prefix: `surgery01` (Saved as: yourname_frame_00000.jpg)
    - Max attempts per slot: `5`
    - ✅ Separate folder per video
  - ปุ่ม **Start Extraction** (สีแดง)
  - Log ผลลัพธ์: `done — 11 frames saved`
    ```
    [Info] Video Project 3.mp4: 11.8s -> 0.99s/frame
    วิดีโอ: f3f3cca7cdb34eafa08967e7f00d3cfb.mp4
      FPS: 30.0 | เฟรมทั้งหมด: 355 | ความยาว: 11.8 วิ
      สัมผัส 0.99 วิ | ซึ: motion_iou | threshold: 2.0
    [saved] เฟรม 0 (slot 0) -> surgery01_frame_00000.jpg (score=999.0)
    [saved] เฟรม 29 (slot 1) -> surgery01_frame_00001.jpg (score=100.0)
    [saved] เฟรม 58 (slot 2) -> surgery01_frame_00002.jpg (score=23.7)
    [saved] เฟรม 87 (slot 3) -> surgery01_frame_00003.jpg (score=52.3)
    [saved] เฟรม 116 (slot 4) -> surgery01_frame_00004.jpg (score=28.1)
    [saved] เฟรม 145 (slot 5) -> surgery01_frame_00005.jpg (score=2.7)
    [skip] เฟรม 174 (slot 6) -> คล้าย (score=1.7), ลอง frame ถัดไป
    [skip] เฟรม 175 (slot 6) -> คล้าย (score=1.7), ลอง frame ถัดไป
    [skip] เฟรม 176 (slot 6) -> คล้าย (score=1.7), ลอง frame ถัดไป
    ```
  - ปุ่ม **Download frames as ZIP**

---

## หน้า 3 (สไลด์ 19) — "2. ตรวจจับ (Detect)"

หน้าจอเว็บแอป แสดงส่วน **Model**, **Inference Settings**, **Augmentation**, **Create Version**:

- **Model**
  - เลือก Local (.pt) หรือ Roboflow Cloud API
  - Model: `models/ssid_v6i_50ep_20260810_map50-608.pt — 5 classes · 5.5 MB`
  - Upload trained model (.pt): Choose File
  - ปุ่ม **Load model** — สถานะ: `Not loaded yet`
  - Device: CPU [เลือกอยู่] / CUDA / MPS
- **Inference Settings**
  - Confidence threshold: `0.25`
- **Augmentation**
  - ✅ Flip (Horizontal/Vertical)
  - ✅ Rotation (Between -15° and +15°)
  - ✅ Brightness & Contrast
  - ✅ Blur / Noise
  - ✅ Random Crop
  - Augmentation Multiplier: `1` (หมายเหตุ: Multiplier > 1x ต้องติดตั้งแพ็กเกจ albumentations ซึ่งไม่ได้ติดตั้งมาโดยดีฟอลต์)
- **Create Version**
  - Maximum Version Size: 11 images (1x)
  - ปุ่ม **Create Version**
  - สถานะ: `done — 11 images exported`
  - ปุ่ม **Download dataset as ZIP**

---

## หน้า 4 (สไลด์ 19) — "3. กำกับข้อมูล (Annotate)"

หน้าจอเว็บแอป (แถบเมนูบน: Extract | Detect | **Annotate** | Export | Analytics):

- แถบเครื่องมือ: Select / Draw / Polygon / Keypoint / Needs Review / Mark as Reviewed (มีปุ่ม "Press ? for shortcuts")
- ด้านซ้าย: ช่องค้นหา OCR text, dropdown filter "All", ปุ่ม "Confirm 6 shown", รายการภาพ (thumbnails): `21_frame_00306...`, `21_frame_00307...`, `21_frame_00308...`, `42_frame_00003...`, `42_frame_00004...`, `42_frame_00005...`
- ตรงกลาง: ภาพตัวอย่างมือกำลังเย็บแผลบนแผ่นซิลิโคนจำลอง มีกรอบ (bounding box) และ label กำกับวัตถุ เช่น `needle_holder`, `finger`, `hand`, `Tip_forcep`, `needle`
- ด้านขวา: **DETECTIONS** panel
  - `needle_holder` — score 0.92
  - `finger` — score 0.74
  - `forcep` — score 0.69
  - checkboxes: occluded / truncated
  - ปุ่ม "← Copy from previous frame"
  - **AI SUGGESTIONS (DASHED)** — คำอธิบาย: กรอบเส้นประยังไม่ยืนยัน มาจาก Detect, Label Assist หรือ interpolated span การบันทึกเฟรมจะยืนยันสิ่งที่กรอบนั้นระบุ
  - ปุ่ม **Confirm All** / **Reject All**
  - **INTERPOLATE**: "No start keyframe", ปุ่ม "Set start keyframe (S)"
- ด้านล่าง: `Frame 2 / 6`, `23 box(es) (23 unconfirmed AI)`, `0 / 6 reviewed`, ปุ่ม "← Detect" / "Export →"

---

## หน้า 5 (สไลด์ 20) — "4. ส่งออก (Export)"

หน้าจอเว็บแอป สองแผง:

**แผงซ้าย**
- **Version Info & Dataset Status**
  - `2726 frame(s) available from the last Detect run.`
  - Version Name: `v1`
  - ☐ Only export reviewed frames
  - Badges: Total: 2726 | Classes: 5 | ⚠ Unreviewed: 2725
- **Export Format**
  - ⦿ Detect (bounding boxes)
  - ○ Segment (polygons — Ultralytics YOLO seg format)
  - ○ Pose (keypoints — Ultralytics YOLO-pose format)
  - หมายเหตุ: Bbox-only detections export เป็น 4 มุมของสี่เหลี่ยมเมื่อเลือก Segment หรือเป็น bbox-only พร้อม keypoint slot ว่างทั้งหมดเมื่อเลือก Pose — เพื่อให้ dataset แบบผสมเทรนได้ทั้งสองแบบ
- **Train / Val / Test Split**
  - Train %: 70, Val %: 20 → 70% Train / 20% Val / 10% Test

**แผงขวา**
- **Train / Val / Test Split** (ซ้ำ) — Train 70% / Val 20% / 70% Train / 20% Val / 10% Test
- **Preprocessing**: ✅ Resize (Fit within 640x640)
- **Augmentation**: ✅ Flip (Horizontal/Vertical), ✅ Rotation (-15°~+15°), ✅ Brightness & Contrast, ✅ Blur / Noise, ✅ Random Crop; Augmentation Multiplier: 1 (multiplier > 1x ต้องมี albumentations ซึ่งไม่ได้ติดตั้งมาโดยดีฟอลต์)

---

## หน้า 6 (สไลด์ 20) — System Framework (บริการที่เว็บแอปวิ่งอยู่บน)

### แผนภาพสถาปัตยกรรม (System Framework Diagram)

```
«PROCESS» webapp/server.py — Python 1 โปรเซสเดียว (FastAPI + Uvicorn)
Frontend ไม่ใช่บริการแยก — เสิร์ฟจากโปรเซสเดียวกับ Server ทั้งหมด

┌─────────────────────┐   ┌──────────────────────────┐        ┌──────────────────────────┐
│ Frontend         [1] │   │ Server               [2] │        │ Database             [3] │
│ ไม่ใช่บริการแยก        │   │ บริการจริงหนึ่งเดียว        │        │ ไม่มีฐานข้อมูล (No database)│
│ ──────────────────  │   │ ────────────────────────│        │ ─────────────────────── │
│ index.html           │   │ FastAPI + Uvicorn         │        │ state.json                │
│ style.css             │   │ 1 process · CPU-only      │──────>│ ไฟล์แบนราบ (flat file)     │
│ app.js                │   │                            │อ่าน/  │ เขียนแบบ atomic: tmp→rename│
│ ไม่มี framework · ไม่มี build│ │ 38                        │เขียนไฟล์│ ผู้ใช้คนเดียว เครื่องเดียว    │
│ เสิร์ฟผ่าน StaticFiles mount│ │ endpoint                  │        │ ย้ายเครื่อง = คัดลอกโฟลเดอร์  │
│ โดยโปรเซสเดียวกับ Server │   │ @get · @post · @put        │        │                            │
│                       │   │ @delete · @patch          │        │ webapp/state.json         │
│ server.py:2199        │   │                            │        └──────────────────────────┘
└─────────────────────┘   │ ให้บริการทั้ง API และไฟล์ static │        ภายนอกระบบ · ทางเลือก
                            │ (mount เดียวกับ Frontend)   │        ┌──────────────────────────┐
                            │ งานหนักกันด้วย threading +   │- - -REST API- ->│ Roboflow Cloud API      │
                            │ polling                    │(ทางเลือก)│ ภายนอก · ทางเลือก (ไม่ผูกพัน)│
                            │                            │        │ ใช้เฉพาะเมื่อ backend = roboflow│
                            │ server.py — 2,199 บรรทัด    │        │ มีปุ่มยืนยันก่อนเรียกทุกครั้ง │
                            └──────────────────────────┘        └──────────────────────────┘

Frontend และ Server อยู่ในโปรเซสเดียวกัน — ไม่มีการเรียกข้ามเครือข่ายระหว่างกัน
```
(หมายเหตุ: มีบรรทัดตัวหนังสือขนาดเล็กมากใต้แผนภาพที่อ่านไม่ชัดในภาพต้นฉบับ ดูเหมือนเป็นเชิงอรรถเสริม ไม่กระทบเนื้อหาหลัก)

### ประเด็นสำคัญ (bullet points)

- **Frontend ไม่ใช่บริการแยก** — `index.html` · `app.js` · `style.css` เป็นไฟล์ static ธรรมดา
  - ไม่มี framework ไม่มีขั้นตอน build เสิร์ฟผ่าน `app.mount("/", StaticFiles(...))`
- **Server คือบริการจริงหนึ่งเดียว** — FastAPI + Uvicorn โปรเซสเดียว รับทั้ง 38 endpoint
  - ของ API และไฟล์ static พร้อมกัน
- **ไม่มี Database service** — ใช้ `webapp/state.json` ไฟล์แบนราบไฟล์เดียว เขียนแบบ atomic
  - (tmp แล้วค่อย rename) **เป็นการตัดสินใจเชิงออกแบบ ไม่ใช่ข้อจำกัด**
- **Roboflow Cloud API** เป็นบริการภายนอก เสริมทางเลือก ไม่นับเป็นหนึ่งใน 3 บริการหลักนี้

---

## หน้า 7 (สไลด์ 20) — Infrastructure (Frontend / Server / Database Service)

### แผนภาพ UML Deployment Diagram

```
«device» เครื่องคอมพิวเตอร์ของผู้ใช้ — ใช้ CPU เท่านั้น (ไม่ต้องใช้ GPU)
┌──────────────────────────────────────────────────────┐        ┌──────────────────────────┐
│ «executionEnvironment»        «executionEnvironment»    │        │ «device»                  │
│ เว็บเบราว์เซอร์                Python 3.11 + Uvicorn      │        │ Roboflow Cloud            │
│ ┌────────────────────┐   ┌─────────────────────────┐│        │ บริการภายนอก              │
│ │ «artifact»          │   │ server.py (FastAPI)       ││        │ (ทางเลือก ไม่ผูกพัน)         │
│ │ index.html·style.css│   │ frame_extractor·detector· ││ «HTTPS>└──────────────────────────┘
│ │ ·app.js              │   │ exporter                  ││───────>│
│ └────────────────────┘   │ state.json·state.json.bak ││ใช้เฉพาะเมื่อ
│              │«HTTP» localhost:8000│ data/·models/     ││ backend=roboflow
│              └───────────────────>│                     ││
└──────────────────────────────────────────────────────┘
```

### ประเด็นสำคัญ (bullet points)

- **Frontend Service** — ไม่ใช่บริการแยก เสิร์ฟเป็นไฟล์ static จากโปรเซสเดียวกับ Server (ดู System Framework)
- **Server Service** — ปัจจุบันรัน local เครื่องเดียว ยังไม่ได้ deploy ขึ้นจริง
  - มี runbook + config พร้อมใช้แล้ว (เพิ่มเข้ามาที่ commit `8e704c8`): VPS DigitalOcean/Vultr (สิงคโปร์) · Ubuntu 24.04 · ไม่ใช้ GPU
  - รันเป็น systemd service ตัวเดียว (**single worker เท่านั้น** — state เป็น in-process dict ถ้ามีหลาย worker จะเขียนทับกัน) หลังบ้านมี **Caddy** เป็น reverse proxy ออก HTTPS ให้อัตโนมัติ
  - เสริม (ชั่วคราว ไม่ใช่แผน deploy จริง): เคยใช้ **Cloudflare Tunnel** (cloudflared) สร้างลิงก์ชั่วคราวเข้าเครื่อง local ให้ดูได้ทันทีโดยไม่ต้องรอ VPS
- **Database Service** — ไม่มี และไม่มีแผนจะมี
  - ใช้ `state.json` ไฟล์แบนราบแทน เป็นการตัดสินใจเชิงออกแบบ — instance สาธารณะจะเริ่มด้วย `data/` ว่างเปล่า ไม่เอาชุดข้อมูลจริงของโครงงานขึ้นไป
- **อื่นๆ ที่เว็บใช้แทนระบบ login ที่ตัดออกแล้ว**: `ULTRALYTICS_SAFE_LOAD` (กันโหลด .pt อันตราย) · rate limit ต่อ IP · disk-space floor · request body cap

---

## หน้า 8 (สไลด์ 20) — Analytics — AI-Assist Accept Rate

หน้าจอเว็บแอป (แถบเมนู: ...tate | Export | **Analytics**):

- **AI-Assist Accept Rate** (ค่าจากภาพหน้าจอจริง)
  - Accept rate: `33.3%`
  - Boxes suggested: `57`
  - Boxes accepted: `19`
  - Assist calls counted: `3`
  - Model-sourced boxes (all routes): `28213`
  - คำอธิบายในภาพ: The rate counts boxes accepted from Label Assist against the suggestions those same calls made. Boxes written by a bulk Detect run were never offered as suggestions, so they are reported separately on the right rather than folded into the rate. 55 earlier assist calls are excluded: they predate accept tracking, and the boxes accepted from them cannot be told apart from Detect output.
- **Dataset Status**: Frames: 4761 | With detections: 3723 | Reviewed: 15
- **Detections by Class** (บางส่วนแสดงในภาพหน้าจอ — ดูตารางเต็มในหน้า 9)

### ประเด็นสำคัญ (bullet points)

- **Accept rate ปัจจุบัน: 33.3%** — 19 จาก 57 กล่องที่ Label Assist เคยเสนอถูกยืนยันใช้จริง
- **Assist calls ที่นับได้: 3 ครั้ง** (มีอีก 55 ครั้งเก่ากว่าระบบติดตามผล แยกไม่ออกจากผล Detect ปกติ จึงไม่นับ)
- **กล่องจากโมเดลทั้งหมดทุกช่องทาง: 28,213 กล่อง** — รายงานแยกต่างหาก ไม่หารรวมเป็น rate
- **เคยมีบั๊ก**: ตัวเลขเดิมอ่านได้ 4834.6% เพราะตัวหารกับตัวตั้งนับคนละอย่างกัน (ตัวหารนับเฉพาะที่เสนอผ่าน `/assist` แต่ตัวตั้งนับกล่องจากโมเดลทุกช่องทางรวม bulk detect) — **แก้แล้วตั้งแต่ 13 ส.ค. 2569**
- **Dataset Status ปัจจุบัน**: 4,761 เฟรม · มีกรอบ 3,723 เฟรม · ตรวจทานแล้ว 15 เฟรม

---

## หน้า 9 (สไลด์ 20) — Analytics — Detections by Class

**ตาราง (ข้อมูลจริงจากเว็บแอป ณ 17 ส.ค. 2569)**

| คลาส | จำนวนกรอบ |
|---|---|
| finger | 17,315 |
| wound | 3,678 |
| needle_holder | 2,651 |
| needle | 2,237 |
| hand | 804 |
| forcep | 785 |
| Tip_needle_holder | 589 |
| Stitch Scissors | 96 |
| Tip_forcep | 85 |

หมายเหตุ: **รวม 28,240 กรอบ จาก 4,761 เฟรม** (ณ 17 ส.ค. 2569) — ตัวเลขนี้เปลี่ยนได้เมื่อมีการกำกับข้อมูลเพิ่ม นี่คือชุดข้อมูลกำกับสดในเว็บแอป **คนละตัวกับชุด re-annotated 2,489 ภาพ / 24,421 กรอบ** ที่ใช้เทรนโมเดลในส่วนผลการทดลอง

---

## หน้า 10 — Section Header
**Results Summary**

---

## หน้า 11 (สไลด์ 21) — สถิติของชุดข้อมูล (Dataset Statistics)

**ตารางที่ 1 — จำนวนต่อคลาส (ชุดฝึก / ตรวจสอบ / ทดสอบ / รวม)**

| คลาส | ชุดฝึก | ตรวจสอบ | ทดสอบ | รวม |
|---|---|---|---|---|
| finger | 7,157 | 1,775 | 952 | 9,884 |
| needle_holder | 1,947 | 525 | 257 | 2,729 |
| wound | 1,742 | 467 | 254 | 2,463 |
| needle | 1,387 | 366 | 191 | 1,944 |
| hand | 1,339 | 364 | 181 | 1,884 |
| forcep | 1,238 | 340 | 176 | 1,754 |
| Tip_needle_holder | 1,031 | 291 | 145 | 1,467 |
| Tip_forcep | 564 | 158 | 81 | 803 |
| Stitch Scissors | 16 | 10 | 3 | 29 |

**ตารางที่ 2 — จำนวนภาพและกรอบต่อ Split**

| ชุดข้อมูล (Split) | จำนวนภาพ | จำนวนกรอบวัตถุ (boxes) |
|---|---|---|
| Train | 1,575 | 16,421 |
| Valid | 400 | 4,296 |
| Test | 215 | 2,240 |
| **รวม** | **2,190** | **22,957** |

หมายเหตุในสไลด์: Stitch Scissors มีแค่ 16 กรอบในชุดฝึก น้อยเกินกว่าจะสรุปอะไรได้ และคะแนนของมันแกว่งมากข้ามรอบการทดลอง (จะกลับมาพูดอีกครั้งที่สไลด์ผลการทดลอง)

---

## หน้า 12 (สไลด์ 22) — ตัวชี้วัดที่ใช้ในส่วนนี้ — mAP50 vs mAP50-95 ต่างกันยังไง

**ตาราง**

| ตัวชี้วัด | ถามว่าอะไร | ตัวอย่างจากงานนี้ |
|---|---|---|
| IoU | กรอบที่ทำนายซ้อนทับกรอบจริงกี่เปอร์เซ็นต์ | IoU 0.5 = ซ้อนทับครึ่งหนึ่ง = "ถูกแบบคร่าวๆ" |
| precision | ในสิ่งที่โมเดลบอกว่าเจอ ถูกกี่ % | 0.73 = บอกว่าเจอ 100 อัน ถูกจริง 73 |
| recall | ในของที่มีอยู่จริง โมเดลเจอกี่ % | needle 0.36 = มีเข็ม 100 อัน เจอ 36 |
| mAP50 | ค่าเฉลี่ยความแม่น ณ เกณฑ์ IoU 0.50 | ตัวอย่าง: 0.7160 (รอบ aug960) — เลขหัวข่าวที่คนมักอ้างถึง |
| mAP50-95 | เฉลี่ยตั้งแต่ IoU 0.50 ถึง 0.95 ทีละ 0.05 (เข้มกว่ามาก) → วัดคุณภาพการวางตำแหน่งกรอบ ไม่ใช่แค่เจอหรือไม่เจอ | 0.4532 — ต่ำกว่า mAP50 เสมอ เพราะเกณฑ์เข้มกว่า |

หมายเหตุ: **สรุปสั้นๆ**: mAP50 บอกว่า "เจอไหม" · mAP50-95 บอกว่า "กรอบตรงตำแหน่งแค่ไหน" — สองค่านี้ไม่ได้ขยับไปด้วยกันเสมอ (เช่น ตารางถัดๆ ไปที่ mAP50 ขึ้นแต่ mAP50-95 ลง)

---

## หน้า 13 (สไลด์ 22) — ตัวอย่างจริง: ขยายเกณฑ์ถึง IoU 0.95 แล้วเห็นอะไรที่ IoU 0.50 มองไม่เห็น

ทดลองเพิ่มความละเอียดภาพจาก 640px → 960px (แถวล่างสุด 2 แถว, คุมรอบ/ชุดข้อมูลเท่ากัน)

| รอบการทดลอง | mAP50 | mAP50-95 | precision | recall | เวลา (นาที) |
|---|---|---|---|---|---|
| noaug · 640px | 0.5746 | 0.3245 | 0.6985 | 0.5417 | 43.5 |
| aug · 640px | 0.6559 | 0.4007 | 0.6872 | 0.6641 | 49.7 |
| aug150 · 640px | 0.7163 | 0.4366 | 0.7702 | 0.7090 | 162.6 |
| **aug960 · 960px** | 0.7160 | 0.4532 | 0.7335 | 0.7173 | 97.9 |

ประเด็นสำคัญ:
- เทียบที่ IoU 0.50 (คอลัมน์ mAP50): 0.7163 vs 0.7160 — แทบไม่ต่างกันเลย ถ้าดูแค่ค่านี้ค่าเดียวจะสรุปว่า "เพิ่มความละเอียดไม่ช่วยอะไร"
- แต่พอขยายเกณฑ์ไปถึง IoU 0.95 (คอลัมน์ mAP50-95): 0.4366 → 0.4532 ขึ้นชัดเจน แปลว่ากรอบวางตำแหน่งแม่นขึ้นจริง แถมความละเอียด 960px ยังทำให้ recall ของคลาส needle (วัตถุเล็กที่สุดในชุดข้อมูล) ขึ้นจาก 0.2435 เป็น 0.3579 ด้วย
- สรุป: การเทียบผลข้าม IoU ตั้งแต่หลวม (0.50) ถึงเข้ม (0.95) เป็นวิธีแยกว่าโมเดลดีขึ้นเพราะ "เจอวัตถุมากขึ้น" หรือ "วางตำแหน่งกรอบแม่นขึ้น" — สองอย่างนี้ mAP50 อย่างเดียวแยกไม่ออก

---

## หน้า 14 (สไลด์ 22) — บันทึกเสริม/หมายเหตุการแก้ไขสไลด์ (Meta note)

> **หมายเหตุ**: หน้านี้ดูเหมือนเป็นข้อความบันทึกการทำงาน/แชทที่หลงเหลืออยู่ในเดคสไลด์ (ไม่ใช่เนื้อหานำเสนอโดยตรง) แต่ขอแยกไว้ครบตามที่ขอ:

ใส่ในสไลด์แล้วครับ — เพิ่มสไลด์ใหม่ "ตัวชี้วัดที่ใช้ในส่วนนี้ — mAP50 vs mAP50-95 ต่างกันยังไง" ไว้ตอนต้นสุดของ Results Summary (ก่อนตาราง Dataset Statistics) ตอนนี้เดคมี 25 สไลด์ ตรวจขอบสไลด์ผ่าน

สรุปคำตอบ:
- IoU (Intersection over Union) = กรอบที่โมเดลทำนายซ้อนทับกรอบจริงกี่ % — เป็นเกณฑ์ตั้งต้นของทั้งสองตัว
- mAP50 = ค่าเฉลี่ยความแม่น ที่เกณฑ์ IoU = 0.50 เกณฑ์เดียว (ผ่อนปรน) — ถามแค่ว่า "เจอวัตถุไหม" ซ้อนทับกันแค่ครึ่งหนึ่งก็นับว่าถูกแล้ว เป็นเลขหัวข่าวที่มักอ้างถึง
- mAP50-95 = ค่าเฉลี่ยของ mAP ที่คำนวณซ้ำๆ ตั้งแต่ IoU 0.50 ไปจนถึง 0.95 ทีละ 0.05 (รวม 10 เกณฑ์) แล้วเฉลี่ยรวม — ถามว่า "กรอบตรงตำแหน่งแค่ไหน" เพราะรวมเกณฑ์ที่เข้มมาก (เช่น IoU≥0.95 = ซ้อนทับเกือบสนิท) จึงเข้มกว่า mAP50 มาก และต่ำกว่า mAP50 เสมอ

ทำไมสำคัญ: สองค่านี้ไม่จำเป็นต้องขยับไปด้วยกัน — อย่างในตาราง Roboflow-vs-reannot ที่เพิ่งทำ mAP50 ขึ้น (+0.9%) แต่ mAP50-95 กลับลง (−1.9%) แปลว่าโมเดลรุ่นใหม่ "เจอ" ได้ดีขึ้นนิดหน่อย แต่ "ความแม่นของตำแหน่งกรอบ" ไม่ได้ดีขึ้นตาม — เป็นนิยามตาม COCO evaluation protocol เดียวกับที่เดคหลักใช้

---

## หน้า 15 (สไลด์ 22) — Model Result — Validation split / Benchmark comparison

โมเดลหลักที่นำเสนอคือ **baseline9-reannot** (ชุดข้อมูล re-annotated)

| run | mAP50 | mAP50_95 | precision | recall |
|---|---|---|---|---|
| aug960 | 0.7160 | 0.4532 | 0.7335 | 0.7173 |
| baseline9-reannot | 0.7225 | 0.4444 | 0.7359 | 0.7290 |

หมายเหตุ: ชุด re-annotated แบ่ง validation split ใหม่ จึงเทียบกับ aug960 ทางสถิติตรงๆ ไม่ได้ — เหตุผลที่ดีขึ้นเป็นเชิงผลิตภัณฑ์ (ดูหน้าถัดไป)

---

## หน้า 16 (สไลด์ 23) — Model Result — per-class metrics (test) — aug960

| id | class | images | instances | precision | recall | f1 | mAP50 | mAP50_95 |
|---|---|---|---|---|---|---|---|---|
| 0 | Stitch Scissors | 3 | 3 | 0.8106 | 0.6667 | 0.7316 | 0.6650 | 0.3990 |
| 1 | Tip_forcep | 77 | 81 | 0.7669 | 0.7531 | 0.7599 | 0.7374 | 0.3500 |
| 2 | Tip_needle_holder | 139 | 145 | 0.7819 | 0.7911 | 0.7865 | 0.8434 | 0.3952 |
| 3 | finger | 177 | 952 | 0.7209 | 0.8246 | 0.7693 | 0.8137 | 0.4604 |
| 4 | forcep | 123 | 176 | 0.8259 | 0.6989 | 0.7571 | 0.7312 | 0.5968 |
| 5 | hand | 59 | 181 | 0.6176 | 0.9012 | 0.7329 | 0.6444 | 0.5984 |
| 6 | needle | 131 | 191 | 0.6211 | 0.3351 | 0.4353 | 0.3556 | 0.1586 |
| 7 | needle_holder | 170 | 257 | 0.7630 | 0.7549 | 0.7589 | 0.7550 | 0.5869 |
| 8 | wound | 195 | 254 | 0.6900 | 0.5079 | 0.5851 | 0.6578 | 0.3678 |

หมายเหตุ: needle (แถวเน้น) ยังเป็นคลาสที่อ่อนที่สุด mAP50 0.3556 — ปัญหาขนาดวัตถุ ไม่ใช่ปัญหาการจำแนก

---

## หน้า 17 (สไลด์ 23) — Model Result — per-class metrics (test) — baseline9-reannot

| id | class | images | instances | precision | recall | f1 | mAP50 | mAP50_95 |
|---|---|---|---|---|---|---|---|---|
| 0 | Stitch Scissors | 3 | 3 | 0.8663 | 1.0000 | 0.9284 | 0.9950 | 0.5980 |
| 1 | Tip_forcep | 82 | 85 | 0.7439 | 0.7294 | 0.7366 | 0.6852 | 0.2949 |
| 2 | Tip_needle_holder | 153 | 157 | 0.8113 | 0.8766 | 0.8427 | 0.8422 | 0.4030 |
| 3 | finger | 189 | 915 | 0.6855 | 0.8206 | 0.7471 | 0.7565 | 0.4285 |
| 4 | forcep | 115 | 153 | 0.7792 | 0.7647 | 0.7719 | 0.7914 | 0.5907 |
| 5 | hand | 45 | 137 | 0.5116 | 0.8467 | 0.6378 | 0.5309 | 0.4824 |
| 6 | needle | 128 | 165 | 0.5437 | 0.4000 | 0.4609 | 0.3338 | 0.1375 |
| 7 | needle_holder | 187 | 258 | 0.7275 | 0.8070 | 0.7652 | 0.8059 | 0.5936 |
| 8 | wound | 232 | 273 | 0.7728 | 0.6356 | 0.6975 | 0.7401 | 0.3884 |

หมายเหตุ: needle ยังเป็นคลาสที่อ่อนที่สุดในรุ่นนี้เช่นกัน mAP50 0.3338 — สอดคล้องกับ aug960 ยืนยันว่าเป็นปัญหาขนาดวัตถุจริง ไม่ใช่ความบังเอิญของรอบทดลองใดรอบหนึ่ง

---

## หน้า 18 (สไลด์ 23) — การทดลอง balance กรอบคลาส finger ด้วยการสุ่ม

คำถาม: ชุดข้อมูลไม่สมดุลมาก (finger เยอะกว่า Stitch Scissors ~340 เท่า) ควรสุ่มลดคลาสที่มีเยอะไหม?

| แบบ | ชุดข้อมูลต่างยังไง | mAP50 | mAP50-95 | Δ mAP50 vs baseline (จุด) |
|---|---|---|---|---|
| baseline9-reannot | 9 คลาสครบ (ไม่ทำอะไรเพิ่ม) | 0.7169 | 0.4312 | — (อ้างอิง) |
| drop-stitch | ตัด Stitch Scissors ออก เหลือ 8 คลาส | 0.7062 | 0.4272 | −1.1 |
| class5 | เหลือ 5 คลาสแบบระยะที่ 1 | 0.6807 | 0.4310 | −3.6 |
| balanced-finger | สุ่มลดภาพที่มี finger ให้สัดส่วนสมดุลขึ้น | 0.5343 | 0.3006 | −18.3 |

ประเด็นสำคัญ:
- ทดลอง 4 แบบบนชุด re-annotated ที่ 50 รอบ คุมให้ต่างกันแค่ชุดข้อมูล — วัดบนชุดตรวจสอบเดียวกันทั้ง 4 แบบ เทียบกันเองได้สะอาด
- "18.3 จุด" คือ percentage point ของ mAP50 เทียบกับ baseline9-reannot (0.7169 − 0.5343 = 0.1826 ≈ 18.3 จุด บนสเกล mAP50 0-100%) — คอลัมน์ขวาสุดคือค่านี้
- ข้อสรุป: การสุ่มลด finger ทำให้แย่ที่สุดในบรรดา 4 แบบ เพราะภาพที่มี finger เยอะมักมีคลาสอื่นติดอยู่ในภาพเดียวกันด้วย พอสุ่มตัดภาพออกเลยตัดตัวอย่างของคลาสอื่นทิ้งไปพร้อมกัน — สรุปคือ "ไม่ทำอะไรเลย" (ใช้ 9 คลาสครบ) ยังดีที่สุด

---

## หน้า 19 (สไลด์ 23) — ข้อมูล re-annotated ดีกว่าข้อมูลเดิมจาก Roboflow แค่ไหน

aug960 เทรนจากข้อมูลรอบแรกที่ export จาก Roboflow ตรงๆ · baseline9-reannot เทรนจากข้อมูลที่กลับไปกำกับเพิ่มในเว็บแอปของทีมเอง

| ตัวชี้วัด | ข้อมูลเดิม (Roboflow) aug960 | ข้อมูล re-annotated baseline9-reannot | ผลต่าง |
|---|---|---|---|
| mAP50 | 0.7160 | 0.7225 | +0.0065 (+0.9%) |
| mAP50-95 | 0.4532 | 0.4444 | −0.0088 (−1.9%) |
| precision | 0.7335 | 0.7359 | +0.0024 (+0.3%) |
| recall | 0.7173 | 0.7290 | +0.0117 (+1.6%) |

ประเด็นสำคัญ:
- ผลต่างเล็กน้อยและไม่ได้ดีขึ้นทุกด้าน — mAP50/precision/recall ขึ้นเล็กน้อย แต่ mAP50-95 (เกณฑ์ IoU เข้มกว่า) ลดลงเล็กน้อย แสดงตัวเลขตามจริงเพื่อความโปร่งใส ไม่ใช่การอ้างว่าดีขึ้นทุกตัวชี้วัด
- สิ่งที่เปลี่ยนในข้อมูล: 2,190→2,489 ภาพ (+299) · 22,957→24,421 กรอบ (+1,464) · เพิ่ม 2 คลาสใหม่ (Tip_needle_holder, Tip_forcep) · re-split แบบ stratified ใหม่ 72/18/10 (ดูเหตุผลเต็มในหน้าถัดไป)

---

## หน้า 20 (สไลด์ 24) — เหตุผลที่ baseline9-reannot ดีกว่า aug960 ใน Validation split

จากตารางจะเห็นได้ว่า baseline9-reannot ดีกว่า aug960 ใน Validation split เพราะ:

- **ข้อมูลที่เพิ่มขึ้นและมีคุณภาพ**: baseline9-reannot ใช้ชุดข้อมูลที่มีการ re-annotate ซึ่งมีจำนวนรูปภาพและจำนวน instance ของแต่ละคลาสเพิ่มขึ้น ทำให้โมเดลมีข้อมูลที่หลากหลายและเพียงพอต่อการเรียนรู้มากขึ้น
- **การแบ่งชุดข้อมูลที่เหมาะสม (Re-split)**: มีการ re-split ชุดข้อมูลใหม่เป็นอัตราส่วน 72/18/10 สำหรับ train/valid/test และมีการทำ stratified splitting โดยพิจารณาถึงคลาส 'Stitch Scissors' เพื่อให้แน่ใจว่าทุกคลาสมีการกระจายตัวอย่างเหมาะสมในทุกชุดข้อมูล ซึ่งช่วยให้การประเมินผลบน Validation split มีความน่าเชื่อถือมากขึ้นและลดปัญหาการ overfit หรือ underfit ได้ดีกว่าชุดข้อมูลเริ่มต้นของ Roboflow ที่มี Validation และ Test set น้อยเกินไป

---

## หน้า 21 (สไลด์ 25) — สรุปผลและข้อเสนอแนะ

ระบบสามารถตรวจจับและจำแนกอุปกรณ์เย็บแผลด้วย YOLOv11 ได้ตามเกณฑ์ที่กำหนด และเว็บแอปพลิเคชันสามารถสนับสนุนกระบวนการเตรียมชุดข้อมูลได้จริง โดยการเพิ่มขยายข้อมูลมีความสำคัญอย่างยิ่งต่อประสิทธิภาพของแบบจำลองบนชุดข้อมูลขนาดเล็ก

ข้อเสนอแนะ:
1. เก็บข้อมูลเพิ่มเติมสำหรับคลาสที่มีตัวอย่างน้อย เช่น needle และ Stitch Scissors
2. ปรับแต่ง Augmentation เฉพาะสำหรับวัตถุขนาดเล็ก เช่น Copy-paste Augmentation
3. เพิ่มจำนวน epoch ในการฝึกฝนรอบ aug เนื่องจากยังไม่พบสัญญาณ Overfitting
4. พัฒนาแบบจำลอง RNN/LSTM/GRU เพื่อวิเคราะห์ลำดับขั้นตอนการเย็บแผลเชิงเวลา

---

## หน้า 22 — References

[1] กรมการแพทย์ กระทรวงสาธารณสุข. (2565). คู่มือแนวทางการฝึกทักษะหัตถการทางการแพทย์พื้นฐานสำหรับแพทย์ฝึกหัด. โรงพิมพ์ชุมนุมสหกรณ์การเกษตรแห่งประเทศไทย.

[2] เรืองศักดิ์ ทรงพรหม. (2567). การประยุกต์ใช้คอมพิวเตอร์วิทัศน์ในงานสาธารณสุขยุคดิจิทัล. วารสารเทคโนโลยีและนวัตกรรมทางการแพทย์, 10(2), 145–158.

[3] Bradski, G. (2000). The OpenCV library. Dr. Dobb's Journal of Software Tools, 25(11), 120–125.

[4] Hochreiter, S., & Schmidhuber, J. (1997). Long short-term memory. Neural Computation, 9(8), 1735–1780.

[5] Kotthapalli, M., Ravipati, D., & Bhatia, R. (2025). YOLOv1 to YOLOv11: A comprehensive survey of real-time object detection innovations and challenges. arXiv.

[6] Paszke, A., Gross, S., Massa, F., Lerer, A., Chintala, S., et al. (2019). PyTorch: An imperative style, high-performance deep learning library. Advances in Neural Information Processing Systems, 32, 8024–8035.

[7] Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You only look once: Unified, real-time object detection. In Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR) (pp. 779–788).

[8] Smith, J., Johnson, M., & Williams, K. (2021). Automated surgical instrument detection in operating rooms using two-stage object detectors. International Journal of Computer Assisted Radiology and Surgery, 16(4), 512–524.

[9] Ultralytics LLC. (2023). YOLOv8 docs: Real-time object detection and predictive analytics framework. Retrieved June 8, 2026.

[10] Wang, A., Lee, C., & Kim, H. (2023). Temporal sequence analysis for laparoscopic surgery skill assessment using LSTM networks. IEEE Transactions on Medical Robotics and Bionics, 5(1), 89–101.

[11] A glove-wearing detection algorithm based on improved YOLOv8. (n.d.). PubMed Central (PMC).

[12] Optimization of a web-based, real-time, file-based human detection system using YOLOv8 and the Flask framework. (2025). Global Journal of Engineering and Technology Advances, 24(1), 144–150.

[13] Real-time object detection and counting for inventory management using fine-tuned YOLOv11. (n.d.). Multimedia Tools and Applications.

[14] Real-time tool detection in smart manufacturing using You-Only-Look-Once (YOLO)v5. (n.d.). Manufacturing Letters.

[15] YOLOv8: An improved real-time detection of safety equipment in different lighting scenarios on construction sites. (n.d.). ResearchGate.

[16] YOLOv8-MCDE for lightweight detection of small instruments in complex backgrounds from inspection robots' perspective. (n.d.). Scientific Reports.

(หมายเหตุ: ในเอกสารต้นฉบับ ใต้รายการ [5] และ [9] มีข้อความ "ภาพตัวอย่าง การตีกรอบสี่เหลี่ยม (Bounding Box) สีต่างๆ ไว้รอบเครื่องมือผ่าตัดและตำแหน่งแผล" ปรากฏแทรกอยู่ — ดูเหมือนเป็นแคปชันภาพที่หลงเหลือ/ผิดตำแหน่งจากการจัดวางในต้นฉบับ)

---

## หน้า 23 — Section Header
**Q & A**

---

## หน้า 24 — Closing
**Thank You**

---

## สรุปการเปลี่ยนแปลงหลักเทียบกับไฟล์เวอร์ชันก่อนหน้า (66120361.pdf, 15 หน้า)

ไฟล์นี้ (66120361_real.pdf, 24 หน้า) เป็นฉบับที่ขยายความเพิ่มจากฉบับก่อนหน้าอย่างมาก โดยมีส่วนที่เพิ่มเข้ามาใหม่คือ:

1. **System Framework** (หน้า 6) และ **Infrastructure** (หน้า 7) — อธิบายสถาปัตยกรรมเว็บแอปแบบละเอียด (Frontend/Server/Database เป็น process เดียว ไม่มี DB จริง ใช้ state.json, แผน deploy บน VPS)
2. **Analytics — AI-Assist Accept Rate** (หน้า 8) และ **Detections by Class** (หน้า 9) — ข้อมูลสดจากเว็บแอปจริง พร้อมคำอธิบายบั๊กที่เคยพบและแก้ไขแล้ว (Accept rate จากที่เคยผิดพลาดอ่านได้ 4834.6% แก้เป็น 33.3%)
3. **ตัวชี้วัดที่ใช้ในส่วนนี้ — mAP50 vs mAP50-95** (หน้า 12-14) — อธิบายความหมายของตัวชี้วัดอย่างละเอียด พร้อมตัวอย่างจริงจากการทดลอง
4. **การทดลอง balance กรอบคลาส finger** (หน้า 18) — ตารางทดลอง 4 แบบเปรียบเทียบผลกระทบของการ balance ข้อมูล
5. **ข้อมูล re-annotated เทียบกับ Roboflow เดิม** (หน้า 19) — ตารางเปรียบเทียบตัวชี้วัดอย่างละเอียด

ส่วนที่เหมือนเดิม (จากไฟล์เก่า): หน้า Web Application Demonstration (1-5), Dataset Statistics (11), Model Result validation split (15), per-class metrics ทั้งสองรุ่น (16-17), เหตุผลที่ baseline9-reannot ดีกว่า (20), สรุปผลและข้อเสนอแนะ (21), References (22), Q&A (23), Thank You (24)
