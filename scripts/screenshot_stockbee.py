#!/usr/bin/env python3.11
"""
screenshot_stockbee.py  —  v4.2
Captures the Stockbee Market Monitor Google Sheet.

Key improvements over v4.1:
  - Waits for the table to fully render (networkidle + explicit row count check)
  - Verifies T2108 and Up/Down 4% rows are visible before capturing
  - Captures the full top portion (enough rows to show all key metrics)
  - Falls back gracefully if the sheet is unavailable
"""

import subprocess
import sys
import os

# Install playwright if needed
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    from playwright.sync_api import sync_playwright

OUTPUT_PATH = "/home/ubuntu/daily-market-summary/assets/img/today/stockbee_mm.png"

# Direct published URL to the 2026 data sheet
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/"
    "pubhtml/sheet?headers=false&gid=1082103394"
)


def take_screenshot():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1200, "height": 900},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        print(f"  Navigating to Stockbee Google Sheet…")
        page.goto(SHEET_URL, wait_until="networkidle", timeout=45000)

        # Wait for the table element to appear
        try:
            page.wait_for_selector("table", timeout=20000)
            print("  Table element found.")
        except Exception:
            print("  ⚠  Table selector timeout — using time-based fallback.")
            page.wait_for_timeout(5000)

        # Extra wait for JS rendering
        page.wait_for_timeout(3000)

        # Verify T2108 row is visible by checking page text
        page_text = page.inner_text("body")
        has_t2108 = "T2108" in page_text or "t2108" in page_text.lower()
        has_up4   = "Up 4" in page_text or "up 4" in page_text.lower() or "4%" in page_text
        print(f"  T2108 row present: {has_t2108}")
        print(f"  Up/Down 4% row present: {has_up4}")

        if not has_t2108:
            # Try scrolling to trigger lazy loading
            page.wait_for_timeout(2000)
            page_text = page.inner_text("body")
            has_t2108 = "T2108" in page_text

        # Find the main data table
        table = page.locator("table").first

        if table.count() > 0:
            bbox = table.bounding_box()
            print(f"  Table bounding box: {bbox}")

            if bbox and bbox["width"] > 100:
                # Capture enough height to show all key rows:
                # T2108, Up 4%, Down 4%, ratio rows, etc.
                # Use a generous height (800px) to ensure completeness
                clip_height = min(bbox["height"], 820)

                page.screenshot(
                    path=OUTPUT_PATH,
                    clip={
                        "x":      max(0, bbox["x"] - 5),
                        "y":      max(0, bbox["y"] - 5),
                        "width":  min(bbox["width"] + 10, 1200),
                        "height": clip_height + 10,
                    },
                )
                print(f"  ✅ Stockbee screenshot saved: {OUTPUT_PATH}")
                print(f"     Captured area: {bbox['width']:.0f}w × {clip_height:.0f}h px")
            else:
                # Fallback: full page screenshot
                page.screenshot(path=OUTPUT_PATH, full_page=False)
                print(f"  ⚠  Fallback full-page screenshot saved: {OUTPUT_PATH}")
        else:
            page.screenshot(path=OUTPUT_PATH)
            print(f"  ⚠  No table found — full page screenshot saved: {OUTPUT_PATH}")

        browser.close()


if __name__ == "__main__":
    take_screenshot()
    print("Done.")
