# fetch_stockbee_data.py
# Phase 3: 最終版 - click "2026" + 先找 Frame 1 + frame.wait_for_selector("table.waffle")
# Grok 撰寫 | Gemini 邏輯審核 v2 | Manus 部署至 dev
# v3 修正：Gemini + Grok Hybrid Header + 徹底 1-column offset 修正

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
            
            # 在 frame 內等待 waffle table
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
            
            # ── Grok 新增：自動截圖 waffle table（每次 fetch 覆蓋最新） ──
            png_path = os.path.join("assets", "img", "today", "stockbee_mm.png")
            os.makedirs(os.path.dirname(png_path), exist_ok=True)
            try:
                frame.locator("table.waffle").screenshot(path=png_path)
                print(f"DEBUG: \u2705 Stockbee table screenshot \u5df2\u66f4\u65b0 \u2192 {png_path}")
            except Exception as e:
                print(f"DEBUG: \u26a0\ufe0f Screenshot failed (but data still saved): {e}")
            
            rows = table.find_all("tr")
            print(f"DEBUG: waffle table 共有 {len(rows)} 行 tr")
            
            # ── Grok v3 + Gemini 聯合：Hybrid Header + 徹底 1-column offset 修正 ──
            headers = []
            start_row_idx = 2
            
            # 掃描頭 10 行，尋找真正包含 "t2108" 嘅 Header Row
            for idx, row in enumerate(rows[:10]):
                tds = row.find_all(["th", "td"])
                row_texts = [td.get_text(strip=True) for td in tds]
                if any("t2108" in t.lower() for t in row_texts):
                    # 先建 raw headers（空字串補 col_i）
                    raw_headers = [t if t else f"col_{i:02d}" for i, t in enumerate(row_texts)]
                    
                    # === 徹底修正 offset：捨棄第一格 row number label "2" ===
                    if raw_headers and (raw_headers[0].strip().isdigit() or raw_headers[0].strip() in ["", "1", "2", "3"]):
                        headers = raw_headers[1:]   # 直接 shift，讓 "Date" 成為第一個 key
                        print(f"DEBUG: 偵測到 1-column offset，已移除第一格 '{raw_headers[0]}' → headers 已對齊")
                    else:
                        headers = raw_headers
                    
                    start_row_idx = idx + 1
                    print(f"DEBUG: 成功於行 {idx} 找到 Header Row（修正後）: {headers}")
                    break
            
            # Fallback：如果搵唔到 T2108，就用純位置索引
            if not headers:
                print("DEBUG: 找不到包含 T2108 的 Header，啟用純位置索引 Fallback")
                headers = [f"col_{i:02d}" for i in range(100)]
                start_row_idx = 2
            
            # ── Grok v4 + Gemini 聯合：徹底防呆解析（跳過 freezebar 空行） ──
            data = []
            for row_offset, row in enumerate(rows[start_row_idx:]):
                actual_row_idx = start_row_idx + row_offset
                tds = row.find_all("td")
                if len(tds) < 5:
                    continue

                # === 新增防呆：跳過任何沒有 Date 的空行 / freezebar ===
                date_td = tds[0].get_text(strip=True) if tds else ""
                if not date_td or not any(c.isdigit() for c in date_td):  # 空 or 非日期
                    print(f"DEBUG: 跳過空行 / freezebar（Date='{date_td}'）")
                    continue

                row_data = {}
                color_map = {}
                for i, td in enumerate(tds):
                    col_name = headers[i] if i < len(headers) else f"col_{i:02d}"
                    value = td.get_text(strip=True)

                    # 顏色抓取（保留原有）
                    try:
                        cell_element = frame.locator("table tr").nth(actual_row_idx).locator("td").nth(i)
                        bg_color = cell_element.evaluate("el => window.getComputedStyle(el).backgroundColor")
                    except:
                        bg_color = td.get("style", "")

                    if any(x in str(bg_color).lower() for x in ["rgb(0, 128, 0)", "rgb(0, 255, 0)", "#0f0", "green"]):
                        color = "green"
                    elif any(x in str(bg_color).lower() for x in ["rgb(255, 0, 0)", "rgb(220, 20, 60)", "#f00", "red"]):
                        color = "red"
                    else:
                        color = "none"

                    row_data[col_name] = value
                    color_map[col_name] = color

                row_data["colors"] = color_map
                row_data["last_success_time"] = datetime.now().isoformat()
                data.append(row_data)

            print(f"DEBUG: 最終有效數據筆數: {len(data)}（已排除所有空行）")
            
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
                "debug_rows": len(rows),
                "header_found": bool(headers)
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
