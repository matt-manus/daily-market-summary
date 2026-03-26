#!/usr/bin/env python3.11
"""
Capture Finviz Industry 1-Day Performance bar chart.
The #groups div is very tall (17000+ px). We capture a full-page screenshot
and crop to the 1 DAY PERFORMANCE section only.
"""

from playwright.sync_api import sync_playwright
from PIL import Image
import os

OUTPUT = "/home/ubuntu/daily-market-summary/assets/img/today/industry_performance.png"

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 900, "height": 900},
            device_scale_factor=1.5,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Navigating to Finviz Industry Performance Chart...")
        page.goto(
            "https://finviz.com/groups.ashx?g=industry&sg=&o=perf1d&p=d1",
            wait_until="domcontentloaded",
            timeout=30000
        )

        # Wait for the groups div to load
        try:
            page.wait_for_selector("#groups", timeout=15000)
            print("  #groups div found.")
        except:
            print("  #groups not found, proceeding...")

        page.wait_for_timeout(3000)

        # Get the bounding box of #groups via JS
        result = page.evaluate("""() => {
            const el = document.querySelector('#groups');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {
                x: rect.left + window.scrollX,
                y: rect.top + window.scrollY,
                width: rect.width,
                scrollHeight: el.scrollHeight
            };
        }""")
        print(f"  #groups info: {result}")

        if result:
            # The chart has multiple sections (1D, 1W, 1M, 3M, YTD)
            # We only want the 1 DAY PERFORMANCE section
            # Each section is approximately scrollHeight/5 tall
            section_height = result['scrollHeight'] // 5
            # Add some padding for the title
            capture_height = min(section_height + 80, 2200)

            print(f"  Capturing 1D section: {result['width']}x{capture_height} from y={result['y']}")

            # Take a full-page screenshot then crop
            tmp_path = "/tmp/finviz_industry_full.png"
            page.screenshot(path=tmp_path, full_page=True)

            img = Image.open(tmp_path)
            w, h = img.size
            print(f"  Full page size: {w}x{h}")

            # Crop to 1D performance section
            # x: from groups x, width: groups width
            # y: from groups y (in page coords, multiply by device_scale_factor=1.5)
            scale = 1.5
            crop_x = int(result['x'] * scale)
            crop_y = int(result['y'] * scale)
            crop_w = int(result['width'] * scale)
            crop_h = int(capture_height * scale)

            # Ensure within bounds
            crop_x = max(0, crop_x)
            crop_y = max(0, crop_y)
            crop_w = min(crop_w, w - crop_x)
            crop_h = min(crop_h, h - crop_y)

            print(f"  Cropping: ({crop_x}, {crop_y}, {crop_x+crop_w}, {crop_y+crop_h})")
            cropped = img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
            cropped.save(OUTPUT)
            print(f"  ✅ Saved: {OUTPUT} ({cropped.size})")
        else:
            # Fallback: full page screenshot
            page.screenshot(path=OUTPUT, full_page=True)
            print(f"  ⚠️ Full page saved: {OUTPUT}")

        browser.close()

if __name__ == "__main__":
    capture()
    print("Done.")
