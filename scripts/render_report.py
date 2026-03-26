#!/usr/bin/env python3
"""
render_report.py  —  Credit-Efficient Market Summary System  v4.0
Reads:  data/today_market.json
Writes: index.html

Dynamic coloring:
  > 0  → text-green  (#4caf50)
  < 0  → text-red    (#f44336)
  RSI ≥ 70 → text-red + rsi-ob-cell
  RSI ≤ 30 → text-green + rsi-os-cell
  F&G ≤ 25 → text-red  |  F&G ≥ 75 → text-green
  P/C > 1.0 → text-red
  % Above MA ≥ 60% → text-green | ≤ 35% → text-red | else text-amber
  N/A safety: all .get() default to None → rendered as <span class="na-val">N/A</span>
"""

import json, os, re
from pathlib import Path

BASE   = Path(__file__).resolve().parent.parent
JSON   = BASE / "data"      / "today_market.json"
TMPL   = BASE / "templates" / "report_template.html"
OUTPUT = BASE / "index.html"

# ── Helpers ────────────────────────────────────────────────────────────────

def safe_float(val, default=None):
    if val is None: return default
    try: return float(val)
    except (TypeError, ValueError): return default

def na(val, fmt=None, dec=2):
    if val is None: return '<span class="na-val">N/A</span>'
    f = safe_float(val)
    if f is None: return '<span class="na-val">N/A</span>'
    if fmt == "pct":
        sign = "+" if f > 0 else ""
        return f"{sign}{f:.{dec}f}%"
    if fmt == "price": return f"{f:,.{dec}f}"
    if fmt == "int":   return f"{int(f):,}"
    return f"{f:.{dec}f}"

def css_dir(val, neutral=""):
    f = safe_float(val)
    if f is None: return neutral
    return "text-green" if f > 0 else ("text-red" if f < 0 else neutral)

def chg_cell(val, dec=2):
    f = safe_float(val)
    if f is None: return '<span class="na-val">N/A</span>'
    cls = "text-green-bg" if f >= 0 else "text-red-bg"
    sign = "+" if f > 0 else ""
    return f'<span class="chg-pill {cls}">{sign}{f:.{dec}f}%</span>'

def rsi_cell(val):
    f = safe_float(val)
    if f is None: return '<span class="na-val">N/A</span>', ""
    clamped = max(0, min(100, f))
    if f >= 70:   fill, txt, row = "rsi-fill rsi-ob",  "text-red",   "rsi-ob-cell"
    elif f <= 30: fill, txt, row = "rsi-fill rsi-os",  "text-green", "rsi-os-cell"
    else:         fill, txt, row = "rsi-fill rsi-neu", "",           ""
    bar = (f'<div class="rsi-wrap"><span class="{txt}">{f:.1f}</span>'
           f'<div class="rsi-track"><div class="{fill}" style="width:{clamped:.0f}%"></div></div></div>')
    return bar, row

def pct_bar_cell(val, dec=1):
    f = safe_float(val)
    if f is None: return '<span class="na-val">N/A</span>'
    clamped = max(0, min(100, f))
    if f >= 60:   bar_cls, txt_cls = "pct-bar-green", "text-green"
    elif f <= 35: bar_cls, txt_cls = "pct-bar-red",   "text-red"
    else:         bar_cls, txt_cls = "pct-bar-amber",  "text-amber"
    return (f'<div class="pct-bar-wrap"><span class="{txt_cls}">{f:.{dec}f}%</span>'
            f'<div class="pct-bar-track"><div class="{bar_cls}" style="width:{clamped:.0f}%"></div></div></div>')

def status_badge(s):
    s = (s or "").upper()
    if "ABOVE" in s: return '<span class="status-badge badge-above">Above All</span>'
    if "BELOW" in s: return '<span class="status-badge badge-below">Below All</span>'
    return '<span class="status-badge badge-mixed">Mixed</span>'

def fg_color(score):
    f = safe_float(score)
    if f is None: return ""
    if f <= 25: return "text-red"
    if f >= 75: return "text-green"
    if f <= 45: return "text-amber"
    return "text-green"

def pc_color(val):
    f = safe_float(val)
    if f is None: return ""
    if f > 1.0:  return "text-red"
    if f <= 0.8: return "text-green"
    return "text-amber"

def pc_rating(val):
    f = safe_float(val)
    if f is None: return "N/A"
    if f > 1.0:  return "Bearish (High Fear)"
    if f <= 0.8: return "Bullish (Low Fear)"
    return "Neutral"

def adr_color(val):
    f = safe_float(val)
    if f is None: return ""
    if f >= 1.0: return "text-green"
    if f < 0.8:  return "text-red"
    return "text-amber"

# ── Symbol metadata ────────────────────────────────────────────────────────

SYM_NAMES = {
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF",
    "DIA": "Dow Jones ETF", "IWM": "Russell 2000 ETF",
}
SECTOR_NAMES = {
    "XLK": "Technology",       "XLV": "Health Care",
    "XLF": "Financials",       "XLE": "Energy",
    "XLY": "Cons. Discretionary", "XLP": "Cons. Staples",
    "XLI": "Industrials",      "XLB": "Materials",
    "XLRE": "Real Estate",     "XLU": "Utilities",
    "XLC": "Communication Svcs",
}
BREADTH_KEYS = [
    ("sp500",       "S&P 500",    "SPY"),
    ("nasdaq",      "NASDAQ",     "QQQ"),
    ("nyse",        "NYSE",       "DIA"),
    ("russell2000", "Russell 2000","IWM"),
]

# ── Section builders ───────────────────────────────────────────────────────

def build_indices_rows(indices, breadth):
    rows = []
    vol_adr = (breadth or {}).get("volatility_adr", {})
    for sym in ["SPY", "QQQ", "DIA", "IWM"]:
        d = indices.get(sym, {})
        price   = na(d.get("price"), "price")
        chg     = chg_cell(d.get("change_1d_pct"))
        rsi_html, rsi_row = rsi_cell(d.get("rsi14"))
        vs20    = na(d.get("vs_ma20_pct"),  "pct")
        vs50    = na(d.get("vs_ma50_pct"),  "pct")
        vs200   = na(d.get("vs_ma200_pct"), "pct")
        vs20_c  = css_dir(d.get("vs_ma20_pct"))
        vs50_c  = css_dir(d.get("vs_ma50_pct"))
        vs200_c = css_dir(d.get("vs_ma200_pct"))
        adr_f   = safe_float(d.get("ad_ratio"))
        adr_c   = adr_color(adr_f)
        adr_str = (f'<span class="{adr_c}">{adr_f:.3f}</span>'
                   if adr_f is not None else '<span class="na-val">N/A</span>')
        badge   = status_badge(d.get("status"))
        name    = SYM_NAMES.get(sym, "")
        rows.append(
            f'<tr class="{rsi_row}">'
            f'<td><div class="sym-cell"><span class="sym">{sym}</span>'
            f'<span class="sym-name">{name}</span></div></td>'
            f'<td>{price}</td><td>{chg}</td><td>{rsi_html}</td>'
            f'<td class="{vs20_c}">{vs20}</td>'
            f'<td class="{vs50_c}">{vs50}</td>'
            f'<td class="{vs200_c}">{vs200}</td>'
            f'<td>{adr_str}</td><td>{badge}</td></tr>'
        )
    return "\n".join(rows)

def build_naaim_history(naaim):
    history = (naaim or {}).get("history", [])
    if not history:
        return '<div class="naaim-hist-row"><span>No history</span></div>'
    rows = []
    for e in history[:3]:
        d = e.get("date", "—")
        v = safe_float(e.get("value"))
        v_str = f"{v:.2f}" if v is not None else "N/A"
        rows.append(f'<div class="naaim-hist-row"><span>{d}</span>'
                    f'<span class="nh-val">{v_str}</span></div>')
    return "\n".join(rows)

def build_breadth_rows(breadth, indices):
    if not breadth:
        return '<tr><td colspan="7"><span class="na-val">N/A</span></td></tr>'
    pct_above = breadth.get("pct_above_ma", {})
    vol_adr   = breadth.get("volatility_adr", {})
    rows = []
    for key, label, etf in BREADTH_KEYS:
        d     = pct_above.get(key, {})
        total = na(d.get("total"), "int")
        p20   = pct_bar_cell(d.get("above_20ma_pct"))
        p50   = pct_bar_cell(d.get("above_50ma_pct"))
        p200  = pct_bar_cell(d.get("above_200ma_pct"))
        vadr  = safe_float(vol_adr.get(etf))
        vadr_str = f"{vadr:.2f}%" if vadr is not None else '<span class="na-val">N/A</span>'
        rows.append(
            f'<tr><td><strong>{label}</strong></td><td>{total}</td>'
            f'<td>{p20}</td><td>{p50}</td><td>{p200}</td>'
            f'<td style="color:var(--text-muted)">{etf}</td><td>{vadr_str}</td></tr>'
        )
    return "\n".join(rows)

def build_adr_cards(breadth):
    if not breadth:
        return '<div class="na-val">N/A</div>'
    mwad = breadth.get("market_wide_advance_decline", {})
    cards = []
    for mkt in ["NYSE", "NASDAQ"]:
        d = mwad.get(mkt, {})
        adv     = na(d.get("advances"),    "int")
        dec     = na(d.get("declines"),    "int")
        unch    = na(d.get("unchanged"),   "int")
        total   = na(d.get("total_issues"),"int")
        pct_adv = na(d.get("pct_advancing"),"pct",1)
        pct_dec = na(d.get("pct_declining"),"pct",1)
        adr_f   = safe_float(d.get("ad_ratio"))
        adr_c   = adr_color(adr_f)
        adr_str = (f'<span class="{adr_c}">{adr_f:.3f}</span>'
                   if adr_f is not None else '<span class="na-val">N/A</span>')
        hi52    = na(d.get("new_52w_highs"),"int")
        lo52    = na(d.get("new_52w_lows"), "int")
        av      = safe_float(d.get("adv_vol"))
        dv      = safe_float(d.get("dec_vol"))
        av_str  = f"{int(av/1e6):.0f}M" if av else '<span class="na-val">N/A</span>'
        dv_str  = f"{int(dv/1e6):.0f}M" if dv else '<span class="na-val">N/A</span>'
        cards.append(
            f'<div class="adr-card"><div class="adr-card-head">{mkt}</div>'
            f'<div class="adr-row"><span>Advances</span><span class="adr-val text-green">{adv}</span></div>'
            f'<div class="adr-row"><span>Declines</span><span class="adr-val text-red">{dec}</span></div>'
            f'<div class="adr-row"><span>Unchanged</span><span class="adr-val">{unch}</span></div>'
            f'<div class="adr-row"><span>Total Issues</span><span class="adr-val">{total}</span></div>'
            f'<div class="adr-row"><span>% Advancing</span><span class="adr-val text-green">{pct_adv}</span></div>'
            f'<div class="adr-row"><span>% Declining</span><span class="adr-val text-red">{pct_dec}</span></div>'
            f'<div class="adr-row"><span>A/D Ratio</span><span class="adr-val">{adr_str}</span></div>'
            f'<div class="adr-row"><span>Adv Volume</span><span class="adr-val">{av_str}</span></div>'
            f'<div class="adr-row"><span>Dec Volume</span><span class="adr-val">{dv_str}</span></div>'
            f'<div class="adr-row"><span>52W Highs</span><span class="adr-val text-green">{hi52}</span></div>'
            f'<div class="adr-row"><span>52W Lows</span><span class="adr-val text-red">{lo52}</span></div>'
            f'</div>'
        )
    return "\n".join(cards)

def build_sector_rows(sectors):
    if not sectors:
        return '<tr><td colspan="9"><span class="na-val">N/A</span></td></tr>'
    rows = []
    for s in sectors:  # already RSI-sorted by fetch_all_data.py
        sym   = s.get("symbol", "")
        name  = SECTOR_NAMES.get(sym, s.get("name", ""))
        price = na(s.get("price"), "price")
        c1d   = chg_cell(s.get("change_1d_pct"))
        c1w   = chg_cell(s.get("change_1w_pct"))
        c1m   = chg_cell(s.get("change_1m_pct"))
        rsi_html, rsi_row = rsi_cell(s.get("rsi14"))
        vs20  = na(s.get("vs_ma20_pct"), "pct")
        vs20_c = css_dir(s.get("vs_ma20_pct"))
        badge = status_badge(s.get("status"))
        rows.append(
            f'<tr class="{rsi_row}">'
            f'<td><strong>{sym}</strong></td>'
            f'<td style="color:var(--text-label)">{name}</td>'
            f'<td>{price}</td><td>{c1d}</td><td>{c1w}</td><td>{c1m}</td>'
            f'<td>{rsi_html}</td><td class="{vs20_c}">{vs20}</td><td>{badge}</td></tr>'
        )
    return "\n".join(rows)

def build_industry_rows(industry):
    if not industry:
        return '<tr><td colspan="8"><span class="na-val">N/A</span></td></tr>'
    rows = []
    for row in industry:
        rank   = row.get("rank", "")
        label  = row.get("label", "")
        ns     = row.get("num_stocks")
        ns_str = str(int(ns)) if ns is not None else '<span class="na-val">N/A</span>'
        c1d    = chg_cell(row.get("change_1d_pct"))
        c1w    = chg_cell(row.get("change_1w_pct"))
        c1m    = chg_cell(row.get("change_1m_pct"))
        c3m    = chg_cell(row.get("change_3m_pct"))
        cytd   = chg_cell(row.get("change_ytd_pct"))
        rows.append(
            f'<tr><td style="text-align:center;color:var(--text-muted)">{rank}</td>'
            f'<td>{label}</td>'
            f'<td style="color:var(--text-label)">{ns_str}</td>'
            f'<td>{c1d}</td><td>{c1w}</td><td>{c1m}</td><td>{c3m}</td><td>{cytd}</td></tr>'
        )
    return "\n".join(rows)

# ── Main ───────────────────────────────────────────────────────────────────

def render():
    with open(JSON, encoding="utf-8") as f:
        data = json.load(f)

    meta      = data.get("meta",      {})
    macro     = data.get("macro",     {})
    indices   = data.get("indices",   {})
    sentiment = data.get("sentiment", {})
    sectors   = data.get("sectors",   [])
    industry  = data.get("industry",  [])
    breadth   = data.get("breadth",   {})
    fg        = sentiment.get("fear_greed", {})
    naaim     = sentiment.get("naaim",      {})
    pc        = sentiment.get("put_call",   {})

    with open(TMPL, encoding="utf-8") as f:
        html = f.read()

    # Header
    html = html.replace("{{DATE}}",   meta.get("date", "—"))
    html = html.replace("{{TS_HKT}}", meta.get("generated_hkt", "—"))
    html = html.replace("{{TS_ET}}",  meta.get("generated_et",  "—"))

    # Section 1: Macro
    for sym, key, dec in [
        ("VIX","VIX",2),("DXY","DXY",3),("TNX","TNX_10Y",3),
        ("GOLD","GOLD",2),("OIL","OIL_WTI",2),("BTC","BTC",0),
    ]:
        d = macro.get(key, {})
        pv = safe_float(d.get("price"))
        cv = safe_float(d.get("change_1d_pct"))
        if pv is None:
            p_str = '<span class="na-val">N/A</span>'
        elif sym == "BTC":
            p_str = f"{pv:,.0f}"
        elif dec == 0:
            p_str = f"{pv:,.0f}"
        else:
            p_str = f"{pv:,.{dec}f}"
        c_str = na(cv, "pct") if cv is not None else '<span class="na-val">N/A</span>'
        c_cls = css_dir(cv)
        html = html.replace(f"{{{{{sym}_PRICE}}}}", p_str)
        html = html.replace(f"{{{{{sym}_CHG_PCT}}}}", c_str)
        html = html.replace(f"{{{{{sym}_CHG_CLASS}}}}", c_cls)

    # Section 2: Indices
    html = html.replace("{{INDICES_ROWS}}", build_indices_rows(indices, breadth))

    # Section 3: Sentiment
    fg_score = safe_float(fg.get("score"))
    html = html.replace("{{FG_SCORE}}",      f"{fg_score:.0f}" if fg_score is not None else '<span class="na-val">N/A</span>')
    html = html.replace("{{FG_RATING}}",     str(fg.get("rating", "N/A")).title())
    html = html.replace("{{FG_COLOR}}",      fg_color(fg_score))
    html = html.replace("{{FG_PREV_CLOSE}}", na(fg.get("prev_close")))
    html = html.replace("{{FG_PREV_1W}}",    na(fg.get("prev_1w")))
    html = html.replace("{{FG_PREV_1M}}",    na(fg.get("prev_1m")))
    html = html.replace("{{FG_PREV_1Y}}",    na(fg.get("prev_1y")))

    nv = safe_float(naaim.get("value"))
    html = html.replace("{{NAAIM_VALUE}}", f"{nv:.2f}" if nv is not None else '<span class="na-val">N/A</span>')
    html = html.replace("{{NAAIM_DATE}}",  naaim.get("date", "—"))
    html = html.replace("{{NAAIM_HISTORY_ROWS}}", build_naaim_history(naaim))

    pv = safe_float(pc.get("value"))
    html = html.replace("{{PC_VALUE}}",  f"{pv:.4f}" if pv is not None else '<span class="na-val">N/A</span>')
    html = html.replace("{{PC_COLOR}}",  pc_color(pv))
    html = html.replace("{{PC_RATING}}", pc_rating(pv))

    # Section 4: Breadth
    html = html.replace("{{BREADTH_ROWS}}", build_breadth_rows(breadth, indices))
    html = html.replace("{{ADR_CARDS}}",    build_adr_cards(breadth))

    # Section 5: Sectors & Industries
    html = html.replace("{{SECTOR_ROWS}}",   build_sector_rows(sectors))
    html = html.replace("{{INDUSTRY_ROWS}}", build_industry_rows(industry))

    # Sections 6 & 7: AI placeholders
    html = html.replace("{{S6_CONTENT}}", "[AI Market Analysis — to be filled by AI commentary step]")
    html = html.replace("{{S7_CONTENT}}", "[AI Trading Outlook & Watchlist — to be filled by AI commentary step]")

    # Residual check
    leftover = re.findall(r"\{\{[A-Z0-9_]+\}\}", html)
    if leftover:
        print(f"  ⚠  Unresolved tags ({len(leftover)}): {leftover[:10]}")
    else:
        print("  ✓  All template tags resolved (0 residual)")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"  ✓  index.html written  ({size_kb:.1f} KB)")

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("  Market Summary Renderer v4.0")
    print("╚══════════════════════════════════════════════╝")
    render()
    print("✅  Render complete.")
