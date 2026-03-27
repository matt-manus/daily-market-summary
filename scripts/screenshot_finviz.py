#!/usr/bin/env python3.11
"""
screenshot_finviz.py  —  v4.3
Captures Finviz S&P 500 heatmap and Industry Performance Top 10 chart.

Key improvements over v4.2:
  - Heatmap: waits for canvas to be non-empty (pixel check via JS)
  - Industry: uses JS to extract bar positions and crops Top 10 area
  - Industry: falls back to a rendered HTML table if chart capture fails
"""

from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont
import os, re, json

OUTPUT_DIR   = "/home/ubuntu/daily-market-summary/assets/img/today"
HEATMAP_OUT  = f"{OUTPUT_DIR}/market_heatmap.png"
INDUSTRY_OUT = f"{OUTPUT_DIR}/industry_performance.png"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def capture_heatmap():
    """Capture Finviz S&P 500 Map — waits for canvas to be fully colored."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            device_scale_factor=1.5,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print("  Navigating to Finviz S&P 500 Map…")
        page.goto(
            "https://finviz.com/map.ashx?t=sec",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # Wait for the canvas element
        try:
            page.wait_for_selector("canvas, #mapCanvas, svg.map, .fv-container", timeout=20000)
            print("  Map element found.")
        except Exception:
            print("  ⚠  Map selector timeout — using time-based wait.")

        # Wait for JS to fill the canvas with colored blocks
        print("  Waiting for canvas to render colored blocks…")
        canvas_ready = False
        for attempt in range(12):
            page.wait_for_timeout(1000)
            try:
                result = page.evaluate("""() => {
                    const canvas = document.querySelector('canvas');
                    if (!canvas) return false;
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return false;
                    const w = canvas.width, h = canvas.height;
                    if (w < 100 || h < 100) return false;
                    const data = ctx.getImageData(w/4, h/4, w/2, h/2).data;
                    let nonWhite = 0;
                    for (let i = 0; i < data.length; i += 4) {
                        const r = data[i], g = data[i+1], b = data[i+2];
                        if (!(r > 240 && g > 240 && b > 240) && !(r < 15 && g < 15 && b < 15)) {
                            nonWhite++;
                        }
                    }
                    return nonWhite > 1000;
                }""")
                if result:
                    print(f"  Canvas has colored blocks (attempt {attempt + 1}).")
                    canvas_ready = True
                    break
            except Exception:
                pass

        if not canvas_ready:
            print("  ⚠  Canvas pixel check inconclusive — proceeding anyway.")

        page.wait_for_timeout(2000)

        map_el = page.locator("canvas").first
        if map_el.count() > 0:
            bbox = map_el.bounding_box()
            if bbox and bbox["width"] > 200:
                print(f"  Canvas: {bbox['width']:.0f}w × {bbox['height']:.0f}h")
                page.screenshot(
                    path=HEATMAP_OUT,
                    clip={
                        "x":      max(0, bbox["x"] - 5),
                        "y":      max(0, bbox["y"] - 5),
                        "width":  min(bbox["width"] + 10, 1600),
                        "height": min(bbox["height"] + 10, 900),
                    },
                )
                print(f"  ✅ Heatmap saved: {HEATMAP_OUT}")
                browser.close()
                return True

        page.screenshot(path=HEATMAP_OUT)
        print(f"  ⚠  Full viewport screenshot saved: {HEATMAP_OUT}")
        browser.close()
        return True


def capture_industry():
    """
    Capture Finviz Industry Performance Top 10.
    Uses JS to extract bar data from the first chart, then crops the Top 10 area.
    Falls back to a PIL-rendered table if chart capture fails.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1000},
            device_scale_factor=1.5,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print("  Navigating to Finviz Industry Performance…")
        page.goto(
            "https://finviz.com/groups.ashx?g=industry&sg=&o=perf1d&p=d1",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        page.wait_for_timeout(8000)

        # Use JS to extract all bar data from the FIRST chart (1-day performance)
        bars_json = page.evaluate("""() => {
            // The first .fv-bar-chart is the 1-day performance chart
            const chart = document.querySelector('.fv-bar-chart');
            if (!chart) return null;
            
            const rects = chart.querySelectorAll('.rect');
            const bars = [];
            rects.forEach(rect => {
                const style = rect.getAttribute('style') || '';
                const topMatch = style.match(/top:\\s*([\\d.]+)px/);
                const top = topMatch ? parseFloat(topMatch[1]) : 9999;
                
                const label = rect.querySelector('.label');
                const value = rect.querySelector('.value span:last-child');
                
                bars.push({
                    top: top,
                    label: label ? label.textContent.trim() : '',
                    value: value ? value.textContent.trim() : ''
                });
            });
            
            // Sort by top (smallest = highest on page = best performer)
            bars.sort((a, b) => a.top - b.top);
            return bars.slice(0, 15);
        }""")

        if bars_json and len(bars_json) > 0:
            print(f"  Extracted {len(bars_json)} bar entries via JS")
            top10 = bars_json[:10]
            for i, b in enumerate(top10):
                print(f"    #{i+1}: {b['label']} ({b['value']}%) [top={b['top']}]")

            # Get chart bounding box
            chart_bbox = page.evaluate("""() => {
                const chart = document.querySelector('.fv-bar-chart');
                if (!chart) return null;
                const rect = chart.getBoundingClientRect();
                return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
            }""")

            if chart_bbox and top10:
                # The bars are positioned absolutely within the chart
                # Top 10 bars have the smallest 'top' values
                min_top = min(b["top"] for b in top10)
                max_top = max(b["top"] for b in top10)

                # Add padding: 30px above the first bar, 30px below the last bar + bar height (16px)
                crop_y_start = chart_bbox["y"] + min_top - 30
                crop_y_end   = chart_bbox["y"] + max_top + 16 + 30

                # Ensure we also capture the chart title and axis
                crop_y_start = max(0, chart_bbox["y"] - 40)
                crop_y_end   = chart_bbox["y"] + max_top + 50

                crop_height = crop_y_end - crop_y_start

                print(f"  Cropping chart: y={crop_y_start:.0f} to {crop_y_end:.0f} (h={crop_height:.0f})")

                page.screenshot(
                    path=INDUSTRY_OUT,
                    clip={
                        "x":      max(0, chart_bbox["x"] - 10),
                        "y":      crop_y_start,
                        "width":  min(chart_bbox["width"] + 20, 1400),
                        "height": crop_height,
                    },
                )
                print(f"  ✅ Industry Top 10 saved: {INDUSTRY_OUT}")
                browser.close()
                return True

        # Fallback: render a PIL table with the data from today_market.json
        print("  ⚠  Chart capture failed — falling back to PIL-rendered table")
        browser.close()

    # PIL fallback: read industry data from JSON and render a table
    _render_industry_fallback()
    return True


def _render_industry_fallback():
    """Render industry Top 10 as a PIL image from the JSON data."""
    import json
    json_path = "/home/ubuntu/daily-market-summary/data/today_market.json"
    try:
        with open(json_path) as f:
            data = json.load(f)
        industries = data.get("industry", [])[:10]
    except Exception as e:
        print(f"  ⚠  Could not load JSON: {e}")
        industries = []

    if not industries:
        print("  ⚠  No industry data — creating placeholder image")
        img = Image.new("RGB", (800, 300), color=(20, 20, 30))
        draw = ImageDraw.Draw(img)
        draw.text((20, 140), "Industry data not available", fill=(180, 180, 180))
        img.save(INDUSTRY_OUT)
        return

    # Render a dark-mode table
    row_h = 36
    header_h = 50
    padding = 20
    width = 900
    height = header_h + row_h * len(industries) + padding * 2

    img = Image.new("RGB", (width, height), color=(18, 18, 28))
    draw = ImageDraw.Draw(img)

    # Try to load a font
    try:
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font_reg  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font_bold = ImageFont.load_default()
        font_reg  = font_bold

    # Header
    draw.rectangle([0, 0, width, header_h], fill=(30, 30, 50))
    draw.text((padding, 15), "Finviz Industry Performance — Top 10 (1-Day)", fill=(200, 200, 255), font=font_bold)

    # Column headers
    col_headers = ["#", "Industry", "1D %", "Stocks"]
    col_x = [padding, padding + 30, padding + 530, padding + 620]
    y = header_h + 5
    draw.rectangle([0, y, width, y + row_h], fill=(25, 25, 40))
    for i, hdr in enumerate(col_headers):
        draw.text((col_x[i], y + 10), hdr, fill=(160, 160, 200), font=font_bold)
    y += row_h

    # Data rows
    for idx, ind in enumerate(industries):
        bg = (22, 22, 35) if idx % 2 == 0 else (26, 26, 42)
        draw.rectangle([0, y, width, y + row_h], fill=bg)

        perf = ind.get("perf_1d", 0) or 0
        color = (80, 200, 100) if perf >= 0 else (220, 80, 80)

        draw.text((col_x[0], y + 10), str(idx + 1), fill=(150, 150, 170), font=font_reg)
        draw.text((col_x[1], y + 10), ind.get("name", "")[:45], fill=(220, 220, 240), font=font_reg)
        draw.text((col_x[2], y + 10), f"{perf:+.2f}%", fill=color, font=font_bold)
        draw.text((col_x[3], y + 10), str(ind.get("stock_count", "")), fill=(180, 180, 200), font=font_reg)
        y += row_h

    img.save(INDUSTRY_OUT)
    print(f"  ✅ Industry PIL fallback table saved: {INDUSTRY_OUT}")


if __name__ == "__main__":
    print("=== Finviz Heatmap Capture ===")
    capture_heatmap()
    print("\n=== Finviz Industry Performance Top 10 Capture ===")
    capture_industry()
    print("\nDone.")
