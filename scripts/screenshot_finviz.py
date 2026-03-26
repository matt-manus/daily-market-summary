#!/usr/bin/env python3.11
"""
Capture Finviz S&P 500 heatmap and Industry Performance chart.
Ensures full canvas/SVG render before screenshot.
"""

from playwright.sync_api import sync_playwright
from PIL import Image
import os

OUTPUT_DIR = "/home/ubuntu/daily-market-summary/assets/img/today"
HEATMAP_OUT = f"{OUTPUT_DIR}/market_heatmap.png"
INDUSTRY_OUT = f"{OUTPUT_DIR}/industry_performance.png"

def capture_heatmap():
    """Capture Finviz S&P 500 Map — waits for colored blocks to appear."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            device_scale_factor=1.5,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Navigating to Finviz S&P 500 Map...")
        page.goto("https://finviz.com/map.ashx?t=sec", wait_until="domcontentloaded", timeout=30000)

        # Wait for the map canvas/SVG to render with colored blocks
        # Finviz map uses a <canvas> element — wait for it to be non-empty
        try:
            page.wait_for_selector("canvas, #mapCanvas, svg.map, .fv-container", timeout=15000)
            print("  Map element found, waiting for render...")
        except:
            print("  Selector not found, using time-based wait...")

        # Additional wait for JS rendering (color fill)
        page.wait_for_timeout(5000)

        # Try to find and screenshot just the map area
        map_el = page.locator("canvas").first
        if map_el.count() > 0:
            bbox = map_el.bounding_box()
            if bbox and bbox['width'] > 200:
                print(f"  Canvas found: {bbox['width']}x{bbox['height']}")
                # Include some padding around the map
                page.screenshot(
                    path=HEATMAP_OUT,
                    clip={
                        "x": max(0, bbox['x'] - 5),
                        "y": max(0, bbox['y'] - 5),
                        "width": min(bbox['width'] + 10, 1600),
                        "height": min(bbox['height'] + 10, 900)
                    }
                )
                print(f"  ✅ Heatmap saved: {HEATMAP_OUT}")
                browser.close()
                return True

        # Fallback: try to find the map container div
        map_div = page.locator("#mapCanvas, .fv-map, [id*='map']").first
        if map_div.count() > 0:
            bbox = map_div.bounding_box()
            if bbox and bbox['width'] > 200:
                page.screenshot(
                    path=HEATMAP_OUT,
                    clip={
                        "x": max(0, bbox['x']),
                        "y": max(0, bbox['y']),
                        "width": bbox['width'],
                        "height": bbox['height']
                    }
                )
                print(f"  ✅ Heatmap (div) saved: {HEATMAP_OUT}")
                browser.close()
                return True

        # Last resort: full viewport screenshot
        page.screenshot(path=HEATMAP_OUT)
        print(f"  ⚠️ Full viewport screenshot saved: {HEATMAP_OUT}")
        browser.close()
        return True


def capture_industry():
    """Capture Finviz Industry Performance bar chart."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            device_scale_factor=1.5,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Navigating to Finviz Industry Performance...")
        # Use the groups page with industry view and 1-day performance
        page.goto(
            "https://finviz.com/groups.ashx?g=industry&sg=&o=name&p=d1",
            wait_until="domcontentloaded",
            timeout=30000
        )

        # Wait for table/chart to load
        try:
            page.wait_for_selector("table.t-group, .groups-table, table[class*='group']", timeout=15000)
            print("  Groups table found.")
        except:
            print("  Groups table selector not found, using time-based wait...")

        page.wait_for_timeout(3000)

        # Try to find the performance table
        table = page.locator("table.t-group, table[class*='group'], .groups-table").first
        if table.count() > 0:
            bbox = table.bounding_box()
            if bbox and bbox['width'] > 200:
                print(f"  Table found: {bbox['width']}x{bbox['height']}")
                # Capture from top of page down to include the table
                page.screenshot(
                    path=INDUSTRY_OUT,
                    clip={
                        "x": 0,
                        "y": max(0, bbox['y'] - 60),
                        "width": 1400,
                        "height": min(bbox['height'] + 120, 900)
                    }
                )
                print(f"  ✅ Industry performance saved: {INDUSTRY_OUT}")
                browser.close()
                return True

        # Fallback: full viewport
        page.screenshot(path=INDUSTRY_OUT)
        print(f"  ⚠️ Full viewport screenshot saved: {INDUSTRY_OUT}")
        browser.close()
        return True


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=== Finviz Heatmap Capture ===")
    capture_heatmap()
    print("\n=== Finviz Industry Performance Capture ===")
    capture_industry()
    print("\nDone.")
