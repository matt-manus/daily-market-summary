"""
html_generator.py  —  Credit-Efficient Market Summary System  v5.0
-----------------------------------------------------------------
Modular refactor of render_report.py.

New in v5.0:
  - Accepts regime_info dict from regime_filter.py
  - Injects Correction Checklist at top when regime == 'Correction'
  - Coach's Action Plan (Section 7) promoted to most prominent position
  - Expert Insights block injected from expert_notes.txt
  - All Base64 image embedding preserved
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
    
    TIMEZONE FIX: Archive filenames and report dates always follow
    New York calendar (America/New_York), regardless of server timezone.
    """
    ny_tz = pytz.timezone("America/New_York")
    return datetime.now(ny_tz).strftime("%Y-%m-%d")


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


def build_sector_rows(sectors):
    """5A — Core SPDR Sectors with RS Score & Rating (v2.3)."""
    if not sectors:
        return '<tr><td colspan="10"><span class="na-val">N/A</span></td></tr>'
    # Compute RS scores
    sectors_with_rs = compute_rs_scores(sectors)
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
        vs20  = na(s.get("vs_ma20_pct"), "pct")
        vs20_c = css_dir(s.get("vs_ma20_pct"))
        rows.append(
            f'<tr class="{rsi_row}">'
            f'<td><strong>{sym}</strong></td>'
            f'<td style="color:var(--text-label)">{name}</td>'
            f'<td>{price}</td><td>{c1d}</td><td>{c1m}</td><td>{c3m}</td>'
            f'<td style="text-align:right">{rs_sc}</td>'
            f'<td style="text-align:right">{rs_rt}</td>'
            f'<td>{rsi_html}</td><td class="{vs20_c}">{vs20}</td></tr>'
        )
    return "\n".join(rows)


def build_industry_rs_radar(industry: list, sectors: list) -> str:
    """
    5B — Industry RS Radar: group industries by SECTOR_CATEGORIES.
    Since industry data doesn’t map directly to SPDR ETFs,
    we display all industries sorted by RS Score (1m+3m weighted),
    and mark Hot Cluster based on 1m > 0 and 3m > 0 criteria.
    """
    if not industry:
        return '<div style="color:var(--text-muted);font-size:12px;padding:12px;">No industry data available.</div>'

    # Compute RS scores for industries
    scored_industries = []
    for row in industry:
        c1m = safe_float(row.get("change_1m_pct")) or 0.0
        c3m = safe_float(row.get("change_3m_pct")) or 0.0
        c_ytd = safe_float(row.get("change_ytd_pct")) or c3m
        rs_score = round(0.40 * c1m + 0.40 * c3m + 0.20 * c_ytd, 2)
        scored_industries.append({**row, "rs_score": rs_score})

    # Rank 1-99
    n = len(scored_industries)
    sorted_scores = sorted([s["rs_score"] for s in scored_industries])
    for s in scored_industries:
        rank_idx = sorted_scores.index(s["rs_score"])
        s["rs_rating"] = max(1, min(99, round(1 + (rank_idx / max(n - 1, 1)) * 98)))

    # Sort by RS Rating descending
    scored_industries.sort(key=lambda x: x.get("rs_rating", 0), reverse=True)

    # Determine cluster status for each industry
    # Hot Cluster: rs_rating > 80 AND 1m_pct > 0 (proxy for Price > 20MA)
    hot_count   = sum(1 for s in scored_industries if s.get("rs_rating", 0) > 80 and (safe_float(s.get("change_1m_pct")) or 0) > 0)
    total_count = len(scored_industries)
    cluster_pct = (hot_count / total_count * 100) if total_count > 0 else 0

    # Cluster banner
    if cluster_pct > 50:
        cluster_badge = '<span class="cluster-badge cluster-hot">&#128293; Hot Cluster</span>'
        cluster_desc  = f'<span style="font-size:10px;color:#ff7043;">{hot_count}/{total_count} 行業滿足熱區準則 ({cluster_pct:.0f}%)</span>'
    elif cluster_pct > 30:
        cluster_badge = '<span class="cluster-badge cluster-warm">&#128165; Warming Up</span>'
        cluster_desc  = f'<span style="font-size:10px;color:#ffa726;">{hot_count}/{total_count} 行業滿足温熱準則 ({cluster_pct:.0f}%)</span>'
    else:
        cluster_badge = '<span class="cluster-badge cluster-cool">&#10052; Cool</span>'
        cluster_desc  = f'<span style="font-size:10px;color:#9e9e9e;">{hot_count}/{total_count} 行業滿足熱區準則 ({cluster_pct:.0f}%)</span>'

    # Build table
    header = f'''
<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
  {cluster_badge}
  {cluster_desc}
</div>
<div class="table-wrap">
  <table class="data-table">
    <thead>
      <tr>
        <th style="text-align:center;">#</th>
        <th>Industry</th>
        <th>Stocks</th>
        <th>1D Chg%</th>
        <th>1M Chg%</th>
        <th>3M Chg%</th>
        <th>RS Score</th>
        <th>RS Rating</th>
        <th>Cluster</th>
      </tr>
    </thead>
    <tbody>
'''
    rows = []
    for i, row in enumerate(scored_industries, 1):
        label  = row.get("label", "")
        ns     = row.get("num_stocks")
        ns_str = str(int(ns)) if ns is not None else '<span class="na-val">N/A</span>'
        c1d    = chg_cell(row.get("change_1d_pct"))
        c1m    = chg_cell(row.get("change_1m_pct"))
        c3m_v  = chg_cell(row.get("change_3m_pct"))
        rs_sc  = rs_score_cell(row.get("rs_score"))
        rs_rt  = rs_rating_cell(row.get("rs_rating"))
        # Cluster status per row
        is_hot = row.get("rs_rating", 0) > 80 and (safe_float(row.get("change_1m_pct")) or 0) > 0
        if is_hot:
            cl_cell = '<span class="cluster-badge cluster-hot" style="font-size:10px;">&#128293; Hot</span>'
        else:
            cl_cell = '<span class="cluster-badge cluster-cool" style="font-size:10px;">&#8212;</span>'
        rows.append(
            f'<tr>'
            f'<td style="text-align:center;color:var(--text-muted)">{i}</td>'
            f'<td>{label}</td>'
            f'<td style="color:var(--text-label)">{ns_str}</td>'
            f'<td>{c1d}</td><td>{c1m}</td><td>{c3m_v}</td>'
            f'<td style="text-align:right">{rs_sc}</td>'
            f'<td style="text-align:right">{rs_rt}</td>'
            f'<td style="text-align:center">{cl_cell}</td>'
            f'</tr>'
        )
    footer = '    </tbody>\n  </table>\n</div>'
    return header + "\n".join(rows) + "\n" + footer


def build_volume_climax_block(sectors: list) -> str:
    """
    5C — Market Anomalies: detect ETFs with volume climax (simulated).
    Since we don’t have real volume data in today_market.json,
    we use extreme price moves as a proxy for volume climax:
    - |change_1d_pct| > 2.0% AND |vs_ma20_pct| > 5% (strong divergence)
    """
    anomalies = []
    for s in sectors:
        c1d  = safe_float(s.get("change_1d_pct")) or 0.0
        vs20 = safe_float(s.get("vs_ma20_pct"))  or 0.0
        rsi  = safe_float(s.get("rsi14"))         or 50.0
        sym  = s.get("symbol", "")
        name = SECTOR_NAMES.get(sym, s.get("name", ""))
        # Flag as anomaly if large 1D move AND extreme RSI
        if abs(c1d) >= 1.5 or rsi >= 75 or rsi <= 28:
            tag = ""
            if rsi >= 75:
                tag = "RSI Overbought"
            elif rsi <= 28:
                tag = "RSI Oversold"
            elif c1d >= 1.5:
                tag = "Volume Surge (Up)"
            elif c1d <= -1.5:
                tag = "Volume Surge (Down)"
            anomalies.append({
                "sym": sym, "name": name,
                "c1d": c1d, "vs20": vs20, "rsi": rsi, "tag": tag
            })

    if not anomalies:
        return '<div style="color:var(--text-muted);font-size:12px;padding:12px 0;">No volume climax anomalies detected today.</div>'

    cards = []
    for a in anomalies:
        c1d_str = f"+{a['c1d']:.2f}%" if a['c1d'] > 0 else f"{a['c1d']:.2f}%"
        c1d_cls = "text-green" if a['c1d'] > 0 else "text-red"
        vs20_str = f"+{a['vs20']:.1f}%" if a['vs20'] > 0 else f"{a['vs20']:.1f}%"
        vs20_cls = "text-green" if a['vs20'] > 0 else "text-red"
        cards.append(
            f'<div class="anomaly-card">'
            f'<div class="anomaly-sym">{a["sym"]}</div>'
            f'<div class="anomaly-detail">'
            f'{a["name"]} &nbsp;•&nbsp; '
            f'1D: <span class="{c1d_cls}">{c1d_str}</span> &nbsp;•&nbsp; '
            f'vs 20MA: <span class="{vs20_cls}">{vs20_str}</span> &nbsp;•&nbsp; '
            f'RSI: {a["rsi"]:.1f}'
            f'</div>'
            f'<div class="anomaly-tag">{a["tag"]}</div>'
            f'</div>'
        )
    return "\n".join(cards)

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
    print("  \u2713  Section 5 RS Momentum redesign injected (5A/5B/5C)")

    # Section 6: AI Market Analysis (Checklist + Bull/Bear)
    html = html.replace("{{S6_CONTENT}}", build_s6_analysis(data, ai_strategy))

    # Section 7: Trading Outlook & Watchlist with Technical Triggers (Coach's Action Plan)
    html = html.replace("{{S7_CONTENT}}", build_s7_content(data, ai_strategy))

    # Section 8: Event Calendar with BMO/AMC timing
    html = html.replace("{{S8_CONTENT}}", build_s8_calendar())

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
        print("  ✓  Section 4D Stockbee: Base64 injected into HTML")
    else:
        print("  ⚠  Section 4D Stockbee: image missing, keeping path reference")

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

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("  Market Summary Renderer v4.4  (Semi-Auto Mode)")
    print("╚══════════════════════════════════════════════╝")
    render()
    print("✅  Render complete.")
