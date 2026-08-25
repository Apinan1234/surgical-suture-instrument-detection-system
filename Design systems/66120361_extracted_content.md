# เนื้อหาที่แยกจากไฟล์ 66120361.pdf (15 หน้า)

โปรเจกต์: ระบบตรวจจับและจำแนกอุปกรณ์เย็บแผลด้วย YOLOv11 พร้อมเว็บแอปพลิเคชันสนับสนุนการเตรียมชุดข้อมูล
(หมายเหตุ: เลขหน้าที่ปรากฏในสไลด์ 18-25 คือเลขหน้าเอกสารต้นฉบับ/นำเสนอ ซึ่งอาจไม่ตรงกับลำดับหน้า PDF)

---

## หน้า 1 — Section Header
**WEB APPLICATION DEMONSTRATION**

---

## หน้า 2 (สไลด์ 18) — "2. สกัดเฟรม" (Extract Frames)

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

## หน้า 3 (สไลด์ 19) — "3. ตรวจจับ" (Detect)

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

## หน้า 4 (สไลด์ 19) — "3. หน้ากำกับข้อมูล" (Annotate)

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

## หน้า 5 (สไลด์ 20) — "5. ส่งออก" (Export)

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

## หน้า 6 (สไลด์ 20) — "6. Analytics"

หน้าจอเว็บแอป:

- **AI-Assist Accept Rate**
  - Accept rate: `4834.6%`
  - Boxes suggested: `437`
  - Boxes accepted: `21127`
  - Assist calls: `55`
  - คำอธิบาย: ติดตามคำแนะนำของ Label Assist เทียบกับสิ่งที่บันทึกเป็น model-sourced ในปัจจุบัน นับตั้งแต่ feature นี้เริ่มใช้งาน — annotation ที่ทำก่อนหน้านั้นไม่ถูกนับ
- **Dataset Status**
  - Frames: 2726 | With detections: 2726 | Reviewed: 1
- **Detections by Class**

| Class | Count |
|---|---|
| finger | 13,697 |
| forcep | 577 |
| needle | 2,198 |
| needle_holder | 1,978 |
| wound | 2,677 |

---

## หน้า 7 — Section Header
**สรุปผลการดำเนินงาน** (Results Summary)

---

## หน้า 8 (สไลด์ 21) — สถิติของชุดข้อมูล (Dataset Statistics)

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

**ตารางที่ 2 — จำนวนภาพและจำนวนกรอบวัตถุ (boxes) ต่อชุดข้อมูล**

| ชุดข้อมูล (Split) | จำนวนภาพ | จำนวนกรอบวัตถุ (boxes) |
|---|---|---|
| Train | 1,575 | 16,421 |
| Valid | 400 | 4,296 |
| Test | 215 | 2,240 |
| **รวม** | **2,190** | **22,957** |

หมายเหตุในสไลด์: Stitch Scissors มีแค่ 16 กรอบในชุดฝึก น้อยเกินกว่าจะสรุปอะไรได้ และคะแนนของมันแกว่งมากข้ามรอบการทดลอง (จะกลับมาพูดอีกครั้งที่สไลด์ผลการทดลอง)

---

## หน้า 9 (สไลด์ 22) — MODEL RESULT (Validation split / Benchmark comparison)

หัวข้อย่อย: Validation split, Benchmark comparison (test split)

**ตาราง (screenshot terminal-style)**

| run | mAP50 | mAP50_95 | precision | recall |
|---|---|---|---|---|
| aug960 | 0.7160 | 0.4532 | 0.7335 | 0.7173 |
| baseline9-reannot | 0.7225 | 0.4444 | 0.7359 | 0.7290 |

---

## หน้า 10 (สไลด์ 23) — MODEL RESULT (ผลการประเมินโดยรวมบนชุดข้อมูล validation)

**Per-class detection metrics (test) — aug960**

| class_id | class | images | instances | precision | recall | f1 | mAP50 | mAP50_95 |
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

**Per-class detection metrics (test) — baseline9-reannot**

| class_id | class | images | instances | precision | recall | f1 | mAP50 | mAP50_95 |
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

---

## หน้า 11 (สไลด์ 24) — เหตุผลที่ baseline9-reannot ดีกว่า aug960

จากตารางจะเห็นได้ว่า baseline9-reannot ดีกว่า aug960 ใน Validation split เพราะ:

- **ข้อมูลที่เพิ่มขึ้นและมีคุณภาพ**: baseline9-reannot ใช้ชุดข้อมูลที่มีการ re-annotate ซึ่งมีจำนวนรูปภาพและจำนวน instance ของแต่ละคลาสเพิ่มขึ้น ทำให้โมเดลมีข้อมูลที่หลากหลายและเพียงพอต่อการเรียนรู้มากขึ้น
- **การแบ่งชุดข้อมูลที่เหมาะสม (Re-split)**: มีการ re-split ชุดข้อมูลใหม่เป็นอัตราส่วน 72/18/10 สำหรับ train/valid/test และมีการทำ stratified splitting โดยพิจารณาถึงคลาส 'Stitch Scissors' เพื่อให้แน่ใจว่าทุกคลาสมีการกระจายตัวอย่างเหมาะสมในทุกชุดข้อมูล ซึ่งช่วยให้การประเมินผลบน Validation split มีความน่าเชื่อถือมากขึ้นและลดปัญหาการ overfit หรือ underfit ได้ดีกว่าชุดข้อมูลเริ่มต้นของ Roboflow ที่มี Validation และ Test set น้อยเกินไป

---

## หน้า 12 (สไลด์ 25) — สรุปผลและข้อเสนอแนะ

ระบบสามารถตรวจจับและจำแนกอุปกรณ์เย็บแผลด้วย YOLOv11 ได้ตามเกณฑ์ที่กำหนด และเว็บแอปพลิเคชันสามารถสนับสนุนกระบวนการเตรียมชุดข้อมูลได้จริง โดยการเพิ่มขยายข้อมูลมีความสำคัญอย่างยิ่งต่อประสิทธิภาพของแบบจำลองบนชุดข้อมูลขนาดเล็ก

ข้อเสนอแนะ:
1. เก็บข้อมูลเพิ่มเติมสำหรับคลาสที่มีตัวอย่างน้อย เช่น needle และ Stitch Scissors
2. ปรับแต่ง Augmentation เฉพาะสำหรับวัตถุขนาดเล็ก เช่น Copy-paste Augmentation
3. เพิ่มจำนวน epoch ในการฝึกฝนรอบ aug เนื่องจากยังไม่พบสัญญาณ Overfitting
4. พัฒนาแบบจำลอง RNN/LSTM/GRU เพื่อวิเคราะห์ลำดับขั้นตอนการเย็บแผลเชิงเวลา

---

## หน้า 13 — References

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

## หน้า 14 — Section Header
**Q & A**

---

## หน้า 15 — Closing
**Thank You**
