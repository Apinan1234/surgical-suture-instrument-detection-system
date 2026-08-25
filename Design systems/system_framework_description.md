# System Framework Diagram — เนื้อหาที่แยกจากภาพ

ไฟล์ภาพต้นฉบับ: `system_framework_diagram.png` (1271x481px) — คัดลอกไว้ในโฟลเดอร์ outputs แล้ว

## หัวข้อ
**SYSTEM FRAMWORK** (ต้นฉบับสะกดแบบนี้ ขาด e — น่าจะหมายถึง "SYSTEM FRAMEWORK")

## เนื้อหาแผนภาพ (Flow Diagram)

แผนภาพแสดง data flow จากซ้ายไปขวา 4 องค์ประกอบหลัก:

```
[Emotibit] --Send Signal--> [Database] --Model API--> [Dashboard]
                                 |                          ^
                                 +------Sensor API----------+
```

### รายละเอียดแต่ละองค์ประกอบ

1. **Emotibit** (ซ้ายสุด)
   - รูปภาพ: อุปกรณ์เซ็นเซอร์สวมข้อมือ (wearable sensor board) รัดอยู่บนแขนคน
   - ลูกศรออกจากจุดนี้ไปยัง Database พร้อม label **"Send Signal"**

2. **Database** (กลาง)
   - รูปไอคอน: ทรงกระบอกฐานข้อมูล (database cylinder icon) สีฟ้า
   - รับข้อมูลจาก Emotibit ผ่าน "Send Signal"
   - ส่งข้อมูลออกสองทางไปยัง Dashboard:
     - เส้นบน label **"Model API"**
     - เส้นล่าง label **"Sensor API"**

3. **Dashboard** (ขวาสุด, สะกดในภาพว่า "Dashboad" — ขาด r)
   - รูปไอคอน: หน้าจอคอมพิวเตอร์แสดงกราฟ/ชาร์ต (pie chart, bar chart, line chart) พร้อมไอคอนเฟือง (settings gear) อยู่มุมขวาบน
   - รับข้อมูลจาก Database ผ่านสองเส้นทาง: Model API (บน) และ Sensor API (ล่าง)

## สรุป Flow แบบข้อความ (สำหรับใช้เขียนโค้ด/สถาปัตยกรรมระบบ)

- **Emotibit** → ส่งสัญญาณ (สรีรวิทยา/เซ็นเซอร์) เข้าสู่ → **Database**
- **Database** → เชื่อมกับ **Dashboard** ผ่าน 2 เส้นทาง API แยกกัน:
  - **Model API**: สำหรับดึงผลลัพธ์จากโมเดล (เช่น การพยากรณ์/วิเคราะห์)
  - **Sensor API**: สำหรับดึงข้อมูลเซ็นเซอร์ดิบ/ประมวลผลแล้ว
- **Dashboard**: แสดงผลข้อมูลเป็นกราฟ/ชาร์ตต่างๆ พร้อมมีส่วนตั้งค่า (gear icon)

## หมายเหตุการสะกดคำในภาพต้นฉบับ
- "FRAMWORK" → ควรเป็น "FRAMEWORK"
- "Dashboad" → ควรเป็น "Dashboard"
