# VideoFrameExtractor Web — WORK_PLAN.md
# สร้าง: 17 กรกฎาคม 2026 | อ้างอิง: `app.py` (Tkinter desktop, 5 แท็บ), `frame_extractor.py`, `detector.py`, `dataset_exporter.py`
# สไตล์ตาม: `D:\OPEN DONATE\WORK_PLAN.md` (task-list ละเอียดสำหรับ Claude Code ทำทีละ task)

---

## 🔎 Verification Log

- **25 กรกฎาคม 2026**: ตรวจสอบแผนนี้ซ้ำกับ `app.py` เวอร์ชันปัจจุบัน — ยังตรงทั้งหมด ยกเว้น 4 จุดที่ปรับเพิ่ม (dependency ที่ขาด, รองรับชื่อโมเดล pretrained, bug ของ desktop app, เจตนาต่างจาก desktop ใน annotation persistence)
- **29 กรกฎาคม 2026 (รอบเช้า)**: เทียบกับคู่มือข้อสอบ 3 ไฟล์ของวิชา Back End/Front End Programming มหาวิทยาลัย + พบว่าแผนตอนนั้น stale เพราะ `app.py`/`detector.py` เพิ่ม Roboflow Cloud API backend เข้ามาเมื่อ 28 ก.ค. — แก้ไขแล้ว พร้อมเพิ่มหมายเหตุ security/deployment จากเนื้อหาคอร์ส
- **29 กรกฎาคม 2026 (รอบบ่าย) — เขียนใหม่ทั้งหมด**: ผู้ใช้ขอให้ตัดความซับซ้อนของสถาปัตยกรรมลงให้เหลือน้อยที่สุด
  ("โค้ด/tool ง่ายๆ น้อยๆ แต่เว็บทำงานได้ ใช้เท่าที่จำเป็น") — สลับจาก FastAPI+SQLAlchemy+Alembic+JWT+WebSocket+Docker+slowapi
  (~19 dependency, 26 ไฟล์) ไปเป็น FastAPI+Uvicorn ล้วนๆ + in-memory state + JSON snapshot ไฟล์เดียว + session token
  ธรรมดา + HTTP polling แทน WebSocket + ไม่ใช้ Docker ใน MVP (~11 dependency, ~7 ไฟล์) ยืนยันกับผู้ใช้แล้วว่า
  (1) ยอมรับ trade-off ข้อมูล job/annotation หายได้ถ้า server restart กลางงาน แลกกับไม่มี DB/ORM/migration เลย
      (ลด risk ด้วย JSON snapshot อย่างน้อยกันข้อมูลหายทั้งหมด) — เหมือน desktop app เดิมที่ก็ไม่ persist อยู่แล้ว
  (2) ยังเก็บเป้าหมาย deploy cloud ไว้ แต่ใช้เครื่องมือน้อยที่สุดในแต่ละขั้น (HTTPS/reverse proxy ผลักไปทำตอน deploy จริง)
  รายละเอียดเหตุผลการตัดแต่ละจุดอยู่ในหัวข้อ "หลักการออกแบบ: เหตุผลที่ตัดออก" ด้านล่าง
- **29 กรกฎาคม 2026 (รอบเย็น) — เพิ่มระบบ Appearance (theme)**: ผู้ใช้ขอ theme picker แบบ "Follow system
  settings / Dark mode / Light mode" (เหมือน theme picker ของแอปอย่าง Claude) และขอให้ปรับดีไซน์โดยได้แรงบันดาลใจ
  จาก skywork.ai (ดู UI ผ่าน browser จริง — ไม่ได้ล็อกอินด้วย credential ของผู้ใช้ตามที่เสนอมา แค่ดูหน้า dashboard
  ที่ browser profile เปิดค้างอยู่แล้ว ไม่แตะ Notes/Knowledge Base/Projects ที่เป็นข้อมูลส่วนตัว) สรุปสิ่งที่นำมาใช้:
  สี accent ของ skywork (แดง/ส้มอมชมพู) ใกล้เคียงกับ `--highlight:#e94560` ที่มีอยู่แล้วพอดี ไม่ต้องเปลี่ยน, ส่วน
  card/pill/chip ที่มุมโค้งนุ่มนวลนำมาปรับใช้ได้ แต่ sidebar nav ของ skywork **ไม่เอามาใช้** เพราะแอปนี้เป็น
  4-step wizard เชิงเส้น ใช้ top nav tab แบบเดิมสื่อความหมายได้ดีกว่า เพิ่ม Light mode palette ใหม่ (เดิมมีแต่ Dark)
  — รายละเอียดอยู่ในหัวข้อ "🎨 Appearance / Theme System" ที่เพิ่มใหม่ด้านล่าง และแก้ F-0/F-1/F-2
- **29 กรกฎาคม 2026 (ค่ำ) — เพิ่ม Label Assist**: ผู้ใช้ถามถึง annotate tool ของ Roboflow แล้วขอฟีเจอร์ที่ทำได้จริง
  เทียบเท่า "Label Assist" — โหลดโมเดลของตัวเอง (เช่น "Version 1" ที่เทรนจากเฟรมกลุ่มเล็กที่ label มือไปก่อน) มาช่วย
  pre-label เฟรมที่เหลือทีละเฟรมตรงในหน้า Annotate เพิ่ม **S-8 | Label Assist API** (endpoint synchronous ทีละ
  เฟรม ไม่ผ่าน job/polling เพราะ inference 1 เฟรมเร็วพอตอบใน request เดียว, cache detector instance กันโหลด
  โมเดลซ้ำ) และขยาย F-5 (Annotate section) ให้มีปุ่ม Label Assist — reuse `build_detector()` เดียวกับ S-4 ทั้งหมด
  ไม่มี logic detection ใหม่เลย
- **29 กรกฎาคม 2026 (ดึก) — ออกแบบ AI Annotation Platform เต็มรูปแบบ**: ผู้ใช้ส่ง brief แบบเปิดกว้างให้ทำหน้าที่
  Software Architect + AI Workflow Designer + UI/UX Designer ออกแบบระบบ annotate ใหม่ทั้งหมด (ไม่ต้อง clone
  Roboflow/CVAT/Label Studio/Supervisely แค่ศึกษาแนวคิดแล้วออกแบบให้เหมาะกับเว็บนี้) ให้สิทธิ์ปรับ requirement
  เดิมได้เต็มที่ อ่าน `app.py`/`detector.py`/`dataset_exporter.py`/`WORK_PLAN.md` เต็มไฟล์ แล้วบรีฟ Plan agent
  ให้เสนอ tool set/workflow/UI-UX/component structure โดยยึดกรอบ minimal-tool เดิมทั้งหมด (ไม่มี dependency
  ใหม่แม้แต่ตัวเดียว) ผลลัพธ์: เพิ่มหัวข้อใหม่ "✏️ Annotation Workflow & Tool Design (AI-Assisted)" เป็นแหล่งอ้างอิง
  หลัก, ขยาย S-4 (`skip_reviewed`), S-6 (`reviewed_only`), เพิ่ม **S-9 | Frame Thumbnail Endpoint** และ
  **F-7 | app.js — Annotation Canvas Engine** (ยังอยู่ใน `app.js` ไฟล์เดียวเดิม แค่แยก task เพื่อ track ง่ายขึ้น),
  ขยาย F-5 เป็น "ต่อยอดจาก F-7" จุดที่สำคัญที่สุดที่ agent จับได้คือ bug เชิง flow ที่ยังไม่เคยเห็น: รัน S-4 ซ้ำด้วย
  โมเดลใหม่จะเขียนทับเฟรมที่ reviewed ไปแล้วเงียบๆ ถ้าไม่มี `skip_reviewed` กัน
- **30 กรกฎาคม 2026 — ทบทวนช่องโหว่ที่เหลือ (feature/security/design)**: ถามผู้ใช้ 3 จุดที่ยังไม่เคยถามตรงๆ:
  (1) concurrency — ยืนยันว่าใช้คนเดียวทีละ session ตามที่ design ไว้อยู่แล้ว ไม่ต้องแก้อะไร
  (2) `state.json` เป็นบันทึกผลงานเดียวไม่มี DB/version history — ตอนรัน local อยู่ใต้ OneDrive อยู่แล้วเลย
  ได้ backup ฟรี แต่พอ deploy cloud safety net นี้หายไป → ผู้ใช้ขอให้เพิ่ม backup ง่ายๆ ไว้เลย (ไม่ใช่แค่ตอน
  deploy) → เพิ่มหัวข้อใหม่ "💾 Backup ของ state.json" + แก้ S-0
  (3) เคยเจอ Roboflow credit-cap มาก่อน (Core plan, 15 credit/เดือน) → ผู้ใช้ขอ safeguard popup ยืนยันก่อนยิง
  Roboflow API ทุกครั้ง (bulk Detect / Label Assist) + ตัวนับจำนวนครั้งที่ยิงในหน้าเว็บ → แก้ F-4/F-5 (client-side
  ล้วนๆ ไม่ต้องแก้ backend) นอกจากนี้พบเองว่า `MAX_UPLOAD_SIZE_MB` หายไปตอน simplify รอบก่อนโดยไม่ได้ตั้งใจ (ไม่มี
  การจำกัดขนาดไฟล์ upload เลย) → เพิ่มกลับเป็น env var optional (default 8GB)
- **30 กรกฎาคม 2026 — ตัดสินใจเรื่อง GPU**: ผู้ใช้ถามว่า GPU ช่วยงานนี้ไหม/จำเป็นไหม — อธิบายว่า GPU ช่วยเฉพาะ
  training (นอกเว็บแอป) กับ bulk detect (แต่ CPU ก็ทันเวลาที่สเกลนี้อยู่แล้วเพราะเป็น background job) ส่วน
  extract/export ไม่ได้ประโยชน์จาก GPU เลย → ผู้ใช้เลือก **CPU-only hosting ธรรมดา ไม่เช่า GPU cloud** ตัดข้อ
  ตัดสินใจ "GPU cloud provider" ที่ค้างไว้ (แนะนำแยกไปเช่า GPU ชั่วคราวเฉพาะตอนเทรนโมเดลรอบใหม่แทน) — แก้ Project
  Info "Deploy target" และหัวข้อ "จุดที่ต้องตัดสินใจ" ข้อ 1/4
- **30 กรกฎาคม 2026 (บ่าย) — เพิ่ม Landing Page**: ผู้ใช้ขอให้หน้าแรกของเว็บใส่ข้อมูลโปรเจกต์จาก
  `Report-Phase-1-1 (1).pdf` (รายงานผลระยะที่ 1 ของโครงการตรวจจับเครื่องมือผ่าตัด/บริเวณแผลด้วย AI สำหรับ
  บริบทสัตวแพทย์) อ่าน PDF เต็มแล้วสรุปเนื้อหาเป็นหัวข้อใหม่ "🏠 Landing Page Content" (hero, about, grid 5
  class, stat cards ผลลัพธ์ Phase 1 จริง — mAP@50 68.1%/Precision 80.5%/Recall 73.1%, roadmap) เขียนเป็น
  static text ตรงใน `index.html` ไม่มี backend endpoint ใหม่ (ตรงหลักการ "ใช้เท่าที่จำเป็น" — ข้อมูลนิ่งไม่ต้อง
  มี API) แก้ F-1 ให้โชว์ landing section นี้แทนฟอร์ม login เปล่าๆ ตอนยังไม่ login + เพิ่มลิงก์ "About" ใน top
  nav ให้เปิดดูได้แม้ login แล้ว, แก้ F-0 เพิ่ม style สำหรับ hero/stat-card/class-grid — ตั้งใจไม่ดึงรูปประกอบ
  จาก PDF เดิมมาฝัง (รอ screenshot จริงจากเว็บที่ทำงานได้แล้วแทนใน Phase 2)

---

## 🔑 Legend สถานะ

| สัญลักษณ์ | ความหมาย |
|---|---|
| ✅ | เสร็จ + commit + deploy จริงบน cloud แล้ว |
| 🔶 | เสร็จโค้ดแล้วแต่ยังไม่ verify ด้วยสายตา (browser จริง) หรือยังไม่ commit/push |
| ⬜ | ยังไม่เริ่ม |

---

## 📍 Project Info

| รายการ | ค่า |
|---|---|
| Project Root | `C:\Users\USER\OneDrive\Documents\BEAM\VideoFrameExtractor\` |
| Logic เดิม (ห้าม copy ซ้ำ — import ตรงๆ) | `frame_extractor.py` (`extract_frames()`), `detector.py` (`YOLOv11Detector`, `RoboflowDetector`, `Detection`, `CLASS_NAMES`), `dataset_exporter.py` (`export_dataset_pipeline()`, `count_stats()`) |
| Desktop app เดิม (ไม่แตะ ใช้คู่ขนานกันไปก่อน) | `app.py` |
| Stack Backend | Python 3.11 + **FastAPI + Uvicorn เท่านั้น** — ไม่มี DB/ORM/migration (ดูหัวข้อ "หลักการออกแบบ" ด้านล่าง) |
| Stack Frontend | Vanilla HTML + CSS + JS ไฟล์เดียวต่ออย่าง (ไม่ใช้ framework, ไม่ใช้ multi-page routing) |
| Persistence | In-memory Python dict ระหว่างรัน + snapshot ลง `webapp/state.json` เมื่อ job เสร็จ/หยุด หรือมีการแก้ annotation |
| Job execution | `threading.Thread` ตรงๆ (แบบเดียวกับที่ `app.py` ใช้อยู่แล้วทุกวันนี้ — ไม่มี abstraction ใหม่) |
| Progress ระหว่าง job | HTTP polling (`GET /api/.../{job_id}` ทุก ~1 วิ จาก `setInterval`) — ไม่มี WebSocket |
| Default Theme | Appearance ตั้งได้ 3 แบบ: Follow system settings (default) / Dark mode / Light mode — ดูหัวข้อ "🎨 Appearance / Theme System" |
| ขอบเขต MVP | Step 1-4 (Extract/Detect/Annotate/Export) — Live Verifier, Gesture capture, Import legacy data **ทั้งหมด** ตัดไป backlog |
| Deploy target | **CPU-only hosting ธรรมดา** (ตัดสินใจแล้ว 30 ก.ค. 2026 — ไม่ต้องเช่า GPU cloud) เช่น Railway/Fly.io/Render หรือรัน local เครื่องเดิม — `DEVICE_DEFAULT` ยังเป็น `cpu` และยังเลือก cuda/mps ได้จาก radio ต่อ job ถ้าวันหนึ่งมีเครื่อง GPU มาต่อเพิ่มเอง ไม่ผูกมัดสถาปัตยกรรม แต่ Docker/HTTPS/reverse-proxy ยังผลักไปทำตอน deploy จริง ไม่ใช่ตอนนี้ |

## 🎨 Appearance / Theme System

**กลไก** (CSS + vanilla JS ล้วนๆ ไม่มี dependency เพิ่ม — ตรงกับหลักการ "ใช้เท่าที่จำเป็น" ของโปรเจกต์นี้):
- สีทั้งหมดเป็น CSS custom property บน `:root` แล้วมี block `:root[data-theme="dark"]` กับ
  `:root[data-theme="light"]` override ทับ
- **"Follow system settings"** = ไม่ตั้ง `data-theme` attribute เลย → ใช้ `@media (prefers-color-scheme: dark)`
  เป็น fallback + ฟัง `matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...)` เพื่ออัปเดตสด
  ถ้าเปลี่ยนธีม OS ระหว่างเปิดแท็บค้างไว้
- เลือก **"Dark mode"/"Light mode"** ตรงๆ → บังคับ `data-theme="dark"|"light"` บน `<html>`
- เก็บค่าที่เลือกใน `localStorage` (`theme_preference: "system"|"dark"|"light"`, default `"system"`) —
  อ่านค่านี้ด้วย inline `<script>` เล็กๆ ที่บนสุดของ `<head>` (ก่อน CSS render) เพื่อกัน flash-of-wrong-theme
  ตอนโหลดหน้า

**Settings UI**: ไอคอนรูปเฟืองเล็กๆ ที่ top nav bar กดแล้วเปิด popover หัวข้อ "Interface theme" มี 3 แถวให้เลือก
(ตรงกับคำที่ผู้ใช้ระบุเป๊ะๆ): **Follow system settings** / **Dark mode** / **Light mode** — แต่ละแถวมีไอคอน
inline-SVG เล็กๆ (monitor/moon/sun ไม่ใช้ icon library) + แสดงสถานะว่าอันไหนถูกเลือกอยู่ — implement เป็น
HTML+CSS+`<script>` ธรรมดา ไม่ต้องมีไฟล์ใหม่ (รวมอยู่ใน F-1/F-2)

**Palette (Dark = เดิม ไม่เปลี่ยน นำจาก `app.py:35-46` ตรงๆ, Light = ใหม่)**

| CSS Variable | Dark (เดิม) | Light (ใหม่) | ที่มา (dark) |
|---|---|---|---|
| `--bg` | `#1a1a2e` | `#f5f6fa` | `DARK_BG` |
| `--bg-panel` | `#16213e` | `#ffffff` | `PANEL_BG` |
| `--accent` | `#0f3460` | `#e7ebf5` (navy ย้ายไปทำหน้าที่ border/text-secondary แทนในโหมด light) | `ACCENT` |
| `--highlight` | `#e94560` | `#e94560` (คงเดิมทั้งสองธีม — สี accent เดียวกับที่เห็นใน skywork.ai พอดี คอนทราสต์พอบนพื้นขาวอยู่แล้ว) | `HIGHLIGHT` |
| `--text` | `#eaeaea` | `#1a1a2e` (ใช้ hex เดิมของ dark-bg มาเป็น text สี light — ตระกูลสีเดียวกัน) | `TEXT_COLOR` |
| `--muted` | `#8899aa` | `#5c6b7a` (เข้มขึ้นให้พอคอนทราสต์บนพื้นขาว) | `MUTED` |
| `--success` | `#4ecca3` | `#2f9e78` (เข้มขึ้นให้พอคอนทราสต์บนพื้นขาว) | `SUCCESS` |
| `--warning` | `#f5a623` | `#c97a00` (เข้มขึ้นให้พอคอนทราสต์บนพื้นขาว) | `WARNING` |

Class colors (ใช้ตรงจาก `detector.py:30-37`, **เหมือนกันทั้งสองธีม** เพราะเป็นสี semantic ของข้อมูล/ภาพ ไม่ใช่ UI chrome):
`finger #FF6B48`, `forcep #4ECDC4`, `needle #FFE032`, `needle_holder #A8E6A0`, `wound #F064A0`, default `#AAAAAA`

**แรงบันดาลใจจาก skywork.ai ที่นำมาปรับใช้** (ดูหน้า public dashboard ผ่าน browser จริง ไม่ได้ล็อกอินด้วย
credential ผู้ใช้): การ์ดมุมโค้งนุ่มนวล + border จางๆ + padding กว้างพอ, ปุ่มหลัก/ช่อง input ทรง pill โค้งมน,
chip แบบ rounded-pill (ใช้กับ detection confidence chip ใน F-4 ที่วางแผนไว้แล้วได้พอดี) — **ไม่เอา sidebar nav
มาใช้** เพราะแอปนี้เป็น 4-step wizard เชิงเส้น ใช้ top nav tab (ตามที่วางแผนไว้เดิม) สื่อความหมายลำดับขั้นตอนได้
ดีกว่า sidebar ที่เหมาะกับ dashboard หลายฟีเจอร์อิสระแบบ skywork มากกว่า

---

## ✏️ Annotation Workflow & Tool Design (AI-Assisted)

> หัวข้อนี้คือแหล่งอ้างอิงหลักของระบบ Annotate — ออกแบบโดยศึกษาแนวคิดจาก Roboflow/CVAT/Label Studio/
> Supervisely แล้วเลือกเฉพาะส่วนที่เหมาะกับแอปนี้จริงๆ (bbox-only, 5 class คงที่, สเกลจริงหลักร้อยถึงหลักพันเฟรม
> ต่อโปรเจกต์ ไม่ใช่ล้านเฟรม) **ไม่ใช่การ clone แพลตฟอร์มไหน** ทุกอย่างในหัวข้อนี้อยู่ภายใต้กรอบ minimal-tool
> เดิมทั้งหมด (ไม่มี dependency ใหม่, ยังเป็น FastAPI+Uvicorn+3-ไฟล์ frontend เหมือนเดิม)

### 1. Annotation Tool Set (Phase 1)

เครื่องมือใหม่ที่ `AnnotationTab` วันนี้ยังไม่มี:

- **Select/Edit tool** — คลิกเลือกกล่อง, ลากย้าย, ลาก resize handle 8 จุด (วันนี้วาดแล้วขยับ/ปรับขนาดไม่ได้เลย)
- **Draw Box tool** — normalize math เดิม (`app.py:1219-1238`) แต่ **ค้างอยู่ในโหมดวาดได้หลายกล่องต่อเนื่อง**
  (วันนี้วาดเสร็จ 1 กล่องเหมือนออกจากโหมดวาดไปเลย ทั้งที่เฟรมเดียวมักมีอุปกรณ์ซ้ำ class เดียวกันหลายชิ้น)
- **ปุ่มเลข 1-5 → เปลี่ยน class** — มี 5 class พอดีกับปุ่มตัวเลข ลดคลิก dropdown ไปเยอะมาก
- **Delete** (`Delete`/`Backspace` ที่กล่องซึ่งเลือกอยู่) — วันนี้มีแต่ "Clear All Boxes" แบบเหมาว่างทั้งหมด
- **Undo/Redo** — เก็บ snapshot ของ array ทั้งชุด (สูงสุด ~50 ชั้น) — วันนี้ไม่มี undo เลย
- **Pan/Zoom** — จำเป็นสำหรับ class `needle` ที่เล็กมากในภาพ และช่วยลาก resize handle ได้แม่นขึ้น
- **Copy boxes จากเฟรมก่อนหน้า** — ดึง detections ของเฟรมก่อนมาเป็นจุดเริ่มต้น (reuse `GET /api/frames/{id}/detections`
  เดิม ไม่ต้องมี endpoint ใหม่)
- **AI-assist trigger** (ต่อกับ S-8 เดิม)
- **Accept All / Reject All** — จัดการกล่อง `source="model"` ทั้งหมดในเฟรมทีเดียว แทนที่จะกดทีละกล่องแบบ Roboflow

**ตั้งใจไม่ทำตอนนี้** (พร้อมเหตุผล): Polygon/Smart-Polygon (SAM) — `dataset_exporter.py` เขียนออกเป็น YOLO bbox
`.txt` เท่านั้น ไม่มี use case segmentation จริง · Keypoint/Pose — ไม่มี class ท่าทางใน `CLASS_NAMES`, และ
`WF-3` (gesture) ที่ backlog ไว้แนะนำให้ลอง bbox pipeline ก่อนอยู่แล้ว · Foundation model (SAM) แยกต่างหาก —
loop retrain (train→assist→review→retrain) แก้ปัญหาเดียวกันด้วยวิธีของแอปเองอยู่แล้ว ไม่ต้องเพิ่ม dependency
หนักอีกตัว · Occlusion/truncation attribute — YOLO format ไม่มีที่เก็บ ต้องมีหลักฐานว่าปัญหาจริงมาจากเรื่องนี้ก่อน
· Video track-based interpolation — ใหญ่กว่าที่เห็น (ต้องมี tracker) และ "copy จากเฟรมก่อนหน้า" ได้ประโยชน์
ส่วนใหญ่ไปแล้วด้วยต้นทุนต่ำกว่ามาก

### 2. AI-Assisted Annotation Loop (ครบวงจร)

Label เมล็ดพันธุ์ (seed set) เล็กๆ ด้วยมือ → export (`reviewed_only=true`, field ใหม่ ดู S-6) → เทรน "v1"
ข้างนอก → upload ผ่าน Models API เดิม (S-7) → bulk pre-label เฟรมที่เหลือด้วย S-4 พร้อม field ใหม่
**`skip_reviewed: bool = true`** (**จุดสำคัญที่สุดของรอบนี้** — ถ้าไม่มี field นี้ การรัน bulk detect ซ้ำด้วยโมเดล
ใหม่จะเขียนทับเฟรมที่ reviewed/แก้มือไปแล้วจากรอบก่อนอย่างเงียบๆ มี field นี้แล้ว S-4 จะรันซ้ำได้ปลอดภัยทุกรอบ
เทรน) → รีวิวในหน้า Annotate (กล่องที่โมเดลเสนอวาดเป็น **เส้นประ** พร้อม confidence badge สีแดงถ้า <0.5 — reuse
สไตล์เดียวกับ low-confidence chip ที่มีอยู่แล้วใน `DetectionTab`, `app.py:922-947` ไม่ต้องคิดใหม่) → แก้/
เปลี่ยน class/ลบ หรือกด Accept-All/Reject-All → **"Save & Next"** (รวม PUT detections + PATCH reviewed=true +
เลื่อนไปเฟรม unreviewed ถัดไปอัตโนมัติ เป็น action เดียว แทนที่จะกด 3 ครั้งแยกกันแบบวันนี้) → ใช้ S-8 (เดิม ไม่
เปลี่ยน) กด assist เฟรมเดียวตรงจุดที่ผลลัพธ์ bulk ดูผิดปกติ → export "v2" (`reviewed_only=true`) → วนซ้ำ

**Auto-assist ตอนเปิดเฟรม** ตั้งใจเป็น **Phase 2 ไม่ใช่ Phase 1**: ฝั่ง local ทำได้ถูกๆ แต่ฝั่ง Roboflow จะเผา
credit ทุกครั้งที่เลื่อนเฟรมแบบไม่ตั้งใจ — ปล่อยปุ่ม "Run Assist" แบบกดเองก่อน ค่อยเพิ่ม toggle "auto-assist"
ทีหลัง (ปิดใช้งานอัตโนมัติเมื่อ `backend="roboflow"`)

S-4 (batch/job/poll) กับ S-8 (เฟรมเดียว/sync) แยกหน้าที่กันชัดเจน ห้ามเขียน JS loop เรียก S-8 วนหลายเฟรมแทน
batch job เด็ดขาด — งาน bulk ต้องผ่าน S-4 เท่านั้น

### 3. UI/UX Layout (ยังคง 3 ไฟล์ ยังคง palette เดิม)

Filmstrip ซ้าย (thumbnail lazy-load, badge 🔴 ต้องรีวิว/✅ รีวิวแล้ว/🏷 มี AI suggestion ที่ยังไม่ confirm,
dropdown filter) + floating toolbar 2 ปุ่มทรง pill (Select/Draw — ไม่ทำ tool rail ยาวๆ เพราะมีแค่ 2 เครื่องมือ
ตอนนี้ ทำไปก็เกินความจำเป็น) + canvas (พื้นหลังเข้ม `#0d1117` เดียวกับ log panel/preview ที่มีอยู่แล้ว, **สียังคง
สื่อ class อย่างเดียว** ผ่าน `CLASS_COLORS_HEX` เดิม ส่วน **เส้นทึบ/เส้นประสื่อที่มา**: ประ = AI เสนอที่ยังไม่ confirm,
ทึบ = มือวาด/confirm แล้ว — ไม่ให้สีสื่อความหมาย 2 อย่างซ้อนกัน) + property panel ขวา (list detections พร้อม
class dropdown ในบรรทัด + confidence badge + คลิกแถวไฮไลต์กล่องบน canvas, panel Label Assist แบบพับเก็บได้
reuse markup เดียวกับ F-4 ผ่านฟังก์ชันร่วม ไม่ copy-paste, ปุ่ม Accept All/Reject All, ปุ่มหลัก "Save & Next →"
ส่วน Save-only/Mark-Reviewed/Clear-All เป็นปุ่มรอง) + status bar ล่าง (เลขเฟรม, จำนวนกล่อง, ความคืบหน้ารีวิว,
เตือน shortcut)

Keyboard shortcuts ครบชุด: `V`/`B` สลับเครื่องมือ · `1`-`5` เปลี่ยน class · `Delete` ลบ · `Ctrl+Z`/`Ctrl+Shift+Z`
undo/redo · ลูกศรขยับกล่อง (Shift=10px) · `[`/`]` เฟรมก่อน/ถัดไป · `A` รัน assist · `R` toggle reviewed ·
`Enter` Save & Next · `Esc` ยกเลิกวาด/ยกเลิกเลือก · ลาก space = pan · scroll = zoom · `?` เปิด cheat-sheet
(generate จาก lookup table เดียวกับโค้ด กันเอกสารเพี้ยนจากโค้ดจริง) — **shortcut ต้องปิดทำงานเสมอเมื่อ focus
อยู่ที่ช่อง text input ใดๆ** (เช่นช่อง filter/search) กัน typing โดนตีความเป็นคำสั่งเครื่องมือ

### 4. โครงสร้างใน `app.js` (ยังไฟล์เดียวเดิม — นี่คือการจัดระเบียบภายใน ไม่ใช่ไฟล์ใหม่)

โมดูลเล็กๆ แบบ closure/plain object ไม่มี framework/bundler: `Api` (ฟังก์ชันเดียวต่อ endpoint) ·
`AnnotateState` (state object + pub/sub เล็กๆ) · `Canvas` (คุม `<canvas>`, batch redraw ผ่าน
`requestAnimationFrame` + dirty flag, coordinate transform) · **Tool abstraction** (จุดสำคัญที่สุดสำหรับขยาย
ระบบในอนาคต) — registry `{select: SelectTool, draw_box: DrawBoxTool}` ทุก tool มี interface เดียวกัน
(`onPointerDown/Move/Up`, `onKeyDown` (optional), `render`, `onActivate/Deactivate`) — `Canvas` เรียกแค่
`tools[state.activeTool].onPointerDown(...)` เท่านั้น ทำให้ในอนาคตถ้าจะเพิ่ม Polygon/Keypoint tool แค่เขียน
object ใหม่ 1 ตัวตาม interface นี้ + ปุ่ม toolbar 1 ปุ่ม **ไม่ต้องแก้ `Canvas` หรือ event wiring เลย** ·
`SelectTool`, `DrawBoxTool` (implementation จริง) · `UndoManager` (JSON snapshot stack) · `Keyboard`
(listener เดียว + lookup table เดียว) · `Filmstrip` (lazy-load thumbnail ผ่าน `IntersectionObserver` —
native API ไม่มี dependency) · `PropertyPanel`, `StatusBar` (subscribe แล้ว re-render DOM ส่วนของตัวเอง)
แต่ละโมดูลอยู่ที่ราวๆ 150-200 บรรทัด แก้ปัญหา god-function ที่ `AnnotationTab` วันนี้เป็นอยู่ (คลาสเดียวทำ
press/drag/release/save/refresh/draw ทั้งหมด, `app.py:1103-1267`)

หมายเหตุ: client-side id ของแต่ละกล่อง (สำหรับ hit-test บน canvas เท่านั้น) ใช้ `crypto.randomUUID()` ถ้ามี
ไม่งั้น fallback เป็น counter ธรรมดา/`Date.now()` — id พวกนี้ไม่ส่งไป backend เลย เป็นแค่ bookkeeping ฝั่ง client

### 5. Performance (สเกลจริง ไม่ใช่ล้านเฟรมสมมติ)

Filmstrip lazy-load (โหลดจริงแค่ ~20-30 แถวที่มองเห็นเท่านั้นไม่ว่าทั้งหมดจะกี่เฟรม) · `GET /api/frames?...`
คืน list เต็มในครั้งเดียว **ไม่ทำ pagination** (ตั้งเป็นจุดที่ต้องกลับมาพิจารณาใหม่เฉพาะถ้าโปรเจกต์ไหนมีเฟรมหลักหมื่น
เช่นใช้โหมด "ทุกเฟรม" กับวิดีโอยาวมาก) · canvas redraw batch ผ่าน `requestAnimationFrame` + dirty flag ·
JS เก็บแค่เฟรมปัจจุบัน + LRU เล็กๆ (~5-10 เฟรม) ไม่โหลดทั้ง dataset ค้างในหน่วยความจำ · `state.json` ที่สเกลนี้
ยังอยู่หลักสิบ-ร้อย KB ไม่มีเหตุผลต้องกลับไปพิจารณา DB เพราะการออกแบบรอบนี้ · export/augmentation ใช้ loop
sequential เดิมใน background thread ต่อไป ไม่เพิ่ม multiprocessing pool

### 6. Phasing

**Phase 1 (ทำตอนนี้)**: เครื่องมือทั้งหมดในข้อ 1, loop เต็มในข้อ 2 (ยกเว้น auto-assist), UI/UX เต็มในข้อ 3,
โครงสร้างเต็มในข้อ 4, S-4/S-6 amendment, S-9, F-7, F-5 ที่ขยายแล้ว

**Phase 2 (ถัดไป)**: multi-select/rubber-band + bulk delete/reassign, right-click context menu, toggle
"auto-assist ตอนเปิดเฟรม", occlusion/truncation attribute ต่อกล่อง, หน้า analytics เวอร์ชันโมเดล/accept-rate

**Phase 3 (ตั้งใจเลื่อนไปก่อน แต่ architecture ต้องไม่ปิดกั้น)**: polygon/segmentation tool, keypoint/pose tool,
SAM-assisted auto-box, OCR, video track-based annotation, multi-user concurrency — Tool abstraction ในข้อ 4
ออกแบบมาเพื่อให้เพิ่มสิ่งเหล่านี้ทีหลังได้โดยไม่ต้องเขียน canvas engine ใหม่

---

## 🏠 Landing Page Content (อ้างอิงจาก `Report-Phase-1-1 (1).pdf`)

แหล่งที่มา: รายงานผลการดำเนินงานระยะที่ 1 ของโครงการ (`Report-Phase-1-1 (1).pdf`, อยู่ที่ root ของ repo) —
เนื้อหาด้านล่างเป็น**ข้อความ static เขียนตรงใน `index.html`** ไม่ต้องมี backend endpoint ใหม่เลย เพราะเป็น
ข้อมูล "เกี่ยวกับโครงการ" ที่แทบไม่เปลี่ยนบ่อย (ตรงกับหลักการ "ใช้เท่าที่จำเป็น" — ไม่สร้าง API แค่เพื่อ serve
ข้อความนิ่งๆ)

**โครงสร้างเนื้อหา** (แสดงเป็นหน้า default ก่อน login แทนฟอร์มเปล่าๆ, ดู F-1):

1. **Hero**: ชื่อโครงการ "ระบบตรวจจับเครื่องมือผ่าตัดและบริเวณแผลด้วยปัญญาประดิษฐ์" + tagline สั้นๆ
   เช่น "AI ที่ช่วยตรวจจับเครื่องมือผ่าตัดและบริเวณแผล เพื่องานด้านสัตวแพทย์"
2. **About**: ย่อหน้าอธิบายเป้าหมายโครงการจากบทนำของรายงาน — พัฒนาระบบปัญญาประดิษฐ์สำหรับตรวจจับเครื่องมือ
   ผ่าตัดและบริเวณแผลจากวิดีโอการผ่าตัด เน้นใช้ในบริบทสัตวแพทย์ (ช่วยสอนการเย็บแผล, วิเคราะห์ขั้นตอนการผ่าตัด
   ย้อนหลัง, ต่อยอดสู่ระบบช่วยตัดสินใจในอนาคต)
3. **Grid 5 ประเภทวัตถุ** — reuse `CLASS_COLORS_HEX` จาก `detector.py:30-37` เป็น swatch สี ไม่ hardcode สีซ้ำ:
   `needle` (เข็มเย็บแผล), `finger` (นิ้วมือผู้ปฏิบัติงาน), `needle_holder` (คีมจับเข็ม), `wound` (บริเวณแผล),
   `forcep` (ปากคีบ)
4. **Stat cards ผลลัพธ์ Phase 1** (ตัวเลขจากรายงานจริง ไม่ใช่ query สดจาก state.json — ดูหมายเหตุด้านล่าง):
   12 วิดีโอ (~1 นาที/วิดีโอ) · 120 เฟรมที่สกัด+annotate ครบ · แบ่ง Train 106 / Validation 8 / Test 6 ·
   **mAP@50 68.1%** · **Precision 80.5%** · **Recall 73.1%** (โมเดล YOLOv11 Object Detection Accurate)
5. **Roadmap สั้นๆ**: เพิ่มความหลากหลายของข้อมูล (วิดีโอ/สัตว์/มุมกล้อง/แสง) + augmentation, พัฒนาโมเดล RNN
   วิเคราะห์ลำดับการเคลื่อนไหวของเครื่องมือตลอดขั้นตอนการเย็บแผล (ไม่ใช่แค่ detect ทีละเฟรม), เชื่อมกล้อง
   real-time ในห้องผ่าตัด, ทำ interface ที่ใช้งานง่ายสำหรับผู้ไม่มีพื้นฐานเทคโนโลยี
6. **Login form** (password field) — วางเป็น CTA หลักท้าย/แทรกกลาง landing section

**หมายเหตุสำคัญ**: ตัวเลข stat ในข้อ 4 เป็นผลจาก**รายงานภายนอก** (การทดลองรอบก่อนหน้าที่ทำนอกเว็บนี้) ไม่ใช่
ตัวเลขที่ backend คำนวณสดจาก dataset ปัจจุบันใน `state.json` — เขียนเป็น static text ชัดเจนว่าเป็นผลจาก
"รายงานระยะที่ 1" ไม่ใช่ตัวเลข real-time ของเว็บ ถ้าอยากให้ตัวเลขอัปเดตสดตาม dataset จริงที่มีอยู่ในระบบ
ต้องต่อกับ backend (`count_stats()` มีอยู่แล้วจาก `dataset_exporter.py:196`) — เกินขอบเขต MVP ตอนนี้ ทำเป็น
static พอ

**ตั้งใจไม่ทำตอนนี้**: ดึงรูปภาพประกอบจาก PDF เดิม (ตัวอย่างเฟรมวิดีโอ/ภาพหลัง annotation/ภาพผลตรวจจับ) มาฝัง
ในหน้าเว็บ — รูปจากรายงานเก่าไม่สะท้อนตัวเว็บที่กำลังสร้าง แนะนำรอจน S-4/S-8 ทำงานได้จริงแล้วค่อยแคป
screenshot จากตัวเว็บเองมาใส่แทน (Phase 2) จะดูน่าเชื่อถือกว่าและตรงกับของจริงมากกว่า

---

## 🧭 หลักการออกแบบ: เหตุผลที่ตัดออก (อ่านก่อนเริ่ม ทุก task อ้างอิงหัวข้อนี้)

| ของเดิมที่เคยวางแผนไว้ | ของใหม่ | เหตุผล |
|---|---|---|
| SQLAlchemy + Alembic + 6 ตาราง DB | in-memory dict + ไฟล์ `state.json` ไฟล์เดียว | เป็นเครื่องมือ single-user — `app.py` เดิมเองก็เก็บ annotation ใน memory (`app.detection_results`) ไม่เคย persist อยู่แล้ว การทำแบบเดียวกันไม่ใช่การถอยหลัง และผู้ใช้ยืนยันรับ trade-off นี้แล้ว |
| python-jose (JWT) + passlib[bcrypt] | `secrets.token_urlsafe()` เป็น session token เก็บใน dict ฝั่ง server + `hmac.compare_digest()` เทียบรหัสผ่าน | มีรหัสผ่านเดียว ไม่มีตาราง user ให้ hash เก็บ — token ที่ server เช็คเองง่ายกว่า JWT และปลอดภัยพอสำหรับ threat model นี้ |
| WebSocket + `ws_manager.py` + reconnect logic | HTTP polling ธรรมดา (`GET /api/.../{job_id}` ทุก ~1 วิ) | ไม่ต้องเขียน/ดีบัก connection lifecycle เลย หน่วง 1 วิ ไม่มีผลกับผู้ใช้คนเดียว ทดสอบด้วย `curl` ตรงๆ ได้ |
| `slowapi` | dict นับจำนวนครั้ง login ผิดต่อ IP ~15 บรรทัด | ตัด dependency ออกสำหรับความต้องการเล็กขนาดนี้ |
| Docker (task ใน MVP) | `pip install -r webapp/requirements.txt && python webapp/server.py` | ผลักไปทำตอน deploy จริงตามที่ผู้ใช้ตอบ ไม่ต้องมีตอนพัฒนา/ใช้งาน local |
| CORS middleware | ไม่ใช้เลย | frontend เป็น static files ที่ FastAPI mount เอง (origin เดียวกัน) ไม่มี cross-site อะไรให้ allow |
| `webapp/backend/` 15 ไฟล์ (config/main/database/models/auth/middleware/job_manager/storage/ws_manager/routers 8 ไฟล์) | `webapp/server.py` ไฟล์เดียว (แตกเป็น 2 ไฟล์เฉพาะถ้ายาวเกิน ~800 บรรทัด) | ไฟล์น้อยลง ต่อ import กันน้อยลง ดูแลคนเดียวง่ายกว่า |
| `webapp/frontend/` 11 ไฟล์ (login.html + css/ + js/ 4 ไฟล์ + 5×(page.html+page.js)) | `webapp/static/index.html` + `style.css` + `app.js` (3 ไฟล์) | Single-page app สลับแสดง/ซ่อน section ด้วย JS ธรรมดา แทน multi-page + router + localStorage sync — mirror `Notebook` tabs ของ `app.py` ตรงๆ |
| Import Legacy Desktop Data ใน MVP | ย้ายไป backlog | เป็นฟีเจอร์ช่วยย้ายข้อมูลเก่า ไม่ใช่ 1 ใน 4 ขั้นตอนจริงของ pipeline — ตัดออกจาก MVP คือการ "ใช้เท่าที่จำเป็น" อีกชั้นหนึ่ง |
| 8 env vars (`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `DEVICE_DEFAULT` ฯลฯ) | เหลือ 1 ตัวจำเป็น (`APP_PASSWORD`) + 2 ตัวเลือก (`DATA_DIR`, `MODEL_DIR`) | ไม่มี DB ไม่มี JWT signing key ไม่มี CORS ไม่ต้องมี env ผลัก device default (ใช้ radio ในหน้าเว็บเหมือน desktop) |

**สิ่งที่ยังคงไว้เหมือนเดิม** (ไม่ใช่ต้นตอความซับซ้อนที่ต้องตัด และตัดออกจะเสียของจริง):
- FastAPI + Uvicorn — ได้ request validation ฟรีผ่าน Pydantic ไม่ต้องรันเป็น service แยก
- Pydantic request model ที่มี constraint จริง (conf/iou/splits) — เป็นแค่โค้ด validation ไม่ใช่ infrastructure เพิ่ม
- Import `frame_extractor.py` / `detector.py` (`YOLOv11Detector` + `RoboflowDetector`) / `dataset_exporter.py` ตรงๆ ผ่าน `sys.path` — เหมือนแผนเดิมทุกประการ
- `threading.Thread` สำหรับงานพื้นหลัง — `app.py` ใช้แบบนี้อยู่แล้วทุกวันนี้ (`threading.Thread(target=self._run, daemon=True).start()`)
- Path-safety-via-ID, upload extension whitelist, httpOnly/samesite cookie — แทบไม่มีต้นทุนเพิ่ม ไม่ต้องพึ่ง library ไหนเลย
- รองรับ Roboflow backend (`backend: "local"|"roboflow"` ใน detect job, ไม่ persist api_key) — ยังอยู่ในขอบเขตเดิม แค่ implement โดยไม่มีคอลัมน์ DB

---

## 📄 โครงสร้างไฟล์ที่จะสร้าง

```
VideoFrameExtractor\
  app.py                      ← เดิม ไม่แตะ
  frame_extractor.py          ← เดิม ไม่แตะ (import จาก backend)
  detector.py                 ← เดิม ไม่แตะ (import จาก backend)
  dataset_exporter.py         ← เดิม ไม่แตะ (import จาก backend)
  requirements.txt            ← เดิม (desktop deps)
  WORK_PLAN.md                ← ไฟล์นี้
  webapp\
    requirements.txt           ← fastapi, uvicorn[standard], python-multipart
                                  + opencv-python, Pillow, numpy, ultralytics, PyYAML, imagehash,
                                    albumentations, inference-sdk (deps ของโมดูลเดิมที่ import มาใช้)
    server.py                  ← ไฟล์เดียว: FastAPI app + auth + videos + extract + detect + annotate
                                  + export + models endpoints + state.json load/save + job threads
                                  (แตกเป็น 2 ไฟล์เฉพาะถ้ายาวเกิน ~800 บรรทัด — ไม่วางแผนแตกล่วงหน้า)
    state.json                 ← runtime: snapshot วิดีโอ/jobs/เฟรม/detections (ใส่ .gitignore)
    static\
      index.html                ← หน้าเดียว: login form + 4 section (Extract/Detect/Annotate/Export)
                                   สลับด้วย JS โชว์/ซ่อน (mirror Notebook tabs ของ app.py)
      style.css                 ← palette เดียวกับ app.py
      app.js                    ← fetch() ตรงๆ + setInterval polling progress + canvas annotation
    data\                       ← runtime: videos/, frames/, exports/ (DATA_DIR)
    models\                     ← runtime: .pt files (MODEL_DIR)
```

---

## 🔧 Environment Variables

| ตัวแปร | Default | คำอธิบาย |
|---|---|---|
| `APP_PASSWORD` | (ต้องตั้งเอง ไม่มี default) | รหัสผ่านเดียวสำหรับ login เข้าเว็บ |
| `DATA_DIR` | `./webapp/data` | โฟลเดอร์เก็บวิดีโอ/เฟรม/export (optional — ไม่ตั้งก็ใช้ default นี้) |
| `MODEL_DIR` | `./webapp/models` | โฟลเดอร์เก็บไฟล์ `.pt` ของ YOLO (optional) |
| `MAX_UPLOAD_SIZE_MB` | `8192` (8GB) | จำกัดขนาดไฟล์วิดีโอ/โมเดลที่อัพโหลดได้ต่อไฟล์ (optional — default กว้างพอสำหรับวิดีโอผ่าตัดไฟล์ใหญ่ แต่ยังกันกรณีไม่มี limit เลยซึ่งเสี่ยง disk เต็ม/DoS ถ้าเปิดออนไลน์ ปรับได้ผ่าน env โดยไม่ต้องแก้โค้ด) |

ไม่มี `DATABASE_URL` (ไม่มี DB), ไม่มี `JWT_SECRET` (ไม่ sign JWT — session token เช็คจาก dict ฝั่ง server เอง),
ไม่มี `CORS_ORIGINS` (same-origin เสมอ), ไม่มี `DEVICE_DEFAULT` (เลือกจาก radio ในหน้าเว็บเหมือน desktop)

⚠️ **หมายเหตุ cookie `secure` flag**: ต้องตั้งตามว่าแอปถูก serve ผ่าน HTTPS จริงหรือไม่ ไม่ใช่แค่เดาจาก "prod vs dev" —
รันบน local machine เฉยๆ (ไม่มี reverse proxy/TLS) ต้อง `secure=False` เสมอ มิฉะนั้น browser จะไม่ยอมตั้ง cookie
เลยบน plain `http://localhost` และผู้ใช้จะ login ไม่ผ่านอย่างงงๆ

---

## 💾 Backup ของ `state.json` (กัน data loss)

`state.json` คือบันทึกผลงาน annotate ทั้งหมด ไม่มี DB ไม่มี version history — ต้องมี safety net ของตัวเอง
ทำด้วย stdlib ล้วนๆ ไม่มี dependency เพิ่ม:

- **Rolling single backup (ทำเสมอ ทั้ง local และ cloud)**: ก่อนเขียน `state.json` ทับทุกครั้งใน `save_state()`
  ให้ `shutil.copy()` ไฟล์เดิมไปเป็น `state.json.bak` ก่อน — กันกรณีเขียนไฟล์ค้าง/พังระหว่าง save (คนละเรื่องกับ
  atomic write ผ่าน `.tmp`+`os.replace` ที่มีอยู่แล้วใน S-0 — อันนั้นกัน "ไฟล์เสียระหว่างเขียน" อันนี้กัน
  "เขียนข้อมูลผิดทับของถูกไปแล้ว")
- **Periodic timestamped snapshot (สำคัญกว่าตอน deploy cloud)**: ทุกครั้งที่ `save_state()` ถูกเรียกและผ่านไป
  ≥15 นาทีจาก snapshot ล่าสุด (เช็คจาก timestamp ในหน่วยความจำ ไม่ต้องมี background scheduler) ให้คัดลอก
  `state.json` ไปเก็บที่ `webapp/data/backups/state_YYYYMMDD_HHMMSS.json` แล้วลบไฟล์เก่าสุดถ้าเกิน 10 ไฟล์
  (`os.listdir` + sort ตามชื่อ + `os.remove` ตัวเกิน) — ให้ rollback กลับไปจุดก่อนหน้าได้ถ้าทำงานพลาดหนักๆ
- **เหตุผลที่ต้องมีแม้รัน local ก็ตาม**: แม้ตอนนี้โปรเจกต์อยู่ใต้ OneDrive (`C:\Users\USER\OneDrive\Documents\
  BEAM\VideoFrameExtractor\`) ซึ่งช่วย backup/เก็บ version ให้พื้นฐานอยู่แล้วตอนรัน local แต่พอย้ายไป deploy บน
  cloud provider (RunPod/Lambda/Vast.ai ฯลฯ) safety net จาก OneDrive จะหายไปทันที — ทำ backup mechanism นี้ไว้
  ใน `save_state()` ตั้งแต่ต้นเลยดีกว่า ไม่ต้องมาแก้เพิ่มตอน deploy จริง
- ไม่ต้องมี UI restore ใน MVP (ยังทำมือผ่านการ copy ไฟล์กลับได้อยู่) — ถ้าต้องการปุ่ม "Restore from backup" ในหน้าเว็บ
  ค่อยพิจารณาเพิ่มทีหลังเมื่อเห็นว่าจำเป็นจริง

---

## กฎที่ต้องทำตามตลอดโปรเจกต์

- **ใช้เครื่องมือ/dependency เท่าที่จำเป็นเท่านั้น** — ก่อนเพิ่ม library ใหม่ ให้ถามว่า "เขียนเองด้วย stdlib ใน ~20 บรรทัด
  ได้ไหม" ถ้าได้ ให้เขียนเอง (ดูตัวอย่างการตัดสินใจในหัวข้อ "หลักการออกแบบ" ด้านบน)
- **ห้าม copy logic ซ้ำ** — `extract_frames()`, `YOLOv11Detector`, `RoboflowDetector`, `export_dataset_pipeline()`, `count_stats()` ต้อง `import` จากไฟล์เดิมที่ root ตรงๆ (เพิ่ม root เข้า `sys.path`) ห้ามเขียน logic เหล่านี้ใหม่ในฝั่ง backend
- ห้าม hardcode สีใดๆ ใน CSS/JS — ใช้ CSS variable จาก palette ที่ระบุไว้ข้างบนเท่านั้น
- งานหนักทุกตัว (extract/detect/export) รันผ่าน `threading.Thread` (แบบเดียวกับ `app.py`) ห้าม block HTTP request — progress อ่านผ่าน polling endpoint ตาม job_id
- ทุก endpoint ที่แก้ไฟล์ในดิสก์ต้อง resolve path ผ่าน id ใน state dict แล้วเช็คว่าอยู่ใต้ `DATA_DIR`/`MODEL_DIR` เท่านั้น (กัน path traversal)
- UI ข้อความภาษาไทยของ `app.py` เดิม (เช่น "เพิ่มวิดีโอ", "กำลังสกัดเฟรม...") ให้คงไว้เหมือนเดิมในหน้าเว็บ ไม่ต้องแปลใหม่ เพื่อ parity กับผู้ใช้เดิม
- ทดสอบจริงหลังทำเสร็จแต่ละ task (curl/browser) ก่อนไป task ถัดไป
- ค่า default ของทุกฟอร์ม (conf=0.25, iou=0.45, target=30, similarity=30.0, blur=50.0, train=70%, val=20%, augment multiplier=3 ฯลฯ) ต้องตรงกับใน `app.py` เป๊ะ — ห้ามเปลี่ยนโดยไม่แจ้ง

---

## ⚠️ ข้อควรระวัง: bug ของ desktop app ที่ไม่ต้องก็อปตาม

- **`LiveVerifierTab` (`app.py:1033`)** เรียก `time.sleep(0.03)` แต่ไฟล์ `app.py` ไม่มี `import time` เลย → กล้อง crash ทันที
  ด้วย `NameError` ตั้งแต่เฟรมแรกที่ประมวลผล เป็น bug ที่มีอยู่ก่อนแล้วในโค้ดปัจจุบัน — ตอนทำ **WF-1 (Live Verifier ผ่าน browser)**
  ต้อง**ไม่**พอร์ต bug นี้ตามไปด้วย
- **`DetectionTab._on_done` (`app.py:812-824`)**: ข้อความ dialog ถามว่า "ไปที่ Step 3 (Export Dataset) เลยไหม?" แต่โค้ดจริงเรียก
  `go_to_tab(2)` ซึ่งไปที่ **Annotation** ไม่ใช่ Export — ลำดับ Extract→Detect→Annotate→Export ในแผนนี้ **ถูกต้องอยู่แล้ว**
  ไม่ต้องแก้ไขอะไร แค่บันทึกไว้กันสับสนเวลาเทียบ behavior กับ desktop จริง
- **`AnnotationTab._save_changes` (`app.py:1254-1256`)** ไม่ persist ลงดิสก์จริง แค่เก็บใน memory แล้วขึ้น "Saved to state" — เว็บเวอร์ชันที่ save ลง `state.json` จริงคือการปรับปรุงที่ตั้งใจ ไม่ใช่ parity ที่ต้องแก้ย้อนกลับ

---

## 🔒 Security & Validation Rules (ทำด้วย stdlib/FastAPI ล้วนๆ ไม่มี security library เพิ่ม)

- **Video upload**: whitelist นามสกุล `.mp4 .avi .mov .mkv .wmv` (ตรงกับ `app.py:454` filetypes) + เช็ค MIME แบบ magic-byte เบื้องต้น ไม่เชื่อแค่ extension + จำกัดขนาดไม่เกิน `MAX_UPLOAD_SIZE_MB`
- **Model upload**: whitelist เฉพาะ `.pt` + จำกัดขนาดไม่เกิน `MAX_UPLOAD_SIZE_MB` เช่นกัน
- **Path safety**: ทุก id ที่มาจาก client (video id, frame id, model name) ต้อง lookup ผ่าน state dict ก่อนเสมอ ห้ามเอา string จาก client ไป join path โดยตรง
- **Secrets**: `APP_PASSWORD` เก็บใน `.env` เท่านั้น ห้าม commit, ต้องอยู่ใน `.gitignore` (พร้อมกับ `state.json`, `data/`, `models/`)
- **Timing-safe password compare**: เทียบรหัสผ่านกับ `APP_PASSWORD` ด้วย `hmac.compare_digest()` ไม่ใช่ `==`
- **Session token**: `secrets.token_urlsafe(32)` เก็บใน `dict[token, expiry]` ในหน่วยความจำ ส่งเป็น cookie
  `httpOnly=True, secure=<ตาม HTTPS จริง>, samesite="strict"`, TTL 8-12 ชม. (job รันได้นาน ไม่อยากให้หลุด login กลางงาน)
- **Rate limit login**: dict `{ip: [timestamps ที่ผิด]}` ในหน่วยความจำ บล็อกหลังผิด 5 ครั้งใน 5 นาที (~15 บรรทัด ไม่ใช้ library)
- **Validate ด้วย Pydantic เสมอ**: ทุก request body ต้องผ่าน Pydantic model ที่มี constraint จริง (เช่น `conf`/`iou`
  อยู่ใน `[0.01, 0.99]`, `splits.train + splits.val + splits.test` ≈ 1.0) — ห้ามเชื่อ client แม้ frontend จะจำกัดค่าด้วย
  slider/spinbox ไว้แล้วก็ตาม
- **Roboflow `api_key`**: รับมาต่อ request เท่านั้น **ห้าม persist ลง `state.json` หรือ log ใดๆ**
- **Roboflow cost guard (client-side, ใหม่)**: ก่อนยิง request ที่ใช้ `backend="roboflow"` (POST /api/detect หรือ
  POST /api/frames/{id}/assist) ต้องมี `window.confirm()` ยืนยันก่อนเสมอ (บอกจำนวนเฟรมที่จะส่งถ้าเป็น bulk detect
  เพราะเคยเจอปัญหา credit-cap ของ Roboflow Core plan มาก่อน — ดู F-4/F-5) + แสดงตัวนับ "เรียก Roboflow ไปแล้ว N
  ครั้ง" ในหน้าเว็บ (client-side ล้วนๆ, reset ทุกครั้งที่ reload หน้า, ไม่ต้องมี endpoint ใหม่)
- **Backup**: `state.json` มี rolling backup + periodic snapshot ตามหัวข้อ "💾 Backup ของ state.json" ด้านบน
- **Security headers**: middleware เล็กๆ ใส่ `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (ไม่ต้องใช้ library เพิ่ม เขียนเป็น middleware ธรรมดาของ FastAPI)

---

## 🔧 SETUP + BACKEND TASKS (ทั้งหมดอยู่ใน `webapp/server.py` ไฟล์เดียว)

### S-0 | Project Setup + App Skeleton
```
สร้าง: webapp/requirements.txt (รายการ dep ด้านบน), webapp/server.py, webapp/.env.example
เพิ่ม root เข้า sys.path เพื่อให้ `from frame_extractor import extract_frames` /
  `from detector import YOLOv11Detector, RoboflowDetector, CLASS_NAMES` /
  `from dataset_exporter import export_dataset_pipeline, count_stats` ใช้ได้ตรงๆ
server.py มี: FastAPI app instance, mount static (webapp/static), GET /api/health → {status:ok},
  load_state()/save_state() (json.load/json.dump แบบ atomic: เขียน .tmp แล้ว os.replace),
  โหลด state ตอน startup ถ้ามีไฟล์ `state.json` อยู่แล้ว
  save_state() ยังทำ backup ตาม "💾 Backup ของ state.json" ด้วย: shutil.copy() ไฟล์เดิมไป state.json.bak ก่อน
  เขียนทับทุกครั้ง + ถ้าผ่านไป ≥15 นาทีจาก snapshot ล่าสุด (timestamp เก็บใน memory) ให้คัดลอกไป
  webapp/data/backups/state_YYYYMMDD_HHMMSS.json แล้ว prune ไฟล์เกิน 10 อัน
ทดสอบ: uvicorn webapp.server:app → GET /api/health → {"status":"ok"}, restart แล้ว state ไม่หาย (ถ้ามี snapshot อยู่),
  save_state() หลายครั้งติดกัน → state.json.bak มีข้อมูลจาก save ก่อนหน้า, รอ >15 นาทีแล้ว save อีกครั้ง →
  มีไฟล์ใหม่ใน webapp/data/backups/
พึ่งพา: ไม่มี
```

### S-1 | Auth
```
เพิ่มใน server.py:
  POST /api/login  → body {password} → hmac.compare_digest กับ APP_PASSWORD →
    ถ้าผิด: เช็ค rate-limit dict ก่อน (บล็อกถ้าผิดเกิน 5 ครั้ง/5 นาทีต่อ IP) → 401
    ถ้าถูก: สร้าง session token (secrets.token_urlsafe(32)) ใส่ dict พร้อม expiry (+8-12 ชม.) → set cookie
  POST /api/logout → ลบ token จาก dict + clear cookie
  GET  /api/me     → require_auth dependency (เช็ค cookie อยู่ใน session dict และยังไม่หมดอายุ) → {authenticated:true}
  ทุก endpoint อื่นนอกจาก /api/login, /api/health, static files ต้องผ่าน require_auth
ทดสอบ: login รหัสผิด 401, ถูก → cookie ตั้ง → /api/me → 200, เรียก endpoint อื่นไม่มี cookie → 401
พึ่งพา: S-0
```

### S-2 | Videos API
```
Endpoints:
  POST   /api/videos          → multipart upload (multi-file) → validate ext/magic-byte + ขนาดไม่เกิน
                                 MAX_UPLOAD_SIZE_MB (413 ถ้าเกิน) → save under DATA_DIR/videos/
                                 → เพิ่มเข้า state["videos"], save_state()
  GET    /api/videos          → list จาก state["videos"]
  DELETE /api/videos/{id}     → ลบไฟล์ + ลบออกจาก state, save_state()
ทดสอบ: upload .mp4 ตัวอย่าง → ปรากฏใน GET list → DELETE → ไฟล์หายจากดิสก์ + list ว่าง, upload ไฟล์ปลอมที่เกิน
  MAX_UPLOAD_SIZE_MB (หรือลด env ชั่วคราวมาทดสอบ) → 413 ไม่ถูกบันทึก
พึ่งพา: S-0, S-1
```

### S-3 | Extraction API
```
POST /api/extract
  body (Pydantic model): { video_ids: [], mode: "interval"|"target"|"all",
    interval_sec: 1.0, target_frames: 30,
    compare_method: "none"|"motion_iou"|"frame_diff"|"phash", similarity_threshold: 30.0,
    filter_blur: true, blur_threshold: 50.0, prefix: "frame",
    slot_fallback: false, max_attempts_per_slot: 5, separate_per_video: true }
  → สร้าง entry ใน state["extract_jobs"][job_id] = {status:"running", progress:0, log:[]}
  → threading.Thread รัน extract_frames() (frame_extractor.py:40) ต่อวิดีโอทีละตัว เหมือน app.py._run()
    ทุกกรณี (target-mode คำนวณ interval จาก duration/target, all-mode compare_method="none")
  → progress_callback/log_callback เขียนเข้า state["extract_jobs"][job_id] ตรงๆ (in-memory, ไม่ save_state()
    ทุก tick — save_state() เฉพาะตอนจบ/หยุด)
  → เมื่อเสร็จ: เพิ่ม Frame record เข้า state["frames"] ต่อไฟล์ภาพที่ extract_frames() สร้างไว้ แล้ว save_state()
GET  /api/extract/{job_id}         → อ่านสถานะ/progress/log ปัจจุบันจาก state (ให้ frontend polling)
GET  /api/extract/{job_id}/frames  → list Frame ของ job นี้
POST /api/extract/{job_id}/stop    → ตั้ง flag ให้ thread หยุด (mirror app.py._stop())
ทดสอบ: extract วิดีโอสั้น (10s) โหมด target=5 → ได้ 5 Frame, polling เห็น progress ขยับ 0→100, log ตรงกับที่
  extract_frames() log จริง ([saved]/[skip]/[blur])
พึ่งพา: S-0, S-1, S-2
```

### S-4 | Detection API (รองรับ Local + Roboflow)
```
POST /api/detect
  body: { frame_ids: [], backend: "local"|"roboflow", conf: 0.25, iou: 0.45, device: "cpu",
          skip_reviewed: true,                            # ใหม่ — ดู "✏️ Annotation Workflow" §2
          model_path,                                    # เมื่อ backend="local"
          api_key, workspace_name, workflow_id }          # เมื่อ backend="roboflow"
  → validate ตาม backend (mirror app.py DetectionTab._build_detector()/_start(), app.py:776-804):
      local: ยอมรับไฟล์จริงใต้ MODEL_DIR หรือชื่อ pretrained (ขึ้นต้น "yolo"/"rtdetr" ลงท้าย ".pt")
      roboflow: ต้องมี api_key ไม่ว่าง (400 ถ้าไม่มี)
  → สร้าง state["detect_jobs"][job_id] = {backend, model_path (null ถ้า roboflow), conf, iou, device,
      status, progress} — **ห้ามเก็บ api_key ใน state เด็ดขาด** (ใช้แค่ในหน่วยความจำของ thread ระหว่าง request นี้)
  → **แยก validate+build detector ออกเป็นฟังก์ชันกลาง `build_detector(backend, params)`** (คืน YOLOv11Detector
    หรือ RoboflowDetector, detector.py:92/222) — S-8 (Label Assist) เรียกใช้ฟังก์ชันเดียวกันนี้ ห้ามเขียนซ้ำ
  → threading.Thread เรียก build_detector() 1 ครั้ง, loop ทุกเฟรมใน frame_ids **ยกเว้นเฟรมที่ `reviewed=true`
    ถ้า `skip_reviewed=true`** (default true — ป้องกันรัน bulk detect ซ้ำด้วยโมเดลใหม่แล้วเขียนทับเฟรมที่รีวิว/
    แก้มือไปแล้วจากรอบก่อนอย่างเงียบๆ ทำให้ endpoint นี้รันซ้ำได้ปลอดภัยทุกรอบเทรนโมเดลใหม่) → predict() →
    เก็บ detection เข้า state["frames"][frame_id]["detections"] (source="model")
  → ⚠️ RoboflowDetector._extract_predictions() (detector.py:197) ยังไม่เคยเจอ response สำเร็จจริง (ทุก test ก่อนหน้า
    เจอ 402/401 ก่อนถึง prediction จริง) — คง fallback เดิมไว้ (print raw JSON ลง server log เมื่อ parse ไม่ตรง schema)
GET  /api/detect/{job_id}              → status/progress (polling)
GET  /api/frames/{id}/preview.jpg      → cv2.imread + draw_boxes() (detector.py:149) วาดสดแล้ว stream JPEG
POST /api/detect/{job_id}/stop
ทดสอบ: run detection บน 5 เฟรมด้วย backend=local → detections ถูกเพิ่มครบ, preview.jpg มีกรอบสี
  ทดสอบ backend=roboflow แยกเมื่อมี credit ใช้งานได้จริง (ดู handoff เรื่อง Roboflow billing)
พึ่งพา: S-0, S-1, S-3, S-7
```

### S-5 | Annotation API
```
Endpoints (ไม่ต้องใช้ thread — เร็วพอที่จะตอบ sync ได้เลย):
  GET   /api/frames/{id}/detections     → state["frames"][id]["detections"]
  PUT   /api/frames/{id}/detections     → แทนที่ทั้งหมดด้วย list ใหม่จาก client (source="manual" สำหรับกล่องที่วาดเอง)
                                           validate x_center/y_center/width/height อยู่ในช่วง [0,1] ด้วย Pydantic
                                           → save_state() ทันที (annotation แก้ไม่บ่อยเท่า per-frame progress)
  PATCH /api/frames/{id}/review         → { reviewed: true|false } → save_state()
  GET   /api/frames?job_id=&reviewed=   → filter สำหรับ filmstrip
หมายเหตุ: `source: "manual"|"model"` (มีอยู่แล้วใน Detection dataclass, `detector.py:46-86`) คือตัวขับ
  เส้นทึบ/เส้นประบน canvas ตาม "✏️ Annotation Workflow" §3, และ `confidence` ยังอยู่ครบหลัง save แม้กล่องนั้น
  จะถูก accept ไปแล้ว — ทั้งสองอย่างมีอยู่แล้วใน shape เดิม ไม่ต้องเพิ่ม field ใหม่
ทดสอบ: PUT กล่องใหม่ (normalize เหมือน AnnotationTab._on_release, app.py:1219-1238) → GET กลับมาตรง,
  restart server → กล่องยังอยู่ (มาจาก state.json), PATCH reviewed=true → filmstrip badge เปลี่ยนเป็น ✅
พึ่งพา: S-0, S-1, S-3
```

### S-6 | Export API
```
POST /api/export
  body: { extract_job_id, version_name, notes,
          reviewed_only: false,                        # ใหม่ — true = export เฉพาะเฟรมที่ reviewed=true
          splits: {train:0.7, val:0.2, test:0.1},
          preprocess: {resize:true, resize_size:640},
          augment: {multiplier:3, flip:true, rotate:true, blur:true, brightness:true, crop:true} }
  → validate splits.train+val+test ≈ 1.0 ด้วย Pydantic
  → ถ้า reviewed_only=true: filter เฉพาะเฟรมที่ reviewed=true ก่อนส่งเข้า export_dataset_pipeline() (ดู
    "✏️ Annotation Workflow" §2 — ใช้ตอน export dataset รอบใหม่ที่มีทั้งเฟรมรีวิวแล้วและยังไม่รีวิวปนกัน)
  → state["export_jobs"][job_id] = {status:"running", progress:0}, threading.Thread wraps
    export_dataset_pipeline() (dataset_exporter.py:11) as_zip=True → save_state() เมื่อจบ
GET  /api/export/{job_id}              → status/progress (polling)
GET  /api/export/{job_id}/stats        → wraps count_stats() (dataset_exporter.py:196)
GET  /api/export/{job_id}/download     → stream zip file (images/labels/data.yaml)
ทดสอบ: export dataset เล็กๆ → zip ดาวน์โหลดได้ → unzip → data.yaml มี nc/names ตรงกับ CLASS_NAMES,
  สัดส่วน train/val/test ใกล้เคียงที่ตั้งไว้
พึ่งพา: S-0, S-1, S-5
```

### S-7 | Models API
```
Endpoints (ใช้เฉพาะ backend="local" ของ S-4 — โหมด Roboflow ไม่มีไฟล์โมเดลในเครื่อง):
  GET  /api/models         → scan MODEL_DIR หา .pt ทั้งหมด (client ยังพิมพ์ชื่อ pretrained เช่น yolo11n.pt ได้ ดู S-4)
  POST /api/models         → upload .pt ใหม่ (validate ตาม Security rules) → save ใต้ MODEL_DIR
ทดสอบ: วาง best.pt ใน MODEL_DIR → ปรากฏใน GET list, upload ไฟล์ใหม่ → บันทึกและ list ได้
พึ่งพา: S-0, S-1
```

### S-8 | Label Assist API (ในหน้า Annotate, ทีละเฟรม, synchronous)
```
เป้าหมาย: ให้ผู้ใช้โหลดโมเดลที่เทรนไว้เอง (เช่น "Version 1" ที่เทรนจากเฟรมกลุ่มเล็กที่ label มือไปก่อน) มาช่วย
pre-label เฟรมที่เหลือ "ทีละเฟรม" ตรงในหน้า Annotate — เทียบเท่า Label Assist ของ Roboflow แต่ทำแบบ sync
ไม่ผ่าน job/polling เพราะ inference เฟรมเดียวเร็วพอที่จะตอบใน request เดียวได้เลย (ไม่ต้องใช้ threading.Thread
เหมือน S-4 ที่เป็น batch หลายเฟรม)

Endpoint:
  POST /api/frames/{id}/assist
    body: { backend: "local"|"roboflow", conf: 0.25, iou: 0.45, device: "cpu",
            model_path,                                   # เมื่อ backend="local"
            api_key, workspace_name, workflow_id }         # เมื่อ backend="roboflow"
    → validate ผ่าน `build_detector()` ตัวเดียวกับ S-4 (ห้ามเขียน validate/construct logic ซ้ำ)
    → รัน detector.predict() กับภาพของเฟรมนี้เฟรมเดียว → return { detections: [...] } (source="model") ตรงๆ
      **ไม่บันทึกลง state/state.json เอง** — frontend เอาไปรวมกับ detections บน canvas แล้วผู้ใช้กด
      "Save Changes" (PUT /api/frames/{id}/detections ของ S-5) เป็นคนสั่ง commit จริงอีกที (จุดนี้คือ
      "accept/reject" ของ Label Assist — เก็บกล่องที่ชอบไว้ ลบกล่องที่ไม่ชอบทิ้ง ก่อน Save)
    → cache detector instance ล่าสุดไว้ใน module-level dict คีย์ด้วย (backend, model_path/workspace+workflow,
      conf, iou, device) กันโหลดโมเดลซ้ำทุกครั้งที่กด assist ต่อเนื่องหลายเฟรมด้วยโมเดลเดียวกัน (โหลด YOLO
      weight ใหม่ทุกครั้งช้าโดยไม่จำเป็น) — พารามิเตอร์เปลี่ยนเมื่อไหร่ค่อยสร้าง detector ใหม่ทับ cache
ทดสอบ: โหลด custom .pt (หรือ pretrained) → กด assist บนเฟรมที่ยังไม่มี detection ใดๆ → ได้กล่องที่โมเดลเสนอ
  กลับมาแสดงบน canvas ทันที, กด assist ซ้ำเฟรมถัดไปด้วยโมเดลเดิม → ไม่โหลดโมเดลซ้ำ (เร็วกว่าครั้งแรกชัดเจน)
พึ่งพา: S-4 (reuse `build_detector()`), S-5 (frame lookup)
```

### S-9 | Frame Thumbnail Endpoint
```
เป้าหมาย: ให้ filmstrip (F-5) โหลด thumbnail เร็วๆ โดยไม่ต้องรัน draw_boxes() บนภาพความละเอียดเต็มทุกครั้งที่
แถวเลื่อนเข้ามาในจอ (ถ้าใช้ preview.jpg ของ S-4 ซ้ำจะช้าโดยไม่จำเป็นที่สเกลหลักร้อย-พันเฟรม)

Endpoint:
  GET /api/frames/{id}/thumbnail.jpg?max=160
    → cv2.imread + resize ให้ด้านยาวสุด ≤ max px + JPEG encode → stream ตรงๆ (ไม่วาด box, ไม่ cache ฝั่ง server
      ที่สเกลนี้ไม่จำเป็น สร้างใหม่ทุก request ก็เร็วพอ)
ทดสอบ: เปิด filmstrip ที่มีเฟรมหลายร้อยรูป → thumbnail โหลดเฉพาะแถวที่เลื่อนเข้าจอ (ดู Network tab), ขนาดไฟล์
  เล็กกว่า preview.jpg เต็มความละเอียดชัดเจน
พึ่งพา: S-0, S-1, S-3 (frame lookup)
```

---

## 📋 API Endpoint Reference (สรุปทุก endpoint)

| Method | Path | Task |
|---|---|---|
| POST | `/api/login` | S-1 |
| POST | `/api/logout` | S-1 |
| GET | `/api/me` | S-1 |
| POST | `/api/videos` | S-2 |
| GET | `/api/videos` | S-2 |
| DELETE | `/api/videos/{id}` | S-2 |
| POST | `/api/extract` | S-3 |
| GET | `/api/extract/{job_id}` | S-3 |
| GET | `/api/extract/{job_id}/frames` | S-3 |
| POST | `/api/extract/{job_id}/stop` | S-3 |
| POST | `/api/detect` | S-4 |
| GET | `/api/detect/{job_id}` | S-4 |
| GET | `/api/frames/{id}/preview.jpg` | S-4 |
| POST | `/api/detect/{job_id}/stop` | S-4 |
| GET | `/api/frames/{id}/detections` | S-5 |
| PUT | `/api/frames/{id}/detections` | S-5 |
| PATCH | `/api/frames/{id}/review` | S-5 |
| GET | `/api/frames` | S-5 |
| POST | `/api/frames/{id}/assist` | S-8 |
| GET | `/api/frames/{id}/thumbnail.jpg` | S-9 |
| POST | `/api/export` | S-6 |
| GET | `/api/export/{job_id}` | S-6 |
| GET | `/api/export/{job_id}/stats` | S-6 |
| GET | `/api/export/{job_id}/download` | S-6 |
| GET | `/api/models` | S-7 |
| POST | `/api/models` | S-7 |
| GET | `/api/health` | S-0 |

---

## 🎨 FRONTEND TASKS (3 ไฟล์: `index.html`, `style.css`, `app.js`)

### F-0 | static/style.css
```
:root { /* fallback = dark, ไว้เผื่อ prefers-color-scheme ไม่รองรับ */
  --bg:#1a1a2e; --bg-panel:#16213e; --accent:#0f3460; --highlight:#e94560;
  --text:#eaeaea; --muted:#8899aa; --success:#4ecca3; --warning:#f5a623; }
@media (prefers-color-scheme: light) {
  :root:not([data-theme]) { --bg:#f5f6fa; --bg-panel:#ffffff; --accent:#e7ebf5; --highlight:#e94560;
    --text:#1a1a2e; --muted:#5c6b7a; --success:#2f9e78; --warning:#c97a00; } }
:root[data-theme="light"] { --bg:#f5f6fa; --bg-panel:#ffffff; --accent:#e7ebf5; --highlight:#e94560;
  --text:#1a1a2e; --muted:#5c6b7a; --success:#2f9e78; --warning:#c97a00; }
:root[data-theme="dark"] { --bg:#1a1a2e; --bg-panel:#16213e; --accent:#0f3460; --highlight:#e94560;
  --text:#eaeaea; --muted:#8899aa; --success:#4ecca3; --warning:#f5a623; }
(ตารางเต็มพร้อมที่มาอยู่ในหัวข้อ "🎨 Appearance / Theme System" ด้านบน)
Layout: top nav (4 tab: Extract/Detect/Annotate/Export) + เฟืองไอคอน Appearance ชิดขวา + status bar ล่างสุด
  (mirror app.py header/notebook)
Components: .btn-primary(--success) .btn-stop(--highlight) .card(--bg-panel, มุมโค้ง+border จาง+padding กว้าง
  แบบ skywork.ai) .input(ทรง pill) .progress-bar .chip(rounded-pill, ใช้กับ detection confidence chip ใน F-4)
  .theme-popover (กล่อง "Interface theme" 3 แถว, ดูหัวข้อ Appearance ด้านบน)
Landing page (ใหม่ — ดู "🏠 Landing Page Content"): .hero (พื้นหลังไล่เฉด --accent→--bg, ชื่อโครงการตัวใหญ่
  + tagline), .class-grid (5 การ์ด class-swatch สีวงกลม/สี่เหลี่ยมมนจาก CLASS_COLORS_HEX + ชื่อ + คำอธิบาย),
  .stat-card (ตัวเลข mAP@50/Precision/Recall ตัวใหญ่เด่น + label เล็กใต้ตัวเลข, เรียงเป็นแถว responsive),
  .roadmap-item (list แบบ bullet มี icon เล็กๆ) — ใช้ .card/.chip/palette เดียวกับส่วนอื่นของแอป ไม่เพิ่ม
  component ใหม่นอกเหนือจากที่จำเป็น
Log panel: .log-ok=--success .log-skip=--warning .log-blur=--muted .log-info=#58a6ff (ตรงกับ tag_config
  ใน app.py ExtractionTab._build_log())
ทดสอบ: เปิดหน้า → สีตรงตาม palette ของธีมที่ active, active tab เปลี่ยนสีถูก, สลับ 3 ธีมแล้วสีเปลี่ยนทันทีไม่ต้อง reload,
  landing page อ่านง่ายทั้ง light/dark theme (โดยเฉพาะ .hero ที่ไล่เฉดสี ต้องเช็คคอนทราสต์ข้อความทั้ง 2 ธีม)
พึ่งพา: ไม่มี
```

### F-1 | static/index.html (โครงหน้าเดียว)
```
- ใน <head> บนสุด: inline <script> อ่าน localStorage("theme_preference") แล้วตั้ง data-theme บน <html> ทันที
  ก่อน CSS render (กัน flash-of-wrong-theme) — ถ้าไม่มีค่าเก็บไว้ (default "system") ไม่ต้องตั้ง attribute อะไรเลย
  ปล่อยให้ @media (prefers-color-scheme) ใน F-0 ทำงานเอง
- Top nav: เฟืองไอคอนเปิด popover "Interface theme" — 3 แถว (Follow system settings / Dark mode / Light mode)
  พร้อมไอคอน inline-SVG (monitor/moon/sun) + เครื่องหมายเลือกอยู่ + ลิงก์ "About" เล็กๆ (เปิด landing section
  กลับมาดูได้แม้ login แล้ว)
- **Landing section (ใหม่)** — แสดงเป็นค่า default แทนฟอร์ม login เปล่าๆ เมื่อยังไม่ login (เนื้อหาเต็มอยู่ใน
  "🏠 Landing Page Content" ด้านล่าง): hero (ชื่อโครงการ+tagline) → About (ย่อหน้าอธิบายเป้าหมาย) → grid 5
  ประเภทวัตถุ (สี swatch จาก CLASS_COLORS_HEX + ชื่อ + คำอธิบาย) → stat cards ผลลัพธ์ Phase 1 (mAP@50/
  Precision/Recall/จำนวนข้อมูล) → roadmap สั้นๆ → ฟอร์ม login (password field) เป็น CTA หลักท้ายหน้า
- 4 section: #extract, #detect, #annotate, #export — สลับด้วย nav tab (JS โชว์/ซ่อน ไม่ redirect หน้า)
- โหลดหน้า → เช็ค /api/me → โชว์ landing (ถ้ายังไม่ login) หรือ app 4 step (ถ้า login แล้ว) ตามผลลัพธ์
พึ่งพา: S-1
```

### F-2 | app.js — Auth + shared fetch helper + Theme + Roboflow guard
```
apiFetch(path, opts) → fetch(path, {credentials:'include', ...opts}) → ถ้า 401 → โชว์ login section กลับ
checkAuth() ตอนโหลดหน้า, handleLogin()/handleLogout() ผูกกับฟอร์ม/ปุ่ม
Theme logic (ใหม่):
  applyTheme(pref) → ตั้ง/ลบ data-theme บน <html> ตาม "system"|"dark"|"light" แล้ว save ลง localStorage
  ผูก 3 แถวใน theme popover เข้ากับ applyTheme() + ติ๊กแถวที่ active อยู่ตอนเปิด popover
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...) → ถ้า preference ปัจจุบันเป็น
    "system" ให้ trigger CSS ให้อัปเดตสด (ไม่ต้องทำอะไรฝั่ง JS มาก เพราะ @media จัดการเองอยู่แล้ว แค่ไม่ไป
    override data-theme ทับตอน preference="system")
Roboflow cost guard (ใหม่ — shared helper ให้ F-4/F-5 เรียกใช้ ไม่ copy-paste):
  robocallCount = 0 (ตัวแปร JS ธรรมดา, reset ทุก reload หน้า) + <span> เล็กๆ แสดง "Roboflow calls: N"
    ใกล้ๆ backend selector ของ F-4/F-5 ทั้งคู่
  confirmRoboflowCall(frameCount) → window.confirm(`จะเรียก Roboflow API ${frameCount ? `กับ ${frameCount}
    เฟรม` : ""} — ยืนยันไหม? (เคยเจอ credit-cap มาก่อน)`) → คืน true/false — เรียกก่อนยิง POST /api/detect
    (backend=roboflow) หรือ POST /api/frames/{id}/assist (backend=roboflow) เท่านั้น ถ้า false ไม่ต้องยิง request
    เลย, ถ้า true ให้ robocallCount++ ก่อนยิง
ทดสอบ: เลือกแต่ละธีม → persist ข้าม reload, เลือก "Follow system" → สลับ OS theme แล้วเว็บเปลี่ยนตามสดๆ,
  กด Start/Run Assist ด้วย backend=roboflow → เห็น confirm popup ก่อนเสมอ, กด Cancel → ไม่มี request ยิงออกไป
  (เช็คจาก Network tab), กด OK → ตัวนับ "Roboflow calls" เพิ่มขึ้น 1
พึ่งพา: F-1, S-1
```

### F-3 | app.js — Extract section (mirror `ExtractionTab`)
```
- Video multi-upload (file picker) → POST /api/videos ทีละไฟล์ → แสดง list + ปุ่มลบ
- ฟอร์ม (default ตรง app.py เป๊ะ): mode radio interval/target/all (default target),
  interval_sec 0.1-60 (default 1.0), target_frames 5-2000 (default 30),
  compare_method select (default motion_iou), similarity_threshold (ปรับ default ตาม compare_method),
  filter_blur checkbox (default true) + blur_threshold (default 50.0), prefix (default "frame"),
  slot_fallback checkbox (default false) + max_attempts_per_slot (default 5), separate_per_video (default true)
- Start → POST /api/extract → เก็บ job_id → setInterval polling GET /api/extract/{job_id} ทุก 1 วิ
  แสดง log สี + progress bar จนกว่า status จะเป็น done/stopped/failed (แล้วเลิก poll)
- Stop → POST /api/extract/{job_id}/stop
- เมื่อ done → ปุ่ม "ไปที่ Step 2" → บันทึก extract_job_id ไว้ (ตัวแปร JS ธรรมดา ไม่ต้อง localStorage
  เพราะเป็นหน้าเดียวกัน) → สลับไป section #detect
ทดสอบ: extract วิดีโอสั้นจริง 1 ไฟล์ ทั้ง 3 mode ต้องได้ผลลัพธ์เฟรมเหมือนรันผ่าน app.py เดิม
พึ่งพา: F-1, F-2, S-2, S-3
```

### F-4 | app.js — Detect section (mirror `DetectionTab`, รองรับ Roboflow)
```
- Backend radio: Local (.pt) / Roboflow Cloud API (default Local) — สลับ field group ด้วย show/hide
  (mirror app.py DetectionTab._on_backend_change(), app.py:612-644)
  - Local: model select (GET /api/models) + ปุ่มอัพโหลดโมเดลใหม่, Device radio cpu/cuda/mps (default cpu),
    IoU slider (0.01-0.99 default 0.45)
  - Roboflow: 3 ช่อง API Key (type=password) / Workspace / Workflow ID
    ⚠️ ไม่เก็บ API Key ใน localStorage — ส่งแนบไปกับ POST /api/detect ตรงๆ ทุกครั้งที่ Start เท่านั้น
- Confidence slider (0.01-0.99 default 0.25) — ใช้ทั้งสอง backend
- แสดงจำนวนเฟรมจาก extract_job_id ที่เลือกไว้
- Start → ถ้า backend=roboflow: เรียก `confirmRoboflowCall(frameCount)` (F-2) ก่อนเสมอ ถ้าไม่ยืนยันให้หยุด
  ไม่ยิง request → POST /api/detect (แนบ backend + field ที่เกี่ยวข้อง) → polling เหมือน F-3
- Preview: <img src="/api/frames/{id}/preview.jpg"> + ปุ่ม ◄ Prev / Next ►
- Detection chips: จุดสีตาม CLASS_COLORS_HEX + class + confidence, confidence<0.5 → พื้นแดงเข้ม
  (mirror app.py:922-947 has_low_conf logic)
- เมื่อ done → ปุ่ม "ไปที่ Step 3" → สลับไป section #annotate
ทดสอบ: รัน detection บนเฟรมจริง 10 ภาพ (backend=local) → preview กรอบถูกสี, chip confidence ต่ำ highlight ถูก
พึ่งพา: F-1, F-2, S-4, S-7
```

### F-7 | app.js — Annotation Canvas Engine (generic, ไม่ผูกกับ endpoint ไหนเป็นพิเศษ)
```
ทำ Tool abstraction + Canvas engine ตาม "✏️ Annotation Workflow" §4 ทั้งหมด — build/ทดสอบแยกจาก F-5 ได้ก่อน
เพราะพึ่งพาแค่ F-1/F-2 (ไม่ต้องมี S-8/S-9 พร้อมก็เริ่มได้):
  - Canvas: pan/zoom, coordinate transform (image↔screen), render loop ผ่าน requestAnimationFrame + dirty flag
  - Tool registry: { select: SelectTool, draw_box: DrawBoxTool } พร้อม interface มาตรฐาน
    (onPointerDown/Move/Up, onKeyDown?, render, onActivate/Deactivate?)
  - SelectTool: hit-test กล่อง, ลากย้าย, ลาก resize handle 8 จุด
  - DrawBoxTool: click-drag สร้างกล่องใหม่ (normalize เหมือน app.py:1219-1238), ค้างโหมดวาดจนกด Esc/สลับ tool
  - UndoManager: JSON snapshot ของ array detections ทั้งชุด, cap ~50
  - Keyboard: listener เดียว + lookup table เดียว (ปิดทำงานถ้า focus อยู่ที่ text input) — ชุด shortcut ตาม
    "✏️ Annotation Workflow" §3
  - Client-side box id: crypto.randomUUID() (fallback เป็น counter ถ้าไม่มี) ใช้ hit-test บน canvas เท่านั้น
    ไม่ส่งไป backend
ทดสอบ: วาดกล่องใหม่ 3 กล่องต่อเนื่องไม่ต้องสลับ tool, ลากย้าย/resize กล่องที่มีอยู่, Undo/Redo ย้อนกลับถูกต้อง,
  ปุ่ม 1-5 เปลี่ยน class ของกล่องที่เลือกอยู่, พิมพ์ในช่อง text input แล้ว shortcut ไม่ทำงาน
พึ่งพา: F-1, F-2
```

### F-5 | app.js — Annotate section (ต่อยอดจาก F-7, mirror `AnnotationTab` + Label Assist)
```
เชื่อม F-7 (canvas engine) เข้ากับ DOM จริงของหน้า Annotate:
- Filmstrip ซ้าย: รายชื่อเฟรม (thumbnail จาก S-9, lazy-load ผ่าน IntersectionObserver) + badge
  🔴 ต้องรีวิว / ✅ รีวิวแล้ว / 🏷 มี AI suggestion ที่ยังไม่ confirm + dropdown filter (All/Needs Review/Reviewed)
- Canvas กลาง (จาก F-7): โหลดภาพ → draw boxes จาก GET /api/frames/{id}/detections — กล่อง `source="model"`
  ที่ยังไม่ถูกแก้วาดเป็น **เส้นประ** พร้อม confidence badge (แดงถ้า <0.5, mirror app.py:922-947), กล่อง
  manual/accepted วาดเส้นทึบตามปกติ (pixel bbox จาก normalized coords แบบเดียวกับ app.py:1192-1199)
- Toolbar ลอย (pill, 2 ปุ่ม): Select / Draw — ผูกกับ F-7's tool registry
- Class dropdown (CLASS_NAMES) + ปุ่มเลข 1-5 (จาก F-7's Keyboard) กำหนด/เปลี่ยน class
- Property panel ขวา: list detections (class dropdown ในบรรทัด + confidence badge + คลิกแถวไฮไลต์กล่องบน
  canvas), ปุ่ม Accept All / Reject All (จัดการกล่อง source="model" ทั้งหมดในเฟรมทีเดียว)
- ปุ่ม "Copy from previous frame" — ดึง GET /api/frames/{prev_id}/detections มาเป็นจุดเริ่มต้นของเฟรมนี้
- 🏷️ **Label Assist**: ช่องเลือก backend+model แบบย่อ (reuse markup เดียวกับ F-4 ผ่านฟังก์ชันร่วม ไม่ copy-paste,
  พับเก็บได้) + ปุ่ม "Run Assist on this frame" → ถ้า backend=roboflow: เรียก `confirmRoboflowCall()` (F-2,
  ไม่ต้องส่ง frameCount เพราะเป็นเฟรมเดียว) ก่อนเสมอ ถ้าไม่ยืนยันให้หยุด → POST /api/frames/{id}/assist → เอา
  detections ที่ได้กลับมา **เพิ่มต่อท้าย** ลิสต์ปัจจุบันบน canvas (วาดเป็นเส้นประ) แล้วปล่อยให้ผู้ใช้ลบ/แก้/
  Accept-Reject-All ก่อน Save เอง (นี่คือขั้น accept/reject ของ Label Assist) — จำค่า backend/model ที่เลือกไว้
  ในตัวแปร JS ข้ามเฟรม
- ปุ่มหลัก **"Save & Next →"** → PUT /api/frames/{id}/detections แล้ว PATCH reviewed=true แล้วเลื่อนไปเฟรม
  unreviewed ถัดไปอัตโนมัติ (รวม 3 action เดิมเป็นคลิกเดียว/ปุ่ม Enter เดียว)
- ปุ่มรอง: Save (ไม่เปลี่ยนเฟรม) · Mark as Reviewed แยก · Clear All Boxes (PUT [] แล้ว redraw)
- Status bar: เฟรม N/Total · จำนวนกล่อง (กี่กล่องเป็น AI suggestion) · ความคืบหน้ารีวิวรวม
ทดสอบ: วาดกล่องใหม่ → Save & Next → reload หน้าเว็บทั้งหน้า → กล่องยังอยู่ตรงเดิม (มาจาก state.json ไม่ใช่แค่
  memory JS) และเลื่อนไปเฟรม unreviewed ถัดไปจริง · กด Label Assist บนเฟรมว่าง → กล่องเส้นประขึ้นบน canvas ทันที
  → Reject All ลบทิ้งหมด หรือแก้บางกล่องแล้ว Save → GET กลับมาตรงตามที่แก้
พึ่งพา: F-7, F-1, F-2, S-5, S-8, S-9
```

### F-6 | app.js — Export section (mirror `ExportTab`)
```
- Version name / notes text input
- Stats จาก GET /api/export/{job_id}/stats: Source Images, Classes, Unannotated/Needs Review
- Slider Train% (50-90 default 70) / Val% (0-40 default 20) → Test% คำนวณอัตโนมัติ (auto-adjust ถ้า
  train+val > 100, mirror app.py:1387-1391)
- Checkbox Resize (default true, 640x640)
- Checkbox Augmentation Flip/Rotate/Brightness/Blur/Crop (ทั้งหมด default true) + Multiplier slider (1-10 default 3)
- Label "Maximum Version Size" คำนวณฝั่ง client เหมือน app.py:1394-1407
- Create Version → POST /api/export → polling เหมือน F-3
- เมื่อเสร็จ → ปุ่ม Download (ลิงก์ GET .../download)
ทดสอบ: export dataset จริง → ตัวเลข "Maximum Version Size" ตรงกับจำนวนไฟล์ในภาพหลัง unzip จริง
พึ่งพา: F-1, F-2, S-6
```

---

## 📊 ลำดับ Dependencies ที่สำคัญ

```
S-0 → S-1 (auth) ← ต้องก่อนทุก endpoint อื่น
S-1 → S-2 (videos) → S-3 (extract) → F-3
S-3 → S-4 (detect, ต้องมี S-7 models ด้วย) → F-4
S-4 → S-8 (label assist, reuse build_detector() จาก S-4)
S-3 → S-9 (thumbnail, พึ่งพาแค่ frame lookup)
S-3 → S-5 (annotate) → F-5 (ต้องมี F-7 + S-8 + S-9 ด้วย)
S-5 → S-6 (export)  → F-6

F-1 (index.html) → F-2 (auth/fetch helper) → F-3, F-4, F-6 (ทำแยกอิสระได้หลัง F-2 เสร็จ)
F-1, F-2 → F-7 (canvas engine, สร้าง/ทดสอบแยกได้ก่อน ไม่ต้องรอ S-8/S-9) → F-5 (ต่อยอดจาก F-7)
```

---

## 🎯 MVP Launch Checklist

### Backend (S-0 → S-9, 10 tasks)
- ⬜ S-0 Project setup + app skeleton + state.json load/save
- ⬜ S-1 Auth (session token + rate limit)
- ⬜ S-2 Videos API
- ⬜ S-3 Extraction API (wraps `extract_frames()`)
- ⬜ S-4 Detection API (wraps `YOLOv11Detector` + `RoboflowDetector`, exposes shared `build_detector()`,
  `skip_reviewed` guard)
- ⬜ S-5 Annotation API
- ⬜ S-6 Export API (wraps `export_dataset_pipeline()`, `reviewed_only` filter)
- ⬜ S-7 Models API
- ⬜ S-8 Label Assist API (single-frame sync, reuses `build_detector()`)
- ⬜ S-9 Frame Thumbnail Endpoint

### Frontend (F-0 → F-7, 3 ไฟล์)
- ⬜ F-0 style.css · F-1 index.html · F-2 auth/fetch helper
- ⬜ F-3 Extract section · F-4 Detect section (+ Roboflow) · F-7 Annotation Canvas Engine ·
  F-5 Annotate section (+ Label Assist, ต่อยอดจาก F-7) · F-6 Export section

---

## ❓ จุดที่ต้องตัดสินใจก่อนเริ่ม S-0 (ห้ามเดาเอง — ถามก่อนลงมือ)

1. ~~**GPU cloud provider**~~ — **ตัดสินใจแล้ว (30 ก.ค. 2026): ไม่เช่า GPU cloud** เอาแบบธรรมดา/ง่ายที่สุดพอ
   → deploy บน CPU-only hosting ทั่วไป (Railway/Fly.io/Render หรือ local) เหตุผล: งานส่วนใหญ่ของเว็บแอป
   (extract/annotate/export) ไม่ได้ประโยชน์จาก GPU เลย ส่วน bulk detect ที่สเกลหลักร้อยเฟรมก็ยังอยู่ในระดับไม่กี่
   นาทีบน CPU ซึ่งเป็น background job อยู่แล้ว ไม่บล็อกงานอื่น — ถ้าจะเทรนโมเดลรอบใหม่ (v1→v2→v3) ที่ได้ประโยชน์
   จาก GPU จริงๆ แนะนำเช่า GPU แค่ชั่วคราวตอนเทรน (เช่น Google Colab หรือเช่า RunPod/Vast.ai เป็นชั่วโมง) แล้ว
   upload ไฟล์ `.pt` ที่ได้กลับเข้าเว็บผ่าน Models API (S-7) เดิม — แยกเรื่อง "โฮสต์เว็บแอป" กับ "compute สำหรับ
   เทรน" ออกจากกัน ประหยัดกว่าเช่า GPU ค้างไว้ทั้งตัว 24 ชม. มาก เมื่อ deploy จริงจึงไม่ต้องกังวลเรื่อง HTTPS/
   reverse-proxy ของ raw GPU rental (RunPod/Lambda/Vast.ai) อีกต่อไป — provider CPU-only ทั่วไปส่วนใหญ่มี HTTPS
   ให้อัตโนมัติอยู่แล้วเหมือน Render/Vercel
2. **ขนาด/ความยาวสูงสุดของวิดีโอที่อัพโหลดได้** — ไฟล์ผ่าตัดมักไฟล์ใหญ่ (หลาย GB) — multipart POST ก้อนเดียวไม่มี
   resume ถ้าอัพโหลดหลุดกลางทางต้องเริ่มใหม่ทั้งไฟล์ (ยอมรับได้ไหมสำหรับตอนนี้ หรือต้องพิจารณา resumable upload)
3. **นโยบายเก็บ/ลบข้อมูล และความอ่อนไหวของข้อมูล** — เก็บวิดีโอ/เฟรม/dataset ไว้ถาวรหรือลบอัตโนมัติ (พื้นที่ disk cloud
   จำกัด) วิดีโอเป็นภาพขั้นตอนผ่าตัด (finger/forcep/needle/wound) — แม้ไม่มีข้อมูลระบุตัวผู้ป่วยในเฟรม ก็ควรถามว่ามี
   ข้อกำหนดด้านความเป็นส่วนตัว/compliance ที่ต้องทำตามหรือไม่ ก่อนเลือก storage/retention จริง (ไม่ได้สันนิษฐานว่า
   ต้องทำตาม HIPAA หรือมาตรฐานใดๆ เพราะไม่ทราบบริบทใช้งานจริง) — ส่วน `state.json` (metadata การรีวิว/detections)
   มี backup mechanism แล้ว (ดู "💾 Backup ของ state.json") แต่นี่คือคำถามเรื่องไฟล์วิดีโอ/เฟรม/dataset ตัวจริงที่
   ยังไม่มีนโยบายเก็บ/ลบอัตโนมัติ ยังต้องตัดสินใจแยกกัน
4. **โดเมนที่จะ deploy** — มีโดเมนอยู่แล้วหรือต้องจดใหม่/ใช้ subdomain (ยังไม่ต้องตัดสินใจตอนนี้ก็ได้ — และตอนนี้
   ง่ายขึ้นกว่าเดิมเพราะเลือก CPU-only hosting แล้ว provider กลุ่มนี้ส่วนใหญ่ให้ HTTPS + subdomain ฟรีมาให้เลย
   ไม่ต้องตั้ง reverse proxy/Let's Encrypt เองแบบที่ raw GPU rental ต้องทำ)

---

## 📋 Backlog หลัง MVP

### WF-1: Live Verifier ผ่าน Browser
> ย้าย `LiveVerifierTab` (เดิมใช้ `cv2.VideoCapture` ในเครื่อง) มาใช้ browser camera (`getUserMedia`) → ส่งเฟรมผ่าน HTTP/polling เดิมไปให้ backend รัน `predict()` → ส่ง detection กลับมาวาดบน `<canvas>` ฝั่ง client + checklist UI เดิม (ครบ instrument ✅ / ไม่ครบ ❌ / ซ้ำ ⚠️ mirror app.py:993-1020)

### WF-2: Gesture-Triggered Auto-Capture (Hand-Readiness → Countdown → Record)
> ต่อยอดจาก WF-1 — เช็คว่ามือผู้ใช้ "พร้อม" ในเฟรมหรือไม่ ถ้าพร้อม → นับถอยหลัง → เริ่มอัด/เก็บข้อมูลอัตโนมัติ
1. **Readiness check**: แนะนำ **MediaPipe Hands** (รันฝั่ง browser, ไม่ต้องเรียก backend, latency ต่ำ) ตรวจ landmark มือ 21 จุด → กำหนดเงื่อนไข "พร้อม" แบบ geometric (มืออยู่ในกรอบที่กำหนด + ท่านิ่งค้าง N วินาที) — ไม่ต้อง train โมเดลใหม่สำหรับขั้นนี้
2. **Countdown → Auto-record → Auto-save**: เมื่อ readiness ผ่านเงื่อนไขค้างต่อเนื่อง (เช่น 1.5s) → countdown 3-2-1 บนจอ → เริ่มอัด (`MediaRecorder` API หรือส่งเฟรมต่อเนื่องไป backend) → auto-stop เมื่อมือออกจากกรอบหรือครบเวลา → ผลลัพธ์เข้าสู่ pipeline เดิมอัตโนมัติ (Extract → pre-label ด้วยโมเดลปัจจุบัน → คิว Annotation ให้รีวิว)

### WF-3: สร้างโมเดล Gesture-Command Detection
> เมื่อเก็บข้อมูลท่ามือจาก WF-2 ได้มากพอ มี 2 แนวทาง:
- **แนวทาง A (แนะนำเริ่มก่อน) — ขยาย YOLO pipeline เดิม**: เพิ่ม class ท่ามือใหม่ใน `CLASS_NAMES` (`detector.py:39` เช่น `gesture_start`, `gesture_stop`) → label ผ่าน Annotation tool (F-5) → train ตาม pipeline เดิมทั้งหมด (Extract→Detect→Annotate→Export→train) — reuse ของเดิม 100% ไม่ต้องเขียนโค้ดใหม่ ข้อเสีย: ต้องเก็บ/label หลายร้อยภาพต่อท่าทางถึงแม่น
- **แนวทาง B — MediaPipe Hands + Landmark Classifier**: สกัด landmark 21 จุด/มือ → เก็บ vector พิกัดพร้อม label ท่าทาง → เทรน classifier เบา (RandomForest/small MLP) แยกจาก YOLO — เทรนเร็ว ใช้ข้อมูลน้อยกว่า แม่นเรื่อง pose กว่า แต่ต้องเขียน exporter ใหม่ (ไม่ reuse `dataset_exporter.py` ได้ตรงๆ)
- เริ่มจากแนวทาง A ก่อนเสมอ แล้วค่อยประเมินย้ายไป B ถ้าความแม่นยำไม่พอหลังทดลองจริง

### WF-4: Import Legacy Desktop Data
> POST /api/import/legacy — multipart zip ของโฟลเดอร์ที่มาจาก app.py เดิม (เฟรมที่สกัดไว้ หรือ dataset ที่ export แล้ว)
> validate zip-slip ก่อน extract → เฟรมปรากฏใน Annotation/Export ได้ทันทีโดยไม่ต้องสกัดซ้ำ (ย้ายจาก MVP มา backlog
> เพราะเป็นฟีเจอร์ช่วยย้ายข้อมูล ไม่ใช่ 1 ใน 4 ขั้นตอนหลักของ pipeline)

### WF-5: Automated Testing + Structured Logging
> ตอนนี้ทดสอบด้วยมือทุก task (curl/browser) เท่านั้น — พอสำหรับ MVP แต่ถ้าแอปนี้ขึ้น online ใช้กับวิดีโอจริงต่อเนื่อง ควรมี:
- **pytest smoke tests** ต่อกลุ่ม endpoint (S-1 ถึง S-7) — อย่างน้อย happy-path + 1 validation-error case,
  ใช้ FastAPI `TestClient`
- **Structured logging** แทนที่จะมีแค่ `GET /api/health` — อย่างน้อย log job failures พร้อม job_id

### WF-6: อื่นๆ (ถ้าโตเกิน single-user)
> multi-user auth, DB จริงถ้า state.json ใหญ่เกินจะโหลด/เขียนทุกครั้งไหว, Postgres/Redis job queue สำหรับ concurrency สูง, resumable jobs, S3/R2 offload สำหรับไฟล์ใหญ่, cleanup job ลบข้อมูลเก่าอัตโนมัติ, Docker + reverse-proxy/HTTPS ตอน deploy จริง (ดูข้อ 1 ในหัวข้อ "จุดที่ต้องตัดสินใจ")

---

## 📊 Progress Dashboard

| ชุดงาน | เลข | สถานะ |
|---|---|---|
| Backend | S-0 ถึง S-9 | ⬜ ยังไม่เริ่ม (10 งาน) |
| Frontend | F-0 ถึง F-7 | ⬜ ยังไม่เริ่ม (3 ไฟล์ / 8 ส่วน) |
| Live Verifier (browser) | WF-1 | ⬜ backlog |
| Gesture Auto-Capture | WF-2 | ⬜ backlog (รอ WF-1) |
| Gesture-Command Model | WF-3 | ⬜ backlog (รอ WF-2) |
| Import Legacy Data | WF-4 | ⬜ backlog |
| Automated Testing + Logging | WF-5 | ⬜ backlog |

---

*WORK_PLAN.md | VideoFrameExtractor Web — สร้าง 2026-07-17, เขียนใหม่ 2026-07-29*
*Path: `C:\Users\USER\OneDrive\Documents\BEAM\VideoFrameExtractor\` | อ้างอิงสไตล์: `D:\OPEN DONATE\WORK_PLAN.md`*
*MVP: S-0→9 (Backend, 10 งาน) + F-0→7 (Frontend, 3 ไฟล์ / 8 ส่วน) — ยังไม่เริ่ม*
*หลักการ: FastAPI+Uvicorn เท่านั้น ไม่มี DB/ORM/JWT/WebSocket/Docker/rate-limit library — ใช้ stdlib +
in-memory dict + JSON snapshot + threading.Thread + HTTP polling แทนทั้งหมด*
*Annotation: AI-assisted loop เต็มรูปแบบ (bbox tools + undo/redo + Label Assist + Save&Next) ดู "✏️ Annotation
Workflow & Tool Design" — ยังอยู่ในกรอบ minimal-tool เดิม ไม่มี dependency ใหม่แม้แต่ตัวเดียว*
*Backlog: WF-1→6 (Live Verifier + Gesture capture/model + Import legacy + Testing/Logging + multi-user/scale)*
