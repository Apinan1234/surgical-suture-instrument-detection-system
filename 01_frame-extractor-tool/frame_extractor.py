"""
Frame Extractor with Similarity Filter
=======================================
ตัดเฟรมจากวิดีโอ พร้อมระบบกรองภาพซ้ำ/คล้ายกันเกินไป
ใช้ Perceptual Hashing (pHash) เปรียบเทียบความคล้ายของภาพ

Libraries: opencv-python, imagehash, Pillow, numpy, tqdm
"""

import cv2
import os
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import imagehash
import numpy as np
from datetime import datetime
from tqdm import tqdm


# ─────────────────────────────────────────────
#  Core Logic
# ─────────────────────────────────────────────

def compute_phash(frame_bgr: np.ndarray, hash_size: int = 16) -> imagehash.ImageHash:
    """แปลง OpenCV frame (BGR) → pHash"""
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(frame_rgb)
    return imagehash.phash(pil_img, hash_size=hash_size)


def is_blurry(frame_bgr: np.ndarray, threshold: float = 50.0) -> bool:
    """ตรวจสอบว่าภาพเบลอเกินไปไหม (Laplacian variance)"""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var() < threshold


def resize_to_max_side(frame_bgr: np.ndarray, max_px: int) -> np.ndarray:
    """ย่อภาพให้ด้านยาวสุด <= max_px (คงสัดส่วนเดิม, ไม่ขยายถ้าภาพเล็กกว่าอยู่แล้ว)"""
    h, w = frame_bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_px:
        return frame_bgr
    scale = max_px / longest
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return cv2.resize(frame_bgr, new_size, interpolation=cv2.INTER_AREA)


def extract_frames(
    video_path: str,
    output_folder: str,
    interval_sec: float = 1.0,
    compare_method: str = "motion_iou",
    similarity_threshold: float = 30.0,
    blur_threshold: float = 50.0,
    filter_blur: bool = True,
    max_attempts_per_slot: int = 5,    # ลิมิตการลองต่อ 1 slot (ป้องกัน scan นาน)
    prefix: str = "frame",
    start_sec: float = 0.0,
    end_sec: float | None = None,
    resize_max_px: int | None = None,
    start_index: int = 0,
    log_name: str = "extraction_log.json",
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    ตัดเฟรมจากวิดีโอพร้อมกรองภาพซ้ำ

    Parameters
    ----------
    video_path          : path ของไฟล์วิดีโอ
    output_folder       : folder สำหรับบันทึกภาพ
    interval_sec        : ตัดทุกกี่วินาที
    similarity_threshold: ระยะ Hamming ต่ำสุดที่ถือว่า "แตกต่างกันพอ"
                          (0 = เหมือนกันทุกพิกเซล, สูง = ยอมรับภาพคล้ายกันมากขึ้น)
    blur_threshold      : ค่า Laplacian variance ต่ำสุด (ต่ำกว่านี้ = เบลอ)
    filter_blur         : True = กรองภาพเบลอออก
    prefix              : prefix ชื่อไฟล์ภาพ
    start_sec           : เริ่มตัดจากวินาทีที่เท่าไหร่ (0 = ตั้งแต่ต้นวิดีโอ)
    end_sec             : ตัดถึงวินาทีที่เท่าไหร่ (None = จนจบวิดีโอ)
    resize_max_px       : ย่อภาพที่บันทึกให้ด้านยาวสุด <= ค่านี้ (None = ขนาดต้นฉบับ)
    start_index         : เลขลำดับเริ่มต้นของชื่อไฟล์ (0 = เริ่มที่ _00000)
                          ใช้ตอนสกัดหลายวิดีโอลงโฟลเดอร์เดียวกัน เพื่อไม่ให้เลขซ้ำแล้วเขียนทับกัน
    log_name            : ชื่อไฟล์ log ที่เขียนลง output_folder
                          (เปลี่ยนได้เมื่อหลายวิดีโอใช้โฟลเดอร์ร่วมกัน จะได้ไม่ทับกัน)
    progress_callback   : fn(current, total) สำหรับ update progress bar
    log_callback        : fn(str) สำหรับ print log

    Returns
    -------
    dict with stats
    """

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    os.makedirs(output_folder, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"ไม่สามารถเปิดวิดีโอได้: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames_full = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec_full = total_frames_full / fps if fps > 0 else 0

    start_frame = max(0, int(round(start_sec * fps))) if fps > 0 else 0
    end_frame = total_frames_full
    if end_sec is not None and fps > 0:
        end_frame = min(total_frames_full, int(round(end_sec * fps)))
    total_frames = max(0, end_frame - start_frame)
    duration_sec = total_frames / fps if fps > 0 else 0
    frame_step = max(1, int(fps * interval_sec))

    log(f"📹 วิดีโอ: {os.path.basename(video_path)}")
    log(f"   FPS: {fps:.1f} | เฟรมทั้งหมด: {total_frames_full} | ความยาว: {duration_sec_full:.1f} วิ")
    if start_sec > 0 or end_sec is not None:
        log(f"   ตัดช่วง: {start_sec:.1f}s – {(f'{end_sec:.1f}s' if end_sec is not None else 'จบวิดีโอ')}")
    log(f"   ตัดทุก {interval_sec:.2f} วิ | วิธี: {compare_method} | threshold: {similarity_threshold}")
    log("─" * 55)

    if total_frames <= 0:
        log(f"⚠️  start_sec ({start_sec:.1f}s) อยู่เกินความยาววิดีโอ ({duration_sec_full:.1f}s) — ข้ามวิดีโอนี้")
        cap.release()
        stats = {
            "video": os.path.basename(video_path),
            "compare_method": compare_method,
            "total_frames_checked": 0,
            "saved": 0,
            "skipped_similar": 0,
            "skipped_blurry": 0,
            "output_folder": output_folder,
            "similarity_log": [],
        }
        return stats

    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    # ── Comparison structures ──────────────────────────────
    saved_repr = []   # stores hash / frame / fg_mask per method
    bg_gray   = None  # static background for motion_iou

    def get_fg_mask(frame_bgr: np.ndarray) -> np.ndarray:
        """ตัดพื้นหลังออก เหลือแค่ mask ของส่วนที่เคลื่อนไหว (มือ+อุปกรณ์)"""
        nonlocal bg_gray
        gray    = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)
        if bg_gray is None:          # เฟรมแรก = พื้นหลัง reference
            bg_gray = blurred
            return np.zeros_like(blurred)
        diff = cv2.absdiff(bg_gray, blurred)
        _, mask = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
        kernel = np.ones((15, 15), np.uint8)
        return cv2.dilate(mask, kernel, iterations=2)

    def diff_score(frame_bgr: np.ndarray, fg_mask: np.ndarray) -> float:
        """
        คืนค่า "ความต่าง" เทียบกับทุกภาพที่บันทึกไว้
        ค่าสูง = แตกต่างมาก | ค่าต่ำ = คล้ายกัน
        """
        if not saved_repr or compare_method == "none":
            return 999.0   # none = บันทึกทุกเฟรมโดยไม่กรอง

        if compare_method == "phash":
            h = compute_phash(frame_bgr)
            return float(min(h - r for r in saved_repr))

        elif compare_method == "frame_diff":
            scores = []
            for r in saved_repr:
                d = cv2.absdiff(frame_bgr, r)
                scores.append(cv2.cvtColor(d, cv2.COLOR_BGR2GRAY).mean())
            return float(min(scores))   # pixel diff 0-255

        else:  # motion_iou
            if fg_mask.sum() == 0:
                # ไม่ตรวจพบการเคลื่อนไหว → fallback เปรียบเทียบด้วย frame_diff
                scores = []
                for saved_frame, _ in saved_repr:
                    d = cv2.absdiff(frame_bgr, saved_frame)
                    scores.append(cv2.cvtColor(d, cv2.COLOR_BGR2GRAY).mean())
                return float(min(scores)) if scores else 0.0

            scores = []
            for saved_frame, saved_mask in saved_repr:
                if saved_mask.sum() == 0:
                    # saved mask ว่าง (เฟรมแรก) → ถือว่าต่างกัน
                    scores.append(100.0)
                    continue
                inter = float(cv2.bitwise_and(fg_mask, saved_mask).sum())
                union = float(cv2.bitwise_or(fg_mask, saved_mask).sum())
                iou   = inter / (union + 1e-6)
                scores.append((1.0 - iou) * 100)
            return float(min(scores))

    def save_repr(frame_bgr: np.ndarray, fg_mask: np.ndarray):
        if compare_method == "none":
            # diff_score() คืน 999.0 ทันทีในโหมดนี้ ไม่เคยอ่าน saved_repr เลย
            # ถ้าเก็บต่อไปจะกินหน่วยความจำทุกเฟรมโดยไม่ได้ใช้ (โหมด "ทุกเฟรม" กระทบหนักสุด)
            return
        if compare_method == "phash":
            saved_repr.append(compute_phash(frame_bgr))
        elif compare_method == "frame_diff":
            saved_repr.append(frame_bgr.copy())
        else:  # motion_iou — เก็บทั้ง frame และ mask
            saved_repr.append((frame_bgr.copy(), fg_mask.copy() if fg_mask is not None else np.zeros((1,), dtype=np.uint8)))

    # ── Main extraction loop ───────────────────────────────
    stats = {
        "video": os.path.basename(video_path),
        "compare_method": compare_method,
        "total_frames_checked": 0,
        "saved": 0,
        "skipped_similar": 0,
        "skipped_blurry": 0,
        "output_folder": output_folder,
        "similarity_log": [],
    }

    # ── Main extraction loop (Slot-based fallback) ───────────
    # แต่ละ "slot" = ช่วงเวลา frame_step เฟรม
    # ถ้าเฟรมแรกใน slot ไม่ผ่าน → ลองเฟรมถัดไปใน slot เดียวกัน
    # จนกว่าจะบันทึกได้ หรือหมด slot
    frame_idx    = 0
    current_slot = -1
    slot_filled  = False
    slot_attempts = 0   # จำนวนครั้งที่ลองใน slot ปัจจุบัน

    while True:
        if frame_idx >= total_frames:
            break
        ret, frame = cap.read()
        if not ret:
            break

        slot = frame_idx // frame_step

        # ขึ้น slot ใหม่ → reset
        if slot != current_slot:
            if not slot_filled and slot_attempts >= max_attempts_per_slot:
                log(f"  [warn]   slot {current_slot} → ไม่พบเฟรมที่ใช้ได้ใน {slot_attempts} ครั้ง")
            current_slot  = slot
            slot_filled   = False
            slot_attempts = 0
            if progress_callback:
                progress_callback(frame_idx, total_frames)

        # slot นี้บันทึกแล้ว หรือลองครบลิมิตแล้ว → ข้ามไป slot ถัดไป
        if slot_filled or slot_attempts >= max_attempts_per_slot:
            frame_idx += 1
            continue

        stats["total_frames_checked"] += 1
        slot_attempts += 1   # นับจำนวนครั้งที่ลองใน slot นี้

        # ── กรองเบลอ → ลองเฟรมถัดไปใน slot เดียวกัน ──
        if filter_blur and is_blurry(frame, blur_threshold):
            stats["skipped_blurry"] += 1
            log(f"  [blur]   เฟรม {frame_idx:5d} (slot {slot}) → เบลอ, ลอง frame ถัดไป")
            frame_idx += 1
            continue

        # ── เปรียบเทียบความคล้าย ──
        fg = get_fg_mask(frame) if compare_method == "motion_iou" else None
        score = diff_score(frame, fg)
        is_diff_enough = score >= similarity_threshold

        stats["similarity_log"].append({
            "frame_idx": frame_idx,
            "slot": slot,
            "score": round(score, 2),
            "saved": is_diff_enough,
        })

        if not is_diff_enough:
            stats["skipped_similar"] += 1
            log(f"  [skip]   เฟรม {frame_idx:5d} (slot {slot}) → คล้าย (score={score:.1f}), ลอง frame ถัดไป")
        else:
            filename  = f"{os.path.basename(prefix)}_{start_index + stats['saved']:05d}.jpg"
            save_path = os.path.join(output_folder, filename)
            save_frame = resize_to_max_side(frame, resize_max_px) if resize_max_px else frame
            cv2.imwrite(save_path, save_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            save_repr(frame, fg)
            stats["saved"] += 1
            slot_filled = True
            log(f"  [saved]  เฟรม {frame_idx:5d} (slot {slot}) → {filename} (score={score:.1f})")

        frame_idx += 1

    cap.release()

    log_path = os.path.join(output_folder, log_name)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    log("─" * 55)
    log(f"เสร็จสิ้น! บันทึก {stats['saved']} ภาพ | ข้าม(คล้าย) {stats['skipped_similar']} | ข้าม(เบลอ) {stats['skipped_blurry']}")
    log(f"Log: {log_path}")
    return stats


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────

DARK_BG      = "#1a1a2e"
PANEL_BG     = "#16213e"
ACCENT       = "#0f3460"
HIGHLIGHT    = "#e94560"
TEXT_COLOR   = "#eaeaea"
MUTED        = "#8899aa"
SUCCESS      = "#4ecca3"
WARNING      = "#f5a623"
FONT_HEAD    = ("Segoe UI", 13, "bold")
FONT_BODY    = ("Segoe UI", 10)
FONT_MONO    = ("Consolas", 9)


class FrameExtractorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Frame Extractor  |  Similarity Filter")
        self.geometry("960x720")
        self.configure(bg=DARK_BG)
        self.resizable(True, True)
        self.minsize(800, 600)
        # เปิดแบบ minimized ทันทีที่รัน
        self.after(0, lambda: self.state("iconic"))

        self._video_paths: list[str] = []
        self._output_folder: str = ""
        self._running = False
        self._thread: threading.Thread | None = None

        self._build_ui()

    # ── Layout ──────────────────────────────
    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=HIGHLIGHT, height=50)
        header.pack(fill="x")
        tk.Label(
            header, text="🎬  Frame Extractor  +  Similarity Filter",
            font=("Segoe UI", 14, "bold"), bg=HIGHLIGHT, fg="white", pady=12
        ).pack()

        main = tk.Frame(self, bg=DARK_BG)
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # Left column — scrollable controls
        left_outer = tk.Frame(main, bg=PANEL_BG, width=340)
        left_outer.pack(side="left", fill="y", padx=(0, 10))
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, bg=PANEL_BG, bd=0,
                                highlightthickness=0, width=320)
        left_scroll = ttk.Scrollbar(left_outer, orient="vertical",
                                    command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)

        left = tk.Frame(left_canvas, bg=PANEL_BG)
        _win = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _on_frame_resize(e):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        def _on_canvas_resize(e):
            left_canvas.itemconfig(_win, width=e.width)
        def _on_mousewheel(e):
            left_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        left.bind("<Configure>", _on_frame_resize)
        left_canvas.bind("<Configure>", _on_canvas_resize)
        left_canvas.bind("<Enter>",
            lambda e: left_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        left_canvas.bind("<Leave>",
            lambda e: left_canvas.unbind_all("<MouseWheel>"))

        # Right column — log
        right = tk.Frame(main, bg=DARK_BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_controls(left)
        self._build_log(right)
        self._build_statusbar()

    def _section(self, parent, title):
        frame = tk.LabelFrame(
            parent, text=f"  {title}  ",
            font=FONT_HEAD, bg=PANEL_BG, fg=SUCCESS,
            bd=1, relief="groove", padx=12, pady=8,
            labelanchor="nw"
        )
        frame.pack(fill="x", pady=(0, 10))
        return frame

    def _row(self, parent, label, widget_fn, **kw):
        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=FONT_BODY, bg=PANEL_BG,
                 fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        widget_fn(row, **kw)
        return row

    def _build_controls(self, parent):
        # ไม่ lock width ที่นี่ เพราะ Canvas จัดการขนาดแทนแล้ว

        # ── ไฟล์วิดีโอ ──
        sec1 = self._section(parent, "📂 ไฟล์วิดีโอ")

        self._video_listbox = tk.Listbox(
            sec1, font=FONT_MONO, bg=ACCENT, fg=TEXT_COLOR,
            selectbackground=HIGHLIGHT, height=4, bd=0
        )
        self._video_listbox.pack(fill="x", pady=(0, 6))

        btn_row = tk.Frame(sec1, bg=PANEL_BG)
        btn_row.pack(fill="x")
        self._btn(btn_row, "➕ เพิ่มวิดีโอ", self._add_videos, SUCCESS).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "🗑️ ลบที่เลือก", self._remove_video, MUTED).pack(side="left")

        # ── Output ──
        sec2 = self._section(parent, "📁 โฟลเดอร์ Output")
        out_row = tk.Frame(sec2, bg=PANEL_BG)
        out_row.pack(fill="x")
        self._out_var = tk.StringVar(value="กดเลือกโฟลเดอร์...")
        tk.Label(out_row, textvariable=self._out_var, font=FONT_MONO,
                 bg=DARK_BG, fg=MUTED, anchor="w", padx=6,
                 relief="flat").pack(side="left", fill="x", expand=True)
        self._btn(out_row, "📂", self._choose_output, ACCENT).pack(side="right")

        # ── Parameters ──
        sec3 = self._section(parent, "⚙️ ตั้งค่า")

        # ── Mode selector ──
        tk.Label(sec3, text="โหมดตัดเฟรม", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x", pady=(0, 2))
        mode_frame = tk.Frame(sec3, bg=PANEL_BG)
        mode_frame.pack(fill="x", pady=(0, 6))
        self._mode_var = tk.StringVar(value="target")
        tk.Radiobutton(
            mode_frame, text="Fixed Interval", variable=self._mode_var,
            value="interval", bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
            activebackground=PANEL_BG, font=FONT_BODY,
            command=self._toggle_mode
        ).pack(side="left", padx=(0, 12))
        tk.Radiobutton(
            mode_frame, text="Adaptive (Target)", variable=self._mode_var,
            value="target", bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
            activebackground=PANEL_BG, font=FONT_BODY,
            command=self._toggle_mode
        ).pack(side="left")

        # ── Mode-specific container ──
        # ใช้ container เพื่อให้การสลับ row มั่นคง ไม่หายไปไหน
        self._mode_container = tk.Frame(sec3, bg=PANEL_BG)
        self._mode_container.pack(fill="x")

        # Interval row (Fixed mode)
        self._interval_var = tk.DoubleVar(value=1.0)
        self._interval_row = tk.Frame(self._mode_container, bg=PANEL_BG)
        tk.Label(self._interval_row, text="ตัดทุกกี่วินาที", font=FONT_BODY, bg=PANEL_BG,
                 fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        self._spin(self._interval_row, var=self._interval_var, from_=0.1, to=60.0,
                   inc=0.5, fmt="%.1f")

        # Target frame count row (Adaptive mode)
        self._target_var = tk.IntVar(value=30)
        self._target_row = tk.Frame(self._mode_container, bg=PANEL_BG)
        tk.Label(self._target_row, text="เป้าหมายภาพ/วิดีโอ", font=FONT_BODY, bg=PANEL_BG,
                 fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        self._spin(self._target_row, var=self._target_var, from_=5, to=1000,
                   inc=5, fmt="%.0f")
        tk.Label(self._target_row, text="ภาพ", font=("Segoe UI", 8),
                 bg=PANEL_BG, fg=MUTED).pack(side="left", padx=(4, 0))

        # เริ่มต้นที่ Adaptive mode
        self._target_row.pack(fill="x", pady=3)
        self._interval_row.pack_forget()

        # ── Compare Method ──
        cmp_frame = tk.Frame(sec3, bg=PANEL_BG)
        cmp_frame.pack(fill="x", pady=(6, 0))
        tk.Label(cmp_frame, text="วิธีเปรียบเทียบภาพ", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        self._cmp_var = tk.StringVar(value="motion_iou")
        cmp_menu = ttk.Combobox(
            cmp_frame, textvariable=self._cmp_var, width=14,
            values=["none", "motion_iou", "frame_diff", "phash"],
            state="readonly", font=FONT_MONO
        )
        cmp_menu.pack(side="left")
        cmp_menu.bind("<<ComboboxSelected>>", self._on_cmp_change)

        self._cmp_hint = tk.Label(sec3, text="Motion IoU: วิเคราะห์ตำแหน่งมือ+อุปกรณ์ (ดีที่สุดสำหรับพื้นหลังนิ่ง)",
                                  font=("Segoe UI", 8), bg=PANEL_BG, fg=WARNING,
                                  wraplength=280, justify="left")
        self._cmp_hint.pack(anchor="w", pady=(2, 4))

        # Similarity threshold
        self._sim_var = tk.DoubleVar(value=30.0)
        self._sim_label_var = tk.StringVar(value="Min diff (0-100)")
        sim_row = tk.Frame(sec3, bg=PANEL_BG)
        sim_row.pack(fill="x", pady=3)
        self._sim_label_widget = tk.Label(sim_row, textvariable=self._sim_label_var,
                                          font=FONT_BODY, bg=PANEL_BG, fg=TEXT_COLOR,
                                          width=22, anchor="w")
        self._sim_label_widget.pack(side="left")
        self._spin(sim_row, var=self._sim_var, from_=0.1, to=256, inc=1, fmt="%.1f")
        tk.Label(sim_row, text="(ยิ่งสูง ยิ่งเข้มงวด)", font=("Segoe UI", 8),
                 bg=PANEL_BG, fg=MUTED).pack(side="left", padx=4)

        # Blur threshold
        self._blur_en_var = tk.BooleanVar(value=True)
        self._blur_var = tk.DoubleVar(value=50.0)
        blur_check = tk.Checkbutton(
            sec3, text="กรองภาพเบลอ (Laplacian)", variable=self._blur_en_var,
            bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
            activebackground=PANEL_BG, font=FONT_BODY,
            command=self._toggle_blur
        )
        blur_check.pack(anchor="w", pady=(4, 0))
        self._blur_row = self._row(sec3, "  Blur threshold", self._spin,
                                   var=self._blur_var, from_=1, to=500, inc=10, fmt="%.0f")

        # Prefix
        self._prefix_var = tk.StringVar(value="frame")
        self._row(sec3, "Prefix ชื่อไฟล์", self._entry, var=self._prefix_var)

        # ── Slot Fallback ──
        self._slot_en_var = tk.BooleanVar(value=False)  # default: ไม่จำกัด
        self._slot_var    = tk.IntVar(value=5)
        tk.Checkbutton(
            sec3, text="จำกัด Max Attempts/Slot",
            variable=self._slot_en_var,
            bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
            activebackground=PANEL_BG, font=FONT_BODY,
            command=self._toggle_slot_fallback
        ).pack(anchor="w", pady=(6, 0))
        self._slot_row = self._row(sec3, "  Max attempts/slot", self._spin,
                                   var=self._slot_var, from_=1, to=30, inc=1, fmt="%.0f")
        # default: disabled (ไม่จำกัด)
        for child in self._slot_row.winfo_children():
            try:
                child.configure(state="disabled")
            except tk.TclError:
                pass

        # Separator per video
        self._sep_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            sec3, text="แยกโฟลเดอร์ตามวิดีโอ", variable=self._sep_var,
            bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
            activebackground=PANEL_BG, font=FONT_BODY
        ).pack(anchor="w", pady=(6, 0))

        # ── Start / Stop ──
        btn_frame = tk.Frame(parent, bg=PANEL_BG)
        btn_frame.pack(fill="x", pady=8)
        self._start_btn = self._btn(btn_frame, "▶  เริ่มทำงาน", self._start, SUCCESS)
        self._start_btn.pack(fill="x", ipady=6, pady=(0, 4))
        self._stop_btn = self._btn(btn_frame, "⏹  หยุด", self._stop, HIGHLIGHT)
        self._stop_btn.pack(fill="x", ipady=6)
        self._stop_btn.configure(state="disabled")

        # ── Progress ──
        prog_sec = self._section(parent, "📊 Progress")
        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(
            prog_sec, variable=self._progress_var,
            maximum=100, mode="determinate", length=280
        )
        self._progress_bar.pack(fill="x", pady=(0, 4))
        self._prog_label = tk.Label(prog_sec, text="รอเริ่มต้น...",
                                    font=FONT_MONO, bg=PANEL_BG, fg=MUTED)
        self._prog_label.pack()

    def _build_log(self, parent):
        tk.Label(parent, text="📋 Log", font=FONT_HEAD,
                 bg=DARK_BG, fg=SUCCESS).pack(anchor="w", pady=(0, 4))

        log_frame = tk.Frame(parent, bg=DARK_BG)
        log_frame.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            log_frame, font=FONT_MONO, bg="#0d1117", fg="#c9d1d9",
            insertbackground="white", bd=0, wrap="none",
            state="disabled"
        )
        self._log_text.pack(side="left", fill="both", expand=True)

        scroll_y = ttk.Scrollbar(log_frame, orient="vertical",
                                  command=self._log_text.yview)
        scroll_y.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=scroll_y.set)

        # Color tags
        self._log_text.tag_config("ok",      foreground=SUCCESS)
        self._log_text.tag_config("skip",    foreground=WARNING)
        self._log_text.tag_config("blur",    foreground=MUTED)
        self._log_text.tag_config("info",    foreground="#58a6ff")
        self._log_text.tag_config("divider", foreground=ACCENT)
        self._log_text.tag_config("bold",    font=("Consolas", 9, "bold"))

        btn_clear = self._btn(parent, "🗑️ ล้าง Log", self._clear_log, MUTED)
        btn_clear.pack(anchor="e", pady=(6, 0))

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=ACCENT, height=26)
        bar.pack(fill="x", side="bottom")
        self._status_var = tk.StringVar(value="พร้อมใช้งาน")
        tk.Label(bar, textvariable=self._status_var, font=("Segoe UI", 9),
                 bg=ACCENT, fg=TEXT_COLOR, anchor="w", padx=10).pack(fill="x")

    # ── Widget helpers ───────────────────────
    def _btn(self, parent, text, cmd, color):
        return tk.Button(
            parent, text=text, command=cmd,
            font=FONT_BODY, bg=color, fg="white",
            relief="flat", cursor="hand2",
            activebackground=HIGHLIGHT, activeforeground="white",
            padx=10, pady=4
        )

    def _spin(self, parent, var, from_, to, inc, fmt):
        sv = tk.Spinbox(
            parent, textvariable=var, from_=from_, to=to,
            increment=inc, format=fmt,
            font=FONT_MONO, bg=ACCENT, fg=TEXT_COLOR,
            insertbackground="white", bd=0, width=8,
            buttonbackground=ACCENT
        )
        sv.pack(side="left")

    def _entry(self, parent, var):
        tk.Entry(parent, textvariable=var, font=FONT_MONO,
                 bg=ACCENT, fg=TEXT_COLOR, insertbackground="white",
                 bd=0, width=14).pack(side="left")

    # ── Actions ─────────────────────────────
    def _add_videos(self):
        paths = filedialog.askopenfilenames(
            title="เลือกไฟล์วิดีโอ",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.MOV *.MP4"),
                       ("All files", "*.*")]
        )
        for p in paths:
            if p not in self._video_paths:
                self._video_paths.append(p)
                self._video_listbox.insert("end", os.path.basename(p))

    def _remove_video(self):
        sel = self._video_listbox.curselection()
        for i in reversed(sel):
            self._video_listbox.delete(i)
            self._video_paths.pop(i)

    def _choose_output(self):
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์ Output")
        if folder:
            self._output_folder = folder
            self._out_var.set(folder)

    def _on_cmp_change(self, _event=None):
        method = self._cmp_var.get()
        hints = {
            "none":       ("N/A (ไม่กรอง)",          0.0,  "None: ตัดเฟรมทุกตัวโดยไม่เปรียบเทียบ เหมาะสำหรับคัดด้วยตาเอง"),
            "motion_iou": ("Min diff % (0-100)",     30.0, "Motion IoU: วิเคราะห์ตำแหน่งมือ+อุปกรณ์ (ดีที่สุดสำหรับพื้นหลังนิ่ง)"),
            "frame_diff": ("Pixel diff (0-255)",     10.0, "Frame Diff: เทียบความต่างพิกเซลโดยตรง"),
            "phash":      ("Hamming dist (0-256)",    8.0, "pHash: เปรียบเทียบโครงสร้างภาพรวม"),
        }
        label, default, hint = hints.get(method, hints["motion_iou"])
        self._sim_label_var.set(label)
        self._sim_var.set(default)
        self._cmp_hint.configure(text=hint)

    def _toggle_mode(self):
        """สลับหน้าจอกลุ่มตั้งค่าตามโหมดที่เลือก"""
        if self._mode_var.get() == "interval":
            self._target_row.pack_forget()
            self._interval_row.pack(fill="x", pady=3)
        else:
            self._interval_row.pack_forget()
            self._target_row.pack(fill="x", pady=3)

    def _toggle_slot_fallback(self):
        state = "normal" if self._slot_en_var.get() else "disabled"
        for child in self._slot_row.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass

    def _toggle_blur(self):
        state = "normal" if self._blur_en_var.get() else "disabled"
        for child in self._blur_row.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass

    # ── Log helpers ─────────────────────────
    def _log(self, msg: str):
        self._log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")

        tag = "info"
        if "✅" in msg:
            tag = "ok"
        elif "🔁" in msg:
            tag = "skip"
        elif "🌫️" in msg or "เบลอ" in msg:
            tag = "blur"
        elif "─" in msg:
            tag = "divider"
        elif "🎉" in msg or "เสร็จ" in msg:
            tag = "bold"

        line = f"[{timestamp}] {msg}\n"
        self._log_text.insert("end", line, tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ── Start / Stop ────────────────────────
    def _start(self):
        if not self._video_paths:
            messagebox.showwarning("ขาดข้อมูล", "กรุณาเพิ่มไฟล์วิดีโออย่างน้อย 1 ไฟล์")
            return
        if not self._output_folder:
            messagebox.showwarning("ขาดข้อมูล", "กรุณาเลือกโฟลเดอร์ Output")
            return

        self._running = True
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._status_var.set("กำลังทำงาน...")

        self._thread = threading.Thread(target=self._run_extraction, daemon=True)
        self._thread.start()

    def _stop(self):
        self._running = False
        self._log("⏹  ผู้ใช้หยุดการทำงาน")
        self._status_var.set("หยุดโดยผู้ใช้")

    def _run_extraction(self):
        total_saved = 0
        total_skip_sim = 0
        total_skip_blur = 0

        for video_path in self._video_paths:
            if not self._running:
                break

            # กำหนด output folder
            if self._sep_var.get():
                vname = os.path.splitext(os.path.basename(video_path))[0]
                out = os.path.join(self._output_folder, vname)
            else:
                out = self._output_folder

            try:
                # ── คำนวณ interval ──
                if self._mode_var.get() == "target":
                    # Adaptive: คำนวณ interval จากความยาววิดีโอ
                    _cap = cv2.VideoCapture(video_path)
                    _fps = _cap.get(cv2.CAP_PROP_FPS)
                    _frames = int(_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    _cap.release()
                    _duration = _frames / _fps if _fps > 0 else 60.0
                    _target = max(1, self._target_var.get())
                    interval_sec = max(0.1, _duration / _target)
                    self.after(0, self._log,
                        f"  [Adaptive] {os.path.basename(video_path)}: "
                        f"{_duration:.1f}s / {_target} = interval {interval_sec:.2f}s")
                else:
                    interval_sec = self._interval_var.get()

                # Progress callback
                def prog_cb(cur, total, vp=video_path):
                    if total > 0:
                        pct = (cur / total) * 100
                        self._progress_var.set(pct)
                        self._prog_label.configure(
                            text=f"{os.path.basename(vp)}  {pct:.1f}%"
                        )

                stats = extract_frames(
                    video_path=video_path,
                    output_folder=out,
                    interval_sec=interval_sec,
                    compare_method=self._cmp_var.get(),
                    similarity_threshold=self._sim_var.get(),
                    blur_threshold=self._blur_var.get(),
                    filter_blur=self._blur_en_var.get(),
                    max_attempts_per_slot=(
                        int(self._slot_var.get()) if self._slot_en_var.get() else 999999
                        # ☑ จำกัด N ครั้ง  |  ☐ ไม่จำกัด (ตามหาเฟรมที่ดีไปเรื่อยๆ)
                    ),
                    prefix=self._prefix_var.get(),
                    progress_callback=prog_cb,
                    log_callback=lambda m: self.after(0, self._log, m),
                )

                if not self._running:
                    break

                total_saved      += stats["saved"]
                total_skip_sim   += stats["skipped_similar"]
                total_skip_blur  += stats["skipped_blurry"]

            except Exception as e:
                self.after(0, self._log, f"❌ Error: {e}")

        # Done
        summary = (
            f"─" * 50 + "\n"
            f"🎉 เสร็จทั้งหมด!\n"
            f"   ✅ บันทึก:        {total_saved} ภาพ\n"
            f"   🔁 ข้าม (คล้าย): {total_skip_sim} ภาพ\n"
            f"   🌫️  ข้าม (เบลอ):  {total_skip_blur} ภาพ"
        )
        self.after(0, self._log, summary)
        self.after(0, self._finish_ui)

    def _finish_ui(self):
        self._running = False
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._progress_var.set(100)
        self._prog_label.configure(text="เสร็จสิ้น ✅")
        self._status_var.set("เสร็จสิ้น")
        messagebox.showinfo("เสร็จสิ้น", "ตัดเฟรมเสร็จเรียบร้อยแล้ว!\nดู Log สำหรับรายละเอียด")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = FrameExtractorApp()

    # Style progress bar
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=ACCENT, background=SUCCESS,
        thickness=12
    )

    app.mainloop()
