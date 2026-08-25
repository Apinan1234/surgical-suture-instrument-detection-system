# -*- coding: utf-8 -*-
"""Design system ของสไลด์ เขียนเป็นโค้ด — ที่มา: SLIDE-BRIEF.md ส่วนที่ 3

สีทุกค่ายึดจาก webapp/static/style.css ของตัวผลิตภัณฑ์เอง เพื่อให้สไลด์กับระบบเป็นชุดเดียวกัน
ฟอนต์เลือก Leelawadee UI เพราะมากับ Windows ทุกเครื่อง (IBM Plex Sans Thai / Noto Sans Thai
ไม่ได้ติดตั้งบนเครื่องนี้ และเครื่องห้องสอบก็ไม่มีแน่นอน — ฟอนต์หายทำ layout พังทั้งแผ่น)
"""
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

# ── สี 7 บทบาท ────────────────────────────────────────────────────────────────
ACCENT   = RGBColor(0xE9, 0x45, 0x60)   # ตัวเลขหัวข่าว เส้นเน้น
INK      = RGBColor(0x1A, 0x1A, 0x2E)   # ตัวอักษรหลัก / พื้นสไลด์คั่นบท
NAVY     = RGBColor(0x16, 0x21, 0x3E)   # พื้นการ์ด แถบหัว
NAVY2    = RGBColor(0x0F, 0x34, 0x60)   # หัวตาราง
SURFACE  = RGBColor(0xF5, 0xF6, 0xFA)   # พื้นการ์ดอ่อน
WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
MUTED    = RGBColor(0x5C, 0x6B, 0x7A)   # ข้อความรอง / ที่มาของตัวเลข
GREEN    = RGBColor(0x2F, 0x9E, 0x78)   # ค่าที่ดีขึ้น
ORANGE   = RGBColor(0xC9, 0x7A, 0x00)   # ข้อควรระวัง ข้อจำกัด
HAIRLINE = RGBColor(0xD8, 0xDD, 0xE6)   # เส้นคั่นบาง

# ── ฟอนต์และสเกล (pt) ────────────────────────────────────────────────────────
FONT = "Leelawadee UI"
FONT_MONO = "Consolas"

SZ_TITLE     = 32
SZ_SUBTITLE  = 21
SZ_BODY      = 16
SZ_BODY_SM   = 14
SZ_NOTE      = 11
SZ_SOURCE    = 9
SZ_NUMBER    = 66
SZ_METRIC    = 40
SZ_TABLE     = 12
SZ_EYEBROW   = 11

# ── เรขาคณิตของสไลด์ 16:9 ────────────────────────────────────────────────────
SLIDE_W = 13.333
SLIDE_H = 7.5
MARGIN  = 0.70
CONTENT_W = SLIDE_W - 2 * MARGIN

EYEBROW_Y = 0.34
TITLE_Y   = 0.60
TITLE_H   = 0.62
RULE_Y    = 1.30
BODY_Y    = 1.58
BODY_H    = 5.05
SOURCE_Y  = 6.90

# สีธีมที่จะยัดลง theme1.xml เพื่อให้แถบเลือกสีของ PowerPoint เป็นชุดเดียวกับสไลด์
THEME_COLORS = {
    "dk1": "1A1A2E", "lt1": "FFFFFF", "dk2": "16213E", "lt2": "F5F6FA",
    "accent1": "E94560", "accent2": "0F3460", "accent3": "2F9E78",
    "accent4": "C97A00", "accent5": "5C6B7A", "accent6": "16213E",
    "hlink": "0F3460", "folHlink": "5C6B7A",
}
