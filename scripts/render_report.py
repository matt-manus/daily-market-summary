"""
render_report.py
----------------
讀取 data/today_market.json
打開 templates/report_template.html
把 {{TAGS}} 替換成最新數據
輸出成 index.html
"""

import json
import os

# ── 路徑 ──────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON   = os.path.join(BASE, "data", "today_market.json")
TMPL   = os.path.join(BASE, "templates", "report_template.html")
OUTPUT = os.path.join(BASE, "index.html")

# ── 讀取數據 ───────────────────────────────────────────────────────
with open(JSON, encoding="utf-8") as f:
    data = json.load(f)

meta    = data["meta"]
macro   = data["macro"]
indices = data["indices"]
sectors = data["sectors"]

# ── 工具函數 ───────────────────────────────────────────────────────
def pct(val, sign=True):
    """格式化百分比，例：+1.23 或 -0.45"""
    if val is None: return "N/A"
    prefix = "+" if sign and float(val) >= 0 else ""
    return f"{prefix}{float(val):.2f}"

def price(val, dec=2):
    """格式化價格，千位分隔"""
    if val is None: return "N/A"
    return f"{float(val):,.{dec}f}"

def css(val):
    """正數 → 'up'，負數 → 'down'，None → 'flat'"""
    if val is None: return "flat"
    return "up" if float(val) >= 0 else "down"

def badge(status):
    """status 字串 → CSS badge class"""
    return {"ABOVE ALL": "badge-above",
            "BELOW ALL": "badge-below",
            "MIXED":     "badge-mixed"}.get(status, "badge-mixed")

def rsi_class(rsi):
    """RSI 值 → bar 顏色 class"""
    if rsi is None: return "rsi-neu"
    return "rsi-ob" if float(rsi) >= 70 else ("rsi-os" if float(rsi) <= 30 else "rsi-neu")

# ── 建立替換字典 ───────────────────────────────────────────────────
tags = {}

# Meta
tags["{{DATE}}"]           = meta["date"]
tags["{{GENERATED_HKT}}"]  = meta["generated_hkt"]
tags["{{GENERATED_ET}}"]   = meta["generated_et"]

# Macro（VIX / DXY / TNX / GOLD / OIL / BTC）
for label, key, dec in [
    ("VIX",  "VIX",     3),
    ("DXY",  "DXY",     3),
    ("TNX",  "TNX_10Y", 3),
    ("GOLD", "GOLD",    2),
    ("OIL",  "OIL_WTI", 3),
    ("BTC",  "BTC",     0),
]:
    m = macro.get(key, {})
    p = m.get("price")
    c = m.get("change_1d_pct")
    tags[f"{{{{{label}_PRICE}}}}"]  = price(p, dec)
    tags[f"{{{{{label}_CHG_PCT}}}}"] = pct(c)
    tags[f"{{{{{label}_DIR}}}}"]     = css(c)

# Index ETFs（SPY / QQQ / DIA / IWM）
for sym in ["SPY", "QQQ", "DIA", "IWM"]:
    e = indices.get(sym, {})
    tags[f"{{{{{sym}_PRICE}}}}"]        = price(e.get("price"))
    tags[f"{{{{{sym}_CHG_PCT}}}}"]       = pct(e.get("change_1d_pct"))
    tags[f"{{{{{sym}_CHG_DIR}}}}"]       = css(e.get("change_1d_pct"))
    tags[f"{{{{{sym}_STATUS}}}}"]        = e.get("status", "")
    tags[f"{{{{{sym}_BADGE_CLASS}}}}"]   = badge(e.get("status", ""))
    tags[f"{{{{{sym}_MA20}}}}"]          = price(e.get("ma20"))
    tags[f"{{{{{sym}_MA50}}}}"]          = price(e.get("ma50"))
    tags[f"{{{{{sym}_MA200}}}}"]         = price(e.get("ma200"))
    tags[f"{{{{{sym}_VS_MA20_PCT}}}}"]   = pct(e.get("vs_ma20_pct"))
    tags[f"{{{{{sym}_VS_MA50_PCT}}}}"]   = pct(e.get("vs_ma50_pct"))
    tags[f"{{{{{sym}_VS_MA200_PCT}}}}"]  = pct(e.get("vs_ma200_pct"))
    tags[f"{{{{{sym}_VS_MA20_DIR}}}}"]   = css(e.get("vs_ma20_pct"))
    tags[f"{{{{{sym}_VS_MA50_DIR}}}}"]   = css(e.get("vs_ma50_pct"))
    tags[f"{{{{{sym}_VS_MA200_DIR}}}}"]  = css(e.get("vs_ma200_pct"))
    tags[f"{{{{{sym}_RSI}}}}"]           = f"{float(e['rsi14']):.1f}" if e.get("rsi14") else "N/A"

# Sector rows（整塊 <tr> 注入）
rows = []
for s in sectors:
    sym  = s["symbol"]
    r    = s.get("rsi14")
    r_s  = f"{float(r):.1f}" if r else "N/A"
    r_w  = f"{min(float(r),100):.0f}%" if r else "0%"
    vs20 = s.get("vs20ma", "")
    rows.append(f"""
        <tr>
          <td class="sym">{sym}</td>
          <td>${price(s.get("price"))}</td>
          <td class="{css(s.get("change_1d_pct"))}">{pct(s.get("change_1d_pct"))}%</td>
          <td>
            <div class="rsi-bar-wrap">
              <span>{r_s}</span>
              <div class="rsi-bar">
                <div class="rsi-fill {rsi_class(r)}" style="width:{r_w}"></div>
              </div>
            </div>
          </td>
          <td class="{'up' if vs20=='Green' else 'down'}">{vs20}</td>
          <td><span class="status-badge {badge(s.get('status',''))}">{s.get("status","")}</span></td>
        </tr>""")
tags["{{SECTOR_ROWS}}"] = "\n".join(rows)

# ── 讀取模板，執行替換，輸出 ───────────────────────────────────────
with open(TMPL, encoding="utf-8") as f:
    html = f.read()

for tag, value in tags.items():
    html = html.replace(tag, str(value))

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ 完成！輸出至: {OUTPUT}")
