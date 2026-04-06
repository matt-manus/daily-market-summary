"""
html_generator.py  —  Credit-Efficient Market Summary System  v5.3
-----------------------------------------------------------------
Updated for Gemini Emergency Fix (Step 2).

New in v5.3 (Gemini Emergency Reorg Step 2):
  - Section 5 (SPDR ETFs): added vs 50MA + vs 200MA columns
  - Section 7 (RS Leaderboard): added vs 20MA/50MA/200MA + Sector ETF columns
  - Added SPDR_ETF_MAP constant and get_spdr_etf() helper
  - build_sector_rows: 10-col → 12-col (+ vs 50MA, vs 200MA)
  - build_volume_climax_block leaderboard: + vs MA cols + Sector ETF col

New in v5.2 (Gemini Emergency Reorg Step 1):
  - Section 3: removed A/D Ratio column (moved to Section 4A)
  - Section 4A: removed ETF column, added A/D Ratio column
  - build_indices_rows: 7-col → 6-col (no A/D)
  - build_breadth_rows: ETF removed, A/D Ratio added from index_ad_ratios

New in v5.1:
  - Full 9-section architecture enforced
  - hide-on-mobile class injected into all tables (RSI, MA, 1D%, 3M%, A/D)
  - Mobile Epic Fail fixed at Python level
  - hide_on_mobile() helper function added

Inherited from v5.0:
  - Accepts regime_info dict from regime_filter.py
  - Injects Correction Checklist at top when regime == 'Correction'
  - Coach's Action Plan (Section 7) promoted to most prominent position
  - Expert Insights block injected from expert_notes.txt
  - Cache-busted image paths (no Base64)
  - Date-stamped archive logic preserved

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

import json, os, re, base64
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

# 新增：hide-on-mobile 輔助函數 (v5.1)
def hide_on_mobile(extra_cls=""):
    """Return combined class string with hide-on-mobile and optional extra class."""
    return f'hide-on-mobile {extra_cls}'.strip() if extra_cls else 'hide-on-mobile'

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
    """Return today's NY Trade Date as YYYY-MM-DD string.
    
    TRADE DATE ENFORCEMENT v3.0:
    Primary source: today_market.json meta.date (derived from SPY last trade date in fetch_all_data.py).
    Fallback: NY system time (only if JSON is missing or malformed).
    NEVER use HKT or server local time.
    """
    # Primary: read from today_market.json meta.date (SPY-derived)
    try:
        if JSON.exists():
            with open(JSON, encoding="utf-8") as _f:
                _meta = json.load(_f).get("meta", {})
            _date = _meta.get("date", "")
            if _date and len(_date) >= 10:
                print(f"  [TradeDate] Using JSON meta.date: {_date[:10]} (SPY-derived)")
                return _date[:10]
    except Exception as _e:
        print(f"  [TradeDate] JSON read error: {_e}")
    # Fallback: NY system time
    ny_tz = pytz.timezone("America/New_York")
    _fallback = datetime.now(ny_tz).strftime("%Y-%m-%d")
    print(f"  [TradeDate] Fallback to NY system time: {_fallback}")
    return _fallback


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
            f'<td>{price}</td>'
            f'<td class="hide-on-mobile">{chg}</td>'
            f'<td class="hide-on-mobile">{rsi_html}</td>'
            f'<td class="hide-on-mobile {vs20_c}">{vs20}</td>'
            f'<td class="hide-on-mobile {vs50_c}">{vs50}</td>'
            f'<td class="hide-on-mobile {vs200_c}">{vs200}</td></tr>'
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
    """Section 4A — Index Breadth (v5.2: ETF col removed, A/D Ratio added)."""
    if not breadth:
        return '<tr><td colspan="6"><span class="na-val">N/A</span></td></tr>'
    rows = []
    # ETF ticker used as key to look up index_ad_ratios
    ETF_TO_ADR_KEY = {"SPY": "SPY", "QQQ": "QQQ", "DIA": "DIA", "IWM": "IWM"}
    index_ad = breadth.get("index_ad_ratios", {})
    for entry in BREADTH_KEYS:
        key, label, etf = entry[0], entry[1], entry[2]
        d     = breadth.get(key, {})
        total = na(d.get("total"), "int")
        p20   = pct_bar_cell(d.get("pct_above_20ma"))
        p50   = pct_bar_cell(d.get("pct_above_50ma"))
        p200  = pct_bar_cell(d.get("pct_above_200ma"))
        # A/D Ratio from index_ad_ratios (same source as Section 3 used to use)
        adr_key = ETF_TO_ADR_KEY.get(etf, etf)
        iad   = index_ad.get(adr_key, {})
        adr_f = safe_float(iad.get("ad_ratio"))
        adv   = iad.get("advances")
        dec   = iad.get("declines")
        adr_c = adr_color(adr_f)
        if adr_f is not None and adv is not None and dec is not None:
            adr_str = (f'<span class="{adr_c}">{adr_f:.3f}</span>'
                       f'<span style="font-size:10px;color:var(--text-muted)"> ({adv}↑/{dec}↓)</span>')
        elif adr_f is not None:
            adr_str = f'<span class="{adr_c}">{adr_f:.3f}</span>'
        else:
            adr_str = '<span class="na-val">N/A</span>'
        rows.append(
            f'<tr><td><strong>{label}</strong></td><td>{total}</td>'
            f'<td>{p20}</td>'
            f'<td class="hide-on-mobile">{p50}</td>'
            f'<td class="hide-on-mobile">{p200}</td>'
            f'<td>{adr_str}</td></tr>'
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

# ── RS Score / Rating helpers ────────────────────────────────────────────────

# SECTOR_CATEGORIES: maps each SPDR ETF to a logical cluster group
SECTOR_CATEGORIES = {
    "XLK":  "Growth",
    "XLC":  "Growth",
    "XLY":  "Growth",
    "XLF":  "Cyclical",
    "XLI":  "Cyclical",
    "XLB":  "Cyclical",
    "XLRE": "Cyclical",
    "XLE":  "Defensive",
    "XLV":  "Defensive",
    "XLP":  "Defensive",
    "XLU":  "Defensive",
}

def compute_rs_scores(sectors: list) -> list:
    """
    Compute RS Score for each sector ETF.
    RS Score = (40% * 1m Return) + (40% * 3m Return) + (20% * 6m Return)
    Since we don’t have 6m data, approximate 6m ≈ change_ytd_pct or fallback to 3m.
    Then rank 1-99 within the universe.
    Returns list of dicts with rs_score and rs_rating added.
    """
    scored = []
    for s in sectors:
        c1m = safe_float(s.get("change_1m_pct")) or 0.0
        c3m = safe_float(s.get("change_3m_pct")) or 0.0
        # Use ytd as 6m proxy; fallback to 3m if ytd not available
        c6m = safe_float(s.get("change_ytd_pct")) or safe_float(s.get("change_3m_pct")) or 0.0
        rs_score = round(0.40 * c1m + 0.40 * c3m + 0.20 * c6m, 2)
        scored.append({**s, "rs_score": rs_score})

    # Rank 1-99 within the universe (higher score = higher rank)
    n = len(scored)
    if n == 0:
        return scored
    sorted_scores = sorted([s["rs_score"] for s in scored])
    for s in scored:
        rank_idx = sorted_scores.index(s["rs_score"])
        # Scale to 1-99
        rs_rating = max(1, min(99, round(1 + (rank_idx / max(n - 1, 1)) * 98)))
        s["rs_rating"] = rs_rating
    return scored


def rs_rating_cell(rating):
    """Return HTML badge for RS Rating."""
    if rating is None:
        return '<span class="na-val">N/A</span>'
    r = int(rating)
    if r >= 90:   cls, label = "rs-badge rs-elite",  f"{r} ★★"
    elif r >= 80: cls, label = "rs-badge rs-strong", f"{r} ★"
    elif r >= 60: cls, label = "rs-badge rs-mid",    str(r)
    else:         cls, label = "rs-badge rs-weak",   str(r)
    return f'<span class="{cls}">{label}</span>'


def rs_score_cell(score):
    """Return colored RS Score value."""
    if score is None:
        return '<span class="na-val">N/A</span>'
    f = float(score)
    cls = "text-green" if f > 5 else ("text-red" if f < -5 else "text-amber")
    sign = "+" if f > 0 else ""
    return f'<span class="{cls}">{sign}{f:.1f}</span>'


# ── Strict 11 SPDR ETF symbols for Section 5A ────────────────────────────────
CORE_SPDR_11 = {"XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLC", "XLRE"}

# ── 11 Core SPDR ETF Sector Mapping (v5.3) ───────────────────────────────────
SPDR_ETF_MAP = {
    "XLK":  "Technology",      "XLY":  "Consumer Disc.",  "XLP":  "Consumer Stap.",
    "XLE":  "Energy",          "XLF":  "Financials",       "XLI":  "Industrials",
    "XLB":  "Materials",       "XLRE": "Real Estate",      "XLU":  "Utilities",
    "XLV":  "Health Care",     "XLC":  "Communication"
}

def get_spdr_etf(symbol: str) -> str:
    """Map a ticker to its SPDR sector ETF label. Returns '-' if not found."""
    sym = symbol.upper()
    # Direct SPDR match
    if sym in SPDR_ETF_MAP:
        return f'<span style="font-size:11px;color:#aaa">{sym}</span>'
    # Lookup via SECTOR_CATEGORIES mapping
    for cat_etfs in SECTOR_CATEGORY_GROUPS.values() if 'SECTOR_CATEGORY_GROUPS' in dir() else []:
        if sym in cat_etfs:
            pass  # category found but no SPDR mapping
    return '<span style="font-size:11px;color:#555">—</span>'


def build_sector_rows(sectors):
    """5A — Core Market Pulse: STRICTLY 11 SPDR ETFs only.
    
    CRITICAL: Only XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLB, XLU, XLC, XLRE.
    ANY other symbol (XOP, SMH, IGV, etc.) must be excluded.
    """
    if not sectors:
        return '<tr><td colspan="10"><span class="na-val">N/A</span></td></tr>'
    # STRICT FILTER: Only the 11 core SPDR ETFs
    spdr_only = [s for s in sectors if s.get("symbol", "") in CORE_SPDR_11]
    if not spdr_only:
        return '<tr><td colspan="10"><span class="na-val">No SPDR ETF data found</span></td></tr>'
    # Compute RS scores within this 11-ETF universe
    sectors_with_rs = compute_rs_scores(spdr_only)
    # Sort by RS Rating descending (highest RS first)
    sectors_sorted = sorted(sectors_with_rs, key=lambda x: x.get("rs_rating", 0), reverse=True)
    rows = []
    for s in sectors_sorted:
        sym   = s.get("symbol", "")
        name  = SECTOR_NAMES.get(sym, s.get("name", ""))
        price = na(s.get("price"), "price")
        c1d   = chg_cell(s.get("change_1d_pct"))
        c1m   = chg_cell(s.get("change_1m_pct"))
        c3m   = chg_cell(s.get("change_3m_pct"))
        rs_sc = rs_score_cell(s.get("rs_score"))
        rs_rt = rs_rating_cell(s.get("rs_rating"))
        rsi_html, rsi_row = rsi_cell(s.get("rsi14"))
        vs20   = na(s.get("vs_ma20_pct"),  "pct")
        vs50   = na(s.get("vs_ma50_pct"),  "pct")
        vs200  = na(s.get("vs_ma200_pct"), "pct")
        vs20_c  = css_dir(s.get("vs_ma20_pct"))
        vs50_c  = css_dir(s.get("vs_ma50_pct"))
        vs200_c = css_dir(s.get("vs_ma200_pct"))
        rows.append(
            f'<tr class="{rsi_row}">'
            f'<td><strong>{sym}</strong></td>'
            f'<td style="color:var(--text-label)">{name}</td>'
            f'<td>{price}</td><td>{c1d}</td><td>{c1m}</td><td>{c3m}</td>'
            f'<td style="text-align:right">{rs_sc}</td>'
            f'<td style="text-align:right">{rs_rt}</td>'
            f'<td>{rsi_html}</td>'
            f'<td class="{vs20_c}">{vs20}</td>'
            f'<td class="hide-on-mobile {vs50_c}">{vs50}</td>'
            f'<td class="hide-on-mobile {vs200_c}">{vs200}</td></tr>'
        )
    return "\n".join(rows)


# ── 5B: SECTOR_CATEGORIES grouping (45 non-SPDR ETFs) ────────────────────────────────
# Category display names and their ETF members
SECTOR_CATEGORY_GROUPS = {
    "Core Industry":       ["SMH", "IGV", "SKYY", "XBI", "IBB", "IHI", "KRE", "KBE", "IAI",
                            "XRT", "IYT", "JETS", "XOP", "XHB", "LIT"],
    "Thematic & Tech":     ["AIQ", "ARKQ", "ARKK", "BOTZ", "ROBO", "SOXX", "CIBR", "BUG",
                            "BLOK", "FINX", "IPAY", "QTUM", "MAGS"],
    "Commodities & Power": ["NLR", "URA", "COPX", "TAN", "GLD", "SLV", "GDX", "PICK"],
    "Defense & Space":     ["ITA", "XAR", "ROKT"],
    "Macro & Global":      ["PAVE", "TLT", "VNQ", "FXI", "KWEB", "MSOS"],
}

# Full name lookup for all 56 ETFs
ALL_ETF_NAMES = {
    # Core Industry sub-sectors
    "SMH": "Semiconductors", "IGV": "Software", "SKYY": "Cloud Computing",
    "XBI": "Biotech (Equal Wt)", "IBB": "Biotech (Mkt Cap)", "IHI": "Medical Devices",
    "KRE": "Regional Banks", "KBE": "Banks Broad", "IAI": "Investment Banking",
    "XRT": "Retail", "IYT": "Transportation", "JETS": "Airlines",
    "XOP": "Oil & Gas E&P", "XHB": "Homebuilders", "LIT": "Lithium & Battery",
    # Thematic & Tech
    "AIQ": "AI & Big Data", "ARKQ": "ARK Autonomous", "ARKK": "ARK Innovation",
    "BOTZ": "Robotics & AI", "ROBO": "Robotics & Automation", "SOXX": "Semis (iShares)",
    "CIBR": "Cybersecurity", "BUG": "Cybersecurity (Global X)", "BLOK": "Blockchain",
    "FINX": "FinTech", "IPAY": "Digital Payments", "QTUM": "Quantum Computing",
    "MAGS": "Magnificent 7",
    # Commodities & Power
    "NLR": "Nuclear Energy", "URA": "Uranium Mining", "COPX": "Copper Miners",
    "TAN": "Solar Energy", "GLD": "Gold ETF", "SLV": "Silver ETF",
    "GDX": "Gold Miners", "PICK": "Diversified Metals",
    # Defense & Space
    "ITA": "Aerospace & Defense", "XAR": "Aerospace & Defense (SPDR)", "ROKT": "Space Exploration",
    # Macro & Global
    "PAVE": "Infrastructure", "TLT": "20Y Treasury Bond", "VNQ": "Real Estate (Vanguard)",
    "FXI": "China Large-Cap", "KWEB": "China Internet", "MSOS": "Cannabis",
    # Core SPDR (for reference)
    **SECTOR_NAMES,
}


def _load_analysis_results() -> dict:
    """Load analysis_results.json from data/ directory."""
    ar_path = BASE / "data" / "analysis_results.json"
    if ar_path.exists():
        try:
            with open(ar_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠  Failed to load analysis_results.json: {e}")
    return {}


def build_industry_rs_radar(industry: list, sectors: list) -> str:
    """
    5B — Thematic & Sub-Sector Breakdown: 45 non-SPDR ETFs.
    Grouped by SECTOR_CATEGORIES, sorted by RS Rating within each group.
    Data sourced from analysis_results.json (rs_engine.py output).
    """
    # Load RS data from analysis_results.json
    ar = _load_analysis_results()
    latest_rs = ar.get("latest_rs", [])
    hot_clusters = ar.get("hot_clusters", [])

    # Build ticker -> RS data lookup
    rs_lookup = {}
    for row in latest_rs:
        ticker = row.get("ticker", "")
        if ticker:
            rs_lookup[ticker] = row

    # Also build from sectors list (today_market.json) for price/RSI/MA data
    sector_lookup = {s.get("symbol", ""): s for s in sectors}

    # Hot cluster summary banner
    if hot_clusters:
        hot_names = ", ".join(hot_clusters)
        cluster_banner = f'<div style="background:rgba(255,112,67,0.1);border:1px solid #ff7043;border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:12px;color:#ff7043;"><strong>&#128293; Hot Clusters:</strong> {hot_names}</div>'
    else:
        cluster_banner = '<div style="background:rgba(158,158,158,0.1);border:1px solid #555;border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:12px;color:#9e9e9e;">&#10052; No Hot Clusters detected today</div>'

    # Build grouped sections
    sections_html = cluster_banner

    for group_name, group_tickers in SECTOR_CATEGORY_GROUPS.items():
        # Collect ETFs in this group with RS data
        group_etfs = []
        for ticker in group_tickers:
            rs_data = rs_lookup.get(ticker, {})
            sec_data = sector_lookup.get(ticker, {})
            rs_score  = safe_float(rs_data.get("rs_score"))
            rs_rating = safe_float(rs_data.get("rs_rating"))
            above_20ma = rs_data.get("above_20ma")
            vol_climax = rs_data.get("volume_climax", False)
            is_strong  = rs_data.get("is_strong", False)
            # Fallback: compute from sector data if no RS data
            if rs_score is None and sec_data:
                c1m = safe_float(sec_data.get("change_1m_pct")) or 0.0
                c3m = safe_float(sec_data.get("change_3m_pct")) or 0.0
                c6m = safe_float(sec_data.get("change_ytd_pct")) or c3m
                rs_score = round(0.40 * c1m + 0.40 * c3m + 0.20 * c6m, 2)
            group_etfs.append({
                "ticker":    ticker,
                "name":      ALL_ETF_NAMES.get(ticker, ticker),
                "rs_score":  rs_score,
                "rs_rating": int(rs_rating) if rs_rating is not None else None,
                "above_20ma": above_20ma,
                "vol_climax": vol_climax,
                "is_strong":  is_strong,
                "c1d":  safe_float(sec_data.get("change_1d_pct")),
                "c1m":  safe_float(sec_data.get("change_1m_pct")),
                "c3m":  safe_float(sec_data.get("change_3m_pct")),
                "rsi":  safe_float(sec_data.get("rsi14")),
                "vs20": safe_float(sec_data.get("vs_ma20_pct")),
            })

        # Sort by RS Rating descending within group
        group_etfs.sort(key=lambda x: x.get("rs_rating") or 0, reverse=True)

        # Detect if this group is a hot cluster
        group_key = group_name
        is_hot_group = any(group_key in hc for hc in hot_clusters)
        group_icon = "&#128293;" if is_hot_group else "&#128202;"
        group_color = "#ff7043" if is_hot_group else "#42a5f5"

        # Group header
        sections_html += f'''
<div style="margin-bottom:20px;">
  <div style="font-size:12px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;
    color:{group_color};border-left:3px solid {group_color};padding-left:10px;
    margin-bottom:8px;">{group_icon} {group_name}</div>
  <div class="table-wrap">
  <table class="data-table" style="font-size:12px;">
    <thead><tr>
      <th>Symbol</th><th>Name</th>
      <th>1D%</th><th>1M%</th><th>3M%</th>
      <th>RS Score</th><th>RS Rating</th><th>Flag</th>
    </tr></thead>
    <tbody>
'''
        for etf in group_etfs:
            c1d_html = chg_cell(etf["c1d"]) if etf["c1d"] is not None else '<span class="na-val">N/A</span>'
            c1m_html = chg_cell(etf["c1m"]) if etf["c1m"] is not None else '<span class="na-val">N/A</span>'
            c3m_html = chg_cell(etf["c3m"]) if etf["c3m"] is not None else '<span class="na-val">N/A</span>'
            rs_sc_html = rs_score_cell(etf["rs_score"]) if etf["rs_score"] is not None else '<span class="na-val">N/A</span>'
            rs_rt_html = rs_rating_cell(etf["rs_rating"]) if etf["rs_rating"] is not None else '<span class="na-val">N/A</span>'
            # Flag column
            flags = []
            if etf["is_strong"]:  flags.append("&#128293;")
            if etf["vol_climax"]: flags.append("&#9889;")
            flag_html = " ".join(flags) if flags else "—"
            sections_html += (
                f'<tr>'
                f'<td><strong>{etf["ticker"]}</strong></td>'
                f'<td style="color:var(--text-label);font-size:11px;">{etf["name"]}</td>'
                f'<td>{c1d_html}</td><td>{c1m_html}</td><td>{c3m_html}</td>'
                f'<td style="text-align:right">{rs_sc_html}</td>'
                f'<td style="text-align:right">{rs_rt_html}</td>'
                f'<td style="text-align:center;font-size:14px;">{flag_html}</td>'
                f'</tr>\n'
            )
        sections_html += '    </tbody>\n  </table>\n  </div>\n</div>\n'

    return sections_html


def build_volume_climax_block(sectors: list) -> str:
    """
    5C — Industry RS Leaderboard & Anomalies.
    
    Part 1: Top 10 RS Leaders across all 56 ETFs (from analysis_results.json).
    Part 2: Volume Climax alerts (real volume data from rs_engine) + RSI extremes.
    """
    # ── Load RS analysis results ─────────────────────────────────────────────────
    ar = _load_analysis_results()
    latest_rs = ar.get("latest_rs", [])
    volume_climax_etfs = ar.get("volume_climax_etfs", [])
    sector_lookup = {s.get("symbol", ""): s for s in sectors}

    html_parts = []

    # ── Part 1: Top 10 RS Leaderboard ───────────────────────────────────────────────
    if latest_rs:
        # Sort all 56 ETFs by RS Rating descending, take top 10
        top10 = sorted(
            [r for r in latest_rs if r.get("rs_rating") is not None],
            key=lambda x: x.get("rs_rating", 0),
            reverse=True
        )[:10]

        leaderboard_rows = []
        for i, r in enumerate(top10, 1):
            ticker = r.get("ticker", "")
            name   = ALL_ETF_NAMES.get(ticker, ticker)
            cat    = r.get("sector_category", "")
            rs_sc  = rs_score_cell(r.get("rs_score"))
            rs_rt  = rs_rating_cell(r.get("rs_rating"))
            # Get price data from sector_lookup
            sec     = sector_lookup.get(ticker, {})
            c1d     = chg_cell(sec.get("change_1d_pct")) if sec else '<span class="na-val">N/A</span>'
            c1m     = chg_cell(sec.get("change_1m_pct")) if sec else '<span class="na-val">N/A</span>'
            c3m     = chg_cell(sec.get("change_3m_pct")) if sec else '<span class="na-val">N/A</span>'
            # vs MA columns (v5.3)
            vs20    = na(sec.get("vs_ma20_pct"),  "pct") if sec else '<span class="na-val">N/A</span>'
            vs50    = na(sec.get("vs_ma50_pct"),  "pct") if sec else '<span class="na-val">N/A</span>'
            vs200   = na(sec.get("vs_ma200_pct"), "pct") if sec else '<span class="na-val">N/A</span>'
            vs20_c  = css_dir(sec.get("vs_ma20_pct"))  if sec else ""
            vs50_c  = css_dir(sec.get("vs_ma50_pct"))  if sec else ""
            vs200_c = css_dir(sec.get("vs_ma200_pct")) if sec else ""
            # Sector ETF mapping (v5.3)
            spdr_label = SPDR_ETF_MAP.get(ticker, "—")
            medal = ["&#129351;", "&#129352;", "&#129353;"][i-1] if i <= 3 else f"#{i}"
            leaderboard_rows.append(
                f'<tr>'
                f'<td style="text-align:center;font-size:14px;">{medal}</td>'
                f'<td><strong>{ticker}</strong></td>'
                f'<td style="color:var(--text-label);font-size:11px;">{name}</td>'
                f'<td style="font-size:10px;color:#888;">{cat}</td>'
                f'<td>{c1d}</td><td>{c1m}</td><td>{c3m}</td>'
                f'<td style="text-align:right">{rs_sc}</td>'
                f'<td style="text-align:right">{rs_rt}</td>'
                f'<td class="hide-on-mobile {vs20_c}">{vs20}</td>'
                f'<td class="hide-on-mobile {vs50_c}">{vs50}</td>'
                f'<td class="hide-on-mobile {vs200_c}">{vs200}</td>'
                f'<td style="font-size:11px;color:#aaa;">{spdr_label}</td>'
                f'</tr>'
            )

        html_parts.append(f'''
<div style="margin-bottom:20px;">
  <div style="font-size:12px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;
    color:#ffd54f;border-left:3px solid #ffd54f;padding-left:10px;margin-bottom:8px;">
    &#127942; Top 10 RS Leaders (All 56 ETFs)
  </div>
  <div class="table-wrap">
  <table class="data-table" style="font-size:12px;">
    <thead><tr>
      <th style="text-align:center;">Rank</th>
      <th>Symbol</th><th>Name</th><th>Category</th>
      <th>1D%</th><th>1M%</th><th>3M%</th>
      <th>RS Score</th><th>RS Rating</th>
      <th class="hide-on-mobile">vs 20MA</th>
      <th class="hide-on-mobile">vs 50MA</th>
      <th class="hide-on-mobile">vs 200MA</th>
      <th>Sector ETF</th>
    </tr></thead>
    <tbody>
    {chr(10).join(leaderboard_rows)}
    </tbody>
  </table>
  </div>
</div>
''')
    else:
        html_parts.append('<div style="color:var(--text-muted);font-size:12px;padding:12px 0;">RS Leaderboard: Run rs_engine.py to generate analysis_results.json</div>')

    # ── Part 2: Volume Climax Alerts ───────────────────────────────────────────────
    # Combine: real volume climax from rs_engine + RSI extremes from today_market.json
    vol_climax_set = set(volume_climax_etfs)

    # RSI extremes from sectors
    rsi_anomalies = []
    for s in sectors:
        sym = s.get("symbol", "")
        rsi = safe_float(s.get("rsi14")) or 50.0
        c1d = safe_float(s.get("change_1d_pct")) or 0.0
        vs20 = safe_float(s.get("vs_ma20_pct")) or 0.0
        if rsi >= 75 or rsi <= 28:
            tag = "RSI Overbought &#128308;" if rsi >= 75 else "RSI Oversold &#128994;"
            rsi_anomalies.append({"sym": sym, "c1d": c1d, "vs20": vs20, "rsi": rsi, "tag": tag})

    # Build Volume Climax cards
    alert_cards = []
    for ticker in volume_climax_etfs:
        sec = sector_lookup.get(ticker, {})
        c1d  = safe_float(sec.get("change_1d_pct")) or 0.0
        vs20 = safe_float(sec.get("vs_ma20_pct")) or 0.0
        rsi  = safe_float(sec.get("rsi14")) or 50.0
        name = ALL_ETF_NAMES.get(ticker, ticker)
        c1d_str = f"+{c1d:.2f}%" if c1d > 0 else f"{c1d:.2f}%"
        c1d_cls = "text-green" if c1d > 0 else "text-red"
        vs20_str = f"+{vs20:.1f}%" if vs20 > 0 else f"{vs20:.1f}%"
        vs20_cls = "text-green" if vs20 > 0 else "text-red"
        alert_cards.append(
            f'<div class="anomaly-card">'
            f'<div class="anomaly-sym">&#9889; {ticker}</div>'
            f'<div class="anomaly-detail">'
            f'{name} &nbsp;•&nbsp; '
            f'1D: <span class="{c1d_cls}">{c1d_str}</span> &nbsp;•&nbsp; '
            f'vs 20MA: <span class="{vs20_cls}">{vs20_str}</span> &nbsp;•&nbsp; '
            f'RSI: {rsi:.1f}'
            f'</div>'
            f'<div class="anomaly-tag">Volume Climax (Vol &gt; 1.5×20MA)</div>'
            f'</div>'
        )
    for a in rsi_anomalies:
        if a["sym"] not in vol_climax_set:  # avoid duplicates
            c1d_str = f"+{a['c1d']:.2f}%" if a['c1d'] > 0 else f"{a['c1d']:.2f}%"
            c1d_cls = "text-green" if a['c1d'] > 0 else "text-red"
            vs20_str = f"+{a['vs20']:.1f}%" if a['vs20'] > 0 else f"{a['vs20']:.1f}%"
            vs20_cls = "text-green" if a['vs20'] > 0 else "text-red"
            name = ALL_ETF_NAMES.get(a["sym"], a["sym"])
            alert_cards.append(
                f'<div class="anomaly-card">'
                f'<div class="anomaly-sym">{a["sym"]}</div>'
                f'<div class="anomaly-detail">'
                f'{name} &nbsp;•&nbsp; '
                f'1D: <span class="{c1d_cls}">{c1d_str}</span> &nbsp;•&nbsp; '
                f'vs 20MA: <span class="{vs20_cls}">{vs20_str}</span> &nbsp;•&nbsp; '
                f'RSI: {a["rsi"]:.1f}'
                f'</div>'
                f'<div class="anomaly-tag">{a["tag"]}</div>'
                f'</div>'
            )

    alert_section = '\n'.join(alert_cards) if alert_cards else '<div style="color:var(--text-muted);font-size:12px;padding:8px 0;">No volume climax or RSI extreme anomalies detected today.</div>'
    html_parts.append(f'''
<div style="margin-bottom:12px;">
  <div style="font-size:12px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;
    color:#ef5350;border-left:3px solid #ef5350;padding-left:10px;margin-bottom:8px;">
    &#9889; Volume Climax &amp; RSI Alerts
  </div>
  {alert_section}
</div>
''')

    return "\n".join(html_parts)

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

def build_expert_insights_block(expert_insights: str) -> str:
    """
    Build the Expert Insights HTML block from expert_notes.txt content.
    Returns empty string if no insights provided.
    """
    if not expert_insights or not expert_insights.strip():
        return ""

    # Format the text: preserve line breaks
    formatted = expert_insights.replace("\n", "<br/>")

    return f"""<div class="section" style="border:2px solid #42a5f5;border-radius:10px;
  background:linear-gradient(135deg,#0a1628 0%,#0d1a2e 100%);
  padding:20px 24px;margin-bottom:28px;
  box-shadow:0 0 20px rgba(66,165,245,0.1);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
    <span style="font-size:20px;">&#128161;</span>
    <div style="font-size:10px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;
                color:#42a5f5;border-left:3px solid #42a5f5;padding-left:10px;">
      Expert Insights
    </div>
  </div>
  <div style="font-size:13px;color:#e0e0e0;line-height:1.8;white-space:pre-wrap;">{formatted}</div>
  <div style="margin-top:12px;font-size:10px;color:#555;">
    Source: expert_notes.txt &mdash; Updated manually by the analyst.
  </div>
</div>"""


def build_regime_banner(regime_info: dict) -> str:
    """
    Build a regime status banner shown at the top of the report.
    """
    if not regime_info:
        return ""

    regime  = regime_info.get("regime", "Normal")
    label   = regime_info.get("label", "")
    color   = regime_info.get("color", "text-amber")
    desc    = regime_info.get("description", "")
    spy_p   = regime_info.get("spy_price")
    ma20    = regime_info.get("spy_ma20")
    ma50    = regime_info.get("spy_ma50")
    vs20    = regime_info.get("vs_ma20_pct", 0.0)

    color_map = {
        "text-red":   ("#f44336", "rgba(244,67,54,0.08)",  "#f44336"),
        "text-amber": ("#ff9800", "rgba(255,152,0,0.08)",  "#ff9800"),
        "text-green": ("#4caf50", "rgba(76,175,80,0.08)",  "#4caf50"),
    }
    fg_color, bg_color, border_color = color_map.get(color, ("#ff9800", "rgba(255,152,0,0.08)", "#ff9800"))

    spy_str = f"${spy_p:.2f}" if spy_p else "N/A"
    ma20_str = f"${ma20:.2f}" if ma20 else "N/A"
    ma50_str = f"${ma50:.2f}" if ma50 else "N/A"
    vs20_str = f"{vs20:+.2f}%" if vs20 else "N/A"

    return f"""<div style="background:{bg_color};border:1px solid {border_color};
  border-radius:8px;padding:14px 18px;margin-bottom:20px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
  <div>
    <div style="font-size:15px;font-weight:700;color:{fg_color};">{label}</div>
    <div style="font-size:12px;color:#aaaaaa;margin-top:4px;">{desc}</div>
  </div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;">
    <div style="text-align:center;">
      <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.8px;">SPY</div>
      <div style="font-size:14px;font-weight:600;color:#e0e0e0;">{spy_str}</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.8px;">20MA</div>
      <div style="font-size:14px;font-weight:600;color:#aaaaaa;">{ma20_str}</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.8px;">50MA</div>
      <div style="font-size:14px;font-weight:600;color:#aaaaaa;">{ma50_str}</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.8px;">vs 20MA</div>
      <div style="font-size:14px;font-weight:600;color:{fg_color};">{vs20_str}</div>
    </div>
  </div>
</div>"""


def generate_checklist_html(checklist_status):
    """
    Legacy static checklist renderer — kept for backward compatibility.
    Accepts simple {item: 'Y'/'N'} dict.
    For new RegimeFilter output, use generate_dynamic_checklist_html() instead.
    """
    if not checklist_status:
        return ""

    html_content = "<div class='checklist-card' style='background: linear-gradient(135deg, #1a0a0a 0%, #1c1010 100%); border: 2px solid #f44336; border-radius: 10px; padding: 20px 24px; margin-bottom: 28px; box-shadow: 0 0 20px rgba(244,67,54,0.15);'>"
    html_content += "<h3 style='font-size:16px;font-weight:700;color:#f44336;letter-spacing:0.5px;margin-bottom:16px;display:flex;align-items:center;gap:8px;'><span style='font-size:20px;'>\U0001f6e1\ufe0f</span> Market Correction Checklist</h3>"
    html_content += "<ul style='list-style:none;padding:0;margin:0;'>"

    for item, status in checklist_status.items():
        if status == 'Y':
            icon = "<span style='color: #28a745; font-weight: bold; width: 24px; display: inline-block;'>\u2705</span>"
        else:
            icon = "<span style='color: #dc3545; font-weight: bold; width: 24px; display: inline-block;'>\u274c</span>"

        html_content += f"<li style='margin-bottom: 12px; font-size: 13px; color: #e0e0e0; display: flex; align-items: center; padding-bottom: 8px; border-bottom: 1px solid #2a2a2a;'>{icon} <span style='margin-left: 8px;'>{item}</span></li>"

    html_content += "</ul></div>"
    return html_content


def _render_dynamic_checklist(checklist_data: dict) -> str:
    """
    Render the active Y/N checklist table with actual value column.
    Accepts the 'checklist' sub-dict from RegimeFilter.determine_regime().
    Automatically selects green or red checklist based on active_checklist field.
    """
    active = checklist_data.get('active_checklist', 'red')
    items  = checklist_data.get(f'{active}_checklist', {})
    total  = checklist_data.get(f'{active}_total', 0)
    max_items = len(items)

    html = (
        '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:10px;">'
        '<thead><tr>'
        '<th style="text-align:left;padding:6px 10px;color:var(--text-muted);font-weight:600;'
        'border-bottom:1px solid var(--border);">Checklist Item</th>'
        '<th style="text-align:center;padding:6px 10px;color:var(--text-muted);font-weight:600;'
        'border-bottom:1px solid var(--border);width:50px;">Y/N</th>'
        '<th style="text-align:left;padding:6px 10px;color:var(--text-muted);font-weight:600;'
        'border-bottom:1px solid var(--border);">Actual Value</th>'
        '</tr></thead><tbody>'
    )

    for item, info in items.items():
        yn    = info.get('value', 'N')
        actual = info.get('actual', '')
        if yn == 'Y':
            yn_html = '<span style="color:#4caf50;font-weight:700;">Y</span>'
            row_bg  = 'background:rgba(76,175,80,0.05);'
        else:
            yn_html = '<span style="color:#f44336;font-weight:700;">N</span>'
            row_bg  = 'background:rgba(244,67,54,0.05);'
        html += (
            f'<tr style="{row_bg}">'
            f'<td style="padding:7px 10px;border-bottom:1px solid #1e1e1e;color:#e0e0e0;">{item}</td>'
            f'<td style="text-align:center;padding:7px 10px;border-bottom:1px solid #1e1e1e;">{yn_html}</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #1e1e1e;color:#aaaaaa;font-size:12px;">{actual}</td>'
            f'</tr>'
        )

    score_color = '#4caf50' if total >= (max_items / 2) else '#f44336'
    html += (
        f'<tr><td colspan="3" style="padding:8px 10px;font-weight:700;'
        f'color:{score_color};border-top:1px solid var(--border);font-size:13px;">'
        f'\u7e3d\u5206\uff1a{total} / {max_items}</td></tr>'
        '</tbody></table>'
    )
    return html


def _add_criteria_modal() -> str:
    """
    Return the Criteria Modal HTML + JS snippet.
    Inject once near the end of the page body.
    Triggered by showCriteriaModal() JavaScript call.
    """
    return '''
<div id="criteriaModal" style="display:none;position:fixed;top:10%;left:10%;width:80%;
  background:#1a1a2e;padding:24px 28px;border:2px solid #42a5f5;
  border-radius:10px;z-index:9999;box-shadow:0 0 40px rgba(66,165,245,0.25);
  max-height:75vh;overflow-y:auto;">
  <h2 style="color:#42a5f5;font-size:16px;font-weight:700;margin-bottom:14px;">
    Regime Engine + Checklist Criteria (Grok v1.1)
  </h2>
  <p style="color:#e0e0e0;font-size:13px;margin-bottom:10px;">
    <strong style="color:#fff;">Regime 判斷準則：</strong>
  </p>
  <ul style="color:#e0e0e0;font-size:13px;line-height:1.9;padding-left:20px;margin-bottom:14px;">
    <li>\U0001f7e2 <strong>Uptrend</strong>\uff1aVIX &lt; 20 AND SPY &gt; 20MA AND % &gt; 20MA &gt; 40%</li>
    <li>\U0001f7e1 <strong>Correction</strong>\uff1aVIX 20\u201330 OR SPY \u4ecb\u4e4e 20MA\u201350MA OR % &gt; 20MA 25\u201340%</li>
    <li>\U0001f534 <strong>Bear Market</strong>\uff1a\u5176\u4ed6\u60c5\u6cc1</li>
  </ul>
  <p style="color:#e0e0e0;font-size:13px;margin-bottom:10px;">
    <strong style="color:#fff;">Checklist \u9805\u76ee\u4f86\u6e90\uff1a</strong>
    \u4f60\u539f\u672c\u5169\u5f35 Correction Checklist\uff0c\u5df2\u81ea\u52d5\u91cf\u5316
  </p>
  <ul style="color:#e0e0e0;font-size:13px;line-height:1.9;padding-left:20px;margin-bottom:18px;">
    <li><strong>Green Checklist</strong>\uff08\u5e02\u5834\u56de\u6232\u4fe1\u865f\uff09\uff1a\u5171 6 \u9805\uff0c\u6aa2\u67e5 RSI &gt; 50\u3001SPY &gt; 20MA\u3001A/D &gt; 1.0\u3001VIX &lt; 20</li>
    <li><strong>Red Checklist</strong>\uff08\u5e02\u5834\u60e1\u5316\u4fe1\u865f\uff09\uff1a\u5171 5 \u9805\uff0c\u6aa2\u67e5 RSI &lt; 50\u3001SPY &lt; 20MA\u3001A/D &lt; 1.0\u3001VIX &gt; 20</li>
    <li><strong>Active Checklist</strong>\uff1a\u4f9d\u636e green_total vs red_total \u81ea\u52d5\u5207\u63db</li>
  </ul>
  <button onclick="document.getElementById(\'criteriaModal\').style.display=\'none\'">
    style="background:#42a5f5;color:#000;border:none;padding:8px 20px;border-radius:5px;
    font-weight:700;cursor:pointer;font-size:13px;">\u95dc\u9589</button>
</div>
<script>
function showCriteriaModal() {
    document.getElementById(\'criteriaModal\').style.display = \'block\';
}
</script>
'''


def _add_logic_info_modals() -> str:
    """
    Return Logic Info Modals HTML + JS for RS Momentum and Cluster Radar.
    Inject once near the end of the page body.
    Triggered by showLogicModal('rs_momentum') or showLogicModal('cluster_radar').
    """
    return '''
<!-- Logic Info Modal Overlay -->
<div id="liModalOverlay" class="li-modal-overlay" onclick="if(event.target===this)closeLogicModal()">
  <div class="li-modal" id="liModalBox">
    <!-- Content injected by JS -->
  </div>
</div>

<script>
var _liContents = {
  rs_momentum: {
    icon: "\u26a1",
    title: "RS Momentum \u2014 RS Score \u908f\u8f2f\u6e96\u5247",
    html: `
      <p>RS Score \u53cd\u6620\u6a19\u7684\u5728 11 \u500b\u6838\u5fc3 SPDR ETF \u4e2d\u7684\u76f8\u5c0d\u5f37\u5ea6\u6392\u540d (1\u201399)\u3002</p>
      <div class="formula-box">
        RS Score = (40% &times; 1m Return) + (40% &times; 3m Return) + (20% &times; 6m Return)
      </div>
      <p><strong style="color:#90caf9;">\u516c\u5f0f\u8aaa\u660e\uff1a</strong></p>
      <ul style="color:#d0d0d0;font-size:12px;line-height:1.8;padding-left:18px;margin-bottom:10px;">
        <li>1m Return \u5360\u6bd4 40% \u2014 \u8fd1\u671f\u52d5\u80fd\u6700\u91cd\u8981</li>
        <li>3m Return \u5360\u6bd4 40% \u2014 \u4e2d\u671f\u8da8\u52e2\u78ba\u8a8d</li>
        <li>6m Return \u5360\u6bd4 20% \u2014 \u9577\u671f\u80cc\u666f\u53c3\u8003</li>
      </ul>
      <p><strong style="color:#90caf9;">RS Rating \u5206\u7d1a\uff1a</strong></p>
      <ul style="color:#d0d0d0;font-size:12px;line-height:1.8;padding-left:18px;">
        <li><span style="color:#66bb6a;font-weight:700;">90\u201399 \u2605\u2605</span> \u2014 Elite Momentum</li>
        <li><span style="color:#81c784;font-weight:700;">80\u201389 \u2605</span> \u2014 Strong RS</li>
        <li><span style="color:#ffa726;font-weight:700;">60\u201379</span> \u2014 Mid-tier</li>
        <li><span style="color:#ef5350;font-weight:700;">&lt;60</span> \u2014 Weak / Laggard</li>
      </ul>
    `
  },
  cluster_radar: {
    icon: "\U0001f4e1",
    title: "Cluster Radar \u2014 Hot Cluster \u908f\u8f2f\u6e96\u5247",
    html: `
      <p>Cluster Radar \u6aa2\u6e2c\u6a5f\u69cb\u8cc7\u91d1\u6b63\u5728\u96c6\u9ad4\u6027\u6d41\u5165\u7684\u677f\u584a\u3002</p>
      <div class="formula-box">
        Hot Cluster &#128293; \u6e96\u5247\uff1a<br>
        &nbsp;&nbsp;\u7d44\u5167 &gt;50% \u6210\u54e1\u540c\u6642\u6eff\u8db3\uff1a<br>
        &nbsp;&nbsp;(Price &gt; 20MA) \u4e14 (RS Rating &gt; 80)
      </div>
      <p><strong style="color:#90caf9;">\u6e96\u5247\u8aaa\u660e\uff1a</strong></p>
      <ul style="color:#d0d0d0;font-size:12px;line-height:1.8;padding-left:18px;margin-bottom:10px;">
        <li><strong>Price &gt; 20MA</strong> \u2014 \u77ed\u671f\u50f9\u683c\u52d5\u80fd\u6b63\u5411</li>
        <li><strong>RS Rating &gt; 80</strong> \u2014 \u76f8\u5c0d\u5f37\u5ea6\u5728\u524d 20% \u5206\u4f4d</li>
        <li><strong>&gt;50% \u6210\u54e1</strong> \u2014 \u4ee3\u8868\u677f\u584a\u5167\u591a\u6578\u6a19\u7684\u540c\u6b65\u5f37\u52e2</li>
      </ul>
      <p><strong style="color:#90caf9;">\u71b1\u5ea6\u5206\u7d1a\uff1a</strong></p>
      <ul style="color:#d0d0d0;font-size:12px;line-height:1.8;padding-left:18px;">
        <li><span style="color:#ff7043;font-weight:700;">&#128293; Hot Cluster</span> \u2014 &gt;50% \u6eff\u8db3\u6e96\u5247</li>
        <li><span style="color:#ffa726;font-weight:700;">&#128165; Warming Up</span> \u2014 30\u201350% \u6eff\u8db3\u6e96\u5247</li>
        <li><span style="color:#9e9e9e;font-weight:700;">&#10052; Cool</span> \u2014 &lt;30% \u6eff\u8db3\u6e96\u5247</li>
      </ul>
    `
  }
};

function showLogicModal(type) {
  var overlay = document.getElementById(\'liModalOverlay\');
  var box     = document.getElementById(\'liModalBox\');
  var content = _liContents[type];
  if (!content) return;
  box.innerHTML = (
    \'<h3>\' + content.icon + \' \' + content.title + \'</h3>\' +
    content.html +
    \'<button class="li-close-btn" onclick="closeLogicModal()">&#10006; \u95dc\u9589</button>\'
  );
  overlay.classList.add(\'active\');
}

function closeLogicModal() {
  document.getElementById(\'liModalOverlay\').classList.remove(\'active\');
}
</script>
'''


def render(regime_info: dict = None, expert_insights: str = "", checklist_status: dict = None):
    with open(JSON, encoding="utf-8") as f:
        data = json.load(f)

    # Load AI strategy if available
    ai_strategy = None
    if AI_JSON.exists():
        with open(AI_JSON, encoding="utf-8") as f:
            ai_strategy = json.load(f)
        print("  \u2713  AI strategy loaded from ai_strategy.json")
    else:
        print("  \u26a0  ai_strategy.json not found, using computed fallback")

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

    # Section 5: Sectors & Industries — RS Momentum Redesign (v2.3)
    # 5A: Core SPDR Sectors with RS Score & Rating
    html = html.replace("{{SECTOR_ROWS}}",       build_sector_rows(sectors))
    # 5B: Industry RS Radar with Cluster Detection
    html = html.replace("{{INDUSTRY_RS_RADAR}}", build_industry_rs_radar(industry, sectors))
    # 5C: Market Anomalies (Volume Climax proxy)
    html = html.replace("{{VOLUME_CLIMAX_BLOCK}}", build_volume_climax_block(sectors))
    # Legacy placeholder (no longer in template but keep for safety)
    html = html.replace("{{INDUSTRY_ROWS}}",     build_industry_rows(industry))
    print("  ✓  Section 5 RS Momentum redesign injected (5A/5B/5C)")
    # Step 2 Reorg: Section 5/6/7 趨勢化 — Thematic / RS Leaders / Laggards
    html = html.replace("{{THEMATIC_ROWS}}",    build_thematic_rows(data))
    html = html.replace("{{RS_LEADERS_ROWS}}",  build_rs_leaders_rows(data))
    html = html.replace("{{LAGGARDS_ROWS}}",    build_laggards_rows(data))
    print("  ✓  Step 2 Section 5/6/7 Thematic/RS Leaders/Laggards injected")

    # Section 6: AI Market Analysis (Checklist + Bull/Bear)
    html = html.replace("{{S6_CONTENT}}", build_s6_analysis(data, ai_strategy))

    # Section 7: Trading Outlook & Watchlist with Technical Triggers (Coach's Action Plan)
    html = html.replace("{{S7_CONTENT}}", build_s7_content(data, ai_strategy))

    # Section 8: Event Calendar with BMO/AMC timing
    html = html.replace("{{S8_CONTENT}}", build_s8_calendar())

    # ── DATA WARNING BANNER (Grok v5.1) ────────────────────────────────────────────
    _data_status   = data.get("data_status", "fresh")
    _data_warnings = data.get("data_warnings", [])
    if _data_status == "warning" and _data_warnings:
        _warn_text = " | ".join(_data_warnings)
        _warning_banner_html = (
            f'<div class="data-warning-banner active">'
            f'⚠️ Data Stale / Warning: {_warn_text} — Please check source data'
            f'</div>'
        )
    else:
        _warning_banner_html = '<div class="data-warning-banner"></div>'
    html = html.replace("{{DATA_WARNING_BANNER}}", _warning_banner_html)

    # ── REGIME BANNER & DYNAMIC CORRECTION CHECKLIST (v1.2) ─────────────────────
    regime_banner_html = build_regime_banner(regime_info or {})
    html = html.replace("{{REGIME_BANNER}}", regime_banner_html)

    # Inject Dynamic Checklist for ALL regimes (not just Correction)
    # checklist_status may be:
    #   (a) Full RegimeFilter.determine_regime() dict  → use _render_dynamic_checklist()
    #   (b) Legacy {item: 'Y'/'N'} dict                → fall back to generate_checklist_html()
    #   (c) None / empty                               → try import fallback, then empty
    if checklist_status and isinstance(checklist_status, dict):
        if 'checklist' in checklist_status and 'raw_numbers' in checklist_status:
            # ── New v1.2 path: full RegimeFilter output ──────────────────────────
            regime_data = checklist_status
            raw = regime_data.get('raw_numbers', {})
            regime_label = regime_data.get('regime', 'N/A')
            regime_score = regime_data.get('regime_score', 0)
            active = regime_data['checklist'].get('active_checklist', 'red')
            active_total = regime_data['checklist'].get(f'{active}_total', 0)
            max_items = len(regime_data['checklist'].get(f'{active}_checklist', {}))

            dynamic_table = _render_dynamic_checklist(regime_data['checklist'])
            criteria_modal = _add_criteria_modal()

            correction_checklist = f"""
<div style="background:linear-gradient(135deg,#0d1117 0%,#111827 100%);
  border:2px solid #42a5f5;border-radius:10px;padding:20px 24px;
  margin-bottom:28px;box-shadow:0 0 20px rgba(66,165,245,0.12);">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:14px;">
    <div>
      <div style="font-size:10px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;
                  color:#42a5f5;border-left:3px solid #42a5f5;padding-left:10px;">
        Market Regime &amp; Auto Y/N Checklist
      </div>
      <div style="font-size:18px;font-weight:700;color:#e0e0e0;margin-top:6px;">
        {regime_label} &nbsp;<span style="font-size:13px;color:#aaa;">Score: {regime_score}</span>
      </div>
    </div>
    <a href="#" onclick="showCriteriaModal();return false;"
      style="font-size:12px;color:#42a5f5;text-decoration:none;border:1px solid #42a5f5;
      padding:5px 12px;border-radius:5px;font-weight:600;">
      &#128203; View Criteria (Grok v1.1)
    </a>
  </div>

  <!-- 關鍵數據列 -->
  <div style="background:#0a0a0a;border-radius:6px;padding:10px 14px;margin-bottom:14px;
    font-size:12px;color:#aaaaaa;display:flex;flex-wrap:wrap;gap:16px;">
    <span><strong style="color:#e0e0e0;">VIX</strong> = {raw.get('VIX', 'N/A')}</span>
    <span><strong style="color:#e0e0e0;">SPY vs 20MA</strong> = {raw.get('SPY_vs_20MA', 'N/A')}</span>
    <span><strong style="color:#e0e0e0;">% Above 20MA</strong> = {raw.get('percent_above_20ma', 'N/A')}%</span>
    <span><strong style="color:#e0e0e0;">A/D Ratio</strong> = {raw.get('A/D_Ratio', 'N/A')}</span>
    <span><strong style="color:#e0e0e0;">RSI</strong> = {raw.get('RSI', 'N/A')}</span>
  </div>

  <!-- Auto Y/N Checklist Table -->
  <div style="font-size:11px;font-weight:600;letter-spacing:0.8px;text-transform:uppercase;
    color:#42a5f5;margin-bottom:6px;">Correction Checklist (\u81ea\u52d5\u6253\u5206)</div>
  {dynamic_table}
</div>
{criteria_modal}
"""
            print(f"  \u2713  Dynamic Regime Section v1.2 injected ({regime_label}, {active} checklist {active_total}/{max_items})")

        else:
            # ── Legacy path: simple {item: 'Y'/'N'} dict ─────────────────────────
            correction_checklist = generate_checklist_html(checklist_status)
            print("  \u2713  Legacy Checklist injected (static Y/N dict)")
    else:
        # ── Fallback: try module-level build_correction_checklist_html() ─────────
        try:
            from regime_filter import build_correction_checklist_html
            correction_checklist = build_correction_checklist_html()
            print("  \u2713  Fallback Static Correction Checklist injected")
        except (ImportError, AttributeError):
            correction_checklist = ""
            print("  \u2139  No checklist data available, skipping")

    html = html.replace("{{CORRECTION_CHECKLIST}}", correction_checklist)

    # ── EXPERT INSIGHTS BLOCK ─────────────────────────────────────────────────
    expert_block = build_expert_insights_block(expert_insights or "")
    html = html.replace("{{EXPERT_INSIGHTS}}", expert_block)
    if expert_block:
        print("  \u2713  Expert Insights block injected")
    else:
        print("  \u2139  Expert Insights: no content (expert_notes.txt empty)")

    # ── IMAGE CACHE-BUSTING (NO Base64 — standard relative paths + timestamp) ──
    import time as _time_mod
    _cache_ts = str(int(_time_mod.time()))  # Unix timestamp for cache-busting
    print(f"\n  ── IMAGE CACHE-BUSTING (no Base64, timestamp={_cache_ts}) ──")

    # Log image paths for audit
    img_stockbee  = BASE / "assets/img/today/stockbee_mm.png"
    img_industry  = BASE / "assets/img/today/industry_performance.png"
    img_heatmap   = BASE / "assets/img/today/market_heatmap.png"
    print(f"  [IMG PATH] stockbee_mm.png    → {img_stockbee.resolve()} | exists={img_stockbee.exists()} | mtime={img_stockbee.stat().st_mtime if img_stockbee.exists() else 'N/A'}")
    print(f"  [IMG PATH] industry_perf.png  → {img_industry.resolve()} | exists={img_industry.exists()} | mtime={img_industry.stat().st_mtime if img_industry.exists() else 'N/A'}")
    print(f"  [IMG PATH] market_heatmap.png → {img_heatmap.resolve()} | exists={img_heatmap.exists()} | mtime={img_heatmap.stat().st_mtime if img_heatmap.exists() else 'N/A'}")

    # Replace all img src with cache-busted relative paths (NO Base64)
    html = html.replace(
        'src="assets/img/today/stockbee_mm.png"',
        f'src="assets/img/today/stockbee_mm.png?v={_cache_ts}"'
    )
    html = html.replace(
        'src="assets/img/today/industry_performance.png"',
        f'src="assets/img/today/industry_performance.png?v={_cache_ts}"'
    )
    html = html.replace(
        'src="assets/img/today/market_heatmap.png"',
        f'src="assets/img/today/market_heatmap.png?v={_cache_ts}"'
    )
    print(f"  ✓  All 3 images: cache-busted with ?v={_cache_ts} (NO Base64)")
    print("  ── END IMAGE CACHE-BUSTING ──\n")

    # ── CRITERIA MODAL (inject once before </body>) ─────────────────────────────
    # Always inject the modal so the 'View Criteria' link works on every page.
    # Safe to inject even when checklist is not shown — modal stays hidden (display:none).
    html = html.replace("</body>", _add_criteria_modal() + "\n</body>")
    print("  \u2713  Criteria Modal injected before </body>")

    # ── LOGIC INFO MODALS (RS Momentum + Cluster Radar) ────────────────────────
    html = html.replace("</body>", _add_logic_info_modals() + "\n</body>")
    print("  ✓  Logic Info Modals (RS Momentum + Cluster Radar) injected")

    # ── Residual check
    leftover = re.findall(r"\{\{[A-Z0-9_]+\}\}", html)
    if leftover:
        print(f"  ⚠  Unresolved tags ({len(leftover)}): {leftover[:10]}")
    else:
        print("  ✓  All template tags resolved (0 residual)")

    # ── WRITE ARCHIVE FILE (before building history block) ───────────────────
    # Write archive FIRST so the history block can include today's entry
    print("\n  ── ARCHIVE OUTPUT ──")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    today_str    = get_today_date_str()
    json_date    = meta.get("date", today_str)
    archive_date = json_date[:10] if json_date and len(json_date) >= 10 else today_str
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

# ── Step 2 新增：Section 5/6/7 趨勢化 build functions ──────────────────────

def build_thematic_rows(data):
    """Section 5 — Thematic & Sub-Sector (uses data['thematic'] list)"""
    rows = []
    for item in data.get("thematic", []):
        symbol = item.get("symbol", "")
        price  = na(item.get("price"), "price")
        ma20   = na(item.get("vs_20ma"),  "pct")
        ma50   = na(item.get("vs_50ma"),  "pct")
        ma200  = na(item.get("vs_200ma"), "pct")
        rows.append(
            f'<tr>'
            f'<td>{symbol}</td>'
            f'<td>{price}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_20ma"))}">{ma20}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_50ma"))}">{ma50}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_200ma"))}">{ma200}</td>'
            f'</tr>'
        )
    if not rows:
        return '<tr><td colspan="5"><span class="na-val">No thematic data — run fetch_all_data.py Step 3</span></td></tr>'
    return "\n".join(rows)


def build_rs_leaders_rows(data):
    """Section 6 — Top RS Leaders (uses data['rs_leaders'] list)"""
    rows = []
    for item in data.get("rs_leaders", []):
        symbol     = item.get("symbol", "")
        price      = na(item.get("price"), "price")
        ma20       = na(item.get("vs_20ma"),  "pct")
        ma50       = na(item.get("vs_50ma"),  "pct")
        ma200      = na(item.get("vs_200ma"), "pct")
        sector_etf = SPDR_ETF_MAP.get(symbol.upper(), "—")
        rows.append(
            f'<tr>'
            f'<td><strong>{symbol}</strong></td>'
            f'<td>{price}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_20ma"))}">{ma20}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_50ma"))}">{ma50}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_200ma"))}">{ma200}</td>'
            f'<td style="font-size:11px;color:#aaa;">{sector_etf}</td>'
            f'</tr>'
        )
    if not rows:
        return '<tr><td colspan="6"><span class="na-val">No RS leaders data — run fetch_all_data.py Step 3</span></td></tr>'
    return "\n".join(rows)


def build_laggards_rows(data):
    """Section 7 — Laggards / Weakest (uses data['laggards'] list)"""
    rows = []
    for item in data.get("laggards", []):
        symbol     = item.get("symbol", "")
        price      = na(item.get("price"), "price")
        ma20       = na(item.get("vs_20ma"),  "pct")
        ma50       = na(item.get("vs_50ma"),  "pct")
        ma200      = na(item.get("vs_200ma"), "pct")
        sector_etf = SPDR_ETF_MAP.get(symbol.upper(), "—")
        rows.append(
            f'<tr>'
            f'<td><strong>{symbol}</strong></td>'
            f'<td>{price}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_20ma"))}">{ma20}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_50ma"))}">{ma50}</td>'
            f'<td class="hide-on-mobile {css_dir(item.get("vs_200ma"))}">{ma200}</td>'
            f'<td style="font-size:11px;color:#aaa;">{sector_etf}</td>'
            f'</tr>'
        )
    if not rows:
        return '<tr><td colspan="6"><span class="na-val">No laggards data — run fetch_all_data.py Step 3</span></td></tr>'
    return "\n".join(rows)


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("  Market Summary Renderer v5.3  (Semi-Auto Mode)")
    print("╚══════════════════════════════════════════════╝")
    render()
    print("✅  Render complete.")
