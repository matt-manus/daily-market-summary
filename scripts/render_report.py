"""
render_report.py  —  Credit-Efficient Market Summary System  v4.3
Reads:  data/today_market.json + data/ai_strategy.json
Writes: index.html  +  archive/YYYY-MM-DD.html

v4.3 Changes:
  - ARCHIVAL SYSTEM: Every render also writes archive/YYYY-MM-DD.html
  - Archive files use Base64-embedded images (self-contained, permanently readable)
  - HISTORY ARCHIVE BLOCK: index.html footer shows last 7 archive links
  - All prior v4.2 features retained

v4.2 Changes:
  - Integrates AI strategy JSON for Section 6 & 7 (GPT-generated analysis)
  - Section 6: AI Bull/Bear analysis with real data, Trend column (Value hidden)
  - Section 7: Dynamic Risk Score (x/9) from AI engine, Technical Triggers with exact MA levels
  - Section 8: Event Calendar with BMO/AMC timing labels
  - Section 5B: Top 10 industries only
  - Dark mode + Inter font throughout

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

import json, os, re, base64, subprocess
from datetime import datetime
from pathlib import Path
import pytz

BASE    = Path(__file__).resolve().parent.parent
JSON    = BASE / "data"      / "today_market.json"
AI_JSON = BASE / "data"     / "ai_strategy.json"
TMPL    = BASE / "templates" / "report_template.html"
OUTPUT  = BASE / "index.html"
ARCHIVE = BASE / "archive"

# ── Helpers ────────────────────────────────────────────────────────────────

def img_to_base64(img_path: Path) -> str:
    """
    Convert an image file to a Base64-encoded data URI string.
    Returns a data:image/png;base64,... string for direct use in <img src>.
    Falls back to empty string if file is missing.
    """
    try:
        if not img_path.exists():
            print(f"  ⚠  Base64 encode: file not found: {img_path}")
            return ""
        with open(img_path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        size_kb = len(data) / 1024
        print(f"  ✓  Base64 encoded: {img_path.name} ({size_kb:.1f} KB → {len(b64):,} chars)")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"  ⚠  Base64 encode error for {img_path}: {e}")
        return ""


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
# Section 4B: ETF-specific breadth (index constituents only)
# sp500 → SPY (Finviz idx_sp500, ~503 stocks)
# nasdaq100 → QQQ (Finviz idx_ndx, ~101 stocks)  — NOT the full NASDAQ exchange
# dji30 → DIA (yfinance DJI-30 components, exact 30 stocks)
# russell2000 → IWM (Finviz idx_rut, ~1930 stocks)
BREADTH_KEYS = [
    ("sp500",       "S&P 500",      "SPY",  "Finviz idx_sp500"),
    ("nasdaq100",   "NASDAQ 100",   "QQQ",  "Finviz idx_ndx"),
    ("dji30",       "Dow Jones 30", "DIA",  "yfinance DJI-30"),
    ("russell2000", "Russell 2000", "IWM",  "Finviz idx_rut"),
]

# ── Archive helpers ───────────────────────────────────────────────────────

def get_today_date_str() -> str:
    """Return today's date in HKT as YYYY-MM-DD string."""
    hkt = pytz.timezone("Asia/Hong_Kong")
    return datetime.now(hkt).strftime("%Y-%m-%d")


def build_history_archive_block() -> str:
    """
    Scan archive/ folder and build an HTML block listing the last 7 reports.
    Returns a styled <div> section with links to archive/*.html files.
    """
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    # Collect all YYYY-MM-DD.html files, sorted newest first
    archive_files = sorted(
        [f for f in ARCHIVE.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].html")],
        reverse=True
    )[:7]

    if not archive_files:
        links_html = '<p style="color:var(--text-muted);font-size:12px;">No archived reports yet.</p>'
    else:
        links_html = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;">'
        for f in archive_files:
            date_str = f.stem  # e.g. "2026-03-27"
            links_html += (
                f'<a href="archive/{f.name}" '
                f'style="display:inline-block;padding:6px 14px;background:var(--bg-card2);'
                f'border:1px solid var(--border);border-radius:5px;color:var(--blue);'
                f'text-decoration:none;font-size:12px;font-weight:600;letter-spacing:0.3px;'
                f'transition:border-color 0.2s;" '
                f'onmouseover="this.style.borderColor=\'#42a5f5\'" '
                f'onmouseout="this.style.borderColor=\'var(--border)\'"'
                f'>{date_str}</a>'
            )
        links_html += '</div>'

    return f"""<div class="section" style="border-top:2px solid var(--border);margin-top:24px;">
  <div class="section-title" style="color:var(--blue);">&#128196; History Archive</div>
  <p style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">
    Last {len(archive_files)} archived report(s) — each file is fully self-contained with Base64-embedded images.
  </p>
  {links_html}
</div>"""


# ── Section builders ───────────────────────────────────────────────────────

def build_indices_rows(indices, breadth):
    """
    Section 2: Index ETF table.
    A/D Ratio comes from breadth.index_ad_ratios (real advancing/declining issues),
    NOT from the old breadth-proxy stored in indices[sym]['ad_ratio'].
    """
    rows = []
    index_ad = (breadth or {}).get("index_ad_ratios", {})
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
        # Use real index A/D ratio from Finviz/yfinance (index_ad_ratios)
        iad     = index_ad.get(sym, {})
        adv     = iad.get("advances")
        dec     = iad.get("declines")
        adr_f   = safe_float(iad.get("ad_ratio"))
        adr_c   = adr_color(adr_f)
        if adr_f is not None and adv is not None and dec is not None:
            adr_str = (f'<span class="{adr_c}">{adr_f:.3f}</span>'
                       f'<span style="font-size:10px;color:var(--text-muted)"> ({adv}↑/{dec}↓)</span>')
        elif adr_f is not None:
            adr_str = f'<span class="{adr_c}">{adr_f:.3f}</span>'
        else:
            adr_str = '<span class="na-val">N/A</span>'
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
    for entry in BREADTH_KEYS:
        # Support both 3-tuple (legacy) and 4-tuple (new with source)
        key, label, etf = entry[0], entry[1], entry[2]
        source = entry[3] if len(entry) > 3 else ""
        d     = breadth.get(key, {})
        total = na(d.get("total"), "int")
        p20   = pct_bar_cell(d.get("pct_above_20ma"))
        p50   = pct_bar_cell(d.get("pct_above_50ma"))
        p200  = pct_bar_cell(d.get("pct_above_200ma"))
        etf_label = f'<strong>{etf}</strong><br><span style="font-size:10px;color:var(--text-muted)">{source}</span>'
        rows.append(
            f'<tr><td><strong>{label}</strong></td><td>{total}</td>'
            f'<td>{p20}</td><td>{p50}</td><td>{p200}</td>'
            f'<td>{etf_label}</td></tr>'
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
    for row in industry[:10]:   # ← TOP 10 LIMIT
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
    if vix_now and vix_now >= 30:
        vix_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Extreme Fear</span>'
    elif vix_now and vix_now >= 20:
        vix_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    else:
        vix_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Calm</span>'
    # Trend: VIX up = worsening (red ↑), VIX down = improving (green ↓)
    if vix_chg is not None:
        vix_trend = trend_cell(improved=(vix_chg < 0), arrow_up_is_good=False)
    else:
        vix_trend = '<span class="na-val">—</span>'
    vix_val = f"{vix_now:.2f} ({'+' if vix_chg and vix_chg>0 else ''}{vix_chg:.1f}%)" if vix_now and vix_chg else (f"{vix_now:.2f}" if vix_now else "N/A")

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
    fg_disp = f"{fg_score:.0f} (prev {fg_prev:.0f})" if fg_score is not None and fg_prev is not None else (f"{fg_score:.0f}" if fg_score is not None else "N/A")

    # ── Put/Call Ratio ────────────────────────────────────────────────────
    pc_val = safe_float(pc.get("value"))
    if pc_val is not None and pc_val > 1.0:
        pc_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    elif pc_val is not None and pc_val <= 0.8:
        pc_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Bullish</span>'
    else:
        pc_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Neutral</span>'
    # P/C: no prev_close in JSON; use absolute level for trend direction
    if pc_val is not None:
        if pc_val > 1.0:
            pc_trend = '<span style="color:var(--red);font-weight:600;">🔴 ↑</span>'
        elif pc_val <= 0.8:
            pc_trend = '<span style="color:var(--green);font-weight:600;">🟢 ↓</span>'
        else:
            pc_trend = '<span style="color:var(--amber);font-weight:600;">🟡 →</span>'
    else:
        pc_trend = '<span class="na-val">—</span>'
    pc_disp = f"{pc_val:.4f}" if pc_val is not None else "N/A"

    # ── S&P 500 % Above 20MA ──────────────────────────────────────────────
    sp_p20 = safe_float((breadth.get("sp500") or {}).get("pct_above_20ma"))
    if sp_p20 is not None and sp_p20 <= 25:
        sp_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Breadth Collapse</span>'
    elif sp_p20 is not None and sp_p20 >= 60:
        sp_status = '<span style="background:var(--green-bg);color:var(--green);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟢 Bullish</span>'
    elif sp_p20 is not None and sp_p20 >= 40:
        sp_status = '<span style="background:var(--amber-bg);color:var(--amber);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🟡 Neutral</span>'
    else:
        sp_status = '<span style="background:var(--red-bg);color:var(--red);padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;">🔴 Bearish</span>'
    # Trend: use absolute level
    if sp_p20 is not None:
        if sp_p20 <= 25:
            sp_trend = '<span style="color:var(--red);font-weight:600;">🔴 ↓</span>'
        elif sp_p20 >= 60:
            sp_trend = '<span style="color:var(--green);font-weight:600;">🟢 ↑</span>'
        else:
            sp_trend = '<span style="color:var(--amber);font-weight:600;">🟡 →</span>'
    else:
        sp_trend = '<span class="na-val">—</span>'
    sp_disp = f"{sp_p20:.1f}%" if sp_p20 is not None else "N/A"

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
    naaim_disp = f"{naaim_now:.2f} (prev {naaim_prev:.2f})" if naaim_now is not None and naaim_prev is not None else (f"{naaim_now:.2f}" if naaim_now is not None else "N/A")

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
    adr_disp = f"{nyse_adr:.3f}" if nyse_adr is not None else "N/A"

    # ── Assemble table ────────────────────────────────────────────────────
    rows = [
        ("VIX (Volatility)",        vix_val,    vix_status,   vix_trend),
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

# ── Section 6: Bull/Bear analysis (AI-powered) ────────────────────────────

def build_s6_analysis(data, ai_strategy):
    """Build the full Section 6 content: Checklist + AI Bull/Bear analysis.
    Bull/Bear are rendered as <ul><li> bullet points (not paragraphs).
    """
    checklist = build_s6_checklist(data)
    ai = ai_strategy or {}

    # Prefer new bullet-point arrays; fall back to legacy text
    bull_points = ai.get("bull_points", [])
    bear_points = ai.get("bear_points", [])

    # If no bullet arrays, convert legacy paragraph text to single-item list
    if not bull_points:
        bull_text = ai.get("bull_text", "")
        if not bull_text:
            # Compute fallback
            sentiment = data.get("sentiment", {})
            fg        = sentiment.get("fear_greed", {})
            indices   = data.get("indices", {})
            breadth   = data.get("breadth", {})
            fg_score  = safe_float(fg.get("score"))
            spy_rsi   = safe_float((indices.get("SPY") or {}).get("rsi14"))
            qqq_rsi   = safe_float((indices.get("QQQ") or {}).get("rsi14"))
            sp_p200   = safe_float((breadth.get("sp500") or {}).get("pct_above_200ma"))
            bull_text = (
                f"Fear & Greed={fg_score:.0f} (極度恐恨)，歷史逆向買入窗口"
                if fg_score is not None else "市場處於極度恐恨區間"
            )
        bull_points = [bull_text]

    if not bear_points:
        bear_text = ai.get("bear_text", "")
        if not bear_text:
            macro   = data.get("macro", {})
            breadth = data.get("breadth", {})
            vix_chg = safe_float((macro.get("VIX") or {}).get("change_1d_pct"))
            vix_now = safe_float((macro.get("VIX") or {}).get("price"))
            sp_p20  = safe_float((breadth.get("sp500") or {}).get("pct_above_20ma"))
            bear_text = (
                f"VIX +{vix_chg:.1f}% 至 {vix_now:.2f}，市場廣度崩潰，僅 {sp_p20:.1f}% 股票在 20MA 之上"
                if all(v is not None for v in [vix_chg, vix_now, sp_p20]) else "市場趨勢全面轉弱"
            )
        bear_points = [bear_text]

    # Render as <ul><li> bullet points
    def points_to_ul(points, color):
        items = "".join(f'<li style="margin-bottom:6px;line-height:1.6;">{p}</li>' for p in points if p)
        return f'<ul style="color:{color};font-size:13px;margin:8px 0 14px 0;padding-left:20px;">{items}</ul>'

    bull_html = points_to_ul(bull_points, "#81c784")  # green tint for bull
    bear_html = points_to_ul(bear_points, "#ef9a9a")  # red tint for bear

    return f"""{checklist}

  <h4 class="sub-title">Bull Case (利好邏輯)</h4>
  {bull_html}

  <h4 class="sub-title">Bear Case (利淡邏輯)</h4>
  {bear_html}"""

# ── Section 7: Trading Outlook & Watchlist (AI-powered) ───────────────────

def build_s7_content(data, ai_strategy):
    """Build Section 7 with AI Risk Score and Actionable Watchlist with Technical Triggers."""

    ai = ai_strategy or {}
    risk_score    = ai.get("risk_score", 5)
    outlook       = ai.get("outlook", "Cautious (Selective)")
    outlook_color = ai.get("outlook_color", "amber")
    risk_reasons  = ai.get("risk_reasons", [])
    watchlist     = ai.get("watchlist", [])

    # Color mapping
    color_map = {
        "red":   "var(--red)",
        "amber": "var(--amber)",
        "green": "var(--green)",
    }
    score_color = color_map.get(outlook_color, "var(--amber)")

    # Risk score bar (visual)
    score_pct = int(risk_score / 9 * 100)
    if risk_score >= 7:
        bar_color = "var(--red)"
    elif risk_score >= 5:
        bar_color = "var(--amber)"
    else:
        bar_color = "var(--green)"

    # Outlook description
    vix_price = ai.get("vix_price", 0)
    vix_chg   = ai.get("vix_chg", 0)
    fg_score  = ai.get("fg_score", 50)
    sp_p20    = ai.get("sp_p20", 50)

    if risk_score >= 7:
        outlook_desc = (
            f"VIX 高企（{vix_price:.2f}，{'+' if vix_chg>0 else ''}{vix_chg:.2f}%）且趨勢向上，"
            f"所有主要指數均在均線之下，市場廣度極差（S&P500 僅 {sp_p20:.1f}% 股票在 20MA 之上）。"
            f"建議維持防守姿態，降低整體倉位，耐心等待 VIX 回落至 20 以下或指數出現放量止跌信號，再逐步加倉。"
        )
    elif risk_score >= 5:
        outlook_desc = (
            f"市場處於調整期，VIX={vix_price:.2f}，Fear & Greed={fg_score:.0f}。"
            f"建議選擇性操作，聚焦相對強勢板塊，控制倉位在 50% 以下。"
        )
    else:
        outlook_desc = (
            f"市場情緒改善，Fear & Greed={fg_score:.0f}，廣度回升。"
            f"可逐步加倉，優先配置動能板塊。"
        )

    # Risk reasons list
    reasons_html = ""
    if risk_reasons:
        reasons_html = '<div style="margin-top:8px;font-size:11px;color:var(--text-muted);">Risk Factors: '
        reasons_html += " | ".join(f'<span style="color:var(--red)">{r}</span>' for r in risk_reasons)
        reasons_html += '</div>'

    # Build watchlist rows
    watchlist_rows_html = ""
    if watchlist:
        for w in watchlist:
            sym    = w.get("symbol", "")
            name   = w.get("name", "")
            rsi_v  = w.get("rsi")
            price_v = w.get("price")
            thesis = w.get("thesis", "")
            trigger = w.get("trigger", "")
            entry  = w.get("entry", "")
            stop   = w.get("stop", "")

            rsi_html, rsi_row = rsi_cell(rsi_v)
            price_str = f"${price_v:.2f}" if price_v else "N/A"

            watchlist_rows_html += f"""        <tr class="{rsi_row}">
          <td><strong>{name}</strong> <span style="color:var(--text-muted);font-size:11px;">{sym}</span></td>
          <td>{rsi_html}</td>
          <td>{price_str}</td>
          <td style="text-align:left;font-size:12px;">{thesis}</td>
          <td style="text-align:left;font-size:12px;color:var(--amber);">{trigger}</td>
        </tr>\n"""
    else:
        # Fallback: use sector data directly
        sectors = data.get("sectors", [])
        sector_map = {s.get("symbol"): s for s in sectors}
        for sym in ["XLE", "XLU", "XLB"]:
            s = sector_map.get(sym, {})
            if not s:
                continue
            price_v = safe_float(s.get("price"))
            ma20_v  = safe_float(s.get("ma20"))
            ma50_v  = safe_float(s.get("ma50"))
            rsi_v   = safe_float(s.get("rsi14"))
            name    = SECTOR_NAMES.get(sym, sym)
            rsi_html, rsi_row = rsi_cell(rsi_v)
            price_str = f"${price_v:.2f}" if price_v else "N/A"
            stop_str  = f"${ma20_v:.2f}" if ma20_v else "20MA"
            watchlist_rows_html += f"""        <tr class="{rsi_row}">
          <td><strong>{name}</strong> <span style="color:var(--text-muted);font-size:11px;">{sym}</span></td>
          <td>{rsi_html}</td>
          <td>{price_str}</td>
          <td style="text-align:left;font-size:12px;">相對強勢板塊，關注均線支撐。</td>
          <td style="text-align:left;font-size:12px;color:var(--amber);">守住 20MA ({stop_str}) 可繼續看多；跌破 {stop_str} 止損。</td>
        </tr>\n"""

    return f"""  <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:14px 18px;margin-bottom:16px;">
    <div style="font-size:10px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px;">Trading Outlook</div>
    <div style="font-size:22px;font-weight:700;color:{score_color};letter-spacing:-0.5px;margin-bottom:4px;">
      {outlook} &nbsp;<span style="font-size:14px;color:var(--text-muted);">Score: {risk_score} / 9</span>
    </div>
    <div style="margin-top:6px;margin-bottom:10px;">
      <div style="background:#222;border-radius:4px;height:6px;width:100%;overflow:hidden;">
        <div style="background:{bar_color};height:100%;width:{score_pct}%;border-radius:4px;transition:width 0.3s;"></div>
      </div>
    </div>
    <p style="color:#e0e0e0;font-size:13px;line-height:1.7;margin-top:8px;">{outlook_desc}</p>
    {reasons_html}
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
{watchlist_rows_html}      </tbody>
    </table>
  </div>"""

# ── Section 8: Event Calendar ──────────────────────────────────────────────

def build_s8_calendar():
    """
    Build Section 8 Event Calendar rows with BMO/AMC timing labels.
    Week of Mar 28 – Apr 3, 2026.
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
        ("Fri Mar 28",  "Good Friday — US Markets Closed",             "—",     "L"),
        ("Mon Mar 31",  "CB Consumer Confidence (Mar)",                "09:00", "M"),
        ("Mon Mar 31",  "JOLTs Job Openings (Feb)",                    "10:00", "M"),
        ("Mon Mar 31",  "Earnings: MKC (McCormick)",                   "BMO",   "L"),
        ("Mon Mar 31",  "Earnings: NKE (Nike)",                        "AMC",   "M"),
        ("Tue Apr 1",   "ADP Non-Farm Employment (Mar)",               "08:15", "H"),
        ("Tue Apr 1",   "ISM Manufacturing PMI (Mar)",                 "10:00", "H"),
        ("Tue Apr 1",   "Fed Speak: Multiple FOMC Members",            "TBD",   "M"),
        ("Wed Apr 2",   "Initial Jobless Claims (weekly)",             "08:30", "M"),
        ("Wed Apr 2",   "Factory Orders (Feb)",                        "10:00", "L"),
        ("Wed Apr 2",   "Earnings: STZ (Constellation Brands)",        "BMO",   "M"),
        ("Thu Apr 3",   "Non-Farm Payrolls (NFP) — Mar",               "08:30", "H"),
        ("Thu Apr 3",   "Unemployment Rate (Mar)",                     "08:30", "H"),
        ("Thu Apr 3",   "ISM Services PMI (Mar)",                      "10:00", "H"),
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
    # ── Phase 3.9: Auto-fetch Finviz Heatmap before rendering ──────────────────
    print("\n  ── PHASE 3.9: HEATMAP FETCH ──")
    heatmap_script = str(BASE / "scripts" / "fetch_finviz_heatmap.py")
    heatmap_result = subprocess.run(
        ["python3", heatmap_script], capture_output=True, text=True, cwd=str(BASE)
    )
    print(heatmap_result.stdout.strip())
    if heatmap_result.returncode == 0:
        print("  ✓  fetch_finviz_heatmap.py 完成")
    else:
        print("  ⚠  fetch_finviz_heatmap.py 失敗，使用舊圖繼續")
        if heatmap_result.stderr:
            print("  ⚠  Error:", heatmap_result.stderr.strip())
    print("  ── END HEATMAP FETCH ──\n")
    # ── End Phase 3.9 ──────────────────────────────────────────────────────────
    # ── PHASE 3.9: STOCKBEE FETCH (T2108 + waffle chart) ──
    print("  ── PHASE 3.9: STOCKBEE FETCH ──")
    stockbee_script = str(BASE / "fetch_stockbee_data.py")
    stockbee_result = subprocess.run(
        ["python3", stockbee_script], capture_output=True, text=True, cwd=str(BASE)
    )
    if stockbee_result.stdout.strip():
        print(stockbee_result.stdout.strip())
    if stockbee_result.returncode == 0:
        print("  \u2713  fetch_stockbee_data.py \u5b8c\u6210\uff08stockbee_mm.png \u5df2\u66f4\u65b0\uff09")
    else:
        print("  \u26a0  Stockbee fetch \u5931\u6557\uff0c\u4f7f\u7528\u820a\u5716\uff08\u4f46\u7e7c\u7e8c\u751f\u6210\uff09")
        if stockbee_result.stderr:
            print("  \u26a0  Error:", stockbee_result.stderr.strip())
    print("  ── END STOCKBEE FETCH ──\n")
    # ── Phase 3.95: Fix Date Logic ──────────────────────────────────────────
    _hk_tz = pytz.timezone('Asia/Hong_Kong')
    _today_hk = datetime.now(_hk_tz)
    _archive_date_str = _today_hk.strftime("%Y-%m-%d")   # 永遠用今日 HKT 日期
    print(f"[Phase 3.95] Archive date (HKT): archive/{_archive_date_str}.html")
    # ── End Phase 3.95 ──────────────────────────────────────────────────────────
    with open(JSON, encoding="utf-8") as f:
        data = json.load(f)

    # Load AI strategy if available
    ai_strategy = None
    if AI_JSON.exists():
        with open(AI_JSON, encoding="utf-8") as f:
            ai_strategy = json.load(f)
        print("  ✓  AI strategy loaded from ai_strategy.json")
    else:
        print("  ⚠  ai_strategy.json not found, using computed fallback")

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

    # ── Section 4C: Stockbee Dynamic Summary (Grok v2 + Gemini) ──────────────────
    s_mm = data.get("stockbee_mm", {})
    t2108_val = s_mm.get("t2108", "-")
    up_4 = s_mm.get("up_4_plus", "-")
    down_4 = s_mm.get("down_4_plus", "-")
    sb_date = s_mm.get("latest_date", "-")

    # T2108 顏色標記
    t2108_class = ""
    if isinstance(t2108_val, (int, float)):
        if t2108_val <= 20:
            t2108_class = "color: #10b981;"   # green-500 超賣
        elif t2108_val >= 80:
            t2108_class = "color: #ef4444;"   # red-500 超買

    sb_summary_html = f'''
    <div class="stockbee-summary">
        <div class="stat">
            <div class="label">T2108</div>
            <div class="value" style="{t2108_class}">{t2108_val}%</div>
        </div>
        <div class="stat">
            <div class="label">Up 4%+</div>
            <div class="value" style="color: #10b981;">{up_4}</div>
        </div>
        <div class="stat">
            <div class="label">Down 4%+</div>
            <div class="value" style="color: #ef4444;">{down_4}</div>
        </div>
    </div>
    <div class="date">Last Data: {sb_date}</div>
    '''

    html = html.replace("{{STOCKBEE_DYNAMIC_SUMMARY}}", sb_summary_html)

    # Section 5: Sectors & Industries (Top 10)
    html = html.replace("{{SECTOR_ROWS}}",   build_sector_rows(sectors))
    html = html.replace("{{INDUSTRY_ROWS}}", build_industry_rows(industry))

    # ── REGIME BANNER ──────────────────────────────────────────────────────────
    spy_vs20     = safe_float((indices.get("SPY") or {}).get("vs_ma20_pct"))
    vix_val_r    = safe_float((macro.get("VIX") or {}).get("price"))
    fg_score_r   = safe_float((sentiment.get("fear_greed") or {}).get("score"))
    sp_p20_r     = safe_float((breadth.get("sp500") or {}).get("pct_above_20ma"))
    if spy_vs20 is not None and spy_vs20 < -3 and vix_val_r is not None and vix_val_r > 25:
        rc = "#f44336"; rb = "rgba(244,67,54,0.10)"
        rl = "&#9888; RISK-OFF REGIME &#8212; Defensive Posture Recommended"
        rs = f"SPY is {spy_vs20:+.1f}% vs 20MA | VIX={vix_val_r:.1f} (Elevated) | F&amp;G={fg_score_r:.0f} (Extreme Fear)"
    elif spy_vs20 is not None and spy_vs20 > 2:
        rc = "#4caf50"; rb = "rgba(76,175,80,0.10)"
        rl = "&#10003; RISK-ON REGIME &#8212; Trend Following Mode"
        rs = f"SPY is {spy_vs20:+.1f}% vs 20MA | VIX={vix_val_r:.1f} | F&amp;G={fg_score_r:.0f}"
    else:
        rc = "#ff9800"; rb = "rgba(255,152,0,0.10)"
        rl = "&#11035; NEUTRAL REGIME &#8212; Selective / Cautious"
        rs = f"SPY is {spy_vs20:+.1f}% vs 20MA | VIX={vix_val_r:.1f} | F&amp;G={fg_score_r:.0f}"
    regime_banner = (
        f'<div style="background:{rb};border:1px solid {rc};border-radius:8px;'
        f'padding:14px 20px;margin-bottom:20px;">'
        f'<div style="font-size:13px;font-weight:700;color:{rc};margin-bottom:4px;">{rl}</div>'
        f'<div style="font-size:11px;color:#aaa;">{rs}</div></div>'
    )
    # ── DATA WARNING BANNER (Phase 3.95: 48-hour Heatmap Rule) ───────────────────
    _data_status   = data.get("data_status", "fresh")
    _data_warnings = data.get("data_warnings", [])
    # Phase 3.95: Override stale check with 48-hour heatmap image freshness rule
    _heatmap_img_path = BASE / "assets" / "images" / "market_heatmap.png"
    _hk_tz_banner = pytz.timezone('Asia/Hong_Kong')
    _show_stale_banner = False
    if _heatmap_img_path.exists():
        _img_mtime = datetime.fromtimestamp(_heatmap_img_path.stat().st_mtime, tz=_hk_tz_banner)
        _hours_old = (datetime.now(_hk_tz_banner) - _img_mtime).total_seconds() / 3600
        if _hours_old > 48:
            _show_stale_banner = True
            print(f"  ⚠  Heatmap 已超過 48 小時（{_hours_old:.1f}h），Stale Banner 顯示")
        else:
            print(f"  ✓  Heatmap 新鮮（{_hours_old:.1f}h < 48h），Stale Banner 隱藏")
    else:
        # Fallback to original data_status logic if no heatmap image
        _show_stale_banner = (_data_status == "warning" and bool(_data_warnings))
        print(f"  ⚠  Heatmap 圖片不存在，使用原有 data_status 邏輯")
    if _show_stale_banner:
        _warn_text = " | ".join(_data_warnings) if _data_warnings else "Heatmap data older than 48 hours"
        _warning_banner_html = (
            f'<div class="data-warning-banner active">'
            f'⚠️ Data Stale / Warning: {_warn_text} — Please check source data'
            f'</div>'
        )
    else:
        _warning_banner_html = '<div class="data-warning-banner"></div>'
    html = html.replace("{{DATA_WARNING_BANNER}}", _warning_banner_html)
    html = html.replace("{{REGIME_BANNER}}", regime_banner)
    # ── CORRECTION CHECKLIST ──────────────────────────────────────────────────────────────────
    if spy_vs20 is not None and spy_vs20 < 0:
        c1 = "&#9989;" if vix_val_r and vix_val_r > 30 else "&#11036;"
        c2 = "&#9989;" if fg_score_r and fg_score_r < 20 else "&#11036;"
        c3 = "&#9989;" if sp_p20_r and sp_p20_r < 20 else "&#11036;"
        c4 = "&#9989;" if spy_vs20 and spy_vs20 < -3 else "&#11036;"
        correction_html = (
            '<div style="background:rgba(244,67,54,0.07);border:1px solid #f44336;'
            'border-radius:8px;padding:14px 20px;margin-bottom:20px;">'
            '<div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;'
            'color:#f44336;margin-bottom:10px;">&#128203; Correction Checklist</div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">'
            f'<div>{c1} VIX &gt; 30 (Panic Level): {vix_val_r:.1f}</div>'
            f'<div>{c2} F&amp;G &lt; 20 (Extreme Fear): {fg_score_r:.0f}</div>'
            f'<div>{c3} SP500 &gt;20MA &lt; 20%: {sp_p20_r:.1f}%</div>'
            f'<div>{c4} SPY &gt;5% below 20MA: {spy_vs20:+.1f}%</div>'
            '</div></div>'
        )
    else:
        correction_html = ""
    html = html.replace("{{CORRECTION_CHECKLIST}}", correction_html)
    # ── EXPERT INSIGHTS ─────────────────────────────────────────────────────────
    expert_file = BASE / "expert_notes.txt"
    expert_html = ""
    if expert_file.exists():
        with open(expert_file, encoding="utf-8") as ef:
            notes = ef.read().strip()
        content_lines = [l for l in notes.splitlines() if l.strip() and not l.strip().startswith("#")]
        if content_lines:
            content_text = "<br/>".join(content_lines)
            expert_html = (
                '<div style="background:rgba(66,165,245,0.08);border:1px solid #42a5f5;'
                'border-radius:8px;padding:14px 20px;margin-bottom:20px;">'
                '<div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;'
                'color:#42a5f5;margin-bottom:8px;">&#128161; Expert Insights</div>'
                f'<div style="font-size:12px;color:#ccc;line-height:1.6;">{content_text}</div></div>'
            )
    html = html.replace("{{EXPERT_INSIGHTS}}", expert_html)
    # Section 6: AI Market Analysis (Checklist + Bull/Bear)
    html = html.replace("{{S6_CONTENT}}", build_s6_analysis(data, ai_strategy))

    # Section 7: Trading Outlook & Watchlist with Technical Triggers
    html = html.replace("{{S7_CONTENT}}", build_s7_content(data, ai_strategy))

    # Section 8: Event Calendar with BMO/AMC timing
    html = html.replace("{{S8_CONTENT}}", build_s8_calendar())

    # ── BASE64 IMAGE EMBEDDING (No Path Errors) ───────────────────────────────────────
    print("\n  ── BASE64 IMAGE EMBEDDING ──")
    img_stockbee  = BASE / "assets/img/today/stockbee_mm.png"
    img_industry  = BASE / "assets/img/today/industry_performance.png"
    img_heatmap   = BASE / "assets/img/today/market_heatmap.png"

    b64_stockbee  = img_to_base64(img_stockbee)
    b64_industry  = img_to_base64(img_industry)
    b64_heatmap   = img_to_base64(img_heatmap)

    # Replace <img src> paths with Base64 data URIs
    if b64_stockbee:
        html = html.replace(
            'src="assets/img/today/stockbee_mm.png"',
            f'src="{b64_stockbee}"'
        )
        print("  ✓  Section 4C Stockbee: Base64 injected into HTML")
    else:
        print("  ⚠  Section 4C Stockbee: image missing, keeping path reference")

    if b64_industry:
        html = html.replace(
            'src="assets/img/today/industry_performance.png"',
            f'src="{b64_industry}"'
        )
        print("  ✓  Section 5B Industry: Base64 injected into HTML")
    else:
        print("  ⚠  Section 5B Industry: image missing, keeping path reference")

    if b64_heatmap:
        html = html.replace(
            'src="assets/img/today/market_heatmap.png"',
            f'src="{b64_heatmap}"'
        )
        print("  ✓  Section 5B Heatmap: Base64 injected into HTML")
    else:
        print("  ⚠  Section 5B Heatmap: image missing, keeping path reference")

    print("  ── END BASE64 EMBEDDING ──\n")

    # Residual check
    leftover = re.findall(r"\{\{[A-Z0-9_]+\}\}", html)
    if leftover:
        print(f"  ⚠  Unresolved tags ({len(leftover)}): {leftover[:10]}")
    else:
        print("  ✓  All template tags resolved (0 residual)")

    # ── WRITE ARCHIVE FILE (before building history block) ───────────────────
    # Write archive FIRST so the history block can include today's entry
    print("\n  ── ARCHIVE OUTPUT ──")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    # Phase 3.95: Always use today's HKT date for archive filename (override JSON meta.date)
    archive_date = _archive_date_str   # 來自 Phase 3.95 block，永遠用今日 HKT
    archive_path = ARCHIVE / f"{archive_date}.html"

    # Build a temporary archive placeholder (back-link footer)
    archive_footer = (
        f'<div class="section" style="border-top:2px solid var(--border);margin-top:24px;">'
        f'<div class="section-title" style="color:var(--blue);">&#128196; History Archive</div>'
        f'<p style="color:var(--text-muted);font-size:12px;">'
        f'This is an archived report for <strong style="color:#e0e0e0;">{archive_date}</strong>. '
        f'<a href="../index.html" style="color:var(--blue);">&#8592; Back to Latest Report</a></p>'
        f'</div>'
    )
    # Replace the placeholder tag with the archive footer for the archive copy
    archive_html = html.replace("{{HISTORY_ARCHIVE_BLOCK}}", archive_footer)
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(archive_html)
    arch_kb = archive_path.stat().st_size / 1024
    print(f"  ✓  Archive written: archive/{archive_date}.html  ({arch_kb:.1f} KB)")

    # ── HISTORY ARCHIVE BLOCK (built AFTER archive file exists) ──────────────
    # Now today's archive is on disk, so the block will include it
    print("\n  ── HISTORY ARCHIVE BLOCK ──")
    history_block = build_history_archive_block()
    html_with_archive = html.replace("{{HISTORY_ARCHIVE_BLOCK}}", history_block)
    archive_count = len(list(ARCHIVE.glob('[0-9]*.html')))
    print(f"  ✓  History archive block built ({archive_count} archive file(s) found)")

    # ── WRITE index.html (with complete archive block) ────────────────────────
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html_with_archive)
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"  ✓  index.html written  ({size_kb:.1f} KB)")
    print(f"  ✓  Archive block shows {archive_count} link(s) in footer")

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("  Market Summary Renderer v4.4  (Phase 3.9)   ")
    print("╚══════════════════════════════════════════════╝")
    render()
    print("✅  Render complete.")
