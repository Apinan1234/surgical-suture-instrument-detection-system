# -*- coding: utf-8 -*-
"""สร้างไฟล์ .pptx จาก content_webapp_demo.py — ชุดแยก "สาธิตเว็บแอป + สรุปผลการดำเนินงาน"

    python build_webapp_demo_deck.py

ไม่แตะ content.py/build_deck.py/verify_deck.py หรือ .pptx หลัก (102 สไลด์) เลย — ใช้ theme.py/
layouts.py ชุดเดียวกัน และ reuse inject_theme()/check_bounds() จาก build_deck.py ตรงๆ
"""
import os
import sys

from pptx import Presentation
from pptx.util import Inches

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme as T                  # noqa: E402
import layouts as L                # noqa: E402
import content_webapp_demo         # noqa: E402
import build_deck as B             # noqa: E402  (reuse inject_theme/check_bounds)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "สาธิตเว็บแอปและสรุปผล-โครงงาน2.pptx")


def main():
    prs = Presentation()
    prs.slide_width = Inches(T.SLIDE_W)
    prs.slide_height = Inches(T.SLIDE_H)
    B.inject_theme(prs)

    content_webapp_demo.build(prs)

    total = 0
    for i, slide in enumerate(prs.slides, 1):
        total = i
        if i > 1:
            L.page_number(slide, i)

    prs.save(OUT)
    print("บันทึกแล้ว: %s" % OUT)
    print("จำนวนสไลด์: %d  ·  ขนาดไฟล์: %.1f MB" % (total, os.path.getsize(OUT) / 1e6))

    bad = B.check_bounds(prs)
    if bad:
        print("\n!! วัตถุล้นขอบสไลด์ %d จุด:" % len(bad))
        for s, st, name, why in bad:
            print("   สไลด์ %-3d %-22s %s" % (s, name, why))
    else:
        print("ตรวจขอบสไลด์: ไม่มีวัตถุล้นกรอบ")


if __name__ == "__main__":
    main()
