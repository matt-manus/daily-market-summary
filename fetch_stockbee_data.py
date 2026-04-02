# fetch_stockbee_data.py
# Phase 3: 最終版 - click "2026" + 先找 Frame 1 + frame.wait_for_selector("table.waffle")
# Grok 撰寫 | 待 Gemini 審核 | Manus 部署至 dev

from playwright.sync_api import sync_playwright
from datetime import datetime
import json
import os
from bs4 import BeautifulSoup

DATA_DIR = "data"
JSON_FILE = os.path.join(DATA_DIR, "stockbee_mm.json")
DEBUG_HTML = os.path.join(DATA_DIR, "stockbee_table_debug.html")

def fetch_stockbee_data():
    url = "https://docs.google.com/spreadsheet/pub?key=0Am_cU8NLIU20dEhiQnVHN3Nnc3B1S3J6eGhKZFo0N3c&output=html&widget=true"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # 點擊 "2026" tab
            page.wait_for_selector('text="2026"', timeout=15000)
            page.get_by_text("2026", exact=True).first.click()
            print("DEBUG: 已點擊 '2026' tab")
            
            # 等 iframe 載入
            page.wait_for_timeout(3000)
            
            # 找 Frame 1 (Google Sheets iframe)
            frames = page.frames
            print(f"DEBUG: 頁面共有 {len(frames)} 個 frame")
            frame = None
            for f in frames:
                if f.url and "pubhtml/sheet" in f.url:
                    frame = f
                    print(f"DEBUG: 選中 Frame 1 (URL 包含 pubhtml/sheet)")
                    break
            if not frame:
                raise ValueError("Frame 1 (iframe) not found")
            
            # 在 frame 內等待 waffle table（關鍵修正）
            frame.wait_for_selector("table.waffle", timeout=15000)
            print("DEBUG: Frame 1 內 waffle table 已出現")
            
            # 從 frame 抓 HTML + 顏色
            html = frame.content()
            soup = BeautifulSoup(html, "html.parser")
            
            table = soup.find("table", class_="waffle")
            if not table or len(table.find_all("tr")) < 10:
                raise ValueError("waffle table not found in Frame 1")
            
            # DEBUG 保存
            with open(DEBUG_HTML, "w", encoding="utf-8") as f:
                f.write(str(table))
            
            rows = table.find_all("tr")
            print(f"DEBUG: waffle table 共有 {len(rows)} 行 tr")
            
            # header
            headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
            
            data = []
            row_idx = 0
            for row in rows[2:]:
                tds = row.find_all("td")
                if len(tds) < 5:
                    continue
                
                row_data = {}
                color_map = {}
                for i, td in enumerate(tds):
                    col_name = headers[i] if i < len(headers) else f"col_{i}"
                    value = td.get_text(strip=True)
                    
                    try:
                        cell_element = frame.locator("table tr").nth(row_idx + 2).locator("td").nth(i)
                        bg_color = cell_element.evaluate("el => window.getComputedStyle(el).backgroundColor")
                    except:
                        bg_color = td.get("style", "")
                    
                    if any(x in str(bg_color).lower() for x in ["rgb(0, 128, 0)", "rgb(0, 255, 0)", "#0f0", "green"]):
                        color = "green"
                    elif any(x in str(bg_color).lower() for x in ["rgb(255, 0, 0)", "rgb(220, 20, 60)", "#f00", "red"]):
                        color = "red"
                    elif "rgb(0, 0, 0)" in str(bg_color).lower():
                        color = "black"
                    else:
                        color = "none"
                    
                    row_data[col_name] = value
                    color_map[col_name] = color
                
                row_data["colors"] = color_map
                row_data["last_success_time"] = datetime.now().isoformat()
                data.append(row_data)
                row_idx += 1
            
            browser.close()
            
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return {
                "status": "success",
                "records": len(data),
                "last_success_time": datetime.now().isoformat(),
                "file": JSON_FILE,
                "data_stale": False,
                "debug_frames": len(frames),
                "debug_rows": len(rows)
            }
            
    except Exception as e:
        error_result = {
            "status": "error",
            "error_code": "FRAME_PARSE_FAILED",
            "error": str(e),
            "last_success_time": datetime.now().isoformat(),
            "data_stale": True
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump([error_result], f, ensure_ascii=False, indent=2)
        return error_result

if __name__ == "__main__":
    result = fetch_stockbee_data()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n✅ JSON 已儲存至 {JSON_FILE}")
    print(f"DEBUG HTML 已儲存至 data/stockbee_table_debug.html（請 paste 前 50 行返畀我）")
