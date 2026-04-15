#!/usr/bin/env python3
"""
scripts/html_generator.py
Phase 3.9 — Section 4D Market Heatmap 動態化
"""
import os
from datetime import datetime
import pytz
import json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_heatmap_last_modified():
    img_path = os.path.join(BASE, "assets/images/market_heatmap.png")
    if os.path.exists(img_path):
        hkt = pytz.timezone('Asia/Hong_Kong')
        dt = datetime.fromtimestamp(os.path.getmtime(img_path), tz=hkt)
        return dt.strftime("%Y-%m-%d %H:%M")
    return "N/A - No heatmap image found"

def load_stockbee_dynamic_summary():
    json_path = os.path.join(BASE, "data/stockbee_mm.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("summary", data.get("text", "Stockbee data loaded"))
        except Exception:
            pass
    return "⚠️ Stockbee data not available"

def generate_html():
    template_path = os.path.join(BASE, "templates/report_template.html")
    output_path = os.path.join(BASE, "index.html")
    if not os.path.exists(template_path):
        print("❌ template 不存在")
        return False
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    heatmap_time = get_heatmap_last_modified()
    stockbee_summary = load_stockbee_dynamic_summary()

    # Replace Section 4D: update img src to new path and inject Last updated timestamp
    old_4d = '''  <!-- 4D: Market Heatmap (moved here from Sector section) -->
  <div class="sub-title" style="margin-top:20px;">4D — Market Heatmap</div>
  <div class="img-block">
    <img src="assets/img/today/market_heatmap.png" alt="Market Heatmap (Finviz)" />
    <div class="img-caption">Market Heatmap (Finviz) — Size = Market Cap, Color = 1D Performance</div>
  </div>'''

    new_4d = f'''  <!-- 4D: Market Heatmap (moved here from Sector section) -->
  <div class="sub-title" style="margin-top:20px;">4D — Market Heatmap</div>
  <div class="section-4d market-heatmap">
      <img src="assets/images/market_heatmap.png"
           alt="Finviz S&amp;P 500 Market Heatmap"
           style="width: 100%; max-width: 1280px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
      <p class="last-data" style="text-align: right; font-size: 0.9rem; color: #888; margin-top: 8px;">
          Last updated: <strong>{heatmap_time} HKT</strong>
      </p>
      <div class="img-caption">Market Heatmap (Finviz) — Size = Market Cap, Color = 1D Performance</div>
  </div>'''

    if old_4d in content:
        content = content.replace(old_4d, new_4d)
        print("✅ Section 4D HTML block 已更新（img src + Last updated）")
    else:
        # Fallback: just replace the img src path
        content = content.replace(
            'src="assets/img/today/market_heatmap.png"',
            f'src="assets/images/market_heatmap.png"'
        )
        print("⚠️ 用 fallback 替換 img src（template 結構有變）")

    # Replace {{HEATMAP_TIME}} and {{STOCKBEE_DYNAMIC_SUMMARY}} if present
    content = content.replace("{{HEATMAP_TIME}}", heatmap_time)
    content = content.replace("{{STOCKBEE_DYNAMIC_SUMMARY}}", stockbee_summary)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ index.html 生成完成！Heatmap Last Data: {heatmap_time} HKT")
    return True

if __name__ == "__main__":
    generate_html()
