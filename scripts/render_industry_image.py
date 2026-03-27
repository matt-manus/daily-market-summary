#!/usr/bin/env python3.11
"""
render_industry_image.py  —  v1.0
Renders the Industry Top 10 performance table as a high-quality PNG
from the today_market.json data. Dark mode, styled to match the report.
"""

import json
from PIL import Image, ImageDraw, ImageFont
import os

JSON_PATH   = "/home/ubuntu/daily-market-summary/data/today_market.json"
OUTPUT_PATH = "/home/ubuntu/daily-market-summary/assets/img/today/industry_performance.png"

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# ── Load data ──────────────────────────────────────────────────────────────
with open(JSON_PATH) as f:
    data = json.load(f)

industries = data.get("industry", [])[:10]
# Normalize field names
for ind in industries:
    if "label" in ind and "name" not in ind:
        ind["name"] = ind["label"]
    if "change_1d_pct" in ind and "perf_1d" not in ind:
        ind["perf_1d"] = ind["change_1d_pct"]
    if "num_stocks" in ind and "stock_count" not in ind:
        ind["stock_count"] = ind["num_stocks"]
report_date = data.get("generated_at", "")[:10]

# ── Fonts ──────────────────────────────────────────────────────────────────
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_REG_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

def load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

font_title  = load_font(FONT_PATHS,     16)
font_header = load_font(FONT_PATHS,     13)
font_body   = load_font(FONT_REG_PATHS, 13)
font_bold   = load_font(FONT_PATHS,     13)

# ── Layout ─────────────────────────────────────────────────────────────────
SCALE       = 2          # retina-style 2× scaling
W_BASE      = 860
TITLE_H     = 52
COL_HDR_H   = 34
ROW_H       = 38
PADDING     = 22
BAR_MAX_W   = 220        # max width of the performance bar

total_rows = len(industries)
H_BASE     = TITLE_H + COL_HDR_H + ROW_H * total_rows + PADDING

W = W_BASE * SCALE
H = H_BASE * SCALE

# ── Colours ────────────────────────────────────────────────────────────────
BG          = (14, 17, 23)
TITLE_BG    = (20, 24, 36)
HDR_BG      = (26, 30, 46)
ROW_EVEN    = (18, 22, 34)
ROW_ODD     = (22, 26, 40)
COL_TITLE   = (160, 180, 255)
COL_HDR     = (140, 155, 200)
COL_TEXT    = (215, 220, 235)
COL_MUTED   = (120, 130, 160)
COL_GREEN   = (72, 199, 116)
COL_RED     = (239, 83, 80)
COL_BORDER  = (40, 46, 70)

# ── Column definitions ─────────────────────────────────────────────────────
# (label, x_base, width, align)
COLS = [
    ("Rank",     PADDING,            40,  "center"),
    ("Industry", PADDING + 50,       360, "left"),
    ("1D %",     PADDING + 430,      80,  "right"),
    ("Stocks",   PADDING + 530,      60,  "right"),
    ("Bar",      PADDING + 610,      BAR_MAX_W, "left"),
]

# ── Draw ───────────────────────────────────────────────────────────────────
img  = Image.new("RGB", (W, H), color=BG)
draw = ImageDraw.Draw(img)

def s(v):
    """Scale a base value to retina pixels."""
    return int(v * SCALE)

# Title bar
draw.rectangle([0, 0, W, s(TITLE_H)], fill=TITLE_BG)
draw.text(
    (s(PADDING), s(14)),
    f"Section 5B — Top 10 Industries by 1-Day Performance  ({report_date})",
    fill=COL_TITLE, font=font_title,
)
draw.text(
    (s(PADDING), s(33)),
    "Source: Finviz.com  |  Sorted by 1D % descending",
    fill=COL_MUTED, font=font_body,
)

# Column header row
y = s(TITLE_H)
draw.rectangle([0, y, W, y + s(COL_HDR_H)], fill=HDR_BG)
# Bottom border under header
draw.line([0, y + s(COL_HDR_H) - 1, W, y + s(COL_HDR_H) - 1], fill=COL_BORDER, width=1)
for label, x_base, col_w, align in COLS:
    tx = s(x_base)
    if align == "right":
        tx = s(x_base + col_w)
    draw.text(
        (tx, y + s(10)),
        label,
        fill=COL_HDR, font=font_header,
        anchor="ra" if align == "right" else None,
    )

# Data rows
# Find max absolute perf for bar scaling
max_abs = max((abs(ind.get("perf_1d", 0) or 0) for ind in industries), default=1)
if max_abs == 0:
    max_abs = 1

y = s(TITLE_H + COL_HDR_H)
for idx, ind in enumerate(industries):
    bg = ROW_EVEN if idx % 2 == 0 else ROW_ODD
    draw.rectangle([0, y, W, y + s(ROW_H)], fill=bg)

    perf = ind.get("perf_1d") or ind.get("change_1d_pct") or 0
    color = COL_GREEN if perf >= 0 else COL_RED
    name  = (ind.get("name") or ind.get("label") or "")[:50]
    stocks = str(ind.get("stock_count") or ind.get("num_stocks") or "")

    # Rank
    draw.text(
        (s(COLS[0][1] + COLS[0][2] // 2), y + s(ROW_H // 2)),
        str(idx + 1),
        fill=COL_MUTED, font=font_body,
        anchor="mm",
    )
    # Industry name
    draw.text(
        (s(COLS[1][1]), y + s(11)),
        name,
        fill=COL_TEXT, font=font_body,
    )
    # 1D %
    draw.text(
        (s(COLS[2][1] + COLS[2][2]), y + s(11)),
        f"{perf:+.2f}%",
        fill=color, font=font_bold,
        anchor="ra",
    )
    # Stocks
    draw.text(
        (s(COLS[3][1] + COLS[3][2]), y + s(11)),
        stocks,
        fill=COL_MUTED, font=font_body,
        anchor="ra",
    )
    # Performance bar
    bar_x = s(COLS[4][1])
    bar_y = y + s(ROW_H // 2) - s(6)
    bar_h = s(12)
    bar_w = int(abs(perf) / max_abs * s(BAR_MAX_W - 10))
    bar_w = max(bar_w, s(2))
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=color)

    # Row separator
    draw.line([0, y + s(ROW_H) - 1, W, y + s(ROW_H) - 1], fill=COL_BORDER, width=1)

    y += s(ROW_H)

# Save
img.save(OUTPUT_PATH, "PNG", dpi=(144, 144))
print(f"✅ Industry Top 10 image saved: {OUTPUT_PATH}")
print(f"   Size: {W}×{H}px  |  Rows: {total_rows}")
