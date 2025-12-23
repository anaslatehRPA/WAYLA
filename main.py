
import requests
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
import os


# --- 1. ตั้งค่าการเข้าสู่ระบบ ---
# ดึงค่าจาก GitHub Secrets
USER = os.getenv("MY_USER")
PASSWORD = os.getenv("MY_PASSWORD")
LINE_TOKEN = os.getenv("LINE_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

def send_line_message(text):
    """ฟังก์ชันส่งข้อความเข้า LINE Messaging API"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("✅ ส่ง LINE สำเร็จ")
        else:
            print(f"❌ ส่ง LINE ไม่สำเร็จ: {response.text}")
    except Exception as e:
        print(f"⚠️ เกิดข้อผิดพลาดในการส่ง LINE: {e}")

def clean_and_format(table_data):
    """ฟังก์ชันจัดระเบียบข้อมูลให้ตรงตามคอลัมน์จริง"""
    summary = {
        "target": "0",
        "total_hours": "0",
        "total_days": "0",
        "late_min": "0",
        "absent_hours": "0",
        "absent_times": "0"
    }

    for row in table_data:
        name = row[0].upper()
        
        # 1. ชั่วโมงเป้าหมาย
        if "ชั่วโมงการทำงานรายเดือน" in name:
            summary["target"] = row[1]
            
        # 2. สรุปชั่วโมงทำงานรวม
        elif "TOTAL WORKING HOURS" in name:
            summary["total_hours"] = row[1] # 107.95
            summary["total_days"] = row[2]  # 13 วัน
            
        # 3. เข้าสาย
        elif "เข้าสาย" in name:
            summary["late_min"] = row[1]    # 0
            
        # 4. ขาดงาน (คอลัมน์ 1 คือ ชม. / คอลัมน์ 2 คือ ครั้ง)
        elif "ขาดงาน" in name:
            summary["absent_hours"] = row[1] # 16
            summary["absent_times"] = row[2] # 2

    # --- ออกแบบข้อความใหม่ ---
    date_now = datetime.now().strftime("%d/%m/%Y")
    msg = f"📊 สรุปประวัติงาน {date_now}\n"
    msg += "━━━━━━━━━━━━━━━\n"
    msg += f"🎯 เป้าหมายเดือนนี้: {summary['target']} ชม.\n"
    msg += f"🕒 ทำงานไปแล้ว: {summary['total_hours']} ชม.\n"
    msg += f"📅 จำนวนวันที่ทำ: {summary['total_days']} วัน\n"
    
    # เช็คสาย
    late_val = int(summary["late_min"]) if summary["late_min"].isdigit() else 0
    if late_val > 0:
        msg += f"🚨 เข้าสาย: {late_val} นาที\n"
    else:
        msg += "✅ ไม่มีเข้าสาย\n"
        
    # เช็คขาดงาน (แสดงทั้ง ครั้ง และ ชั่วโมง)
    absent_t = int(summary["absent_times"]) if summary["absent_times"].isdigit() else 0
    absent_h = summary["absent_hours"]
    if absent_t > 0:
        msg += f"❌ ขาดงาน: {absent_t} ครั้ง ({absent_h} ชม.)\n"
    else:
        msg += "✅ ไม่มีขาดงาน\n"
    
    msg += "━━━━━━━━━━━━━━━\n"
    msg += "ระบบส่งข้อมูลอัตโนมัติ"
    
    return msg

def run():
    with sync_playwright() as p:
        # เปิด Browser (ถ้าใช้งานจริงใน Task Scheduler ให้แก้เป็น headless=True)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            # 1. เข้าหน้า Login
            print("1. กำลัง Login...")
            page.goto("https://sts.siphhospital.com/adfs/ls/IdpInitiatedSignOn.aspx?LoginToRp=https://SIPH.myhumatrix.com&li=1")
            page.fill("input[name='UserName']", USER)
            page.fill("input[name='Password']", PASSWORD)
            page.click("#submitButton")
            
            # 2. รอการ Redirect (จุดที่สำคัญที่สุด)
            print("รอระบบยืนยันตัวตน...")
            time.sleep(5) # ดีเลย์ตามที่คุณแจ้งว่าต้องรอ
            
            # 3. ไปหน้า My Calendar
            print("2. ไปหน้า My Calendar...")
            page.goto("https://siph.myhumatrix.com/ESS/ETime/Hospital/MyCalendar.aspx")
            
            # รอหน้าเว็บและ Frame โหลด
            time.sleep(7) 

            # 4. ค้นหาตารางในทุก Frame
            target_frame = None
            for frame in page.frames:
                if frame.locator("table.tbActualSummary").count() > 0:
                    target_frame = frame
                    break

            if target_frame:
                print("3. ดึงข้อมูลตาราง...")
                table_data = target_frame.evaluate("""
                    () => {
                        const table = document.querySelector('table.tbActualSummary');
                        const rows = Array.from(table.querySelectorAll('tr'));
                        return rows.map(row => {
                            const cells = Array.from(row.querySelectorAll('td'));
                            return cells.map(cell => cell.innerText.trim());
                        }).filter(row => row.some(c => c !== ""));
                    }
                """)

                # 5. Clean ข้อมูลและส่ง LINE
                formatted_message = clean_and_format(table_data)
                print("\n--- ข้อความที่จะส่ง ---")
                print(formatted_message)
                
                send_line_message(formatted_message)
            else:
                print("❌ ไม่พบตารางข้อมูล")
                page.screenshot(path="not_found.png")

        except Exception as e:
            error_msg = f"⚠️ โปรแกรม RPA ผิดพลาด: {str(e)}"
            print(error_msg)
            # send_line_message(error_msg) # เลือกเปิดถ้าอยากให้แจ้งเตือนแม้ตอนโปรแกรมพัง

        finally:
            browser.close()
            print("ปิดโปรแกรมเรียบร้อย")

if __name__ == "__main__":
    run()