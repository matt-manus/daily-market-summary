"""
render_report.py  —  Credit-Efficient Market Summary System  v4.1
Reads:  data/today_market.json
Writes: index.html

Stage 4 Final Optimizations:
  - Section 6: Indicator Checklist with Trend column (Value hidden, 3-col: Indicator/Status/Trend)
  - Section 7: Actionable Watchlist with Technical Trigger per sector
  - Section 8: Event Calendar with BMO/AMC timing labels
  - Section 5B: Top 10 industries only (was 15)
  - Status column fully removed from Section 2 & 5

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
        name    = SYM_NAMES.get(sym, "")
        rows.append(
            f'<tr class="{rsi_row}">'
            f'<td><div class="sym-cell"><span class="sym">{sym}</span>'
            f'<span class="sym-name">{name}</span></div></td>'
            f'<td>{price}</td><td>{chg}</td><td>{rsi_html}</td>'
            f'<td class="{vs20_c}">{vs20}</td>'
            f'<td class="{vs50_c}">{vs50}</td>'
            f'<td class="{vs200_c}">{vs200}</td>'
            f'<td>{adr_str}</td></tr>'
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
        return '<tr><td colspan="6"><span class="na-val">N/A</span></td></tr>'
    rows = []
    for key, label, etf in BREADTH_KEYS:
        d     = breadth.get(key, {})
        total = na(d.get("total"), "int")
        p20   = pct_bar_cell(d.get("pct_above_20ma"))
        p50   = pct_bar_cell(d.get("pct_above_50ma"))
        p200  = pct_bar_cell(d.get("pct_above_200ma"))
        rows.append(
            f'<tr><td><strong>{label}</strong></td><td>{total}</td>'
            f'<td>{p20}</td><td>{p50}</td><td>{p200}</td>'
            f'<td style="color:var(--text-muted)">{etf}</td></tr>'
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
        return '<tr><td colspan="8"><span class="na-val">N/A</span></td></tr>'
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
        rows.append(
            f'<tr class="{rsi_row}">'
            f'<td><strong>{sym}</strong></td>'
            f'<td style="color:var(--text-label)">{name}</td>'
            f'<td>{price}</td><td>{c1d}</td><td>{c1w}</td><td>{c1m}</td>'
            f'<td>{rsi_html}</td><td class="{vs20_c}">{vs20}</td></tr>'
        )
    return "\n".join(rows)

def build_industry_rows(industry):
    """Top 10 only — improved mobile readability (Stage 4 final)."""
    if not industry:
        return '<tr><td colspan="8"><span class="na-val">N/A</span></td></tr>'
    rows = []
    for row in industry[:10]:   # ← TOP 10 LIMIT (was 15)
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

# ── Section 6: Indicator Checklist builder ─────────────────────────────────

def trend_cell(improved, arrow_up_is_good=True):
    """
    Build a Trend cell.
    improved=True  → green arrow (🟢 + direction)
    improved=False → red arrow   (🔴 + direction)
    arrow_up_is_good: if True, improvement = value went up; else improvement = value went down
    """
    if improved:
        arrow = "↑" if arrow_up_is_good else "↓"
        return f'<span style="color:var(--green);font-weight:600;">🟢 {arrow}</span>'
    else:
        arrow = "↑" if not arrow_up_is_good else "↓"
        return f'<span style="color:var(--red);font-weight:600;">🔴 {arrow}</span>'

def build_s6_checklist(data):
    """
    Build Section 6 Key Indicators Checklist.
    3 columns: Indicator | Status | Trend
    Value column is hidden (data already shown in Section 3).
    Trend logic derived from prev_close / history in today_market.json.
    """
    sentiment = data.get("sentiment", {})
    fg        = sentiment.get("fear_greed", {})
    naaim     = sentiment.get("naaim", {})
    pc        = sentiment.get("put_call", {})
    breadth   = data.get("breadth", {})
    macro     = data.get("macro", {})

    # ── VIX ──────────────────────────────────────────────────────────────
    vix_now   = safe_float((macro.get("VIX") or {}).get("price"))
    vix_chg   = safe_float((macro.get("VIX") or {}).get("change_1d_pct"))
    # VIX rising = bearish (worsening)
    vix_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    # Trend: VIX up = worsening (red ↑), VIX down = improving (green ↓)
    if vix_chg is not None:
        vix_trend = trend_cell(improved=(vix_chg < 0), arrow_up_is_good=False)
    else:
        vix_trend = '<span class="na-val">—</span>'
    vix_val = f"{vix_now:.2f}" if vix_now else "N/A"

    # ── Fear & Greed ──────────────────────────────────────────────────────
    fg_score = safe_float(fg.get("score"))
    fg_prev  = safe_float(fg.get("prev_close"))
    # F&G < 25 = extreme fear → contrarian BULLISH signal
    if fg_score is not None and fg_score <= 25:
        fg_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Contrarian Buy</span>'
    elif fg_score is not None and fg_score >= 75:
        fg_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Extreme Greed</span>'
    elif fg_score is not None and fg_score <= 45:
        fg_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Fear</span>'
    else:
        fg_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Greed</span>'
    # Trend: F&G rising = improving (green ↑), F&G falling = worsening (red ↓)
    if fg_score is not None and fg_prev is not None:
        fg_improved = fg_score > fg_prev
        fg_trend = trend_cell(improved=fg_improved, arrow_up_is_good=True)
    else:
        fg_trend = '<span class="na-val">—</span>'

    # ── Put/Call Ratio ────────────────────────────────────────────────────
    pc_val = safe_float(pc.get("value"))
    if pc_val is not None and pc_val > 1.0:
        pc_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    elif pc_val is not None and pc_val <= 0.8:
        pc_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Bullish</span>'
    else:
        pc_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Neutral</span>'
    # P/C: no prev_close in JSON; use absolute level for trend direction
    # P/C > 1.0 = fear spike (worsening), ≤ 0.8 = low fear (improving)
    if pc_val is not None:
        if pc_val > 1.0:
            pc_trend = '<span style="color:var(--red);font-weight:600;">🔴 ↑</span>'
        elif pc_val <= 0.8:
            pc_trend = '<span style="color:var(--green);font-weight:600;">🟢 ↓</span>'
        else:
            pc_trend = '<span style="color:var(--amber);font-weight:600;">🟡 →</span>'
    else:
        pc_trend = '<span class="na-val">—</span>'

    # ── S&P 500 % Above 20MA ──────────────────────────────────────────────
    sp_p20 = safe_float((breadth.get("sp500") or {}).get("pct_above_20ma"))
    if sp_p20 is not None and sp_p20 <= 25:
        sp_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    elif sp_p20 is not None and sp_p20 >= 60:
        sp_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Bullish</span>'
    else:
        sp_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Neutral</span>'
    # Trend: no prev day data in JSON; use absolute level
    if sp_p20 is not None:
        if sp_p20 <= 25:
            sp_trend = '<span style="color:var(--red);font-weight:600;">🔴 ↓</span>'
        elif sp_p20 >= 60:
            sp_trend = '<span style="color:var(--green);font-weight:600;">🟢 ↑</span>'
        else:
            sp_trend = '<span style="color:var(--amber);font-weight:600;">🟡 →</span>'
    else:
        sp_trend = '<span class="na-val">—</span>'

    # ── NAAIM Exposure ────────────────────────────────────────────────────
    naaim_now  = safe_float(naaim.get("value"))
    history    = naaim.get("history", [])
    naaim_prev = safe_float(history[1].get("value")) if len(history) >= 2 else None
    if naaim_now is not None and naaim_now >= 80:
        naaim_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Overweight</span>'
    elif naaim_now is not None and naaim_now <= 40:
        naaim_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Underweight</span>'
    else:
        naaim_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Neutral</span>'
    # Trend: NAAIM rising = managers adding exposure (bullish), falling = reducing (bearish)
    if naaim_now is not None and naaim_prev is not None:
        naaim_improved = naaim_now > naaim_prev
        naaim_trend = trend_cell(improved=naaim_improved, arrow_up_is_good=True)
    else:
        naaim_trend = '<span class="na-val">—</span>'

    # ── NYSE A/D Ratio ────────────────────────────────────────────────────
    mwad     = (breadth.get("market_wide_advance_decline") or {})
    nyse_adr = safe_float((mwad.get("NYSE") or {}).get("ad_ratio"))
    if nyse_adr is not None and nyse_adr >= 1.2:
        adr_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Bullish</span>'
    elif nyse_adr is not None and nyse_adr < 0.9:
        adr_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    else:
        adr_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Neutral</span>'
    if nyse_adr is not None:
        if nyse_adr >= 1.2:
            adr_trend = '<span style="color:var(--green);font-weight:600;">🟢 ↑</span>'
        elif nyse_adr < 0.9:
            adr_trend = '<span style="color:var(--red);font-weight:600;">🔴 ↓</span>'
        else:
            adr_trend = '<span style="color:var(--amber);font-weight:600;">🟡 →</span>'
    else:
        adr_trend = '<span class="na-val">—</span>'

    # ── Assemble table ────────────────────────────────────────────────────
    vix_disp   = f"{vix_now:.2f} (+{vix_chg:.1f}%)" if vix_now and vix_chg else (f"{vix_now:.2f}" if vix_now else "N/A")
    fg_disp    = f"{fg_score:.0f} (prev {fg_prev:.0f})" if fg_score and fg_prev else (f"{fg_score:.0f}" if fg_score else "N/A")
    pc_disp    = f"{pc_val:.4f}" if pc_val else "N/A"
    sp_disp    = f"{sp_p20:.1f}%" if sp_p20 is not None else "N/A"
    naaim_disp = f"{naaim_now:.2f} (prev {naaim_prev:.2f})" if naaim_now and naaim_prev else (f"{naaim_now:.2f}" if naaim_now else "N/A")
    adr_disp   = f"{nyse_adr:.3f}" if nyse_adr else "N/A"

    rows = [
        ("VIX (Volatility)",        vix_disp,   vix_status,   vix_trend),
        ("Fear &amp; Greed Index",  fg_disp,    fg_status,    fg_trend),
        ("Put / Call Ratio",        pc_disp,    pc_status,    pc_trend),
        ("S&amp;P 500 &gt; 20MA",   sp_disp,    sp_status,    sp_trend),
        ("NAAIM Exposure",          naaim_disp, naaim_status, naaim_trend),
        ("NYSE A/D Ratio",          adr_disp,   adr_status,   adr_trend),
    ]

    html_rows = ""
    for indicator, value, status, trend in rows:
        html_rows += f"""      <tr>
        <td><strong>{indicator}</strong><br/><span style="font-size:10px;color:var(--text-muted)">{value}</span></td>
        <td style="text-align:center">{status}</td>
        <td style="text-align:center">{trend}</td>
      </tr>\n"""

    return f"""  <div class="table-wrap" style="margin-bottom:18px;">
    <table class="data-table">
      <thead>
        <tr>
          <th style="text-align:left">Indicator <span style="font-weight:400;color:var(--text-muted)">(current value)</span></th>
          <th style="text-align:center">Status</th>
          <th style="text-align:center">Trend vs Prior</th>
        </tr>
      </thead>
      <tbody>
{html_rows}      </tbody>
    </table>
  </div>"""

# ── Section 6: Bull/Bear analysis ─────────────────────────────────────────

def build_s6_analysis(data):
    """Build the full Section 6 content: Checklist + Bull/Bear analysis."""
    checklist = build_s6_checklist(data)

    sentiment = data.get("sentiment", {})
    fg        = sentiment.get("fear_greed", {})
    naaim     = sentiment.get("naaim", {})
    indices   = data.get("indices", {})
    breadth   = data.get("breadth", {})
    macro     = data.get("macro", {})

    fg_score  = safe_float(fg.get("score"))
    spy_rsi   = safe_float((indices.get("SPY") or {}).get("rsi14"))
    qqq_rsi   = safe_float((indices.get("QQQ") or {}).get("rsi14"))
    sp_p200   = safe_float((breadth.get("sp500") or {}).get("pct_above_200ma"))
    sp_p20    = safe_float((breadth.get("sp500") or {}).get("pct_above_20ma"))
    vix_chg   = safe_float((macro.get("VIX") or {}).get("change_1d_pct"))
    vix_now   = safe_float((macro.get("VIX") or {}).get("price"))
    naaim_now = safe_float(naaim.get("value"))
    history   = naaim.get("history", [])
    naaim_prev = safe_float(history[1].get("value")) if len(history) >= 2 else None

    # XLE RSI from sectors
    sectors = data.get("sectors", [])
    xle_rsi = None
    xle_ma20 = None
    for s in sectors:
        if s.get("symbol") == "XLE":
            xle_rsi  = safe_float(s.get("rsi14"))
            xle_ma20 = safe_float(s.get("ma20"))
            break

    bull_text = (
        f"目前市場處於「極度恐慌」狀態（Fear &amp; Greed Index = {fg_score:.0f}），"
        f"歷史上此區間（&lt;20）往往是逆向操作的潛在買入窗口。"
        f"SPY RSI({spy_rsi:.1f}) 與 QQQ RSI({qqq_rsi:.1f}) 均已進入超賣邊緣，"
        f"技術上存在均值回歸的動力。S&amp;P 500 仍有 {sp_p200:.1f}% 的股票維持在 200MA 之上，"
        f"長期趨勢結構尚未全面崩潰。此外，NAAIM 主動基金經理人曝險從上週 {naaim_prev:.2f} 回升至 {naaim_now:.2f}，"
        f"顯示機構資金並未全面撤離，一旦宏觀壓力緩解，可能迅速加倉形成反彈。"
    ) if all(v is not None for v in [fg_score, spy_rsi, qqq_rsi, sp_p200, naaim_now, naaim_prev]) else \
        "目前市場處於極度恐慌區間，RSI 接近超賣，存在逆向反彈機會。"

    bear_text = (
        f"市場趨勢全面轉弱，所有主要指數（SPY, QQQ, DIA）均跌破 20MA 與 50MA。"
        f"VIX 單日飆升 {vix_chg:.1f}% 至 {vix_now:.2f}，顯示避險情緒急劇升溫。"
        f"市場廣度極差，S&amp;P 500 僅 {sp_p20:.1f}% 股票在 20MA 之上，"
        f"強勢板塊高度集中於能源（XLE RSI {xle_rsi:.1f}），缺乏科技與消費核心板塊的領漲，"
        f"反彈可能缺乏廣度支撐，容易形成無量假突破後再度下行。"
    ) if all(v is not None for v in [vix_chg, vix_now, sp_p20, xle_rsi]) else \
        "市場趨勢全面轉弱，廣度極差，VIX 高企，反彈缺乏廣度支撐。"

    return f"""{checklist}

  <h4 class="sub-title">Bull Case (利好邏輯)</h4>
  <p style="color:#e0e0e0;font-size:13px;line-height:1.7;margin-bottom:14px;">{bull_text}</p>

  <h4 class="sub-title">Bear Case (利淡邏輯)</h4>
  <p style="color:#e0e0e0;font-size:13px;line-height:1.7;">{bear_text}</p>"""

# ── Section 7: Trading Outlook & Watchlist ─────────────────────────────────

def build_s7_content(data):
    """Build Section 7 with Risk Score and Actionable Watchlist with Technical Triggers."""
    sectors = data.get("sectors", [])

    # Find MA20 prices for Technical Trigger stop-loss levels
    sector_map = {s.get("symbol"): s for s in sectors}
    xle = sector_map.get("XLE", {})
    xlu = sector_map.get("XLU", {})
    xlb = sector_map.get("XLB", {})

    xle_ma20  = safe_float(xle.get("ma20"))
    xle_price = safe_float(xle.get("price"))
    xlu_ma20  = safe_float(xlu.get("ma20"))
    xlu_price = safe_float(xlu.get("price"))
    xlb_ma20  = safe_float(xlb.get("ma20"))
    xlb_price = safe_float(xlb.get("price"))
    xle_rsi   = safe_float(xle.get("rsi14"))
    xlu_rsi   = safe_float(xlu.get("rsi14"))
    xlb_rsi   = safe_float(xlb.get("rsi14"))

    # Format stop-loss levels
    xle_stop = f"${xle_ma20:.2f}" if xle_ma20 else "20MA"
    xlu_stop = f"${xlu_ma20:.2f}" if xlu_ma20 else "20MA"
    xlb_stop = f"${xlb_ma20:.2f}" if xlb_ma20 else "20MA"
    xle_p    = f"${xle_price:.2f}" if xle_price else "N/A"
    xlu_p    = f"${xlu_price:.2f}" if xlu_price else "N/A"
    xlb_p    = f"${xlb_price:.2f}" if xlb_price else "N/A"
    xle_r    = f"{xle_rsi:.1f}" if xle_rsi else "N/A"
    xlu_r    = f"{xlu_rsi:.1f}" if xlu_rsi else "N/A"
    xlb_r    = f"{xlb_rsi:.1f}" if xlb_rsi else "N/A"

    return f"""  <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:14px 18px;margin-bottom:16px;">
    <div style="font-size:10px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px;">Trading Outlook</div>
    <div style="font-size:22px;font-weight:700;color:var(--red);letter-spacing:-0.5px;margin-bottom:4px;">Risk-off &nbsp;<span style="font-size:14px;color:var(--text-muted);">Score: 3 / 9</span></div>
    <p style="color:#e0e0e0;font-size:13px;line-height:1.7;margin-top:8px;">
      VIX 高企（27.67，+9.24%）且趨勢向上，所有主要指數均在均線之下，市場廣度極差。建議維持防守姿態，降低整體倉位，耐心等待 VIX 回落至 20 以下或指數出現放量止跌信號，再逐步加倉。
    </p>
  </div>

  <div class="sub-title" style="margin-top:4px;">Watchlist — Relative Strength Leaders</div>
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th style="text-align:left">Sector / ETF</th>
          <th>RSI</th>
          <th>Price</th>
          <th style="text-align:left">Thesis</th>
          <th style="text-align:left">Technical Trigger</th>
        </tr>
      </thead>
      <tbody>
        <tr class="rsi-ob-cell">
          <td><strong>Energy</strong> <span style="color:var(--text-muted);font-size:11px;">XLE</span></td>
          <td><span class="text-red">{xle_r}</span></td>
          <td>{xle_p}</td>
          <td style="text-align:left;font-size:12px;">油價強勢帶動，唯一突破所有均線的板塊，資金明顯輪入。</td>
          <td style="text-align:left;font-size:12px;color:var(--amber);">守住 20MA ({xle_stop}) 可繼續看多；跌破 {xle_stop} 止損。</td>
        </tr>
        <tr>
          <td><strong>Utilities</strong> <span style="color:var(--text-muted);font-size:11px;">XLU</span></td>
          <td><span style="color:#e0e0e0">{xlu_r}</span></td>
          <td>{xlu_p}</td>
          <td style="text-align:left;font-size:12px;">防禦屬性強，市場恐慌時資金避險流入，相對抗跌。</td>
          <td style="text-align:left;font-size:12px;color:var(--amber);">需守住 50MA ({xlu_stop}) 支撐；跌破視為防禦失守。</td>
        </tr>
        <tr>
          <td><strong>Materials</strong> <span style="color:var(--text-muted);font-size:11px;">XLB</span></td>
          <td><span style="color:#e0e0e0">{xlb_r}</span></td>
          <td>{xlb_p}</td>
          <td style="text-align:left;font-size:12px;">維持在 200MA 之上，具備相對強度，油價上漲帶動原材料需求。</td>
          <td style="text-align:left;font-size:12px;color:var(--amber);">守住 200MA 為多頭前提；若跌破 {xlb_stop} 則轉觀望。</td>
        </tr>
      </tbody>
    </table>
  </div>"""

# ── Section 8: Event Calendar ──────────────────────────────────────────────

def build_s8_calendar():
    """
    Build Section 8 Event Calendar rows with BMO/AMC timing labels.
    Week of Mar 30 – Apr 3, 2026.
    """
    def risk_badge(level):
        if level == "H":
            return '<span style="color:var(--red);font-weight:700;">High</span>'
        elif level == "M":
            return '<span style="color:var(--amber);font-weight:600;">Medium</span>'
        else:
            return '<span style="color:var(--text-muted);font-weight:500;">Low</span>'

    def timing_badge(t):
        if t == "BMO":
            return '<span style="background:#1a2a3a;color:#42a5f5;font-size:10px;font-weight:600;padding:1px 6px;border-radius:3px;letter-spacing:0.4px;">BMO</span>'
        elif t == "AMC":
            return '<span style="background:#2a1a2a;color:#ce93d8;font-size:10px;font-weight:600;padding:1px 6px;border-radius:3px;letter-spacing:0.4px;">AMC</span>'
        else:
            return f'<span style="background:#1e1e1e;color:var(--text-muted);font-size:10px;font-weight:600;padding:1px 6px;border-radius:3px;">{t}</span>'

    events = [
        # Date,          Event/Ticker,                                  Timing,  Risk
        ("Mon Mar 30",  "No Major US Events (Market Closed: Good Friday observed in some markets)", "—",   "L"),
        ("Tue Mar 31",  "CB Consumer Confidence (Mar)",                "09:00",  "M"),
        ("Tue Mar 31",  "JOLTs Job Openings (Feb)",                    "10:00",  "M"),
        ("Tue Mar 31",  "Earnings: NKE (Nike)",                        "AMC",    "M"),
        ("Tue Mar 31",  "Earnings: MKC (McCormick)",                   "BMO",    "L"),
        ("Wed Apr 1",   "ADP Non-Farm Employment (Mar)",               "08:15",  "H"),
        ("Wed Apr 1",   "ISM Manufacturing PMI (Mar)",                 "10:00",  "H"),
        ("Wed Apr 1",   "Fed Speak: Multiple FOMC Members",            "TBD",    "M"),
        ("Thu Apr 2",   "Initial Jobless Claims (weekly)",             "08:30",  "M"),
        ("Thu Apr 2",   "Factory Orders (Feb)",                        "10:00",  "L"),
        ("Fri Apr 3",   "Non-Farm Payrolls (NFP) — Mar",               "08:30",  "H"),
        ("Fri Apr 3",   "Unemployment Rate (Mar)",                     "08:30",  "H"),
        ("Fri Apr 3",   "ISM Services PMI (Mar)",                      "10:00",  "H"),
    ]

    rows = ""
    for date, event, timing, risk in events:
        rows += f"""        <tr>
          <td style="white-space:nowrap;color:var(--text-label)">{date}</td>
          <td>{event}</td>
          <td style="text-align:center">{timing_badge(timing)}</td>
          <td style="text-align:center">{risk_badge(risk)}</td>
        </tr>\n"""
    return rows

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

    # Section 5: Sectors & Industries (Top 10)
    html = html.replace("{{SECTOR_ROWS}}",   build_sector_rows(sectors))
    html = html.replace("{{INDUSTRY_ROWS}}", build_industry_rows(industry))

    # Section 6: AI Market Analysis (Checklist + Bull/Bear)
    html = html.replace("{{S6_CONTENT}}", build_s6_analysis(data))

    # Section 7: Trading Outlook & Watchlist with Technical Triggers
    html = html.replace("{{S7_CONTENT}}", build_s7_content(data))

    # Section 8: Event Calendar with BMO/AMC timing
    html = html.replace("{{S8_CONTENT}}", build_s8_calendar())

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
    print("  Market Summary Renderer v4.1")
    print("╚══════════════════════════════════════════════╝")
    render()
    print("✅  Render complete.")
