#!/usr/bin/env python3
"""
scripts/fetch_finviz_heatmap.py
Phase 3.9 - 動態抓取 Finviz S&P 500 Market Heatmap
"""
import os
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def fetch_finviz_heatmap():
    output_path = "assets/images/market_heatmap.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1600, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            print("🌐 正在訪問 Finviz Heatmap...")
            page.goto("https://finviz.com/map.ashx?t=sec", wait_until="domcontentloaded")
            print("⏳ 等待 Heatmap 元素載入...")
            page.wait_for_selector("canvas, #map-svg, #map", timeout=30000)
            # 處理 Cookie
            try:
                consent = ["button:has-text('Accept')", "#onetrust-accept-btn-handler", ".cc-accept-all"]
                for sel in consent:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click()
                        print("🍪 已關閉 Cookie")
                        page.wait_for_timeout(2000)
                        break
            except:
                pass
            page.wait_for_timeout(5000)
            # 優先用 #map（已確認係正確 heatmap 容器）
            heatmap = page.locator("#map")
            if heatmap.count() > 0:
                heatmap.screenshot(path=output_path)
                print(f"✅ 成功儲存 (#map): {output_path}")
            else:
                # Fallback: 用 canvas.chart（排除廣告）
                chart_canvas = page.locator("canvas.chart")
                if chart_canvas.count() > 0:
                    chart_canvas.first.screenshot(path=output_path)
                    print(f"✅ 成功儲存 (canvas.chart): {output_path}")
                else:
                    page.screenshot(path=output_path)
                    print(f"✅ 成功儲存 (full page): {output_path}")
            hkt = pytz.timezone('Asia/Hong_Kong')
            print(f"🕒 Last Data: {datetime.now(hkt).strftime('%Y-%m-%d %H:%M')} HKT")
            browser.close()
            return True
    except Exception as e:
        print(f"❌ 失敗: {str(e)}")
        print("🚫 舊圖不會被覆蓋")
        return False

if __name__ == "__main__":
    success = fetch_finviz_heatmap()
    if success:
        print("\n🎉 fetch_finviz_heatmap.py 完成")
