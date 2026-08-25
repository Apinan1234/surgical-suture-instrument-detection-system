"""
Gradio-flavor comparison mockup for rare-class-labeler.

Purpose: let the user SEE what the same 3-action flow (upload -> auto-process ->
pick classes -> download) looks like when built with real Gradio components and a
Gradio theme pushed as close to the HTML mockup's teal/clinical palette as
Gradio's CSS hooks reasonably allow -- for a fair side-by-side against
mockup/index.html (the free HTML/CSS/JS version), not a "default unthemed Gradio"
strawman.

Throwaway comparison artifact only, same as mockup/index.html -- not part of any
approved implementation phase. Launched via yolo_wv_custom's existing venv
(already has gradio installed) purely to avoid installing a second ~GB torch/
gradio stack for a disposable demo; this script and its content live entirely in
rare-class-labeler, nothing here depends on yolo_wv_custom's own code.
"""
import os
import time

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
from PIL import Image, ImageDraw

# Real ssid9 class order, same counts/rare-class framing as mockup/index.html,
# so the two mockups are content-identical and only the shell differs.
CLASSES = [
    ("Stitch Scissors", 39, "#5C8A8F"),
    ("Tip_forcep", 60, "#8A7A4C"),
    ("Tip_needle_holder", 44, "#6B7A3E"),
    ("finger", 128, "#3E7CB1"),
    ("forcep", 94, "#4C8C6B"),
    ("hand", 142, "#3E6B7A"),
    ("needle", 6, "#BE6229"),
    ("needle_holder", 71, "#7A6BB0"),
    ("wound", 53, "#B14B62"),
]

WIN_VIDEO = r"C:\Users\USER\OneDrive\Documents\BEAM\VideoFrameExtractor\02_web-app\WIN_20260525_14_47_12_Pro_muted.mp4"


def make_swatch(name: str, color_hex: str) -> Image.Image:
    img = Image.new("RGB", (320, 240), color_hex)
    draw = ImageDraw.Draw(img)
    draw.text((14, 14), name, fill="white")
    return img


SWATCHES = {name: make_swatch(name, color) for name, _count, color in CLASSES}

ACCENT = "#0E7C6B"
RARE_BG = "#FBEBDC"
RARE_INK = "#7A3F16"

CSS = f"""
.gradio-container {{
    max-width: 900px !important;
    margin: 0 auto !important;
    font-family: 'IBM Plex Sans Thai', 'IBM Plex Sans', system-ui, sans-serif !important;
}}
#masthead {{ margin-bottom: 4px; }}
#masthead h1 {{ margin-bottom: 2px !important; }}
.rare-badge {{
    display: inline-block;
    color: {RARE_INK};
    background: {RARE_BG};
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    margin-left: 6px;
}}
.gr-button-primary, button.primary {{
    background: {ACCENT} !important;
    border-color: {ACCENT} !important;
}}
"""

theme = gr.themes.Soft(primary_hue=gr.themes.colors.emerald, neutral_hue=gr.themes.colors.gray)


def process(video_path, progress=gr.Progress()):
    if video_path is None:
        return None, gr.update(visible=False), ""
    stages = [
        (0.08, "กำลังโหลดโมเดล ssid9 อัตโนมัติ..."),
        (0.25, "อ่านวิดีโอ — สุ่มเฟรมตาม interval..."),
        (0.45, "กำลังตรวจจับวัตถุ... (จำลอง)"),
        (0.70, "กำลังตรวจจับวัตถุ... (จำลอง)"),
        (0.90, "กำลังประกอบวิดีโอผลลัพธ์ (H.264)..."),
        (1.00, "เสร็จสิ้น"),
    ]
    for frac, msg in stages:
        progress(frac, desc=msg)
        time.sleep(0.35)
    return video_path, gr.update(visible=True), ""


def do_download(*checkbox_values):
    names = [CLASSES[i][0] for i, v in enumerate(checkbox_values) if v]
    if not names:
        return "เลือกอย่างน้อย 1 คลาสก่อนดาวน์โหลด"
    return f"(จำลอง) จะดาวน์โหลด `rare_class_export.zip` — {len(names)} คลาส: {', '.join(names)} — พร้อม `PARTIAL_LABELS.md`"


with gr.Blocks(title="Rare Class Labeler (Gradio mockup)") as demo:
    gr.Markdown(
        "# 🧵 Rare Class Labeler\n"
        "อัปโหลดวิดีโอ ระบบจัดการที่เหลือให้อัตโนมัติ — **(เวอร์ชัน Gradio เพื่อเปรียบเทียบ ไม่ใช่ของจริง)**",
        elem_id="masthead",
    )
    gr.Markdown(
        "หน้านี้เป็น mockup เปรียบเทียบเท่านั้น — สร้างด้วย Gradio ล้วน ๆ (ไม่ปรับแต่งเกินกว่าที่ Gradio "
        "เปิดให้ทำผ่าน theme/CSS) เพื่อให้เห็นว่าถ้าเลือกสร้างเว็บจริงด้วย Gradio หน้าตาและการโต้ตอบจะเป็น"
        "แบบไหน เทียบกับ `mockup/index.html` ที่ออกแบบอิสระ"
    )

    video_in = gr.Video(label="1. อัปโหลดวิดีโอ")
    video_out = gr.Video(label="วิดีโอผลลัพธ์ (จำลอง — ยังไม่ใช่กรอบตรวจจับจริง)", visible=False)

    with gr.Group(visible=False) as results_group:
        gr.Markdown(
            "### 2. เลือกคลาสที่จะเก็บไว้ทำ dataset\n"
            "จำนวนเป็นค่าจำลอง — สังเกตว่า `needle` "
            f"<span class='rare-badge'>คลาสหายาก</span> เจอน้อยกว่าคลาสอื่นมาก"
        )
        checkboxes = []
        with gr.Row():
            for name, count, _color in CLASSES:
                with gr.Column(min_width=140):
                    gr.Image(value=SWATCHES[name], show_label=False, height=90, interactive=False)
                    label = f"{name} ({count} เฟรม)"
                    cb = gr.Checkbox(value=True, label=label)
                    checkboxes.append(cb)

        gr.Markdown("### 3. ดาวน์โหลด")
        download_btn = gr.Button("ดาวน์โหลดชุดข้อมูล (.zip)", variant="primary")
        download_msg = gr.Markdown()

    video_in.upload(process, inputs=[video_in], outputs=[video_out, results_group, download_msg])
    download_btn.click(do_download, inputs=checkboxes, outputs=download_msg)

    gr.Examples(examples=[[WIN_VIDEO]], inputs=[video_in], label="ตัวอย่างเริ่มต้นด่วน (ไฟล์จริงในเครื่อง)")

    gr.Markdown(
        "---\n"
        "*ประวัติการใช้งาน (History) ในเวอร์ชัน Gradio นี้ไม่ได้ทำ interactive เต็มรูปแบบ "
        "(ต้องใช้ `gr.Dataframe.select()` เพิ่มเติม) — ข้ามไว้ในเดโมเปรียบเทียบนี้เพื่อโฟกัสที่หน้าตา/"
        "การจัดวางองค์ประกอบหลักแทน*"
    )

demo.queue().launch(css=CSS, theme=theme)
