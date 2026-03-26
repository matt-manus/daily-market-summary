#!/usr/bin/env python3.11
"""
Retry IWM chart screenshot with longer timeout and precise crop.
"""

from playwright.sync_api import sync_playwright

OUTPUT = "/home/ubuntu/daily-market-summary/assets/img/today/iwm_trend.png"
URL = "https://stockcharts.com/h-sc/ui?s=IWM&p=D&yr=1&mn=0&dy=0&id=p94683309306"

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 800, "height": 500},
            device_scale_factor=2
        )
        page = context.new_page()
        
        print(f"Navigating to IWM chart (60s timeout)...")
        try:
            # Use domcontentloaded instead of networkidle for faster load
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            # Wait for chart image to appear
            page.wait_for_selector("#chartImg, img[id*='chart']", timeout=20000)
            page.wait_for_timeout(2000)
            
            chart_img = page.locator("#chartImg").first
            if chart_img.count() > 0:
                bbox = chart_img.bounding_box()
                if bbox and bbox['width'] > 100:
                    page.screenshot(
                        path=OUTPUT,
                        clip={
                            "x": bbox['x'],
                            "y": bbox['y'],
                            "width": bbox['width'],
                            "height": bbox['height']
                        }
                    )
                    print(f"✅ IWM chart captured: {OUTPUT} ({bbox['width']}x{bbox['height']})")
                    browser.close()
                    return
        except Exception as e:
            print(f"Attempt 1 failed: {e}")
        
        # Fallback: try with load event
        try:
            page.goto(URL, wait_until="load", timeout=45000)
            page.wait_for_timeout(3000)
            
            # Try to find and crop chart element
            chart_img = page.locator("#chartImg").first
            if chart_img.count() > 0:
                bbox = chart_img.bounding_box()
                if bbox and bbox['width'] > 100:
                    page.screenshot(
                        path=OUTPUT,
                        clip={
                            "x": bbox['x'],
                            "y": bbox['y'],
                            "width": bbox['width'],
                            "height": bbox['height']
                        }
                    )
                    print(f"✅ IWM chart (fallback) captured: {OUTPUT}")
                    browser.close()
                    return
            
            # Last resort: crop the known chart area from full page
            page.screenshot(path=OUTPUT)
            print(f"⚠️ Full page screenshot saved: {OUTPUT}")
        except Exception as e:
            print(f"Attempt 2 failed: {e}")
        
        browser.close()

if __name__ == "__main__":
    capture()
