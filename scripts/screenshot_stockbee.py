#!/usr/bin/env python3.11
"""
Screenshot the Stockbee Market Monitor Google Sheets iframe data table.
Targets the top portion of the 2026 data sheet showing T2108, Up/Down 4%, ratios.
"""

import subprocess
import sys

# Install playwright if needed
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    from playwright.sync_api import sync_playwright

import os

OUTPUT_PATH = "/home/ubuntu/daily-market-summary/assets/img/today/stockbee_mm.png"

# Direct URL to the 2026 sheet (inner iframe content)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/pubhtml/sheet?headers=false&gid=1082103394"

def take_screenshot():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1100, "height": 800},
            device_scale_factor=1.5  # Higher DPI for crisp text
        )
        page = context.new_page()
        
        print(f"Navigating to: {SHEET_URL}")
        page.goto(SHEET_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Find the main data table
        # The table contains the market monitor data
        table = page.locator("table").first
        
        if table:
            # Get bounding box of the table
            bbox = table.bounding_box()
            print(f"Table bounding box: {bbox}")
            
            if bbox:
                # Capture only the top portion showing recent data + headers
                # Limit height to show ~20 rows (headers + ~18 data rows)
                clip_height = min(bbox['height'], 620)  # ~20 rows
                
                page.screenshot(
                    path=OUTPUT_PATH,
                    clip={
                        "x": max(0, bbox['x'] - 5),
                        "y": max(0, bbox['y'] - 5),
                        "width": min(bbox['width'] + 10, 1100),
                        "height": clip_height + 10
                    }
                )
                print(f"Screenshot saved: {OUTPUT_PATH}")
            else:
                # Fallback: full page screenshot
                page.screenshot(path=OUTPUT_PATH, full_page=False)
                print(f"Fallback screenshot saved: {OUTPUT_PATH}")
        else:
            page.screenshot(path=OUTPUT_PATH)
            print(f"No table found, full page screenshot saved: {OUTPUT_PATH}")
        
        browser.close()

if __name__ == "__main__":
    take_screenshot()
    print("Done.")
