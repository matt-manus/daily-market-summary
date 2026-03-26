#!/usr/bin/env python3.11
"""
Capture SPY, QQQ, DIA, IWM daily chart screenshots with 20/50/200 MA from StockCharts.
Viewport: 800x500 per MASTER_INSTRUCTION.md spec.
Output: assets/img/today/{ticker}_trend.png
"""

from playwright.sync_api import sync_playwright
import time

OUTPUT_DIR = "/home/ubuntu/daily-market-summary/assets/img/today"

# StockCharts URLs with 20/50/200 MA overlay (p94683309306 = standard MA chart style)
CHARTS = [
    {
        "ticker": "SPY",
        "url": "https://stockcharts.com/h-sc/ui?s=SPY&p=D&yr=1&mn=0&dy=0&id=p94683309306",
        "output": f"{OUTPUT_DIR}/spy_trend.png"
    },
    {
        "ticker": "QQQ",
        "url": "https://stockcharts.com/h-sc/ui?s=QQQ&p=D&yr=1&mn=0&dy=0&id=p94683309306",
        "output": f"{OUTPUT_DIR}/qqq_trend.png"
    },
    {
        "ticker": "DIA",
        "url": "https://stockcharts.com/h-sc/ui?s=DIA&p=D&yr=1&mn=0&dy=0&id=p94683309306",
        "output": f"{OUTPUT_DIR}/dia_trend.png"
    },
    {
        "ticker": "IWM",
        "url": "https://stockcharts.com/h-sc/ui?s=IWM&p=D&yr=1&mn=0&dy=0&id=p94683309306",
        "output": f"{OUTPUT_DIR}/iwm_trend.png"
    }
]

def capture_charts():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 800, "height": 500},
            device_scale_factor=2  # Retina quality
        )
        page = context.new_page()
        
        for chart in CHARTS:
            ticker = chart["ticker"]
            url = chart["url"]
            output = chart["output"]
            
            print(f"Capturing {ticker} chart...")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                # Wait for chart to render
                page.wait_for_timeout(3000)
                
                # Try to find the chart image element
                chart_img = page.locator("#chartImg, img[id*='chart'], .chart-container img").first
                
                if chart_img and chart_img.count() > 0:
                    bbox = chart_img.bounding_box()
                    if bbox and bbox['width'] > 100:
                        page.screenshot(
                            path=output,
                            clip={
                                "x": bbox['x'],
                                "y": bbox['y'],
                                "width": bbox['width'],
                                "height": bbox['height']
                            }
                        )
                        print(f"  ✅ Chart element screenshot: {output} ({bbox['width']}x{bbox['height']})")
                        continue
                
                # Fallback: full viewport screenshot
                page.screenshot(path=output)
                print(f"  ✅ Full viewport screenshot: {output}")
                
            except Exception as e:
                print(f"  ❌ Error capturing {ticker}: {e}")
                # Try full page screenshot as last resort
                try:
                    page.screenshot(path=output)
                    print(f"  ⚠️ Fallback screenshot saved: {output}")
                except:
                    pass
        
        browser.close()
        print("\nAll charts captured.")

if __name__ == "__main__":
    capture_charts()
