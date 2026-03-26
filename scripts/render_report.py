"""
render_report.py  (Stage 3 — Dark Mode + text-green/text-red)
--------------------------------------------------------------
讀取 data/today_market.json
打開 templates/report_template.html
把 {{TAGS}} 替換成最新數據
輸出成 index.html

Changes in this version:
  - All data access uses .get(key, None) with explicit N/A fallback
  - Dynamic coloring uses text-green / text-red (unified with CSS)
  - RSI cell background class injected (rsi-ob-cell / rsi-os-cell)
  - chg_cell() outputs text-green-bg / text-red-bg pill spans
  - All percentage helpers guard against None / non-numeric values
"""

import json
import os
import re

# ── Paths ──────────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON   = os.path.join(BASE, "data",      "today_market.json")
TMPL   = os.path.join(BASE, "templates", "report_template.html")
OUTPUT = os.path.join(BASE, "index.html")

# ── Load data ──────────────────────────────────────────────────────────
with open(JSON, encoding="utf-8") as f:
    data = json.load(f)

meta      = data.get("meta",      {})
macro     = data.get("macro",     {})
indices   = data.get("indices",   {})
sectors   = data.get("sectors",   [])
sentiment = data.get("sentiment", {})
breadth   = data.get("breadth",   {})
industry  = data.get("industry",  [])

# ══════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def safe_float(val, default=None):
    """Safely convert any value to float; return default on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def pct(val, sign=True):
    """
    Format a percentage value.
    Returns 'N/A' (styled) if the value is missing or non-numeric.
    """
    v = safe_float(val)
    if v is None:
        return '<span class="na-val">N/A</span>'
    prefix = "+" if sign and v >= 0 else ""
    return f"{prefix}{v:.2f}"


def price(val, dec=2):
    """
    Format a price with thousands separator.
    Returns 'N/A' (styled) if the value is missing or non-numeric.
    """
    v = safe_float(val)
    if v is None:
        return '<span class="na-val">N/A</span>'
    return f"{v:,.{dec}f}"


def css_dir(val):
    """
    Map a numeric value to a CSS direction class.
    Uses the new unified naming: text-green / text-red / flat
    Also keeps .up / .down aliases for any legacy references.
    """
    v = safe_float(val)
    if v is None:
        return "flat"
    return "text-green" if v >= 0 else "text-red"


def badge(status):
    """Status string → CSS badge class."""
    return {
        "ABOVE ALL": "badge-above",
        "BELOW ALL": "badge-below",
        "MIXED":     "badge-mixed",
    }.get(str(status), "badge-mixed")


def rsi_bar_class(rsi):
    """RSI value → fill color class for the progress bar."""
    v = safe_float(rsi)
    if v is None:
        return "rsi-neu"
    if v >= 70:
        return "rsi-ob"
    if v <= 30:
        return "rsi-os"
    return "rsi-neu"


def rsi_cell_class(rsi):
    """RSI value → background highlight class for the table cell."""
    v = safe_float(rsi)
    if v is None:
        return ""
    if v >= 70:
        return "rsi-ob-cell"
    if v <= 30:
        return "rsi-os-cell"
    return ""


def rsi_color_class(rsi):
    """RSI value → text color class for the number itself."""
    v = safe_float(rsi)
    if v is None:
        return "flat"
    if v >= 70:
        return "text-red"
    if v <= 30:
        return "text-green"
    return ""


def rsi_width(rsi):
    """RSI value → percentage width string for the bar fill."""
    v = safe_float(rsi)
    if v is None:
        return "0%"
    return f"{min(v, 100):.0f}%"


def rsi_str(rsi):
    """RSI value → formatted string or N/A."""
    v = safe_float(rsi)
    if v is None:
        return '<span class="na-val">N/A</span>'
    return f"{v:.1f}"


def fg_class(score):
    """Fear & Greed score → CSS color class."""
    v = safe_float(score)
    if v is None:
        return "flat"
    if v <= 25:
        return "fg-extreme-fear"
    if v <= 45:
        return "fg-fear"
    if v <= 55:
        return "fg-neutral"
    if v <= 75:
        return "fg-greed"
    return "fg-extreme-greed"


def pc_class(val):
    """
    P/C ratio → CSS class.
    >1.0 = bearish = text-red; <1.0 = bullish = text-green
    """
    v = safe_float(val)
    if v is None:
        return "flat"
    return "text-red" if v >= 1.0 else "text-green"


def pct_bar_class(pct_val):
    """Breadth percentage → bar color class."""
    v = safe_float(pct_val)
    if v is None:
        return "pct-mid"
    if v >= 60:
        return "pct-high"
    if v >= 35:
        return "pct-mid"
    return "pct-low"


def pct_text_color(pct_val):
    """Breadth percentage → inline color for the number."""
    v = safe_float(pct_val)
    if v is None:
        return "#666"
    if v >= 60:
        return "#3ddc84"
    if v >= 35:
        return "#f0c040"
    return "#ff5c5c"


def chg_cell(val):
    """
    Render a colored pill span for a % change value.
    Positive → text-green-bg, Negative → text-red-bg
    """
    v = safe_float(val)
    if v is None:
        return '<span class="na-val">N/A</span>'
    direction = "text-green" if v >= 0 else "text-red"
    prefix = "+" if v >= 0 else ""
    return f'<span class="chg-cell {direction}-bg">{prefix}{v:.2f}%</span>'


def fmt_vol(vol):
    """Format volume in millions."""
    v = safe_float(vol)
    if v is None:
        return "N/A"
    return f"{v / 1_000_000:.0f}M"


def fmt_score(val, decimals=1):
    """Format a score value or return N/A."""
    v = safe_float(val)
    if v is None:
        return '<span class="na-val">N/A</span>'
    return f"{v:.{decimals}f}"


# ══════════════════════════════════════════════════════════════════════
# BUILD REPLACEMENT DICTIONARY
# ══════════════════════════════════════════════════════════════════════
tags = {}

# ── Meta ──────────────────────────────────────────────────────────────
tags["{{DATE}}"]          = meta.get("date",          "N/A")
tags["{{GENERATED_HKT}}"] = meta.get("generated_hkt", "N/A")
tags["{{GENERATED_ET}}"]  = meta.get("generated_et",  "N/A")

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
    p_val = m.get("price")
    c_val = m.get("change_1d_pct")
    tags[f"{{{{{label}_PRICE}}}}"]   = price(p_val, dec)
    tags[f"{{{{{label}_CHG_PCT}}}}"] = pct(c_val)
    tags[f"{{{{{label}_DIR}}}}"]     = css_dir(c_val)

# ── Section 2: Major Indices ──────────────────────────────────────────
for sym in ["SPY", "QQQ", "DIA", "IWM"]:
    e = indices.get(sym, {})
    rsi_val   = e.get("rsi14")
    chg_val   = e.get("change_1d_pct")
    status    = e.get("status", "N/A")

    tags[f"{{{{{sym}_PRICE}}}}"]          = price(e.get("price"))
    tags[f"{{{{{sym}_CHG_PCT}}}}"]        = pct(chg_val)
    tags[f"{{{{{sym}_CHG_DIR}}}}"]        = css_dir(chg_val)
    tags[f"{{{{{sym}_STATUS}}}}"]         = status
    tags[f"{{{{{sym}_BADGE_CLASS}}}}"]    = badge(status)
    tags[f"{{{{{sym}_MA20}}}}"]           = price(e.get("ma20"))
    tags[f"{{{{{sym}_MA50}}}}"]           = price(e.get("ma50"))
    tags[f"{{{{{sym}_MA200}}}}"]          = price(e.get("ma200"))
    tags[f"{{{{{sym}_VS_MA20_PCT}}}}"]    = pct(e.get("vs_ma20_pct"))
    tags[f"{{{{{sym}_VS_MA50_PCT}}}}"]    = pct(e.get("vs_ma50_pct"))
    tags[f"{{{{{sym}_VS_MA200_PCT}}}}"]   = pct(e.get("vs_ma200_pct"))
    tags[f"{{{{{sym}_VS_MA20_DIR}}}}"]    = css_dir(e.get("vs_ma20_pct"))
    tags[f"{{{{{sym}_VS_MA50_DIR}}}}"]    = css_dir(e.get("vs_ma50_pct"))
    tags[f"{{{{{sym}_VS_MA200_DIR}}}}"]   = css_dir(e.get("vs_ma200_pct"))
    tags[f"{{{{{sym}_RSI}}}}"]            = rsi_str(rsi_val)
    tags[f"{{{{{sym}_RSI_CLASS}}}}"]      = rsi_bar_class(rsi_val)
    tags[f"{{{{{sym}_RSI_W}}}}"]          = rsi_width(rsi_val)
    tags[f"{{{{{sym}_RSI_CELL_CLASS}}}}"] = rsi_cell_class(rsi_val)
    tags[f"{{{{{sym}_RSI_COLOR}}}}"]      = rsi_color_class(rsi_val)

# ── Section 3: Sentiment ──────────────────────────────────────────────
fg    = sentiment.get("fear_greed", {})
naaim = sentiment.get("naaim",      {})
pc    = sentiment.get("put_call",   {})

fg_score_val = fg.get("score")
tags["{{FG_SCORE}}"]      = fmt_score(fg_score_val, 1)
tags["{{FG_RATING}}"]     = str(fg.get("rating", "N/A")).title()
tags["{{FG_CLASS}}"]      = fg_class(fg_score_val)
tags["{{FG_PREV_CLOSE}}"] = fmt_score(fg.get("prev_close"), 1)
tags["{{FG_PREV_1W}}"]    = fmt_score(fg.get("prev_1w"),    1)
tags["{{FG_PREV_1M}}"]    = fmt_score(fg.get("prev_1m"),    1)
tags["{{FG_PREV_1Y}}"]    = fmt_score(fg.get("prev_1y"),    1)

naaim_val = naaim.get("value")
tags["{{NAAIM_VALUE}}"] = fmt_score(naaim_val, 2)
tags["{{NAAIM_DATE}}"]  = str(naaim.get("date", "N/A"))

pc_val = pc.get("value")
tags["{{PC_VALUE}}"]  = fmt_score(pc_val, 4)
tags["{{PC_RATING}}"] = str(pc.get("rating", "N/A")).title()
tags["{{PC_CLASS}}"]  = pc_class(pc_val)

# ── Section 4a/b: Breadth % Above MA ─────────────────────────────────
breadth_index_map = [
    ("sp500",       "S&amp;P 500"),
    ("nasdaq",      "NASDAQ"),
    ("nyse",        "NYSE"),
    ("russell2000", "Russell 2000"),
]

def breadth_cell(pct_val):
    """Render a breadth percentage cell with bar and color."""
    v = safe_float(pct_val)
    if v is None:
        return '<td><span class="na-val">N/A</span></td>'
    bc    = pct_bar_class(v)
    color = pct_text_color(v)
    bar_w = f"{min(v, 100):.0f}%"
    return (
        f'<td>'
        f'<div class="pct-bar-wrap">'
        f'<span style="font-weight:600;color:{color}">{v:.1f}%</span>'
        f'<div class="pct-bar"><div class="pct-fill {bc}" style="width:{bar_w}"></div></div>'
        f'</div>'
        f'</td>'
    )

breadth_rows = []
for key, label in breadth_index_map:
    b     = breadth.get(key, {})
    total = b.get("total")
    total_str = f"{int(total):,}" if total is not None else '<span class="na-val">N/A</span>'
    breadth_rows.append(
        f"<tr>"
        f"<td>{label}</td>"
        f"<td style='text-align:center'>{total_str}</td>"
        + breadth_cell(b.get("pct_above_20ma"))
        + breadth_cell(b.get("pct_above_50ma"))
        + breadth_cell(b.get("pct_above_200ma"))
        + "</tr>"
    )
tags["{{BREADTH_ROWS}}"] = "\n".join(breadth_rows)

# ── Section 4: Avg Daily Range ────────────────────────────────────────
adr_data = breadth.get("avg_daily_range", {})
adr_rows = []
for sym in ["SPY", "QQQ", "DIA", "IWM"]:
    val = adr_data.get(sym)
    v   = safe_float(val)
    val_str = f"{v:.2f}%" if v is not None else '<span class="na-val">N/A</span>'
    adr_rows.append(
        f"<tr>"
        f"<td style='font-weight:700'>{sym}</td>"
        f"<td style='text-align:center;font-weight:600'>{val_str}</td>"
        f"</tr>"
    )
tags["{{ADR_ROWS}}"] = "\n".join(adr_rows)

# ── Section 4c: Advance-Decline ───────────────────────────────────────
ad = breadth.get("market_wide_advance_decline", {})

def build_adr_rows(exch):
    """Build the ADR detail rows for one exchange."""
    if not exch:
        return '<div class="adr-row"><span class="adr-key">No data available</span></div>'

    def row(label, val, color_class=""):
        style = f' class="adr-val {color_class}"' if color_class else ' class="adr-val"'
        return (
            f'<div class="adr-row">'
            f'<span class="adr-key">{label}</span>'
            f'<span{style}>{val}</span>'
            f'</div>'
        )

    adv   = exch.get("advances")
    dec   = exch.get("declines")
    unch  = exch.get("unchanged")
    p_adv = exch.get("pct_advancing")
    p_dec = exch.get("pct_declining")
    ratio = exch.get("ad_ratio")
    h52   = exch.get("new_52w_highs")
    l52   = exch.get("new_52w_lows")
    adv_v = exch.get("adv_vol")
    dec_v = exch.get("dec_vol")

    def fmt_int(v):
        iv = safe_float(v)
        return f"{int(iv):,}" if iv is not None else '<span class="na-val">N/A</span>'

    ratio_v = safe_float(ratio)
    ratio_class = "text-green" if ratio_v and ratio_v >= 1 else "text-red"

    return "\n".join([
        row("Advances",    fmt_int(adv),                             "text-green"),
        row("Declines",    fmt_int(dec),                             "text-red"),
        row("Unchanged",   fmt_int(unch)),
        row("% Advancing", fmt_score(p_adv, 1) + "%",               "text-green"),
        row("% Declining", fmt_score(p_dec, 1) + "%",               "text-red"),
        row("A/D Ratio",   fmt_score(ratio, 3),                     ratio_class),
        row("Adv Volume",  fmt_vol(adv_v)),
        row("Dec Volume",  fmt_vol(dec_v)),
        row("52W Highs",   fmt_int(h52),                             "text-green"),
        row("52W Lows",    fmt_int(l52),                             "text-red"),
    ])

tags["{{NASDAQ_ADR_ROWS}}"] = build_adr_rows(ad.get("NASDAQ", {}))
tags["{{NYSE_ADR_ROWS}}"]   = build_adr_rows(ad.get("NYSE",   {}))

# ── Section 5A: Sectors sorted by 1D change ──────────────────────────
sorted_sectors = sorted(
    sectors,
    key=lambda x: safe_float(x.get("change_1d_pct"), 0),
    reverse=True
)

sector_rows_full = []
for s in sorted_sectors:
    sym     = s.get("symbol", "N/A")
    name    = s.get("name",   "N/A")
    pr      = s.get("price")
    c1d     = s.get("change_1d_pct")
    c1w     = s.get("change_1w_pct")
    c1m     = s.get("change_1m_pct")
    rsi_val = s.get("rsi14")
    vs20    = s.get("vs20ma", "N/A")
    stat    = s.get("status", "N/A")

    # vs20ma color
    vs20_class = "text-green" if vs20 == "Green" else ("text-red" if vs20 == "Red" else "flat")

    sector_rows_full.append(
        f"<tr>"
        f"<td><span class='sym'>{sym}</span></td>"
        f"<td style='color:var(--text-sub);font-size:12px'>{name}</td>"
        f"<td style='font-weight:600'>${price(pr)}</td>"
        f"<td>{chg_cell(c1d)}</td>"
        f"<td>{chg_cell(c1w)}</td>"
        f"<td>{chg_cell(c1m)}</td>"
        f"<td class='{rsi_cell_class(rsi_val)}'>"
        f"<div class='rsi-wrap'>"
        f"<span class='{rsi_color_class(rsi_val)}' style='font-weight:600'>{rsi_str(rsi_val)}</span>"
        f"<div class='rsi-bar'><div class='rsi-fill {rsi_bar_class(rsi_val)}' style='width:{rsi_width(rsi_val)}'></div></div>"
        f"</div></td>"
        f"<td class='{vs20_class}' style='font-weight:600'>{vs20}</td>"
        f"<td><span class='status-badge {badge(stat)}'>{stat}</span></td>"
        f"</tr>"
    )
tags["{{SECTOR_ROWS_FULL}}"] = "\n".join(sector_rows_full)

# ── Section 5B: Top 15 Industries ────────────────────────────────────
industry_rows = []
for ind in industry[:15]:
    rank  = ind.get("rank", "")
    label = ind.get("label", "N/A")
    industry_rows.append(
        f"<tr>"
        f"<td style='text-align:center'><span class='rank-num'>{rank}</span></td>"
        f"<td style='font-weight:600;max-width:220px;white-space:normal'>{label}</td>"
        f"<td>{chg_cell(ind.get('change_1d_pct'))}</td>"
        f"<td>{chg_cell(ind.get('change_1w_pct'))}</td>"
        f"<td>{chg_cell(ind.get('change_1m_pct'))}</td>"
        f"<td>{chg_cell(ind.get('change_3m_pct'))}</td>"
        f"<td>{chg_cell(ind.get('change_ytd_pct'))}</td>"
        f"</tr>"
    )
tags["{{INDUSTRY_ROWS}}"] = "\n".join(industry_rows)

# ── Section 6 & 7: AI placeholders ───────────────────────────────────
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

# ── Legacy compatibility: keep {{SECTOR_ROWS}} for any old references ─
rows_legacy = []
for s in sectors:
    sym     = s.get("symbol", "")
    rsi_val = s.get("rsi14")
    vs20    = s.get("vs20ma", "")
    vs20_c  = "text-green" if vs20 == "Green" else "text-red"
    rows_legacy.append(
        f"<tr>"
        f"<td class='sym'>{sym}</td>"
        f"<td>${price(s.get('price'))}</td>"
        f"<td>{chg_cell(s.get('change_1d_pct'))}</td>"
        f"<td>"
        f"<div class='rsi-wrap'>"
        f"<span>{rsi_str(rsi_val)}</span>"
        f"<div class='rsi-bar'><div class='rsi-fill {rsi_bar_class(rsi_val)}' style='width:{rsi_width(rsi_val)}'></div></div>"
        f"</div></td>"
        f"<td class='{vs20_c}'>{vs20}</td>"
        f"<td><span class='status-badge {badge(s.get('status',''))}'>{s.get('status','')}</span></td>"
        f"</tr>"
    )
tags["{{SECTOR_ROWS}}"] = "\n".join(rows_legacy)

# ══════════════════════════════════════════════════════════════════════
# READ TEMPLATE → SUBSTITUTE → WRITE OUTPUT
# ══════════════════════════════════════════════════════════════════════
with open(TMPL, encoding="utf-8") as f:
    html = f.read()

for tag, value in tags.items():
    html = html.replace(tag, str(value))

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅  Done!  Output → {OUTPUT}")
print(f"    Tags injected : {len(tags)}")

# ── Verify: no leftover {{TAGS}} ──────────────────────────────────────
leftover = re.findall(r"\{\{[A-Z_0-9]+\}\}", html)
if leftover:
    print(f"⚠️   Leftover tags ({len(leftover)}): {sorted(set(leftover))}")
else:
    print("✅  All tags resolved — zero residual placeholders.")
