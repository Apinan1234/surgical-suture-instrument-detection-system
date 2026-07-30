"""
YOLOv11 Auto-Labeling Pipeline
================================
GUI 3 ขั้นตอนสำหรับสร้าง YOLO Dataset จากวิดีโอ:

  Step 1 · Extract Frames  — สกัดเฟรมจากวิดีโอ (reuse frame_extractor.py)
  Step 2 · Detection       — รัน YOLOv11 ใส่ BBox + Preview แบบ real-time
  Step 3 · Export Dataset  — สร้าง images/ labels/ data.yaml พร้อม train ทันที

Classes  : finger | forcep | needle | needle_holder | wound
Framework: Ultralytics YOLO v11
"""
from __future__ import annotations

import cv2
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from PIL import Image, ImageTk
import numpy as np

from frame_extractor import extract_frames
from detector import (
    YOLOv11Detector, RoboflowDetector, Detection,
    CLASS_NAMES, CLASS_COLORS_HEX, _DEFAULT_HEX,
)
from dataset_exporter import export_dataset_pipeline, count_stats


# ═══════════════════════════════════════════════════
#  Theme
# ═══════════════════════════════════════════════════
DARK_BG    = "#1a1a2e"
PANEL_BG   = "#16213e"
ACCENT     = "#0f3460"
HIGHLIGHT  = "#e94560"
TEXT_COLOR = "#eaeaea"
MUTED      = "#8899aa"
SUCCESS    = "#4ecca3"
WARNING    = "#f5a623"
FONT_HEAD  = ("Segoe UI", 13, "bold")
FONT_BODY  = ("Segoe UI", 10)
FONT_MONO  = ("Consolas",  9)
FONT_SM    = ("Segoe UI",  8)

PREVIEW_MAX_W = 620
PREVIEW_MAX_H = 430


# ═══════════════════════════════════════════════════
#  Shared widget helpers
# ═══════════════════════════════════════════════════
def btn(parent, text, cmd, color, **kw):
    return tk.Button(
        parent, text=text, command=cmd,
        font=FONT_BODY, bg=color, fg="white",
        relief="flat", cursor="hand2",
        activebackground=HIGHLIGHT, activeforeground="white",
        padx=10, pady=4, **kw,
    )

def spin(parent, var, from_, to, inc, fmt):
    sv = tk.Spinbox(
        parent, textvariable=var,
        from_=from_, to=to, increment=inc, format=fmt,
        font=FONT_MONO, bg=ACCENT, fg=TEXT_COLOR,
        insertbackground="white", bd=0, width=8,
        buttonbackground=ACCENT,
    )
    sv.pack(side="left")
    return sv

def section(parent, title):
    f = tk.LabelFrame(
        parent, text=f"  {title}  ",
        font=FONT_HEAD, bg=PANEL_BG, fg=SUCCESS,
        bd=1, relief="groove", padx=12, pady=8, labelanchor="nw",
    )
    f.pack(fill="x", pady=(0, 10))
    return f

def lbl_row(parent, label_text, width=22):
    row = tk.Frame(parent, bg=PANEL_BG)
    row.pack(fill="x", pady=3)
    tk.Label(row, text=label_text, font=FONT_BODY, bg=PANEL_BG,
             fg=TEXT_COLOR, width=width, anchor="w").pack(side="left")
    return row


# ═══════════════════════════════════════════════════
#  Main Application
# ═══════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YOLOv11 Auto-Labeling Pipeline  |  Surgical Instrument Detection")
        self.geometry("1180x800")
        self.minsize(960, 660)
        self.configure(bg=DARK_BG)

        # ── Shared state ─────────────────────────
        self.extracted_frames:  list[str]  = []   # paths จาก Tab 1
        self.detection_results: list[dict] = []   # results จาก Tab 2

        self._build_ui()

    # ─────────────────────────────────────────────
    def _build_ui(self):
        # Header bar
        hdr = tk.Frame(self, bg=HIGHLIGHT, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="🔬  YOLOv11 Auto-Labeling Pipeline  ·  Surgical Instrument Detection",
            font=("Segoe UI", 14, "bold"), bg=HIGHLIGHT, fg="white",
        ).pack(expand=True)

        # Notebook style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",      background=DARK_BG,   borderwidth=0)
        style.configure("TNotebook.Tab",  background=ACCENT,    foreground=TEXT_COLOR,
                        padding=[18, 8],  font=FONT_BODY)
        style.map("TNotebook.Tab",
                  background=[("selected", HIGHLIGHT)],
                  foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar",
                        troughcolor=ACCENT, background=SUCCESS, thickness=14)
        style.configure("TFrame", background=DARK_BG)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(6, 0))

        self.tab_extract = ExtractionTab(self.nb, app=self)
        self.tab_detect  = DetectionTab(self.nb,  app=self)
        self.tab_export  = ExportTab(self.nb,     app=self)
        self.tab_live    = LiveVerifierTab(self.nb, app=self)
        self.tab_annot   = AnnotationTab(self.nb, app=self)

        self.nb.add(self.tab_extract, text="  📂  Step 1 · Extract Frames  ")
        self.nb.add(self.tab_detect,  text="  🔍  Step 2 · Detection  ")
        self.nb.add(self.tab_annot,   text="  ✏️  Step 3 · Annotation  ")
        self.nb.add(self.tab_export,  text="  📦  Step 4 · Export Dataset  ")
        self.nb.add(self.tab_live,    text="  📷  Live Verifier  ")

        # Status bar
        bar = tk.Frame(self, bg=ACCENT, height=26)
        bar.pack(fill="x", side="bottom")
        self._status_var = tk.StringVar(value="พร้อมใช้งาน")
        tk.Label(bar, textvariable=self._status_var, font=("Segoe UI", 9),
                 bg=ACCENT, fg=TEXT_COLOR, anchor="w", padx=10).pack(fill="x")

    def set_status(self, msg: str):
        self._status_var.set(msg)

    def go_to_tab(self, idx: int):
        self.nb.select(idx)


# ═══════════════════════════════════════════════════
#  Tab 1 — Frame Extraction
#  (Port + Refactor จาก FrameExtractorApp)
# ═══════════════════════════════════════════════════
class ExtractionTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self._video_paths:   list[str] = []
        self._output_folder: str       = ""
        self._running = False
        self._thread:  threading.Thread | None = None
        self._build_ui()

    # ─────────────────────────────────────────────
    def _build_ui(self):
        root = tk.Frame(self, bg=DARK_BG)
        root.pack(fill="both", expand=True, padx=12, pady=10)

        # Left: scrollable controls
        lo = tk.Frame(root, bg=PANEL_BG, width=350)
        lo.pack(side="left", fill="y", padx=(0, 10))
        lo.pack_propagate(False)

        lc = tk.Canvas(lo, bg=PANEL_BG, bd=0, highlightthickness=0, width=330)
        ls = ttk.Scrollbar(lo, orient="vertical", command=lc.yview)
        lc.configure(yscrollcommand=ls.set)
        ls.pack(side="right", fill="y")
        lc.pack(side="left", fill="both", expand=True)

        left = tk.Frame(lc, bg=PANEL_BG)
        wid  = lc.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: lc.configure(scrollregion=lc.bbox("all")))
        lc.bind("<Configure>",   lambda e: lc.itemconfig(wid, width=e.width))
        lc.bind("<Enter>",  lambda e: lc.bind_all(
            "<MouseWheel>", lambda ev: lc.yview_scroll(int(-1*(ev.delta/120)), "units")))
        lc.bind("<Leave>",  lambda e: lc.unbind_all("<MouseWheel>"))

        # Right: log
        right = tk.Frame(root, bg=DARK_BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_controls(left)
        self._build_log(right)

    def _build_controls(self, p):
        # ── Video files ──────────────────────────
        sv = section(p, "📂 ไฟล์วิดีโอ")
        self._video_listbox = tk.Listbox(
            sv, font=FONT_MONO, bg=ACCENT, fg=TEXT_COLOR,
            selectbackground=HIGHLIGHT, height=4, bd=0,
        )
        self._video_listbox.pack(fill="x", pady=(0, 6))
        br = tk.Frame(sv, bg=PANEL_BG)
        br.pack(fill="x")
        btn(br, "➕ เพิ่มวิดีโอ", self._add_videos,  SUCCESS).pack(side="left", padx=(0,6))
        btn(br, "🗑️ ลบที่เลือก",  self._remove_video, MUTED).pack(side="left")

        # ── Output folder ────────────────────────
        so = section(p, "📁 โฟลเดอร์ Output")
        or_ = tk.Frame(so, bg=PANEL_BG); or_.pack(fill="x")
        self._out_var = tk.StringVar(value="กดเลือกโฟลเดอร์...")
        tk.Label(or_, textvariable=self._out_var, font=FONT_MONO,
                 bg=DARK_BG, fg=MUTED, anchor="w", padx=6).pack(side="left", fill="x", expand=True)
        btn(or_, "📂", self._choose_output, ACCENT).pack(side="right")

        # ── Parameters ───────────────────────────
        sp = section(p, "⚙️ ตั้งค่า")

        # Mode
        tk.Label(sp, text="โหมดตัดเฟรม", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x", pady=(0,2))
        mf = tk.Frame(sp, bg=PANEL_BG); mf.pack(fill="x", pady=(0,6))
        self._mode_var = tk.StringVar(value="target")
        for v, txt in [("interval","Fixed Interval"),("target","Adaptive (Target)"),("all","ทุกเฟรม (All Frames)")]:
            tk.Radiobutton(mf, text=txt, variable=self._mode_var, value=v,
                           bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
                           activebackground=PANEL_BG, font=FONT_BODY, anchor="w",
                           command=self._toggle_mode).pack(side="top", fill="x")

        mc = tk.Frame(sp, bg=PANEL_BG); mc.pack(fill="x")

        # Interval row
        self._interval_var = tk.DoubleVar(value=1.0)
        self._interval_row = tk.Frame(mc, bg=PANEL_BG)
        tk.Label(self._interval_row, text="ตัดทุกกี่วินาที", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        spin(self._interval_row, self._interval_var, 0.1, 60.0, 0.5, "%.1f")

        # Target row
        self._target_var = tk.IntVar(value=30)
        self._target_row = tk.Frame(mc, bg=PANEL_BG)
        tk.Label(self._target_row, text="เป้าหมายภาพ/วิดีโอ", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        spin(self._target_row, self._target_var, 5, 2000, 5, "%.0f")
        tk.Label(self._target_row, text="ภาพ", font=FONT_SM,
                 bg=PANEL_BG, fg=MUTED).pack(side="left", padx=4)
        self._target_row.pack(fill="x", pady=3)

        # All-frames info row
        self._all_info_row = tk.Frame(mc, bg=PANEL_BG)
        tk.Label(self._all_info_row,
                 text="จะตัดทุกเฟรมจากวิดีโอ (ไม่กรองภาพซ้ำ/เบลอ — ได้ทุกเฟรมเต็มจำนวน)",
                 font=FONT_SM, bg=PANEL_BG, fg=WARNING,
                 wraplength=290, justify="left").pack(anchor="w")

        # Compare method
        cf = tk.Frame(sp, bg=PANEL_BG); cf.pack(fill="x", pady=(6,0))
        self._cmp_label = tk.Label(cf, text="วิธีเปรียบเทียบภาพ", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w")
        self._cmp_label.pack(side="left")
        self._cmp_var = tk.StringVar(value="motion_iou")
        cbox = ttk.Combobox(cf, textvariable=self._cmp_var, width=14,
                            values=["none","motion_iou","frame_diff","phash"],
                            state="readonly", font=FONT_MONO)
        cbox.pack(side="left")
        cbox.bind("<<ComboboxSelected>>", self._on_cmp_change)
        self._cmp_box = cbox

        self._cmp_hint = tk.Label(sp,
            text="Motion IoU: วิเคราะห์ตำแหน่งมือ+อุปกรณ์ (ดีที่สุดสำหรับพื้นหลังนิ่ง)",
            font=FONT_SM, bg=PANEL_BG, fg=WARNING, wraplength=290, justify="left")
        self._cmp_hint.pack(anchor="w", pady=(2,4))

        # Similarity threshold
        self._sim_var       = tk.DoubleVar(value=30.0)
        self._sim_label_var = tk.StringVar(value="Min diff (0-100)")
        sr = tk.Frame(sp, bg=PANEL_BG); sr.pack(fill="x", pady=3)
        tk.Label(sr, textvariable=self._sim_label_var, font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        spin(sr, self._sim_var, 0.1, 256, 1, "%.1f")
        tk.Label(sr, text="(ยิ่งสูง ยิ่งเข้มงวด)", font=FONT_SM,
                 bg=PANEL_BG, fg=MUTED).pack(side="left", padx=4)
        self._sim_row = sr

        # Blur filter
        self._blur_en_var = tk.BooleanVar(value=True)
        self._blur_var    = tk.DoubleVar(value=50.0)
        self._blur_chk = tk.Checkbutton(sp, text="กรองภาพเบลอ (Laplacian)", variable=self._blur_en_var,
                       bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
                       activebackground=PANEL_BG, font=FONT_BODY,
                       command=self._toggle_blur)
        self._blur_chk.pack(anchor="w", pady=(4,0))
        self._blur_row = tk.Frame(sp, bg=PANEL_BG); self._blur_row.pack(fill="x", pady=3)
        tk.Label(self._blur_row, text="  Blur threshold", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        spin(self._blur_row, self._blur_var, 1, 500, 10, "%.0f")

        # Prefix
        self._prefix_var = tk.StringVar(value="frame")
        pr = tk.Frame(sp, bg=PANEL_BG); pr.pack(fill="x", pady=3)
        tk.Label(pr, text="Prefix ชื่อไฟล์", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        tk.Entry(pr, textvariable=self._prefix_var, font=FONT_MONO,
                 bg=ACCENT, fg=TEXT_COLOR, insertbackground="white",
                 bd=0, width=14).pack(side="left")

        # Slot fallback
        self._slot_en_var = tk.BooleanVar(value=False)
        self._slot_var    = tk.IntVar(value=5)
        self._slot_chk = tk.Checkbutton(sp, text="จำกัด Max Attempts/Slot", variable=self._slot_en_var,
                       bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
                       activebackground=PANEL_BG, font=FONT_BODY,
                       command=self._toggle_slot)
        self._slot_chk.pack(anchor="w", pady=(6,0))
        self._slot_row = tk.Frame(sp, bg=PANEL_BG); self._slot_row.pack(fill="x", pady=3)
        tk.Label(self._slot_row, text="  Max attempts/slot", font=FONT_BODY,
                 bg=PANEL_BG, fg=TEXT_COLOR, width=22, anchor="w").pack(side="left")
        spin(self._slot_row, self._slot_var, 1, 30, 1, "%.0f")
        for c in self._slot_row.winfo_children():
            try: c.configure(state="disabled")
            except: pass

        # Separate folder per video
        self._sep_var = tk.BooleanVar(value=True)
        tk.Checkbutton(sp, text="แยกโฟลเดอร์ตามวิดีโอ", variable=self._sep_var,
                       bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
                       activebackground=PANEL_BG, font=FONT_BODY).pack(anchor="w", pady=(6,0))

        # ── Start / Stop ──────────────────────────
        bf = tk.Frame(p, bg=PANEL_BG); bf.pack(fill="x", pady=8)
        self._start_btn = btn(bf, "▶  เริ่มสกัดเฟรม", self._start, SUCCESS)
        self._start_btn.pack(fill="x", ipady=6, pady=(0,4))
        self._stop_btn = btn(bf, "⏹  หยุด", self._stop, HIGHLIGHT)
        self._stop_btn.pack(fill="x", ipady=6)
        self._stop_btn.configure(state="disabled")

        # Progress
        ps = section(p, "📊 Progress")
        self._pvar = tk.DoubleVar(value=0)
        ttk.Progressbar(ps, variable=self._pvar, maximum=100,
                        mode="determinate", length=300).pack(fill="x", pady=(0,4))
        self._plbl = tk.Label(ps, text="รอเริ่มต้น...", font=FONT_MONO,
                              bg=PANEL_BG, fg=MUTED)
        self._plbl.pack()

    def _build_log(self, p):
        tk.Label(p, text="📋 Log", font=FONT_HEAD,
                 bg=DARK_BG, fg=SUCCESS).pack(anchor="w", pady=(0,4))
        lf = tk.Frame(p, bg=DARK_BG); lf.pack(fill="both", expand=True)
        self._log = tk.Text(lf, font=FONT_MONO, bg="#0d1117", fg="#c9d1d9",
                            insertbackground="white", bd=0, wrap="none", state="disabled")
        self._log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._log.yview)
        sb.pack(side="right", fill="y")
        self._log.configure(yscrollcommand=sb.set)
        self._log.tag_config("ok",      foreground=SUCCESS)
        self._log.tag_config("skip",    foreground=WARNING)
        self._log.tag_config("blur",    foreground=MUTED)
        self._log.tag_config("info",    foreground="#58a6ff")
        self._log.tag_config("divider", foreground=ACCENT)
        self._log.tag_config("bold",    font=("Consolas", 9, "bold"))
        btn(p, "🗑️ ล้าง Log", self._clear_log, MUTED).pack(anchor="e", pady=6)

    # ── Helpers ──────────────────────────────────
    def _write_log(self, msg: str):
        self._log.configure(state="normal")
        ts  = datetime.now().strftime("%H:%M:%S")
        tag = ("ok"      if "✅" in msg else
               "skip"    if "🔁" in msg else
               "blur"    if "เบลอ" in msg else
               "divider" if "─" in msg else
               "bold"    if "🎉" in msg or "เสร็จ" in msg else
               "info")
        self._log.insert("end", f"[{ts}] {msg}\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _toggle_mode(self):
        mode = self._mode_var.get()
        self._interval_row.pack_forget()
        self._target_row.pack_forget()
        self._all_info_row.pack_forget()
        if mode == "interval":
            self._interval_row.pack(fill="x", pady=3)
        elif mode == "target":
            self._target_row.pack(fill="x", pady=3)
        else:
            self._all_info_row.pack(fill="x", pady=3)

        is_all = (mode == "all")
        filter_state = "disabled" if is_all else "readonly"
        self._cmp_box.configure(state=filter_state)
        for c in self._sim_row.winfo_children():
            try: c.configure(state=("disabled" if is_all else "normal"))
            except: pass
        self._blur_chk.configure(state=("disabled" if is_all else "normal"))
        self._slot_chk.configure(state=("disabled" if is_all else "normal"))
        if is_all:
            for c in self._blur_row.winfo_children():
                try: c.configure(state="disabled")
                except: pass
            for c in self._slot_row.winfo_children():
                try: c.configure(state="disabled")
                except: pass
        else:
            self._toggle_blur()
            self._toggle_slot()

    def _on_cmp_change(self, _=None):
        hints = {
            "none":       ("N/A (ไม่กรอง)",         0.0,  "ตัดเฟรมทุกตัวโดยไม่เปรียบเทียบ"),
            "motion_iou": ("Min diff % (0-100)",    30.0, "Motion IoU: วิเคราะห์ตำแหน่งมือ+อุปกรณ์ (แนะนำ)"),
            "frame_diff": ("Pixel diff (0-255)",    10.0, "Frame Diff: เทียบความต่างพิกเซลโดยตรง"),
            "phash":      ("Hamming dist (0-256)",   8.0, "pHash: เปรียบเทียบโครงสร้างภาพรวม"),
        }
        lbl, dflt, hint = hints.get(self._cmp_var.get(), hints["motion_iou"])
        self._sim_label_var.set(lbl)
        self._sim_var.set(dflt)
        self._cmp_hint.configure(text=hint)

    def _toggle_blur(self):
        s = "normal" if self._blur_en_var.get() else "disabled"
        for c in self._blur_row.winfo_children():
            try: c.configure(state=s)
            except: pass

    def _toggle_slot(self):
        s = "normal" if self._slot_en_var.get() else "disabled"
        for c in self._slot_row.winfo_children():
            try: c.configure(state=s)
            except: pass

    def _add_videos(self):
        paths = filedialog.askopenfilenames(
            title="เลือกไฟล์วิดีโอ",
            filetypes=[("Video files","*.mp4 *.avi *.mov *.mkv *.wmv *.MOV *.MP4"),
                       ("All files","*.*")],
        )
        for p in paths:
            if p not in self._video_paths:
                self._video_paths.append(p)
                self._video_listbox.insert("end", os.path.basename(p))

    def _remove_video(self):
        for i in reversed(self._video_listbox.curselection()):
            self._video_listbox.delete(i)
            self._video_paths.pop(i)

    def _choose_output(self):
        d = filedialog.askdirectory(title="เลือกโฟลเดอร์ Output")
        if d:
            self._output_folder = d
            self._out_var.set(d)

    # ── Run ──────────────────────────────────────
    def _start(self):
        if not self._video_paths:
            messagebox.showwarning("ขาดข้อมูล","กรุณาเพิ่มไฟล์วิดีโออย่างน้อย 1 ไฟล์"); return
        if not self._output_folder:
            messagebox.showwarning("ขาดข้อมูล","กรุณาเลือกโฟลเดอร์ Output"); return
        self._running = True
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._pvar.set(0)
        self.app.set_status("กำลังสกัดเฟรม...")
        threading.Thread(target=self._run, daemon=True).start()

    def _stop(self):
        self._running = False
        self._write_log("⏹  ผู้ใช้หยุดการทำงาน")
        self.app.set_status("หยุดโดยผู้ใช้")

    def _run(self):
        saved_total, all_paths = 0, []
        for vp in self._video_paths:
            if not self._running: break
            out = (os.path.join(self._output_folder,
                                os.path.splitext(os.path.basename(vp))[0])
                   if self._sep_var.get() else self._output_folder)
            try:
                mode = self._mode_var.get()
                if mode == "target":
                    cap_ = cv2.VideoCapture(vp)
                    fps_ = cap_.get(cv2.CAP_PROP_FPS) or 30
                    frm_ = int(cap_.get(cv2.CAP_PROP_FRAME_COUNT))
                    cap_.release()
                    dur_ = frm_ / fps_
                    iv   = max(0.1, dur_ / max(1, self._target_var.get()))
                    self.after(0, self._write_log,
                               f"  [Adaptive] {os.path.basename(vp)}: {dur_:.1f}s → {iv:.2f}s/frame")
                elif mode == "all":
                    cap_ = cv2.VideoCapture(vp)
                    fps_ = cap_.get(cv2.CAP_PROP_FPS) or 30
                    cap_.release()
                    iv = 0.0
                    self.after(0, self._write_log,
                               f"  [All Frames] {os.path.basename(vp)}: fps={fps_:.1f} → ตัดทุกเฟรม")
                else:
                    iv = self._interval_var.get()

                is_all = (mode == "all")

                def prog(cur, tot, v=vp):
                    if tot:
                        pct = cur/tot*100
                        self.after(0, self._pvar.set, pct)
                        self.after(0, self._plbl.configure,
                                   {"text": f"{os.path.basename(v)}  {pct:.1f}%"})

                stats = extract_frames(
                    video_path            = vp,
                    output_folder         = out,
                    interval_sec          = iv,
                    compare_method        = "none" if is_all else self._cmp_var.get(),
                    similarity_threshold  = self._sim_var.get(),
                    blur_threshold        = self._blur_var.get(),
                    filter_blur           = False if is_all else self._blur_en_var.get(),
                    max_attempts_per_slot = (999_999 if is_all else
                                             (int(self._slot_var.get())
                                              if self._slot_en_var.get() else 999_999)),
                    prefix                = self._prefix_var.get(),
                    progress_callback     = prog,
                    log_callback          = lambda m: self.after(0, self._write_log, m),
                )
                saved_total += stats["saved"]
                if os.path.exists(out):
                    imgs = sorted([
                        os.path.join(out, f) for f in os.listdir(out)
                        if f.lower().endswith((".jpg",".jpeg",".png"))
                    ])
                    all_paths.extend(imgs)
            except Exception as e:
                self.after(0, self._write_log, f"❌ Error: {e}")

        self.after(0, self._on_done, all_paths, saved_total)

    def _on_done(self, paths, saved):
        self._running = False
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._pvar.set(100)
        self._plbl.configure(text="เสร็จสิ้น ✅")
        self.app.extracted_frames = paths
        self.app.set_status(f"สกัดเฟรมเสร็จ — {saved} ภาพ  |  พร้อมทำ Detection")
        self._write_log(f"🎉 เสร็จ! {saved} ภาพ — ไปที่ Tab 2 ได้เลย")
        if messagebox.askyesno("เสร็จสิ้น",
                               f"สกัดเฟรมเสร็จแล้ว: {saved} ภาพ\n\nไปที่ Step 2 (Detection) เลยไหม?"):
            self.app.go_to_tab(1)
            self.app.tab_detect.on_frames_ready()


# ═══════════════════════════════════════════════════
#  Tab 2 — YOLOv11 Detection + BBox Preview
# ═══════════════════════════════════════════════════
class DetectionTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self._detector:  YOLOv11Detector | None = None
        self._running  = False
        self._processed: list[dict] = []   # results so far
        self._prev_idx   = 0               # preview index
        self._photo_ref  = None            # keep PhotoImage alive
        self._build_ui()

    # ─────────────────────────────────────────────
    def _build_ui(self):
        root = tk.Frame(self, bg=DARK_BG)
        root.pack(fill="both", expand=True, padx=12, pady=10)

        # ── Left panel: settings + controls ──────
        left = tk.Frame(root, bg=PANEL_BG, width=340)
        left.pack(side="left", fill="y", padx=(0,10))
        left.pack_propagate(False)
        self._build_left(left)

        # ── Right panel: preview ─────────────────
        right = tk.Frame(root, bg=DARK_BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_right(right)

    # ── Left ─────────────────────────────────────
    def _build_left(self, p):
        inner = tk.Frame(p, bg=PANEL_BG)
        inner.pack(fill="both", expand=True, padx=8, pady=8)

        # Model
        sm = section(inner, "🤖 โมเดล YOLOv11")

        # Backend selector
        self._backend_var = tk.StringVar(value="local")
        br = tk.Frame(sm, bg=PANEL_BG); br.pack(fill="x", pady=(0,6))
        for v, t in [("local","🖥 Local (.pt)"),("roboflow","☁️ Roboflow Cloud API")]:
            tk.Radiobutton(br, text=t, variable=self._backend_var, value=v,
                           command=self._on_backend_change,
                           bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
                           activebackground=PANEL_BG, font=FONT_BODY).pack(side="left", padx=(0,8))

        # -- Local .pt --
        self._local_frame = tk.Frame(sm, bg=PANEL_BG)
        self._local_frame.pack(fill="x", pady=(0,4))
        default_model = "models/best.pt" if os.path.exists("models/best.pt") else "yolo11n.pt"
        self._model_var = tk.StringVar(value=default_model)
        mr = tk.Frame(self._local_frame, bg=PANEL_BG); mr.pack(fill="x")
        tk.Entry(mr, textvariable=self._model_var, font=FONT_MONO,
                 bg=ACCENT, fg=TEXT_COLOR, insertbackground="white",
                 bd=0).pack(side="left", fill="x", expand=True)
        btn(mr, "📂", self._choose_model, ACCENT).pack(side="right", padx=(4,0))

        # -- Roboflow Cloud API --
        self._rf_frame = tk.Frame(sm, bg=PANEL_BG)
        self._rf_key_var = tk.StringVar(value="")
        self._rf_ws_var  = tk.StringVar(value="fhasai-khuanpan")
        self._rf_wf_var  = tk.StringVar(value="ssid-v5-logic")
        for label_text, var, show in [
            ("API Key",     self._rf_key_var, "*"),
            ("Workspace",   self._rf_ws_var,  None),
            ("Workflow ID", self._rf_wf_var,  None),
        ]:
            row = lbl_row(self._rf_frame, label_text, width=12)
            tk.Entry(row, textvariable=var, font=FONT_MONO,
                     bg=ACCENT, fg=TEXT_COLOR, insertbackground="white",
                     bd=0, show=show or "").pack(side="left", fill="x", expand=True)

        # Conf + IoU sliders
        ss = section(inner, "⚙️ Inference Settings")

        self._conf_var = tk.DoubleVar(value=0.25)
        cr = lbl_row(ss, "Confidence")
        tk.Scale(cr, variable=self._conf_var, from_=0.01, to=0.99,
                 resolution=0.01, orient="horizontal",
                 bg=PANEL_BG, fg=TEXT_COLOR, troughcolor=ACCENT,
                 highlightthickness=0, length=130).pack(side="left")
        self._conf_lbl = tk.Label(cr, text="0.25", font=FONT_MONO,
                                  bg=PANEL_BG, fg=SUCCESS)
        self._conf_lbl.pack(side="left", padx=4)
        self._conf_var.trace_add("write",
            lambda *_: self._conf_lbl.configure(text=f"{self._conf_var.get():.2f}"))

        self._iou_var = tk.DoubleVar(value=0.45)
        ir = lbl_row(ss, "IoU Threshold")
        tk.Scale(ir, variable=self._iou_var, from_=0.01, to=0.99,
                 resolution=0.01, orient="horizontal",
                 bg=PANEL_BG, fg=TEXT_COLOR, troughcolor=ACCENT,
                 highlightthickness=0, length=130).pack(side="left")
        self._iou_lbl = tk.Label(ir, text="0.45", font=FONT_MONO,
                                 bg=PANEL_BG, fg=SUCCESS)
        self._iou_lbl.pack(side="left", padx=4)
        self._iou_var.trace_add("write",
            lambda *_: self._iou_lbl.configure(text=f"{self._iou_var.get():.2f}"))

        # Device
        dr = lbl_row(ss, "Device")
        self._device_var = tk.StringVar(value="cpu")
        for v, t in [("cpu","CPU"),("cuda","GPU (CUDA)"),("mps","Apple MPS")]:
            tk.Radiobutton(dr, text=t, variable=self._device_var, value=v,
                           bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=ACCENT,
                           activebackground=PANEL_BG, font=FONT_BODY).pack(side="left", padx=4)

        # Frames info
        sf = section(inner, "📂 เฟรมที่จะ detect")
        self._frames_info = tk.Label(sf, text="ยังไม่มีเฟรม (ทำ Step 1 ก่อน)",
                                     font=FONT_MONO, bg=PANEL_BG, fg=WARNING,
                                     wraplength=290, justify="left")
        self._frames_info.pack(anchor="w")
        btn(sf, "📁 โหลดเฟรมจากโฟลเดอร์", self._load_frames_folder,
            ACCENT).pack(fill="x", pady=(6,0))

        # Start / Stop
        bf = tk.Frame(inner, bg=PANEL_BG); bf.pack(fill="x", pady=8)
        self._det_start = btn(bf, "▶  เริ่ม Detection", self._start, SUCCESS)
        self._det_start.pack(fill="x", ipady=6, pady=(0,4))
        self._det_stop = btn(bf, "⏹  หยุด", self._stop, HIGHLIGHT)
        self._det_stop.pack(fill="x", ipady=6)
        self._det_stop.configure(state="disabled")

        # Progress
        sp2 = section(inner, "📊 Progress")
        self._det_pvar = tk.DoubleVar(value=0)
        ttk.Progressbar(sp2, variable=self._det_pvar, maximum=100,
                        mode="determinate", length=300).pack(fill="x", pady=(0,4))
        self._det_plbl = tk.Label(sp2, text="รอเริ่มต้น...", font=FONT_MONO,
                                  bg=PANEL_BG, fg=MUTED)
        self._det_plbl.pack()

    # ── Right ─────────────────────────────────────
    def _build_right(self, p):
        tk.Label(p, text="🖼️ Preview", font=FONT_HEAD,
                 bg=DARK_BG, fg=SUCCESS).pack(anchor="w", pady=(0,4))

        # Image canvas
        canvas_bg = tk.Frame(p, bg="#0d1117", relief="flat", bd=1)
        canvas_bg.pack(fill="both", expand=True)
        self._preview_lbl = tk.Label(canvas_bg, bg="#0d1117",
                                     text="ภาพ preview จะแสดงที่นี่\nเมื่อเริ่มทำ Detection",
                                     font=("Segoe UI",12), fg=MUTED)
        self._preview_lbl.pack(expand=True)

        # Navigation bar
        nav = tk.Frame(p, bg=DARK_BG); nav.pack(fill="x", pady=(6,0))

        btn(nav, "◄ Prev", self._prev_frame, ACCENT).pack(side="left", padx=(0,4))
        self._nav_lbl = tk.Label(nav, text="—", font=FONT_MONO,
                                 bg=DARK_BG, fg=TEXT_COLOR)
        self._nav_lbl.pack(side="left", padx=8)
        btn(nav, "Next ►", self._next_frame, ACCENT).pack(side="left")

        # Detection info chips
        info_outer = tk.Frame(p, bg=DARK_BG); info_outer.pack(fill="x", pady=(6,0))
        tk.Label(info_outer, text="Detections:", font=FONT_BODY,
                 bg=DARK_BG, fg=MUTED).pack(anchor="w")
        self._det_chips = tk.Frame(info_outer, bg=DARK_BG)
        self._det_chips.pack(fill="x")

    # ─────────────────────────────────────────────
    def on_frames_ready(self):
        """เรียกจาก Tab 1 เมื่อสกัดเฟรมเสร็จ"""
        n = len(self.app.extracted_frames)
        self._frames_info.configure(
            text=f"✅ {n} เฟรม พร้อม detect",
            fg=SUCCESS,
        )

    def _load_frames_folder(self):
        d = filedialog.askdirectory(title="เลือกโฟลเดอร์ที่มีภาพ")
        if not d: return
        exts = (".jpg",".jpeg",".png",".bmp")
        paths = sorted([
            os.path.join(root, f)
            for root, _, files in os.walk(d)
            for f in files if f.lower().endswith(exts)
        ])
        self.app.extracted_frames = paths
        self._frames_info.configure(
            text=f"✅ {len(paths)} เฟรม จาก {d}",
            fg=SUCCESS,
        )

    def _choose_model(self):
        p = filedialog.askopenfilename(
            title="เลือกไฟล์โมเดล (.pt)",
            filetypes=[("YOLO model","*.pt"),("All","*.*")],
        )
        if p:
            self._model_var.set(p)

    def _on_backend_change(self):
        if self._backend_var.get() == "roboflow":
            self._local_frame.pack_forget()
            self._rf_frame.pack(fill="x", pady=(0,4))
        else:
            self._rf_frame.pack_forget()
            self._local_frame.pack(fill="x", pady=(0,4))

    def _build_detector(self):
        """สร้าง detector ตาม backend ที่เลือกไว้ (local .pt หรือ Roboflow Cloud API)"""
        if self._backend_var.get() == "roboflow":
            return RoboflowDetector(
                api_key        = self._rf_key_var.get().strip(),
                workspace_name = self._rf_ws_var.get().strip(),
                workflow_id    = self._rf_wf_var.get().strip(),
                conf           = self._conf_var.get(),
            )
        return YOLOv11Detector(
            model_path = self._model_var.get(),
            conf       = self._conf_var.get(),
            iou        = self._iou_var.get(),
            device     = self._device_var.get(),
        )

    # ── Run ──────────────────────────────────────
    def _start(self):
        if not self.app.extracted_frames:
            messagebox.showwarning("ไม่มีเฟรม","กรุณาสกัดเฟรมก่อน (Step 1) หรือโหลดโฟลเดอร์"); return

        if self._backend_var.get() == "roboflow":
            if not self._rf_key_var.get().strip():
                messagebox.showerror("ไม่มี API Key", "กรุณากรอก Roboflow API Key ก่อน"); return
        else:
            model_path = self._model_var.get().strip()
            is_known_pretrained = any(model_path.startswith(prefix) for prefix in ["yolo", "rtdetr"]) and model_path.endswith(".pt")
            if not os.path.exists(model_path) and not is_known_pretrained:
                messagebox.showerror("ไม่พบโมเดล", f"ไม่พบไฟล์:\n{model_path}"); return

        self._processed = []
        self._prev_idx  = 0
        self._running   = True
        self._det_start.configure(state="disabled")
        self._det_stop.configure(state="normal")
        self._det_pvar.set(0)
        self.app.set_status("กำลัง load โมเดล...")
        threading.Thread(target=self._run, daemon=True).start()

    def _stop(self):
        self._running = False
        self.app.set_status("หยุด detection โดยผู้ใช้")

    def _run(self):
        try:
            self.after(0, self._det_plbl.configure,
                       {"text": "⏳ กำลัง load โมเดล..."})
            det = self._build_detector()
        except Exception as e:
            self.after(0, messagebox.showerror, "Load โมเดลล้มเหลว", str(e))
            self.after(0, self._finish_ui)
            return

        frames = self.app.extracted_frames
        total  = len(frames)
        self.after(0, self.app.set_status, f"กำลัง detect {total} เฟรม...")

        for idx, fp in enumerate(frames):
            if not self._running: break

            img = cv2.imread(fp)
            if img is None:
                continue

            dets  = det.predict(img)
            label = det.to_yolo_label(dets)
            item  = {
                "image_path":    fp,
                "label_str":     label,
                "has_detection": bool(dets),
                "detections":    [d.to_dict() for d in dets],
                "_img_with_box": det.draw_boxes(img, dets),  # temp cache
            }
            self._processed.append(item)

            pct = (idx + 1) / total * 100
            self.after(0, self._det_pvar.set, pct)
            self.after(0, self._det_plbl.configure,
                       {"text": f"เฟรม {idx+1}/{total}  |  detect: {len(dets)} obj"})

            # อัพเดต preview ทุก 5 เฟรม หรือเฟรมแรก
            if idx == 0 or (idx + 1) % 5 == 0:
                self.after(0, self._show_preview, len(self._processed) - 1)

        # บันทึกผลลัพธ์กลับ App state (ลบ _img_with_box ออก)
        self.app.detection_results = [
            {k: v for k, v in item.items() if k != "_img_with_box"}
            for item in self._processed
        ]
        self.after(0, self._on_done)

    def _on_done(self):
        self._finish_ui()
        n     = len(self._processed)
        n_det = sum(1 for r in self._processed if r["has_detection"])
        self.app.set_status(
            f"Detection เสร็จ — {n_det}/{n} เฟรมมี object  |  ไป Step 3 เพื่อ Export")
        self.app.tab_export.refresh_stats()
        if messagebox.askyesno("Detection เสร็จ",
                               f"Detection เสร็จแล้ว!\n"
                               f"  พบ object: {n_det} เฟรม\n"
                               f"  ว่าง:      {n-n_det} เฟรม\n\n"
                               f"ไปที่ Step 3 (Export Dataset) เลยไหม?"):
            self.app.go_to_tab(2)

    def _finish_ui(self):
        self._running = False
        self._det_start.configure(state="normal")
        self._det_stop.configure(state="disabled")
        self._det_pvar.set(100 if self._processed else 0)

    # ── Preview ──────────────────────────────────
    def _show_preview(self, idx: int):
        if not self._processed or idx < 0 or idx >= len(self._processed):
            return
        self._prev_idx = idx
        item = self._processed[idx]

        # ใช้ภาพที่ draw BBox ไว้แล้ว (cache) หรืออ่านใหม่
        img_box = item.get("_img_with_box")
        if img_box is None:
            raw = cv2.imread(item["image_path"])
            if raw is None: return
            img_box = raw  # ไม่มี box ก็แสดงเปล่า

        # Resize ให้พอดีพื้นที่ preview
        h, w = img_box.shape[:2]
        scale = min(PREVIEW_MAX_W / w, PREVIEW_MAX_H / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(img_box, (nw, nh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        self._photo_ref = ImageTk.PhotoImage(pil)

        self._preview_lbl.configure(image=self._photo_ref, text="")
        self._preview_lbl.image = self._photo_ref   # extra GC guard

        # Nav label
        total = len(self._processed)
        fname = os.path.basename(item["image_path"])
        self._nav_lbl.configure(text=f"{idx+1} / {total}  ·  {fname}")

        # Detection chips
        for w_ in self._det_chips.winfo_children():
            w_.destroy()
        
        has_low_conf = False
        for d in item["detections"]:
            color = CLASS_COLORS_HEX.get(d["class_name"], _DEFAULT_HEX)
            chip  = tk.Frame(self._det_chips, bg=DARK_BG)
            chip.pack(side="left", padx=4, pady=2)
            
            conf = d['confidence']
            if conf < 0.5:
                has_low_conf = True
                bg_color = "#4a1c1c" # Dark red warning
                fg_color = "#ffb3b3"
            else:
                bg_color = DARK_BG
                fg_color = TEXT_COLOR

            tk.Label(chip, text="●", fg=color, bg=bg_color,
                     font=("Segoe UI",13)).pack(side="left")
            tk.Label(chip, text=f"{d['class_name']}  {conf:.2f}",
                     font=FONT_MONO, bg=bg_color, fg=fg_color).pack(side="left")

        if not item["detections"]:
            tk.Label(self._det_chips, text="— ไม่พบ object —",
                     font=FONT_MONO, bg=DARK_BG, fg=MUTED).pack(side="left")
        elif has_low_conf:
            tk.Label(self._det_chips, text="⚠️ Low Confidence",
                     font=FONT_BODY, bg=DARK_BG, fg="#ffb3b3").pack(side="left", padx=10)

    def _prev_frame(self):
        if self._prev_idx > 0:
            self._show_preview(self._prev_idx - 1)

    def _next_frame(self):
        if self._prev_idx < len(self._processed) - 1:
            self._show_preview(self._prev_idx + 1)

# ═══════════════════════════════════════════════════
#  Tab 4 — Live Instrument Verifier
# ═══════════════════════════════════════════════════
class LiveVerifierTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self._cap = None
        self._running = False
        self._detector = None
        self._photo = None
        self._build_ui()

    def _build_ui(self):
        # Top controls
        tc = tk.Frame(self, bg=PANEL_BG)
        tc.pack(fill="x", padx=10, pady=10)
        
        tk.Label(tc, text="Camera Index:", bg=PANEL_BG, fg=TEXT_COLOR).pack(side="left")
        self._cam_idx = tk.IntVar(value=0)
        tk.Entry(tc, textvariable=self._cam_idx, width=5).pack(side="left", padx=5)
        
        self._start_btn = tk.Button(tc, text="▶ Start Camera", command=self._toggle_cam, bg=DARK_BG, fg=TEXT_COLOR)
        self._start_btn.pack(side="left", padx=10)

        # Main content
        main = tk.Frame(self, bg=DARK_BG)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Video preview
        self._video_lbl = tk.Label(main, bg="black", text="Video Preview", fg=MUTED)
        self._video_lbl.pack(side="left", fill="both", expand=True)

        # Status Panel
        sp = tk.Frame(main, bg=PANEL_BG, width=250)
        sp.pack(side="right", fill="y", padx=10)
        
        tk.Label(sp, text="Instrument Checklist", bg=PANEL_BG, fg=TEXT_COLOR, font=("Segoe UI", 14)).pack(pady=10)
        
        self._checks = {}
        self._status_vars = {}
        for name in CLASS_NAMES:
            row = tk.Frame(sp, bg=PANEL_BG)
            row.pack(fill="x", padx=10, pady=2)
            
            var = tk.BooleanVar(value=True)
            chk = tk.Checkbutton(row, text=name, variable=var, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG)
            chk.pack(side="left")
            self._checks[name] = var
            
            st = tk.StringVar(value="❌")
            tk.Label(row, textvariable=st, bg=PANEL_BG, fg=TEXT_COLOR, font=("Segoe UI", 12)).pack(side="right")
            self._status_vars[name] = st

        self._overall_lbl = tk.Label(sp, text="🔴 NOT READY", font=("Segoe UI", 16, "bold"), bg=PANEL_BG, fg="#FF5555")
        self._overall_lbl.pack(side="bottom", pady=20)

    def _toggle_cam(self):
        if self._running:
            self._running = False
            self._start_btn.config(text="▶ Start Camera")
            if self._cap:
                self._cap.release()
            self._video_lbl.config(image="")
            self._overall_lbl.config(text="🔴 NOT READY", fg="#FF5555")
        else:
            backend = self.app.tab_detect._backend_var.get()
            if backend == "roboflow":
                if not self.app.tab_detect._rf_key_var.get().strip():
                    messagebox.showerror("Error", "กรุณากรอก Roboflow API Key ในแท็บ Detection ก่อน")
                    return
            else:
                if not self.app.tab_detect._model_var.get().strip():
                    messagebox.showerror("Error", "Please select a model in Step 2 first.")
                    return

            try:
                # โหลด/สร้าง detector ใหม่ทุกครั้งที่กด Start เพื่อให้ backend/model
                # ที่เลือกไว้ล่าสุดใน Step 2 ถูกใช้เสมอ (ไม่ cache ของเก่าข้าม backend)
                self._detector = self.app.tab_detect._build_detector()
            except Exception as e:
                messagebox.showerror("Error", f"โหลดโมเดลไม่สำเร็จ:\n{e}")
                return

            self._cap = cv2.VideoCapture(self._cam_idx.get())
            if not self._cap.isOpened():
                messagebox.showerror("Error", "Cannot open camera.")
                return
                
            self._running = True
            self._start_btn.config(text="⏹ Stop Camera")
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                break
                
            # inference
            dets = self._detector.predict(frame)
            img = self._detector.draw_boxes(frame, dets)
            
            # update UI
            found_counts = {name: 0 for name in CLASS_NAMES}
            for d in dets:
                found_counts[d.class_name] += 1
                
            all_ready = True
            has_dup = False
            for name in CLASS_NAMES:
                req = self._checks[name].get()
                c = found_counts[name]
                if req:
                    if c == 1:
                        self.after(0, self._status_vars[name].set, "✅")
                    elif c > 1:
                        self.after(0, self._status_vars[name].set, f"⚠️ x{c}")
                        has_dup = True
                    else:
                        self.after(0, self._status_vars[name].set, "❌")
                        all_ready = False
                else:
                    self.after(0, self._status_vars[name].set, "-")
            
            # update overall
            if all_ready and not has_dup:
                self.after(0, self._overall_lbl.config, {"text": "🟢 READY", "fg": "#55FF55"})
            elif all_ready and has_dup:
                self.after(0, self._overall_lbl.config, {"text": "🟡 WARNING (Duplicates)", "fg": "#FFFF55"})
            else:
                self.after(0, self._overall_lbl.config, {"text": "🔴 NOT READY", "fg": "#FF5555"})

            # render image
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            pil_img.thumbnail((640, 480))
            
            self._photo = ImageTk.PhotoImage(pil_img)
            self.after(0, self._video_lbl.config, {"image": self._photo})
            
            time.sleep(0.03)

# ═══════════════════════════════════════════════════
#  Tab 5 — Annotation Editor
# ═══════════════════════════════════════════════════
class AnnotationTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self._photo = None
        self._current_idx = -1
        self._rects = []
        self._build_ui()

    def _build_ui(self):
        # Top toolbar
        tb = tk.Frame(self, bg=PANEL_BG)
        tb.pack(fill="x", padx=10, pady=5)
        tk.Button(tb, text="↺ Refresh List", command=self._refresh_list).pack(side="left", padx=5)
        tk.Label(tb, text="Review Status:", bg=PANEL_BG, fg=TEXT_COLOR).pack(side="left", padx=10)
        self._status_var = tk.StringVar(value="🔴 Needs Review")
        tk.Label(tb, textvariable=self._status_var, fg="#FF8888", bg=PANEL_BG).pack(side="left")
        tk.Button(tb, text="✅ Mark as Reviewed", command=self._mark_reviewed).pack(side="left", padx=10)

        # Main content
        main = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=DARK_BG)
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # Left: Filmstrip (Listbox)
        left = tk.Frame(main, bg=PANEL_BG, width=200)
        main.add(left)
        self._listbox = tk.Listbox(left, bg=PANEL_BG, fg=TEXT_COLOR, selectbackground=HIGHLIGHT)
        self._listbox.pack(fill="both", expand=True)
        self._listbox.bind('<<ListboxSelect>>', self._on_select)

        # Center: Canvas
        center = tk.Frame(main, bg="black")
        main.add(center)
        self._canvas = tk.Canvas(center, bg="black")
        self._canvas.pack(fill="both", expand=True)
        
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._start_x = self._start_y = 0
        self._temp_rect = None

        # Right: Properties
        right = tk.Frame(main, bg=PANEL_BG, width=250)
        main.add(right)
        tk.Label(right, text="New Class:", bg=PANEL_BG, fg=TEXT_COLOR).pack(pady=5)
        self._class_var = tk.StringVar(value=CLASS_NAMES[0])
        ttk.Combobox(right, textvariable=self._class_var, values=CLASS_NAMES, state="readonly").pack()
        
        tk.Button(right, text="Save Changes", command=self._save_changes).pack(pady=20)
        tk.Button(right, text="Clear All Boxes", command=self._clear_boxes).pack(pady=5)

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for idx, item in enumerate(self.app.detection_results):
            name = os.path.basename(item["image_path"])
            status = item.get("review_status", "🔴")
            self._listbox.insert(tk.END, f"{status} {name}")
            
    def _on_select(self, event):
        sel = self._listbox.curselection()
        if not sel: return
        self._current_idx = sel[0]
        self._load_image()

    def _load_image(self):
        if self._current_idx < 0: return
        item = self.app.detection_results[self._current_idx]
        
        st = item.get("review_status", "🔴")
        if st == "✅":
            self._status_var.set("✅ Reviewed")
        else:
            self._status_var.set("🔴 Needs Review")
            
        img_path = item["image_path"]
        pil_img = Image.open(img_path)
        self._orig_w, self._orig_h = pil_img.size
        
        self._photo = ImageTk.PhotoImage(pil_img)
        self._canvas.config(width=self._orig_w, height=self._orig_h)
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        
        self._draw_existing_boxes()

    def _draw_existing_boxes(self):
        self._canvas.delete("bbox")
        if self._current_idx < 0: return
        item = self.app.detection_results[self._current_idx]
        for d in item.get("detections", []):
            x1 = int((d['x_center'] - d['width']/2) * self._orig_w)
            y1 = int((d['y_center'] - d['height']/2) * self._orig_h)
            x2 = int((d['x_center'] + d['width']/2) * self._orig_w)
            y2 = int((d['y_center'] + d['height']/2) * self._orig_h)
            color = CLASS_COLORS_HEX.get(d['class_name'], "white")
            self._canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags="bbox")
            self._canvas.create_text(x1, y1-5, text=d['class_name'], fill=color, anchor="sw", tags="bbox")

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        color = CLASS_COLORS_HEX.get(self._class_var.get(), "white")
        self._temp_rect = self._canvas.create_rectangle(self._start_x, self._start_y, event.x, event.y, outline=color, width=2, tags="bbox")

    def _on_drag(self, event):
        if self._temp_rect:
            self._canvas.coords(self._temp_rect, self._start_x, self._start_y, event.x, event.y)

    def _on_release(self, event):
        if not self._temp_rect: return
        
        if abs(event.x - self._start_x) < 5 or abs(event.y - self._start_y) < 5:
            self._canvas.delete(self._temp_rect)
            self._temp_rect = None
            return
            
        x1, x2 = sorted([self._start_x, event.x])
        y1, y2 = sorted([self._start_y, event.y])
        
        w = (x2 - x1) / self._orig_w
        h = (y2 - y1) / self._orig_h
        cx = ((x1 + x2) / 2) / self._orig_w
        cy = ((y1 + y2) / 2) / self._orig_h
        
        cls_name = self._class_var.get()
        cls_id = CLASS_NAMES.index(cls_name)
        
        new_det = {
            "class_id": cls_id,
            "class_name": cls_name,
            "confidence": 1.0,
            "x_center": cx,
            "y_center": cy,
            "width": w,
            "height": h
        }
        
        if self._current_idx >= 0:
            item = self.app.detection_results[self._current_idx]
            if "detections" not in item:
                item["detections"] = []
            item["detections"].append(new_det)
            self._draw_existing_boxes()
            
        self._temp_rect = None

    def _clear_boxes(self):
        if self._current_idx < 0: return
        self.app.detection_results[self._current_idx]["detections"] = []
        self._draw_existing_boxes()

    def _save_changes(self):
        messagebox.showinfo("Saved", "Annotations saved to state.")
        self._mark_reviewed()

    def _mark_reviewed(self):
        if self._current_idx < 0: return
        self.app.detection_results[self._current_idx]["review_status"] = "✅"
        self._status_var.set("✅ Reviewed")
        
        item = self.app.detection_results[self._current_idx]
        name = os.path.basename(item["image_path"])
        self._listbox.delete(self._current_idx)
        self._listbox.insert(self._current_idx, f"✅ {name}")
        self._listbox.selection_set(self._current_idx)


# ═══════════════════════════════════════════════════
#  Tab 3 — Export Dataset
# ═══════════════════════════════════════════════════
class ExportTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self._out_folder = ""
        self._build_ui()

    def _build_ui(self):
        # Create a scrollable canvas for the long wizard
        self.canvas = tk.Canvas(self, bg=DARK_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=DARK_BG)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=20, pady=16)
        self.scrollbar.pack(side="right", fill="y")
        
        root = self.scrollable_frame

        # ── 1. Version Info & Dataset Status ──────────────────────────
        s1 = section(root, "1️⃣ Version Info & Dataset Status")
        
        dv = lbl_row(s1, "Version Name:")
        self._version_var = tk.StringVar(value="v1")
        tk.Entry(dv, textvariable=self._version_var, width=15, font=FONT_MONO, bg=DARK_BG, fg=TEXT_COLOR).pack(side="left")

        dn = lbl_row(s1, "Version Notes:")
        self._notes_var = tk.StringVar(value="")
        tk.Entry(dn, textvariable=self._notes_var, width=50, font=FONT_BODY, bg=DARK_BG, fg=TEXT_COLOR).pack(side="left")

        # Stats
        self._stat_total = self._stat_row(s1, "📸 Source Images", "—")
        self._stat_classes = self._stat_row(s1, "🏷️ Classes", str(len(CLASS_NAMES)))
        self._stat_unannotated = self._stat_row(s1, "⚠️ Unannotated/Needs Review", "—")

        # ── 2. Train / Val / Test Split ───────────────────────
        s2 = section(root, "2️⃣ Train / Val / Test Split")
        tv = lbl_row(s2, "Train Split (%)")
        self._train_var = tk.IntVar(value=70)
        tk.Scale(tv, variable=self._train_var, from_=50, to=90, resolution=1, orient="horizontal", bg=PANEL_BG, fg=TEXT_COLOR, command=self._update_split_label).pack(side="left")
        
        vv = lbl_row(s2, "Val Split (%)")
        self._val_var = tk.IntVar(value=20)
        tk.Scale(vv, variable=self._val_var, from_=0, to=40, resolution=1, orient="horizontal", bg=PANEL_BG, fg=TEXT_COLOR, command=self._update_split_label).pack(side="left")

        self._split_lbl = tk.Label(s2, text="70% Train / 20% Val / 10% Test", font=FONT_MONO, bg=PANEL_BG, fg=SUCCESS)
        self._split_lbl.pack(anchor="w", padx=10, pady=5)

        # ── 3. Preprocessing ───────────────────────────
        s3 = section(root, "3️⃣ Preprocessing")
        tk.Label(s3, text="Decrease training time and increase performance.", bg=PANEL_BG, fg=MUTED, font=FONT_BODY).pack(anchor="w", padx=10)
        
        self._do_resize = tk.BooleanVar(value=True)
        tk.Checkbutton(s3, text="Resize (Fit within 640x640)", variable=self._do_resize, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG).pack(anchor="w", padx=10, pady=5)
        self._resize_size = tk.IntVar(value=640)
        
        # ── 4. Augmentation ─────────────────────────
        s4 = section(root, "4️⃣ Augmentation")
        tk.Label(s4, text="Create new training examples by generating augmented versions.", bg=PANEL_BG, fg=MUTED, font=FONT_BODY).pack(anchor="w", padx=10)
        
        self._aug_flip = tk.BooleanVar(value=True)
        tk.Checkbutton(s4, text="Flip (Horizontal/Vertical)", variable=self._aug_flip, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG).pack(anchor="w", padx=10)
        
        self._aug_rotate = tk.BooleanVar(value=True)
        tk.Checkbutton(s4, text="Rotation (Between -15° and +15°)", variable=self._aug_rotate, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG).pack(anchor="w", padx=10)
        
        self._aug_brightness = tk.BooleanVar(value=True)
        tk.Checkbutton(s4, text="Brightness & Contrast", variable=self._aug_brightness, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG).pack(anchor="w", padx=10)
        
        self._aug_blur = tk.BooleanVar(value=True)
        tk.Checkbutton(s4, text="Blur / Noise", variable=self._aug_blur, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG).pack(anchor="w", padx=10)

        self._aug_crop = tk.BooleanVar(value=True)
        tk.Checkbutton(s4, text="Random Crop", variable=self._aug_crop, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor=DARK_BG).pack(anchor="w", padx=10)

        ml = lbl_row(s4, "Augmentation Multiplier:")
        self._aug_multiplier = tk.IntVar(value=3)
        tk.Scale(ml, variable=self._aug_multiplier, from_=1, to=10, resolution=1, orient="horizontal", bg=PANEL_BG, fg=TEXT_COLOR, command=self._update_total_lbl).pack(side="left")
        
        # ── 5. Create Version ─────────────────────────
        s5 = section(root, "5️⃣ Create Version")
        
        self._total_gen_lbl = tk.Label(s5, text="Maximum Version Size: — images", font=("Segoe UI", 14, "bold"), bg=PANEL_BG, fg=HIGHLIGHT)
        self._total_gen_lbl.pack(anchor="w", padx=10, pady=10)

        or_ = tk.Frame(s5, bg=PANEL_BG); or_.pack(fill="x")
        self._out_var = tk.StringVar(value="Select Output Folder...")
        tk.Label(or_, textvariable=self._out_var, font=FONT_MONO, bg=DARK_BG, fg=MUTED, anchor="w", padx=6).pack(side="left", fill="x", expand=True)
        btn(or_, "📂", self._choose_out, ACCENT).pack(side="right")

        bf = tk.Frame(s5, bg=PANEL_BG); bf.pack(fill="x", pady=12)
        self._exp_btn = btn(bf, "🚀 Create Version", self._export, HIGHLIGHT)
        self._exp_btn.pack(ipady=8, ipadx=20, side="left")

        self._exp_progress = tk.Label(bf, text="", font=FONT_MONO, bg=PANEL_BG, fg=SUCCESS)
        self._exp_progress.pack(side="left", padx=16)

    def _stat_row(self, parent, label, value):
        row = tk.Frame(parent, bg=PANEL_BG); row.pack(fill="x", pady=2)
        tk.Label(row, text=label, font=FONT_BODY, bg=PANEL_BG, fg=MUTED, width=30, anchor="w").pack(side="left")
        var = tk.StringVar(value=value)
        tk.Label(row, textvariable=var, font=(FONT_MONO[0], FONT_MONO[1], "bold"), bg=PANEL_BG, fg=TEXT_COLOR, anchor="w").pack(side="left")
        return var

    def _update_split_label(self, _=None):
        tr = self._train_var.get()
        va = self._val_var.get()
        if tr + va > 100:
            va = 100 - tr
            self._val_var.set(va)
        te = 100 - tr - va
        self._split_lbl.configure(text=f"{tr}% Train / {va}% Val / {te}% Test")
        self._update_total_lbl()

    def _update_total_lbl(self, _=None):
        if not self.app.detection_results: return
        total = len(self.app.detection_results)
        tr = self._train_var.get() / 100.0
        va = self._val_var.get() / 100.0
        te = max(0, 1.0 - tr - va)
        
        train_count = int(total * tr)
        val_count = int(total * va)
        test_count = total - train_count - val_count
        
        mult = self._aug_multiplier.get()
        final_size = (train_count * mult) + val_count + test_count
        self._total_gen_lbl.configure(text=f"Maximum Version Size: {final_size} images ({mult}x)")

    def refresh_stats(self):
        from dataset_exporter import count_stats
        stats = count_stats(self.app.detection_results)
        self._stat_total.set(str(stats["total"]))
        
        unannotated = 0
        for item in self.app.detection_results:
            if item.get("review_status", "") != "✅":
                unannotated += 1
        self._stat_unannotated.set(str(unannotated))
        self._update_total_lbl()

    def _choose_out(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self._out_folder = d
            self._out_var.set(d)

    def _export(self):
        if not self.app.detection_results:
            messagebox.showwarning("Error","No images to export."); return
        if not self._out_folder:
            messagebox.showwarning("Error","Please select an output folder."); return

        self._exp_btn.configure(state="disabled")
        self._exp_progress.configure(text="Creating Version...")
        threading.Thread(target=self._run_export, daemon=True).start()

    def _run_export(self):
        try:
            def prog(cur, tot):
                self.after(0, self._exp_progress.configure, {"text": f"Processing {cur}/{tot}..."})

            tr = self._train_var.get() / 100.0
            va = self._val_var.get() / 100.0
            
            from dataset_exporter import export_dataset_pipeline
            output = export_dataset_pipeline(
                results        = self.app.detection_results,
                output_dir     = os.path.join(self._out_folder, f"dataset_{self._version_var.get()}"),
                class_names    = CLASS_NAMES,
                splits         = {"train": tr, "val": va, "test": 1.0-tr-va},
                include_empty  = True,
                as_zip         = False,
                preprocess_config = {"resize": self._do_resize.get(), "resize_size": self._resize_size.get()},
                augment_config = {
                    "multiplier": self._aug_multiplier.get(),
                    "flip": self._aug_flip.get(),
                    "rotate": self._aug_rotate.get(),
                    "blur": self._aug_blur.get(),
                    "brightness": self._aug_brightness.get(),
                    "crop": self._aug_crop.get()
                },
                progress_callback = prog,
            )
            self.after(0, self._on_export_done, output)
        except Exception as e:
            self.after(0, messagebox.showerror, "Export Failed", str(e))
            self.after(0, self._exp_btn.configure, {"state": "normal"})
            self.after(0, self._exp_progress.configure, {"text": ""})

    def _on_export_done(self, output_path: str):
        self._exp_btn.configure(state="normal")
        self._exp_progress.configure(text=f"✅ Version Created!")
        self.app.set_status(f"Export done → {output_path}")
        messagebox.showinfo(
            "Success!",
            f"Dataset Version saved to:\n{output_path}"
        )


# ═══════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    if sys.platform == "win32":
        # บอก Windows ว่าแอปนี้จัดการ DPI scaling เอง ไม่งั้น Windows จะ
        # scale ภาพที่ Tkinter render ไว้แล้วซ้ำอีกที ทำให้ตัวอักษร/widget
        # เบลอซ้อนกัน และตำแหน่งคลิกไม่ตรงกับตำแหน่งที่เห็นบนจอ
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    app = App()
    app.mainloop()
