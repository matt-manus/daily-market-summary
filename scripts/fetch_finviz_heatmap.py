#!/usr/bin/env python3
"""
scripts/fetch_finviz_heatmap.py
Phase 3.9 - 動態抓取 Finviz S&P 500 Market Heatmap
已修正路徑 → 匹配 render_report.py + template 使用的 assets/img/today/
（Step 4 patch：selector 保留 Step 1 已驗證的 #map 精準版本）
"""

import os
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def fetch_finviz_heatmap():
    # === 關鍵修正：使用 render_report.py 期望的傳統路徑 ===
    output_path = "assets/img/today/market_heatmap.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            print("🌐 正在訪問 Finviz Heatmap...")
            page.goto("https://finviz.com/map.ashx?t=sec", wait_until="domcontentloaded")

            print("⏳ 等待 Heatmap 元素載入...")
            # Step 1 已驗證：#map 係正確 heatmap 容器，優先使用
            try:
                page.wait_for_selector("#map", timeout=30000)
            except PlaywrightTimeoutError:
                # fallback: 等待 canvas 或 svg
                page.wait_for_selector("canvas, #map-svg", timeout=15000)

            # 處理 Cookie 彈窗
            try:
                consent_selectors = ["button:has-text('Accept')", "#onetrust-accept-btn-handler", ".cc-accept-all"]
                for selector in consent_selectors:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        print("🍪 已自動關閉 Cookie 彈窗")
                        page.wait_for_timeout(2000)
                        break
            except:
                pass

            page.wait_for_timeout(5000)

            # 精準截圖：優先用 #map（Step 1 已驗證正確）
            saved = False
            if page.locator("#map").count() > 0:
                print("📸 正在截取 #map Heatmap 區域...")
                page.locator("#map").screenshot(path=output_path)
                print(f"✅ 成功儲存 (#map): {output_path}")
                saved = True
            else:
                # fallback: canvas.chart
                fallback_sel = "canvas.chart"
                if page.locator(fallback_sel).count() > 0:
                    print(f"📸 fallback 截取 {fallback_sel}...")
                    page.locator(fallback_sel).first.screenshot(path=output_path)
                    print(f"✅ 成功儲存 (fallback): {output_path}")
                    saved = True
                else:
                    print("⚠️ 使用全頁 fallback")
                    page.screenshot(path=output_path)
                    print(f"✅ 全頁截圖儲存: {output_path}")
                    saved = True

            hkt = pytz.timezone('Asia/Hong_Kong')
            last_modified = datetime.now(hkt).strftime("%Y-%m-%d %H:%M")
            print(f"🕒 Last Data: {last_modified} HKT")

            browser.close()
            return saved

    except Exception as e:
        print(f"❌ Fetch Finviz Heatmap 失敗: {str(e)}")
        print("🚫 舊圖不會被覆蓋")
        return False

if __name__ == "__main__":
    success = fetch_finviz_heatmap()
    if success:
        print("\n🎉 fetch_finviz_heatmap.py 執行完成！")
    else:
        print("\n🔴 請檢查網路或 Playwright")
