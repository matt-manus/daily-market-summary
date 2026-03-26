#!/usr/bin/env python3.11
"""Crop IWM screenshot to remove navigation bar and show only chart area."""

from PIL import Image

INPUT = "/home/ubuntu/daily-market-summary/assets/img/today/iwm_trend.png"
OUTPUT = "/home/ubuntu/daily-market-summary/assets/img/today/iwm_trend.png"

img = Image.open(INPUT)
w, h = img.size
print(f"Original size: {w}x{h}")

# Crop from y=370 (below nav bar) to bottom, full width
# The chart starts at approximately y=370 in the 800x868 screenshot
crop_top = 370
cropped = img.crop((0, crop_top, w, h))
print(f"Cropped size: {cropped.size}")
cropped.save(OUTPUT)
print(f"Saved: {OUTPUT}")
