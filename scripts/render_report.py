"""
render_report.py  (Stage 3 — Professional Template)
-----------------------------------------------------
讀取 data/today_market.json
打開 templates/report_template.html
把 {{TAGS}} 替換成最新數據
輸出成 index.html

Sections covered:
  1  Macro Indicators   (VIX, DXY, TNX, GOLD, OIL, BTC)
  2  Major Indices      (SPY, QQQ, DIA, IWM + MA distances)
  3  Market Sentiment   (Fear&Greed, NAAIM, P/C Ratio)
  4  Market Breadth     (4a/b % above MA, 4c ADR, 4d stockbee image)
  5  Sector & Industry  (5A 11 sectors sorted by 1D, 5B Top-15 industries)
  6  Market Analysis    (AI text placeholder)
  7  Trading Outlook    (AI text placeholder)
"""

import json
import os

# ── Paths ──────────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON   = os.path.join(BASE, "data",      "today_market.json")
TMPL   = os.path.join(BASE, "templates", "report_template.html")
OUTPUT = os.path.join(BASE, "index.html")

# ── Load data ──────────────────────────────────────────────────────────
with open(JSON, encoding="utf-8") as f:
    data = json.load(f)

meta      = data["meta"]
macro     = data["macro"]
indices   = data["indices"]
sectors   = data["sectors"]
sentiment = data.get("sentiment", {})
breadth   = data.get("breadth", {})
industry  = data.get("industry", [])
sbee      = data.get("stockbee_mm", {})

# ── Utility functions ──────────────────────────────────────────────────

def pct(val, sign=True):
    """Format percentage: +1.23 or -0.45"""
    if val is None:
        return "N/A"
    v = float(val)
    prefix = "+" if sign and v >= 0 else ""
    return f"{prefix}{v:.2f}"

def price(val, dec=2):
    """Format price with thousands separator"""
    if val is None:
        return "N/A"
    return f"{float(val):,.{dec}f}"

def css(val):
    """Positive → 'up', negative → 'down', None → 'flat'"""
    if val is None:
        return "flat"
    return "up" if float(val) >= 0 else "down"

def badge(status):
    """Status string → CSS badge class"""
    return {
        "ABOVE ALL": "badge-above",
        "BELOW ALL": "badge-below",
        "MIXED":     "badge-mixed",
    }.get(status, "badge-mixed")

def rsi_class(rsi):
    """RSI value → CSS fill class"""
    if rsi is None:
        return "rsi-neu"
    r = float(rsi)
    if r >= 70:
        return "rsi-ob"
    if r <= 30:
        return "rsi-os"
    return "rsi-neu"

def rsi_width(rsi):
    """RSI value → percentage width string for bar"""
    if rsi is None:
        return "0%"
    return f"{min(float(rsi), 100):.0f}%"

def fg_class(score):
    """Fear & Greed score → CSS color class"""
    if score is None:
        return "flat"
    s = float(score)
    if s <= 25:
        return "fg-extreme-fear"
    if s <= 45:
        return "fg-fear"
    if s <= 55:
        return "fg-neutral"
    if s <= 75:
        return "fg-greed"
    return "fg-extreme-greed"

def pc_class(val):
    """P/C ratio → CSS class (high = bearish = down, low = bullish = up)"""
    if val is None:
        return "flat"
    return "down" if float(val) >= 1.0 else "up"

def pct_bar_class(pct_val):
    """Breadth percentage → bar color class"""
    if pct_val is None:
        return "pct-mid"
    v = float(pct_val)
    if v >= 60:
        return "pct-high"
    if v >= 35:
        return "pct-mid"
    return "pct-low"

def chg_cell(val):
    """Render a colored change cell span"""
    direction = css(val)
    return f'<span class="chg-cell {direction}-bg">{pct(val)}%</span>'

def fmt_vol(vol):
    """Format volume in millions"""
    if vol is None:
        return "N/A"
    return f"{float(vol)/1_000_000:.0f}M"

# ── Build replacement dictionary ──────────────────────────────────────
tags = {}

# ── Meta ──────────────────────────────────────────────────────────────
tags["{{DATE}}"]          = meta["date"]
tags["{{GENERATED_HKT}}"] = meta["generated_hkt"]
tags["{{GENERATED_ET}}"]  = meta["generated_et"]

# ── Section 1: Macro ──────────────────────────────────────────────────
for label, key, dec in [
    ("VIX",  "VIX",     2),
    ("DXY",  "DXY",     3),
    ("TNX",  "TNX_10Y", 3),
    ("GOLD", "GOLD",    2),
    ("OIL",  "OIL_WTI", 2),
    ("BTC",  "BTC",     0),
]:
    m = macro.get(key, {})
    p = m.get("price")
    c = m.get("change_1d_pct")
    tags[f"{{{{{label}_PRICE}}}}"]   = price(p, dec)
    tags[f"{{{{{label}_CHG_PCT}}}}"] = pct(c)
    tags[f"{{{{{label}_DIR}}}}"]     = css(c)

# ── Section 2: Major Indices ──────────────────────────────────────────
for sym in ["SPY", "QQQ", "DIA", "IWM"]:
    e = indices.get(sym, {})
    rsi_val = e.get("rsi14")
    tags[f"{{{{{sym}_PRICE}}}}"]        = price(e.get("price"))
    tags[f"{{{{{sym}_CHG_PCT}}}}"]      = pct(e.get("change_1d_pct"))
    tags[f"{{{{{sym}_CHG_DIR}}}}"]      = css(e.get("change_1d_pct"))
    tags[f"{{{{{sym}_STATUS}}}}"]       = e.get("status", "")
    tags[f"{{{{{sym}_BADGE_CLASS}}}}"]  = badge(e.get("status", ""))
    tags[f"{{{{{sym}_MA20}}}}"]         = price(e.get("ma20"))
    tags[f"{{{{{sym}_MA50}}}}"]         = price(e.get("ma50"))
    tags[f"{{{{{sym}_MA200}}}}"]        = price(e.get("ma200"))
    tags[f"{{{{{sym}_VS_MA20_PCT}}}}"]  = pct(e.get("vs_ma20_pct"))
    tags[f"{{{{{sym}_VS_MA50_PCT}}}}"]  = pct(e.get("vs_ma50_pct"))
    tags[f"{{{{{sym}_VS_MA200_PCT}}}}"] = pct(e.get("vs_ma200_pct"))
    tags[f"{{{{{sym}_VS_MA20_DIR}}}}"]  = css(e.get("vs_ma20_pct"))
    tags[f"{{{{{sym}_VS_MA50_DIR}}}}"]  = css(e.get("vs_ma50_pct"))
    tags[f"{{{{{sym}_VS_MA200_DIR}}}}"] = css(e.get("vs_ma200_pct"))
    tags[f"{{{{{sym}_RSI}}}}"]          = f"{float(rsi_val):.1f}" if rsi_val else "N/A"
    tags[f"{{{{{sym}_RSI_CLASS}}}}"]    = rsi_class(rsi_val)
    tags[f"{{{{{sym}_RSI_W}}}}"]        = rsi_width(rsi_val)

# ── Section 3: Sentiment ──────────────────────────────────────────────
fg   = sentiment.get("fear_greed", {})
naaim = sentiment.get("naaim", {})
pc   = sentiment.get("put_call", {})

fg_score = fg.get("score")
tags["{{FG_SCORE}}"]      = f"{float(fg_score):.1f}" if fg_score is not None else "N/A"
tags["{{FG_RATING}}"]     = fg.get("rating", "N/A").title()
tags["{{FG_CLASS}}"]      = fg_class(fg_score)
tags["{{FG_PREV_CLOSE}}"] = f"{float(fg.get('prev_close', 0)):.1f}" if fg.get("prev_close") is not None else "N/A"
tags["{{FG_PREV_1W}}"]    = f"{float(fg.get('prev_1w', 0)):.1f}"    if fg.get("prev_1w")    is not None else "N/A"
tags["{{FG_PREV_1M}}"]    = f"{float(fg.get('prev_1m', 0)):.1f}"    if fg.get("prev_1m")    is not None else "N/A"
tags["{{FG_PREV_1Y}}"]    = f"{float(fg.get('prev_1y', 0)):.1f}"    if fg.get("prev_1y")    is not None else "N/A"

naaim_val = naaim.get("value")
tags["{{NAAIM_VALUE}}"] = f"{float(naaim_val):.2f}" if naaim_val is not None else "N/A"
tags["{{NAAIM_DATE}}"]  = naaim.get("date", "N/A")

pc_val = pc.get("value")
tags["{{PC_VALUE}}"]  = f"{float(pc_val):.4f}" if pc_val is not None else "N/A"
tags["{{PC_RATING}}"] = pc.get("rating", "N/A").title()
tags["{{PC_CLASS}}"]  = pc_class(pc_val)

# ── Section 4a/b: Breadth — % Above MA ───────────────────────────────
breadth_index_map = [
    ("sp500",      "S&P 500"),
    ("nasdaq",     "NASDAQ"),
    ("nyse",       "NYSE"),
    ("russell2000","Russell 2000"),
]
breadth_rows = []
for key, label in breadth_index_map:
    b = breadth.get(key, {})
    total = b.get("total", "N/A")
    p20   = b.get("pct_above_20ma")
    p50   = b.get("pct_above_50ma")
    p200  = b.get("pct_above_200ma")

    def breadth_cell(pct_val):
        if pct_val is None:
            return "<td>N/A</td>"
        v = float(pct_val)
        bc = pct_bar_class(v)
        color = {"pct-high": "#0a7c42", "pct-mid": "#b45309", "pct-low": "#c0392b"}.get(bc, "#1a56db")
        return (
            f'<td><div class="pct-bar-wrap">'
            f'<span style="font-weight:600;color:{color}">{v:.1f}%</span>'
            f'<div class="pct-bar"><div class="pct-fill {bc}" style="width:{min(v,100):.0f}%"></div></div>'
            f'</div></td>'
        )

    breadth_rows.append(
        f"<tr>"
        f"<td>{label}</td>"
        f"<td style='text-align:center'>{total:,}</td>"
        + breadth_cell(p20)
        + breadth_cell(p50)
        + breadth_cell(p200)
        + "</tr>"
    )
tags["{{BREADTH_ROWS}}"] = "\n".join(breadth_rows)

# ── Section 4: Avg Daily Range ────────────────────────────────────────
adr_data = breadth.get("avg_daily_range", {})
adr_rows = []
for sym in ["SPY", "QQQ", "DIA", "IWM"]:
    val = adr_data.get(sym)
    adr_rows.append(
        f"<tr>"
        f"<td style='font-weight:700'>{sym}</td>"
        f"<td style='text-align:center;font-weight:600'>"
        f"{'N/A' if val is None else f'{float(val):.2f}%'}</td>"
        f"</tr>"
    )
tags["{{ADR_ROWS}}"] = "\n".join(adr_rows)

# ── Section 4c: Advance-Decline ───────────────────────────────────────
ad = breadth.get("market_wide_advance_decline", {})

def build_adr_rows(exchange_data):
    if not exchange_data:
        return '<div class="adr-row"><span class="adr-key">No data</span></div>'
    adv  = exchange_data.get("advances", "N/A")
    dec  = exchange_data.get("declines", "N/A")
    unch = exchange_data.get("unchanged", "N/A")
    tot  = exchange_data.get("total_issues", "N/A")
    p_adv = exchange_data.get("pct_advancing")
    p_dec = exchange_data.get("pct_declining")
    ratio = exchange_data.get("ad_ratio")
    h52   = exchange_data.get("new_52w_highs", "N/A")
    l52   = exchange_data.get("new_52w_lows",  "N/A")
    adv_vol = exchange_data.get("adv_vol")
    dec_vol = exchange_data.get("dec_vol")

    adv_color = "color:var(--up)"
    dec_color = "color:var(--down)"
    ratio_color = "color:var(--up)" if ratio and float(ratio) >= 1 else "color:var(--down)"

    rows = [
        f'<div class="adr-row"><span class="adr-key">Advances</span>'
        f'<span class="adr-val" style="{adv_color}">{adv:,}</span></div>',

        f'<div class="adr-row"><span class="adr-key">Declines</span>'
        f'<span class="adr-val" style="{dec_color}">{dec:,}</span></div>',

        f'<div class="adr-row"><span class="adr-key">Unchanged</span>'
        f'<span class="adr-val">{unch:,}</span></div>',

        f'<div class="adr-row"><span class="adr-key">% Advancing</span>'
        f'<span class="adr-val" style="{adv_color}">'
        f'{f"{float(p_adv):.1f}%" if p_adv is not None else "N/A"}</span></div>',

        f'<div class="adr-row"><span class="adr-key">% Declining</span>'
        f'<span class="adr-val" style="{dec_color}">'
        f'{f"{float(p_dec):.1f}%" if p_dec is not None else "N/A"}</span></div>',

        f'<div class="adr-row"><span class="adr-key">A/D Ratio</span>'
        f'<span class="adr-val" style="{ratio_color}">'
        f'{f"{float(ratio):.3f}" if ratio is not None else "N/A"}</span></div>',

        f'<div class="adr-row"><span class="adr-key">Adv Volume</span>'
        f'<span class="adr-val">{fmt_vol(adv_vol)}</span></div>',

        f'<div class="adr-row"><span class="adr-key">Dec Volume</span>'
        f'<span class="adr-val">{fmt_vol(dec_vol)}</span></div>',

        f'<div class="adr-row"><span class="adr-key">52W Highs</span>'
        f'<span class="adr-val" style="color:var(--up)">{h52}</span></div>',

        f'<div class="adr-row"><span class="adr-key">52W Lows</span>'
        f'<span class="adr-val" style="color:var(--down)">{l52}</span></div>',
    ]
    return "\n".join(rows)

tags["{{NASDAQ_ADR_ROWS}}"] = build_adr_rows(ad.get("NASDAQ", {}))
tags["{{NYSE_ADR_ROWS}}"]   = build_adr_rows(ad.get("NYSE", {}))

# ── Section 5A: Sectors sorted by 1D change ──────────────────────────
sorted_sectors = sorted(sectors, key=lambda x: x.get("change_1d_pct", 0), reverse=True)

sector_rows_full = []
for s in sorted_sectors:
    sym  = s.get("symbol", "")
    name = s.get("name", "")
    pr   = s.get("price")
    c1d  = s.get("change_1d_pct")
    c1w  = s.get("change_1w_pct")
    c1m  = s.get("change_1m_pct")
    rsi  = s.get("rsi14")
    vs20 = s.get("vs20ma", "")
    stat = s.get("status", "")

    rsi_str = f"{float(rsi):.1f}" if rsi else "N/A"
    rsi_w   = f"{min(float(rsi),100):.0f}%" if rsi else "0%"
    rsi_c   = rsi_class(rsi)

    # RSI background highlight for overbought (>70) or oversold (<30)
    rsi_style = ""
    if rsi:
        r = float(rsi)
        if r >= 70:
            rsi_style = "background:#fef2f2;"
        elif r <= 30:
            rsi_style = "background:#ecfdf5;"

    sector_rows_full.append(f"""
        <tr>
          <td><span class="sym">{sym}</span></td>
          <td style="color:var(--text-muted);font-size:12px">{name}</td>
          <td style="font-weight:600">${price(pr)}</td>
          <td>{chg_cell(c1d)}</td>
          <td>{chg_cell(c1w)}</td>
          <td>{chg_cell(c1m)}</td>
          <td style="{rsi_style}">
            <div class="rsi-wrap">
              <span style="font-weight:600">{rsi_str}</span>
              <div class="rsi-bar"><div class="rsi-fill {rsi_c}" style="width:{rsi_w}"></div></div>
            </div>
          </td>
          <td class="{'up' if vs20 == 'Green' else 'down'}" style="font-weight:600">{vs20}</td>
          <td><span class="status-badge {badge(stat)}">{stat}</span></td>
        </tr>""")

tags["{{SECTOR_ROWS_FULL}}"] = "\n".join(sector_rows_full)

# ── Section 5B: Top 15 Industries ────────────────────────────────────
industry_rows = []
for ind in industry[:15]:
    rank = ind.get("rank", "")
    label = ind.get("label", "")
    c1d  = ind.get("change_1d_pct")
    c1w  = ind.get("change_1w_pct")
    c1m  = ind.get("change_1m_pct")
    c3m  = ind.get("change_3m_pct")
    cytd = ind.get("change_ytd_pct")

    industry_rows.append(f"""
        <tr>
          <td style="text-align:center"><span class="rank-num">{rank}</span></td>
          <td style="font-weight:600;max-width:220px;white-space:normal">{label}</td>
          <td>{chg_cell(c1d)}</td>
          <td>{chg_cell(c1w)}</td>
          <td>{chg_cell(c1m)}</td>
          <td>{chg_cell(c3m)}</td>
          <td>{chg_cell(cytd)}</td>
        </tr>""")

tags["{{INDUSTRY_ROWS}}"] = "\n".join(industry_rows)

# ── Section 6 & 7: AI text placeholders ──────────────────────────────
tags["{{SECTION6_CONTENT}}"] = (
    '<p class="ai-placeholder">'
    '[ Section 6: Market Analysis — to be filled by AI after data review. '
    'Include macro environment assessment, index trend analysis, and key risk factors. ]'
    '</p>'
)
tags["{{SECTION7_CONTENT}}"] = (
    '<p class="ai-placeholder">'
    '[ Section 7: Trading Outlook &amp; Watchlist — to be filled by AI. '
    'Include sector rotation opportunities, high-momentum setups, and key levels to watch. ]'
    '</p>'
)

# ── Legacy tag: keep backward compat for old {{SECTOR_ROWS}} if needed
# Build a simplified version for any old template references
rows_legacy = []
for s in sectors:
    sym  = s["symbol"]
    r    = s.get("rsi14")
    r_s  = f"{float(r):.1f}" if r else "N/A"
    r_w  = f"{min(float(r),100):.0f}%" if r else "0%"
    vs20 = s.get("vs20ma", "")
    rows_legacy.append(f"""
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
tags["{{SECTOR_ROWS}}"] = "\n".join(rows_legacy)

# ── Read template, apply substitutions, write output ─────────────────
with open(TMPL, encoding="utf-8") as f:
    html = f.read()

for tag, value in tags.items():
    html = html.replace(tag, str(value))

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ Done! Output: {OUTPUT}")
print(f"   Tags injected: {len(tags)}")

# ── Verify no leftover tags ───────────────────────────────────────────
import re
leftover = re.findall(r"\{\{[A-Z_0-9]+\}\}", html)
if leftover:
    print(f"⚠️  Leftover tags ({len(leftover)}): {set(leftover)}")
else:
    print("✅ All tags resolved — zero residual placeholders.")
