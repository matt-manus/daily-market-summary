#!/usr/bin/env python3
"""Render the dark US close report from RUN_DIR/results.json into the dev-3.9 page template.
Usage: render.py RUN_DIR SESSION TEMPLATE_HTML OUT_HTML ARCHIVE_DIR"""
import json, os, re, sys, base64, html, math
from datetime import datetime
from zoneinfo import ZoneInfo

RUN, SESSION, TEMPLATE, OUT, ARCH = sys.argv[1:6]
R = json.load(open(os.path.join(RUN, "results.json")))
META = json.load(open(os.path.join(RUN, "meta.json")))
HK, NY = ZoneInfo("Asia/Hong_Kong"), ZoneInfo("America/New_York")
now = datetime.now(HK)
hkt, et = now.strftime("%Y-%m-%d %H:%M"), now.astimezone(NY).strftime("%Y-%m-%d %H:%M")
esc = lambda s: html.escape(str(s), quote=True)

def pct(x, nd=2, sign=True):
    return "" if x is None else (f"{x*100:+.{nd}f}%" if sign else f"{x*100:.{nd}f}%")
def cls(x):
    return "" if x is None or abs(x) < 5e-5 else ("text-green" if x > 0 else "text-red")
def rsi_cell(f):
    if f is None: return '<span class="na-val"></span>'
    if f >= 70: fill, txt = "rsi-fill rsi-ob", "text-red"
    elif f <= 30: fill, txt = "rsi-fill rsi-os", "text-green"
    else: fill, txt = "rsi-fill rsi-neu", ""
    return f'<div class="rsi-wrap"><span class="{txt}">{f:.1f}</span><div class="rsi-track"><div class="{fill}" style="width:{max(0,min(100,f)):.0f}%"></div></div></div>'
def pill(x):
    return f'<span class="chg-pill {"text-green-bg" if x >= 0 else "text-red-bg"}">{pct(x)}</span>'
def pct_bar(f):
    if f is None: return '<span class="na-val"></span>'
    b, t = ("pct-bar-green", "text-green") if f >= 60 else (("pct-bar-red", "text-red") if f <= 35 else ("pct-bar-amber", "text-amber"))
    return f'<div class="pct-bar-wrap"><span class="{t}">{f:.1f}%</span><div class="pct-bar-track"><div class="{b}" style="width:{max(0,min(100,f)):.0f}%"></div></div></div>'

def replace_section(h, start, new, stop='<div class="section"'):
    i = h.index(start)
    j = h.index(stop, i + len(start))
    seg = h[i:j]
    tail = re.search(r"(\s*(<!--[^\n]*-->\s*)*)$", seg).group(1)
    return h[:i] + new.rstrip("\n") + tail + h[j:]  # tail keeps the old trailing whitespace, so re-renders do not add blank lines

h = open(TEMPLATE, encoding="utf-8").read()

# ---------- header ----------
h = re.sub(r'(<div class="subtitle">Momentum Swing Trading Coach &middot; )\d{4}-\d{2}-\d{2}', r"\g<1>" + SESSION, h, count=1)
h = re.sub(r'<div class="ts-badge">HKT <span>[^<]*</span></div>', f'<div class="ts-badge">HKT <span>{hkt}</span></div>', h, count=1)
h = re.sub(r'<div class="ts-badge">ET <span>[^<]*</span></div>', f'<div class="ts-badge">ET <span>{et}</span></div>', h, count=1)
h = re.sub(r"<title>[^<]*</title>", f"<title>Daily Market Summary — US session {SESSION}</title>", h, count=1)

# ---------- regime banner removed 2026-10-08 (strip it, and its marker comment, from older templates) ----------
fg = META["fg"]
fgs = fg["score"] if fg else None
h = re.sub(r'\n?<!-- ═══ REGIME BANNER \(auto-injected\) ═+ -->\n(<div style="background:[^\n]*</div></div>\n)?', "", h)
assert "REGIME BANNER" not in h and "RISK-ON REGIME" not in h and "NEUTRAL REGIME" not in h and "RISK-OFF REGIME" not in h

# ---------- breadth & participation trends (top of page; last 20 sessions) ----------
BV = R.get("breadth_vs5")
TD = R["daily"][-20:]
PS = R.get("participation_series") or {"rows": [], "base_date": ""}
PR = PS["rows"]

def nice_top(v, step):
    return max(step, int(math.ceil(v / step) * step)) if v and v > 0 else step

def mini_chart(dates, title_html, series=None, bars=None, ymin=0, ymax=10, ystep=5, unit="%", tips=None, zero=False):
    W, H = 360, 176
    x0, x1, yt, yb = 34, 352, 10, 140
    n = len(dates)
    Y = lambda v: yb - (v - ymin) / (ymax - ymin) * (yb - yt)
    slot = (x1 - x0) / max(n, 1)
    X = lambda i: x0 + slot * (i + 0.5)
    o = [f'<svg class="hover-chart" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
    g = ymin
    while g <= ymax + 1e-9:
        lab = (f"{g:+g}" if zero and g != 0 else f"{g:g}") + unit
        o.append(f'<line x1="{x0}" y1="{Y(g):.1f}" x2="{x1}" y2="{Y(g):.1f}" stroke="{"#555" if (zero and g == 0) else "#2a2a2a"}" stroke-width="1"/>'
                 f'<text x="{x0-4}" y="{Y(g)+3:.1f}" fill="#777" font-size="8" text-anchor="end">{lab}</text>')
        g += ystep
    if bars:
        bw = slot * 0.36
        for k, (vals, col) in enumerate(bars):
            for i, v in enumerate(vals):
                if v is None: continue
                bx = X(i) - bw + k * bw
                o.append(f'<rect x="{bx:.1f}" y="{Y(v):.1f}" width="{bw-0.6:.1f}" height="{max(0.5, Y(ymin)-Y(v)):.1f}" fill="{col}" fill-opacity="0.85"/>')
    if series:
        for vals, col in series:
            seg, segs = [], []
            for i, v in enumerate(vals):
                if v is None:
                    if seg: segs.append(seg); seg = []
                else:
                    seg.append(f"{X(i):.1f},{Y(v):.1f}")
            if seg: segs.append(seg)
            for sg in segs:
                o.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" points="{" ".join(sg)}"/>')
            for i, v in enumerate(vals):
                if v is not None:
                    o.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="1.8" fill="{col}"/>')
    for i in sorted(set(list(range(0, n, 5)) + [n - 1])):
        o.append(f'<text x="{X(i):.1f}" y="{yb+12}" fill="#777" font-size="8" text-anchor="middle">{dates[i][5:]}</text>')
    for i, d in enumerate(dates):
        t = esc(tips[i]) if tips else d
        o.append(f'<rect class="hit" data-tip="{t}" x="{x0 + slot*i:.2f}" y="{yt}" width="{slot:.2f}" height="{yb-yt}" fill="transparent"><title>{t}</title></rect>')
    o.append("</svg>")
    return (f'<div class="mom-chart" style="padding:8px 8px 2px;"><div style="font-size:11px;font-weight:700;color:#ccc;margin:0 2px 4px;">{title_html}</div>'
            + "".join(o) + "</div>")

def key(col, label):
    return f'<span style="white-space:nowrap;font-weight:400;color:var(--text-muted);margin-left:8px;"><span style="display:inline-block;width:9px;height:3px;background:{col};vertical-align:middle;margin-right:3px;"></span>{label}</span>'

charts = []
if TD:
    dts = [d["date"] for d in TD]
    a20 = [d["a20"] / d["a20d"] * 100 if d["a20d"] else None for d in TD]
    a50 = [d["a50"] / d["a50d"] * 100 if d["a50d"] else None for d in TD]
    mom = [d["mom"] / d["n"] * 100 if d["n"] else None for d in TD]
    f1 = lambda v: "" if v is None else f"{v:.1f}%"
    tips1 = [f"{d}: above 20-day EMA {f1(a)} · above 50-day SMA {f1(b)} · momentum share {f1(m)}" for d, a, b, m in zip(dts, a20, a50, mom)]
    top1 = nice_top(max(v for v in a20 + a50 + mom if v is not None), 10)
    charts.append(mini_chart(dts, "% above MAs &amp; momentum share" + key("#42a5f5", "&gt; 20-day EMA") + key("#ff9800", "&gt; 50-day SMA") + key("#ce93d8", "Momentum"),
                             series=[(a20, "#42a5f5"), (a50, "#ff9800"), (mom, "#ce93d8")], ymin=0, ymax=top1, ystep=top1 / 4 if top1 % 4 == 0 else 10, tips=tips1))
    ups = [d["up"] for d in TD]; dns = [d["down"] for d in TD]
    tips2 = [f"{d}: Up 4% {u} · Down 4% {w} · universe {x['n']:,}" for d, u, w, x in zip(dts, ups, dns, TD)]
    top2 = nice_top(max(ups + dns), 50)
    charts.append(mini_chart(dts, "Up 4% vs Down 4% (count)" + key("#4caf50", "Up 4%") + key("#f44336", "Down 4%"),
                             bars=[(ups, "#4caf50"), (dns, "#f44336")], ymin=0, ymax=top2, ystep=50 if top2 <= 200 else 100, unit="", tips=tips2))
if PR:
    pd_ = [r["date"] for r in PR]
    def sp(r, a, cum):
        k = "_cum" if cum else ""
        return None if r.get(a + k) is None or r.get("SPY" + k) is None else (r[a + k] - r["SPY" + k]) * 100
    rc = [sp(r, "RSP", True) for r in PR]; ic = [sp(r, "IWM", True) for r in PR]
    rd = [sp(r, "RSP", False) for r in PR]; idd = [sp(r, "IWM", False) for r in PR]
    fp = lambda v: "" if v is None else f"{v:+.2f} pp"
    tips3 = [f"{d}: RSP−SPY {fp(a)} cumulative ({fp(b)} on the day) · IWM−SPY {fp(c)} cumulative ({fp(e)} on the day)" for d, a, b, c, e in zip(pd_, rc, rd, ic, idd)]
    vals = [v for v in rc + ic if v is not None] or [0]
    lo = min(0, int(math.floor(min(vals) / 2) * 2)); hi = max(0, int(math.ceil(max(vals) / 2) * 2))
    if hi - lo < 4: hi = lo + 4 if lo < 0 else 4
    stp = 2 if hi - lo <= 12 else 4
    lo = int(math.floor(lo / stp) * stp); hi = int(math.ceil(hi / stp) * stp)
    charts.append(mini_chart(pd_, f"Participation: cumulative spread vs SPY since {PS['base_date']} close (pp)" + key("#42a5f5", "RSP−SPY") + key("#ff9800", "IWM−SPY"),
                             series=[(rc, "#42a5f5"), (ic, "#ff9800")], ymin=lo, ymax=hi, ystep=stp, unit="", tips=tips3, zero=True))

def bv_item(label, key_, is_pct, higher_is_better=True):
    t = BV["today"].get(key_) if BV else None; b = BV["ref"].get(key_) if BV else None
    if t is None or b is None:
        return f'<span style="white-space:nowrap;">{label} <span class="na-val"></span></span>'
    d = t - b
    dz = abs(d) < 0.05 if is_pct else d == 0
    tv = f"{t:.1f}%" if is_pct else f"{t:,}"
    dv = (f"{d:+.1f} pp" if is_pct else f"{d:+,}").replace("-", "&minus;")
    if dz:
        mark = f'<span style="color:var(--text-muted);">&#9632; {dv}</span>'
    else:
        good = (d > 0) == higher_is_better
        mark = f'<span class="{"text-green" if good else "text-red"}">{"&#9650;" if good else "&#9660;"} {dv}</span>'
    return f'<span style="white-space:nowrap;">{label} <strong style="color:#ddd;">{tv}</strong> {mark}</span>'
cap = ""
if BV:
    cap = (f'<div style="display:flex;flex-wrap:wrap;gap:2px 16px;font-size:11px;color:var(--text-muted);margin-top:6px;"><span>{BV["date"]} vs {BV["ref_date"]} (5 sessions ago):</span>'
           + bv_item("&gt;20EMA", "a20", True) + bv_item("&gt;50SMA", "a50", True) + bv_item("Momentum", "mom", True)
           + bv_item("Up 4%", "up", False) + bv_item("Down 4%", "down", False, higher_is_better=False) + '</div>')
n1 = len(TD); n3 = len(PR)
trend_html = ('<div style="margin:0 0 20px 0;">'
              f'<div style="font-size:12px;font-weight:700;color:#ccc;margin-bottom:6px;">Breadth &amp; participation trend &#8212; last {n1} sessions{(" (" + TD[0]["date"] + " to " + TD[-1]["date"] + ")") if TD else ""}</div>'
              '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;">' + "".join(charts) + '</div>'
              + cap +
              '<div style="font-size:10px;color:var(--text-muted);margin-top:4px;line-height:1.45;">Source: Yahoo Finance daily bars. Breadth charts use the same universe and rules as the Section 7 table (20-day EMA, 50-day SMA, note-rule momentum share, &plusmn;4% vs prior close). '
              f'Participation is the cumulative spread over the window: each ETF&#39;s dividend-adjusted return since the {PS["base_date"]} close, minus SPY&#39;s, in percentage points (pp); below zero means RSP (Invesco S&amp;P 500 Equal Weight) or IWM has lagged SPY since then. Hover a day for values (the daily spread is in the hover). '
              '&#9650; green = breadth improving, &#9660; red = deteriorating (a higher Down 4% count is deteriorating).</div></div>')
if not TD and not PR:
    trend_html = '<div style="font-size:11px;color:var(--text-muted);margin:0 0 20px 0;">Breadth &amp; participation trend: no data this run.</div>'
TR_MARK = "<!-- ═══ BREADTH TRENDS (auto-injected) ═══ -->"
for mk in ("<!-- ═══ BREADTH vs 5 SESSIONS (auto-injected) ═══ -->", TR_MARK):
    h = re.sub(r"\n?" + re.escape(mk) + r"\n[^\n]*\n", "", h)  # drop blocks carried over from the template
anchor = '<div class="data-warning-banner"></div>\n'
assert h.count(anchor) == 1
h = h.replace(anchor, anchor + "\n" + TR_MARK + "\n" + trend_html + "\n", 1)
assert h.count(TR_MARK) == 1

# ---------- section 1 ----------
M = R["macro"]
def card(label, sub, key, fmt):
    m = M.get(key)
    if not m:
        return f'    <div class="macro-card">\n      <div class="mc-label">{label}</div><div class="mc-sub">{sub}</div>\n      <div class="mc-price"></div>\n      <div class="mc-chg"></div>\n    </div>'
    return (f'    <div class="macro-card">\n      <div class="mc-label">{label}</div><div class="mc-sub">{sub}</div>\n'
            f'      <div class="mc-price">{fmt(m["price"])}</div>\n      <div class="mc-chg {cls(m["chg"])}">{pct(m["chg"])}</div>\n    </div>')
cards = [card("VIX", "Fear Index", "VIX", lambda x: f"{x:.2f}"), card("DXY", "US Dollar", "DXY", lambda x: f"{x:.3f}"),
         card("10Y Yield", "TNX %", "TNX", lambda x: f"{x:.3f}"), card("Gold", "USD/oz", "GOLD", lambda x: f"{x:,.2f}"),
         card("WTI Oil", "USD/bbl", "OIL", lambda x: f"{x:.2f}"), card("Bitcoin", "USD", "BTC", lambda x: f"{x:,.0f}")]
btc = M.get("BTC")
s1 = ('<div class="section" id="s1-macro">\n  <div class="section-title">Section 1 — Macro Indicators</div>\n  <div class="macro-grid">\n'
      + "\n".join(cards) + "\n  </div>\n"
      f'  <p class="src-note" style="margin-top:8px;">Source: Yahoo Finance daily bars dated {SESSION}: ^VIX, DX-Y.NYB, ^TNX, GC=F (front-month gold futures), CL=F (front-month WTI futures). Change is versus the prior bar ({M["VIX"]["prev_date"] if M.get("VIX") else ""}). '
      + (f'Bitcoin is the BTC-USD {btc["date"]} UTC daily bar, still open when fetched at {META["fetched_hkt"]} HKT, versus the {btc["prev_date"]} UTC close.' if btc else "Bitcoin not found.")
      + "</p>\n</div>\n")
h = replace_section(h, '<div class="section" id="s1-macro">', s1)

# ---------- section 2 ----------
def fg_color(f):
    if f is None: return ""
    return "text-red" if f <= 25 else ("text-green" if f >= 75 else ("text-amber" if f <= 45 else "text-green"))
pc = META["pc"]
if fg:
    fg_ts = datetime.fromisoformat(fg["timestamp"]).astimezone(NY).strftime("%Y-%m-%d %H:%M ET")
    fgcard = (f'    <div class="sent-card">\n      <div class="sc-label">CNN Fear &amp; Greed Index</div>\n      <div class="sc-value {fg_color(fgs)}">{fgs:.0f}</div>\n'
              f'      <div class="sc-rating {fg_color(fgs)}">{esc(fg["rating"].title())}</div>\n      <table class="hist-table">\n'
              f'        <tr><td>Prev Close</td><td>{fg["previous_close"]:.2f}</td></tr>\n        <tr><td>1 Week Ago</td><td>{fg["previous_1_week"]:.2f}</td></tr>\n'
              f'        <tr><td>1 Month Ago</td><td>{fg["previous_1_month"]:.2f}</td></tr>\n        <tr><td>1 Year Ago</td><td>{fg["previous_1_year"]:.2f}</td></tr>\n'
              f'        <tr><td>As of</td><td>{fg_ts}</td></tr>\n        <tr><td>Source</td><td>CNN Fear &amp; Greed graphdata</td></tr>\n      </table>\n    </div>')
else:
    fgcard = '    <div class="sent-card">\n      <div class="sc-label">CNN Fear &amp; Greed Index</div>\n      <div class="sc-value"></div>\n      <div class="sc-rating">CNN not reached this run</div>\n    </div>'
if pc:
    v = pc["ratio"]; pcc = "text-red" if v > 1.0 else ("text-green" if v <= 0.8 else "text-amber")
    pcr = "Bearish (High Fear)" if v > 1.0 else ("Bullish (Low Fear)" if v <= 0.8 else "Neutral")
    pccard = (f'    <div class="sent-card">\n      <div class="sc-label">Put / Call Ratio</div>\n      <div class="sc-value {pcc}">{v:.2f}</div>\n      <div class="sc-rating {pcc}">{pcr}</div>\n'
              f'      <table class="hist-table">\n        <tr><td>Threshold</td><td>&gt;1.0 = Bearish</td></tr>\n        <tr><td>As of</td><td>{esc(pc["time_text"])}</td></tr>\n'
              f'        <tr><td>Calls / Puts</td><td>{pc["calls"]:,} / {pc["puts"]:,}</td></tr>\n        <tr><td>Source</td><td>Cboe equity put/call</td></tr>\n      </table>\n'
              '      <div style="margin-top:10px;font-size:10px;color:var(--text-muted);">High P/C = more puts = fear. Low P/C = complacency.</div>\n    </div>')
else:
    pccard = '    <div class="sent-card">\n      <div class="sc-label">Put / Call Ratio</div>\n      <div class="sc-value"></div>\n      <div class="sc-rating">Cboe equity put/call not found this run</div>\n    </div>'
s2 = ('<div class="section" id="s2-sentiment">\n  <div class="section-title">Section 2 — Market Sentiment</div>\n  <div class="sentiment-grid">\n\n'
      + fgcard + "\n\n" + pccard + "\n\n  </div>\n"
      + (f'  <p class="src-note" style="margin-top:8px;">Put/call is the official Cboe EQUITY PUT/CALL RATIO from Daily Market Statistics ({esc(pc["url"])}) for {esc(pc["page_date"])}, with that session equity-options call and put volume, as published by Cboe. Fear &amp; Greed from https://production.dataviz.cnn.io/index/fearandgreed/graphdata.</p>\n' if pc else "")
      + "</div>\n")
h = replace_section(h, '<div class="section" id="s2-sentiment">', s2)

# ---------- section 3 ----------
FV = R["finviz"]; DJ = R["dow"]
names = {"SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF", "DIA": "Dow Jones ETF", "IWM": "Russell 2000 ETF"}
adsrc = {"SPY": FV.get("idx_sp500"), "QQQ": FV.get("idx_ndx"), "IWM": FV.get("idx_rut"), "DIA": DJ}
rows = []
for s in ("SPY", "QQQ", "DIA", "IWM"):
    x = R["indices"][s]; a = adsrc[s] or {}
    up, dn = a.get("up"), a.get("down")
    if up is not None and dn:
        r = up / dn; adc = "text-green" if r >= 1.0 else ("text-red" if r < 0.8 else "text-amber")
        ad = f'<span class="{adc}">{r:.3f}</span><span style="font-size:10px;color:var(--text-muted)"> ({up}↑/{dn}↓)</span>'
    else:
        ad = ""
    rows.append(f'        <tr class=""><td><div class="sym-cell"><span class="sym">{s}</span><span class="sym-name">{esc(names[s])}</span></div></td><td>{x["close"]:.2f}</td><td>{pill(x["chg"])}</td><td>{rsi_cell(x["rsi"])}</td>'
                f'<td class="{cls(x["vs20"])}">{pct(x["vs20"])}</td><td class="{cls(x["vs50"])}">{pct(x["vs50"])}</td><td class="{cls(x["vs200"])}">{pct(x["vs200"])}</td><td>{ad}</td></tr>')
PA = R.get("participation") or {}
pc_ = PA.get("chg") or {}
def pa_cell(label, x, spread=False):
    if x is None:
        v = '<span class="na-val"></span>'
    else:
        num = (f"{x*100:+.2f} pp" if spread else pct(x)).replace("-", "&minus;")
        v = f'<strong class="{cls(x)}">{num}</strong>'
    return f'<span style="white-space:nowrap;"><span style="color:var(--text-muted);">{label}</span> {v}</span>'
part = ('  <div style="background:var(--bg-card2);border:1px solid var(--border);border-radius:8px;padding:8px 14px;margin-bottom:10px;font-size:12px;">\n'
        '    <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 22px;"><span style="font-size:11px;font-weight:700;color:#ccc;">Participation (1D)</span>'
        + pa_cell("SPY", pc_.get("SPY")) + pa_cell("RSP (equal weight)", pc_.get("RSP")) + pa_cell("IWM", pc_.get("IWM"))
        + pa_cell("RSP &minus; SPY", PA.get("rsp_minus_spy"), True) + pa_cell("IWM &minus; SPY", PA.get("iwm_minus_spy"), True) + '</div>\n'
        f'    <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Source: Yahoo Finance daily bars, session {SESSION}; RSP is the Invesco S&amp;P 500 Equal Weight ETF. 1-day change uses dividend-adjusted closes, same basis as the 1D Chg% column below. Spreads are percentage points (pp); negative means the equal-weight or small-cap ETF lagged SPY.</div>\n  </div>\n')
s3 = ('<div class="section" id="s3-indices">\n  <div class="section-title">Section 3 — Major Indices</div>\n' + part + '  <div class="table-wrap">\n    <table class="data-table">\n      <thead>\n        <tr>\n'
      '          <th>Symbol</th>\n          <th>Price</th>\n          <th class="hide-on-mobile">1D Chg%</th>\n          <th class="hide-on-mobile">RSI 14</th>\n'
      '          <th class="hide-on-mobile">vs 20MA</th>\n          <th class="hide-on-mobile">vs 50MA</th>\n          <th class="hide-on-mobile">vs 200MA</th>\n          <th>A/D Ratio</th>\n        </tr>\n      </thead>\n      <tbody>\n'
      + "\n".join(rows) + "\n      </tbody>\n    </table>\n  </div>\n"
      f'  <p class="src-note" style="margin-top:8px;">Source: Yahoo Finance daily bars, session {SESSION}. Price is the close. 1D change, Wilder RSI 14, and the 20/50/200-day simple averages use dividend-adjusted closes. A/D counts index members up versus down on the day: Finviz screener (idx_sp500, idx_ndx, idx_rut) read {META["finviz_hkt"]} HKT; Dow 30 from Yahoo daily bars of the 30 DIA holdings (State Street file {META.get("dia_asof", "")}).</p>\n</div>\n')
h = replace_section(h, '<div class="section" id="s3-indices">', s3)

# ---------- section 4 ----------
def brow(label, total, a20, a50, a200, tag, src):
    p = lambda a: (a / total * 100) if (a is not None and total) else None
    return (f'        <tr><td><strong>{label}</strong></td><td>{total:,}</td><td>{pct_bar(p(a20))}</td><td>{pct_bar(p(a50))}</td><td>{pct_bar(p(a200))}</td>'
            f'<td><strong>{tag}</strong><br><span style="font-size:10px;color:var(--text-muted)">{src}</span></td></tr>') if total else \
           f'        <tr><td><strong>{label}</strong></td><td></td><td></td><td></td><td></td><td><strong>{tag}</strong><br><span style="font-size:10px;color:var(--text-muted)">{src} not found</span></td></tr>'
b4 = []
for lab, key, tag in (("S&amp;P 500", "idx_sp500", "SPY"), ("NASDAQ 100", "idx_ndx", "QQQ")):
    f = FV.get(key) or {}
    b4.append(brow(lab, f.get("total"), f.get("a20"), f.get("a50"), f.get("a200"), tag, f"Finviz {key}"))
b4.append(brow("Dow Jones 30", DJ["total"], DJ["a20"], DJ["a50"], DJ["a200"], "DIA", "Yahoo, DIA holdings"))
f = FV.get("idx_rut") or {}
b4.append(brow("Russell 2000", f.get("total"), f.get("a20"), f.get("a50"), f.get("a200"), "IWM", "Finviz idx_rut"))
sb_b64 = base64.b64encode(open(os.path.join(RUN, "stockbee_mm.png"), "rb").read()).decode() if os.path.exists(os.path.join(RUN, "stockbee_mm.png")) else None
s4 = ('<div class="section" id="s4-breadth">\n  <div class="section-title">Section 4 — Market Breadth</div>\n  <div class="sub-title">4A — % of Index Constituents Above Moving Averages</div>\n'
      f'  <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">Source: Finviz screener (index-filtered, price above the 20/50/200-day simple average), read {META["finviz_hkt"]} HKT after the {SESSION} close. Dow 30: Yahoo Finance daily closes of the 30 DIA holdings, close above the simple average.</div>\n'
      '  <div class="table-wrap">\n    <table class="data-table">\n      <thead>\n        <tr>\n          <th>Symbol</th>\n          <th>Total</th>\n          <th>% &gt; 20MA</th>\n'
      '          <th class="hide-on-mobile">% &gt; 50MA</th>\n          <th class="hide-on-mobile">% &gt; 200MA</th>\n          <th>A/D Ratio</th>\n        </tr>\n      </thead>\n      <tbody>\n'
      + "\n".join(b4) + "\n      </tbody>\n    </table>\n  </div>\n\n"
      '  <!-- 4C: Stockbee Market Monitor -->\n  <div class="sub-title" style="margin-top:20px;">4C — Stockbee Market Monitor</div>\n  <div class="img-block">\n'
      + (f'    <img src="data:image/png;base64,{sb_b64}" alt="Stockbee Market Monitor" />\n    <div class="img-caption">Stockbee Market Monitor. Public Google Sheet (docs.google.com/spreadsheets/d/1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE, published view), captured {META["stockbee_hkt"]} HKT without a login. {esc(META["stockbee_note"])}</div>\n'
         if sb_b64 else '    <div class="img-caption">Stockbee sheet not captured this run.</div>\n')
      + '  </div>\n\n</div>\n')
h = replace_section(h, '<div class="section" id="s4-breadth">', s4)

# ---------- section 5 ----------
srows = []
for x in R["sectors"]:
    srows.append(f'        <tr>\n            <td><strong>{x["sym"]}</strong></td>\n            <td>{pill(x["chg"])}</td>\n'
                 f'            <td class="hide-on-mobile {cls(x["vs20"])}">{pct(x["vs20"])}</td>\n            <td class="hide-on-mobile {cls(x["vs50"])}">{pct(x["vs50"])}</td>\n'
                 f'            <td class="hide-on-mobile {cls(x["vs200"])}">{pct(x["vs200"])}</td>\n            <td>{rsi_cell(x["rsi"])}</td>\n        </tr>')
s5 = ('<div class="section" id="s5-core-etf">\n  <div class="section-title">Section 5 — Core Sector ETF (rank by RSI 14)</div>\n  <div class="table-wrap">\n    <table class="data-table">\n      <thead>\n        <tr>\n'
      '          <th>Symbol</th>\n          <th>1D Change%</th>\n          <th class="hide-on-mobile">vs 20MA</th>\n          <th class="hide-on-mobile">vs 50MA</th>\n          <th class="hide-on-mobile">vs 200MA</th>\n          <th>RSI 14</th>\n        </tr>\n      </thead>\n      <tbody>\n'
      f'        <tr><td colspan="6" style="font-size:11px;color:var(--text-muted);">Source: Yahoo Finance chart API, adjusted daily close, session {SESSION}. Simple 20/50/200-day averages, Wilder RSI 14.</td></tr>\n\n'
      + "\n\n".join(srows) + "\n      </tbody>\n    </table>\n  </div>\n</div>\n")
h = replace_section(h, '<div class="section" id="s5-core-etf">', s5)

# ---------- section 7 ----------
D = R["daily"]; last = D[-1]
share = last["mom"] / last["n"]
trow = []
for d in reversed(D[-20:]):
    trow.append(f'        <tr><td>{d["date"]}</td><td>{d["up"]}</td><td>{d["down"]}</td><td>{d["a20"]/d["a20d"]*100:.1f}%</td><td>{d["a50"]/d["a50d"]*100:.1f}%</td><td>{d["mom"]/d["n"]*100:.1f}%</td><td>{d["n"]:,}</td></tr>')

def line_chart(dates, vals):
    x0, y0, x1, y1 = 40, 10, 750, 196
    import math
    top = max(5, int(math.ceil(max(vals) / 5) * 5))
    ybot, ytop = 184.0, 16.0
    Y = lambda v: ybot - (v / top) * (ybot - ytop)
    X = lambda i: x0 + (x1 - x0) * i / (len(vals) - 1)
    out = [f'    <svg class="hover-chart" data-plot="{x0},{y0},{x1},{y1}" viewBox="0 0 760 252" xmlns="http://www.w3.org/2000/svg">']
    for g in range(0, top + 1, 5):
        out.append(f'      <line x1="40" y1="{Y(g):.1f}" x2="750" y2="{Y(g):.1f}" stroke="#2a2a2a" stroke-width="1"/><text x="34" y="{Y(g)+3:.1f}" fill="#777" font-size="9" text-anchor="end">{g}%</text>')
    out.append('      <polyline fill="none" stroke="#42a5f5" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="' + " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals)) + '"/>')
    for i, (d, v) in enumerate(zip(dates, vals)):
        out.append(f'      <circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.5" fill="#42a5f5" data-tip="{d}: {v:.1f}%"><title>{d}: {v:.1f}%</title></circle>')
    for i in list(range(0, len(vals), 8)) + ([len(vals) - 1] if (len(vals) - 1) % 8 else []):
        out.append(f'      <text x="{X(i):.1f}" y="214" fill="#777" font-size="8" text-anchor="end" transform="rotate(-50 {X(i):.1f} 214)">{dates[i][5:]}</text>')
    out.append("    </svg>")
    return "\n".join(out)

dates = [d["date"] for d in D]
mshare = [d["mom"] / d["n"] * 100 for d in D]
chart1 = line_chart(dates, mshare)

inds = R["industries"]; shown_sum = sum(r["mom"] for r in inds); mx = max(r["mom"] for r in inds) if inds else 1
irows, trows2 = [], []
for r in inds:
    sh = r["mom"] / shown_sum * 100
    irows.append(f'        <tr><td class="wrap">{esc(r["industry"])}</td><td><div class="mom-bar" title="{sh:.1f}% of momentum shown"><span style="width:{r["mom"]/mx*100:.2f}%"></span></div></td><td>{r["mom"]}</td><td>{sh:.1f}%</td><td>{r["pen"]*100:.1f}%</td><td class="{"up" if r["excess"] > 0 else "down"}">{r["excess"]*100:+.1f}%</td></tr>')
    trows2.append(f'        <tr><td>{esc(r["industry"])}</td><td>{r["mom"]}</td><td>{sh:.1f}%</td></tr>')

EX = R["excess_top5"]; colors = ["#42a5f5", "#4caf50", "#ff9800", "#ce93d8", "#f44336"]
allv = [v for s in EX["series"].values() for v in s if v is not None]
import math
lo = min(-20, int(math.floor(min(allv) / 20) * 20))
hi = max(20, int(math.ceil(max(allv) / 20) * 20))
def excess_chart():
    x0, x1, yt, yb = 48, 748, 29.2, 188.0
    Y = lambda v: yb - (v - lo) / (hi - lo) * (yb - yt)
    n = len(EX["dates"]); X = lambda i: x0 + (x1 - x0) * i / (n - 1)
    o = ['  <svg class="hover-chart" data-plot="48,22,748,196" viewBox="0 0 760 %d" xmlns="http://www.w3.org/2000/svg">' % (228 + 16 * len(EX["industries"]) + 10)]
    for g in range(lo, hi + 1, 20):
        o.append(f'  <line x1="48" y1="{Y(g):.1f}" x2="748" y2="{Y(g):.1f}" stroke="{"#555555" if g == 0 else "#2a2a2a"}" stroke-width="{1.2 if g == 0 else 1}"/>')
        o.append(f'  <text x="42" y="{Y(g)+3:.1f}" fill="#777" font-size="9" text-anchor="end">{("+" if g > 0 else "") + str(g)}</text>')
    for i in list(range(0, n, 8)) + ([n - 1] if (n - 1) % 8 else []):
        o.append(f'  <text x="{X(i):.1f}" y="206" fill="#777" font-size="8" text-anchor="middle">{EX["dates"][i][5:]}</text>')
    for k, ind in enumerate(EX["industries"]):
        s = EX["series"][ind]; c = colors[k]
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(s) if v is not None)
        o.append(f'  <polyline fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>')
        for i, v in enumerate(s):
            if v is None: continue
            t = f"{esc(ind)}. {EX['dates'][i]} excess {v:+.1f} percentage points."
            o.append(f'  <circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.2" fill="{c}" data-tip="{t}"><title>{t}</title></circle>')
        ly = 228 + 16 * k
        lastv = s[-1]
        o.append(f'  <line x1="48" y1="{ly}" x2="68" y2="{ly}" stroke="{c}" stroke-width="2.4"/>')
        o.append(f'  <text x="76" y="{ly+3}" fill="#cccccc" font-size="11">{esc(ind)} ({lastv:+.1f} pp on {SESSION})</text>')
    o.append("  </svg>")
    return "\n".join(o)
chart2 = excess_chart()

# 10-year chart
T = json.load(open(META["ten_year_monthend"]))
ap = json.load(open(META["ten_year_appended"]))
st = T["stats"]
series = [(r["date"], r["share"], True) for r in T["rows"]] + [(r["date"], r["share"], False) for r in ap if r["date"] > T["rows"][-1]["date"]]
def ten_chart():
    x0, x1, yb, yt = 54.0, 858.88, 440.0, 28.0
    ymax = 60 if max(s for _, s, _ in series) * 100 <= 60 else int(-(-max(s for _, s, _ in series) * 100 // 10) * 10)
    Y = lambda v: yb - v * 100 / ymax * (yb - 53.75) if ymax == 60 else yb - v * 100 / ymax * (yb - 53.75)
    n = len(series); dx = (x1 - x0) / (n - 1); X = lambda i: x0 + dx * i
    o = [f'<svg class="hover-chart" viewBox="0 0 1040 486" width="100%" role="img" aria-label="Momentum share, month-ends {series[0][0][:7]} through {T["rows"][-1]["date"][:7]}, extended through {series[-1][0]}">',
         '<defs>\n<linearGradient id="shareFill" x1="0" y1="0" x2="0" y2="1">\n<stop offset="0%" stop-color="#9ad0ff" stop-opacity="0.42"/>\n<stop offset="100%" stop-color="#9ad0ff" stop-opacity="0.03"/>\n</linearGradient>\n</defs>',
         '<rect x="0" y="0" width="1040" height="486" fill="#0e1116"/>']
    for g in range(0, ymax + 1, 10):
        y = Y(g / 100)
        o.append(f'<line x1="54" y1="{y:.2f}" x2="858.88" y2="{y:.2f}" stroke="#2a3140" stroke-width="1"/>')
        o.append(f'<text x="46" y="{y+4:.2f}" text-anchor="end" fill="#9aa3b2" font-size="11">{g}%</text>')
    seen = set()
    for i, (d, s, _) in enumerate(series):
        yr = d[:4]
        if yr not in seen:
            seen.add(yr)
            o.append(f'<line x1="{X(i):.2f}" y1="440" x2="{X(i):.2f}" y2="445" stroke="#5c677a"/>')
            o.append(f'<text x="{X(i):.2f}" y="458" text-anchor="middle" fill="#9aa3b2" font-size="11">{yr}</text>')
    plines = [("5th", st["p5"]), ("10th", st["p10"]), ("50th", st["median"]), ("90th", st["p90"]), ("95th", st["p95"])]
    for _, v in plines:
        o.append(f'<line x1="54" y1="{Y(v):.2f}" x2="858.88" y2="{Y(v):.2f}" stroke="#8b93a7" stroke-width="1" stroke-dasharray="4 4"/>')
    pts = " ".join(f"L {X(i):.2f} {Y(s):.2f}" for i, (_, s, _) in enumerate(series))
    o.append(f'<path d="M 54.00 440.00 {pts} L {X(n-1):.2f} 440.00 Z" fill="url(#shareFill)"/>')
    o.append(f'<path d="M {pts[2:]}" fill="none" stroke="#9ad0ff" stroke-width="1.8" stroke-linejoin="round"/>')
    for i, (d, s, me) in enumerate(series):
        if s < st["p5"]:
            o.append(f'<rect x="{X(i)-dx/2:.2f}" y="28" width="{dx:.2f}" height="412" fill="#ffb4a8" fill-opacity="0.13"/>')
            o.append(f'<circle cx="{X(i):.2f}" cy="{Y(s):.2f}" r="3.6" fill="#ffb4a8" stroke="#0e1116" stroke-width="1"/>')
    hi_i = max(range(n), key=lambda i: series[i][1])
    for i in (hi_i, n - 1):
        o.append(f'<circle cx="{X(i):.2f}" cy="{Y(series[i][1]):.2f}" r="3.2" fill="#e6e8eb" stroke="#0e1116" stroke-width="1"/>')
    # percentile labels in the right margin, nudged apart
    ys = []
    for lab, v in plines:
        y = Y(v)
        ys.append([lab, v, y])
    ys.sort(key=lambda r: -r[2])
    for k in range(1, len(ys)):
        if ys[k - 1][2] - ys[k][2] < 17: ys[k][2] = ys[k - 1][2] - 17
    for lab, v, y in ys:
        txt = f"{lab}  {v*100:.2f}%"
        o.append(f'<rect x="866" y="{y-12:.1f}" width="{len(txt)*6.2+6:.1f}" height="16.0" rx="3" fill="#0e1116" fill-opacity="0.88"/>')
        o.append(f'<text x="869" y="{y:.1f}" fill="#c5cad3" font-size="11">{txt}</text>')
    hx, hy = X(hi_i), Y(series[hi_i][1])
    o.append(f'<line x1="{hx:.2f}" y1="{hy:.2f}" x2="{hx+16:.1f}" y2="{hy-6:.1f}" stroke="#5c677a" stroke-width="1"/>')
    o.append(f'<rect x="{hx+4:.1f}" y="{hy-40:.1f}" width="131.0" height="34.0" rx="3" fill="#1b2230" stroke="#3a4558"/>')
    o.append(f'<text x="{hx+8:.1f}" y="{hy-27:.1f}" fill="#e6e8eb" font-size="12">{series[hi_i][0]}  {series[hi_i][1]*100:.2f}%</text>')
    o.append(f'<text x="{hx+8:.1f}" y="{hy-12:.1f}" fill="#e6e8eb" font-size="12">highest</text>')
    lx, ly = X(n - 1), Y(series[-1][1])
    o.append(f'<line x1="{lx:.2f}" y1="{ly:.2f}" x2="{lx-20:.1f}" y2="70" stroke="#5c677a" stroke-width="1"/>')
    o.append(f'<rect x="{lx-150:.1f}" y="36" width="140.0" height="34.0" rx="3" fill="#1b2230" stroke="#3a4558"/>')
    o.append(f'<text x="{lx-146:.1f}" y="49" fill="#e6e8eb" font-size="12">{series[-1][0]}  {series[-1][1]*100:.2f}%</text>')
    o.append(f'<text x="{lx-146:.1f}" y="64" fill="#e6e8eb" font-size="12">latest session</text>')
    for i, (d, s, me) in enumerate(series):
        t = f"{d}  {s*100:.2f}%" + ("  ·  strictly below the 5th percentile" if s < st["p5"] else "") + ("" if me else "  ·  daily point after the last month-end")
        o.append(f'<rect class="hit" data-tip="{t}" x="{X(i)-dx/2:.2f}" y="28" width="{dx:.2f}" height="412" fill="transparent"><title>{t}</title></rect>')
    o.append("</svg>")
    return "\n".join(o)
chart3 = ten_chart()
L10 = R["ten_year_latest"]
extra_pts = [r for r in ap if r["date"] > T["rows"][-1]["date"]]
ext_txt = ", ".join(f'{r["date"]} (universe {r["universe"]:,}, momentum {r["momentum"]}, share {r["share"]*100:.2f}%)' for r in extra_pts)

upct = lambda a, b: f"{a/b*100:.1f}%"
s7 = f'''<div class="section" id="s7-momentum-breadth">
  <div class="section-title">Section 7 — Momentum Stock Breadth</div>
  <p class="src-note">Momentum stock: close at least 1.20 times the close from 63 SPY sessions earlier. Universe on the session: common stocks, ordinary shares, and ADRs listed on US exchanges (NASDAQ screener filters; includes foreign-registered issuers; no ETFs, funds, warrants, units, or preferred), close at least $5, volume at least 300,000, and dollar volume (close times volume) at least $5,000,000. A name with no bar on the earlier session stays in the universe and is not counted as momentum. Share is momentum count divided by that day's universe. Source: Yahoo Finance prices; NASDAQ screener for the name list and industry names.</p>
  <div class="table-wrap">
    <table class="data-table">
      <thead><tr><th>Date</th><th>Up 4%</th><th>Down 4%</th><th>% above 20-day</th><th>% above 50-day</th><th>Momentum share</th><th>Universe</th></tr></thead>
      <tbody>
{chr(10).join(trow)}
      </tbody>
    </table>
  </div>
  <p class="src-note" style="margin-top:8px;">Yahoo Finance daily bars (one year of history fetched {META["fetched_hkt"]} HKT), same rules each session. Universe each day: common stocks, ordinary shares, and ADRs listed on US exchanges (including foreign-registered issuers), no ETFs, close at least $5, volume at least 300,000, dollar volume at least $5,000,000. Up/down 4% versus the prior close; above 20-day is the 20-day EMA and above 50-day is the 50-day SMA (breadth only; not part of the momentum gate). Momentum share uses the note-rule definition above. The name list is today's NASDAQ screener (NASDAQ, NYSE, NYSE American; {META["universe_names"]:,} common stocks, ordinary shares, and ADRs after filters, including foreign-registered issuers), applied to every session. Yahoo only carries names that still trade, so delisted names are missing from every session shown.</p>
  <div class="sub-title">Momentum share</div>
  <div class="mom-chart" role="img" aria-label="Momentum share line chart, {len(D)} Yahoo Finance sessions from {D[0]["date"]} to {SESSION}, newest on the right">
{chart1}
  </div>
  <p class="src-note" style="margin-top:8px;">Momentum share over {len(D)} Yahoo Finance sessions from {D[0]["date"]} through {SESSION}. Newest on the right. The latest 20 sessions match the table above. Every session was computed this run with the same rules and the momentum definition in this section. Hover a point for the date and the share.</p>
  <div class="sub-title">Industry composition</div>
  <p class="src-note">NASDAQ screener industry names, Yahoo Finance prices, session {SESSION}. Industries with fewer than 5 momentum names are omitted. Shown counts sum to {shown_sum}; the full momentum tape is {last["mom"]} of {last["n"]:,} ({share*100:.1f}%). Share of momentum is of the names still shown; pool share is that industry's momentum names divided by its names in the universe; excess is pool share minus the universe momentum share. The bar is scaled so the largest count fills the track.</p>
  <div class="table-wrap">
    <table class="data-table">
      <thead><tr><th>Industry</th><th aria-label="Share of momentum"></th><th>Count</th><th>Share of momentum</th><th>Pool share</th><th>Excess</th></tr></thead>
      <tbody>
{chr(10).join(irows)}
      </tbody>
    </table>
  </div>
  <div class="sub-title">Top industries</div>
  <p class="src-note">The same NASDAQ screener industries still shown above (momentum count at least 5). Shown counts sum to {shown_sum}. The full momentum tape is {last["mom"]}; industries under 5 are omitted. Share is of the names still shown.</p>
  <div class="table-wrap">
    <table class="data-table">
      <thead><tr><th>Industry</th><th>Momentum count</th><th>Share</th></tr></thead>
      <tbody>
{chr(10).join(trows2)}
      </tbody>
    </table>
  </div>
  <div class="sub-title">Excess trend, top 5 industries</div>
  <p class="src-note">Excess is that industry's momentum penetration minus the universe momentum share, the same definition as the table. The five NASDAQ screener industries with the most momentum names on {SESSION} (ties by name). Same momentum rule each session, Yahoo Finance daily bars. {len(D)} sessions from {D[0]["date"]} through {SESSION}. Newest on the right. Hover a point for the industry, date, and excess.</p>
  <div class="mom-chart" role="img" aria-label="Excess trend for the five industries with the most momentum names on {SESSION}, {len(D)} sessions from {D[0]["date"]} to {SESSION}, newest on the right">
{chart2}
  </div>
  <div class="sub-title">10-year momentum share</div>
  <p class="src-note">Same momentum definition as the rest of this section (note rule): common stocks, ordinary shares, and ADRs listed on US exchanges (including foreign-registered issuers), no ETFs; universe requires close at least $5, volume at least 300,000, and dollar volume at least $5,000,000; momentum means close at least 1.20 times the close 63 SPY sessions earlier. A name with no bar on that earlier session stays in the universe and is not counted as momentum. Share is momentum count divided by that day's universe. The 10-year series was restated on 2026-11-27 under this same US-listed universe, including ordinary shares of foreign-registered issuers. Points are month-ends from {T["rows"][0]["date"]} through {T["rows"][-1]["date"]}, then each later session as it closes: {ext_txt}. Dashed lines are from this restated {len(T["rows"])} month-end Yahoo sample: 5th {st["p5"]*100:.2f}%, 10th {st["p10"]*100:.2f}%, median {st["median"]*100:.2f}%, 90th {st["p90"]*100:.2f}%, 95th {st["p95"]*100:.2f}%. Yahoo has no delisted names, so the history since 2017 has survivorship bias. Hover a column for the date and the share.</p>
  <div class="mom-chart">
{chart3}
  </div>
</div>
'''
h = replace_section(h, '<div class="section" id="s7-momentum-breadth">', s7)

# ---------- archive ----------
files = sorted([f for f in os.listdir(ARCH) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", f)] + [f"{SESSION}.html"])
files = sorted(set(files))[-7:][::-1]
links = "".join(f'<a href="archive/{f}" style="display:inline-block;padding:6px 14px;background:var(--bg-card2);border:1px solid var(--border);border-radius:5px;color:var(--blue);text-decoration:none;font-size:12px;">{f[:-5]}</a>' for f in files)
arch = ('<div class="section" style="border-top:2px solid var(--border);margin-top:24px;">\n  <div class="section-title" style="color:var(--blue);">&#128196; History Archive</div>\n'
        f'  <p style="color:var(--text-muted);font-size:12px;margin-bottom:4px;">\n    Last {len(files)} archived report(s) — each file is fully self-contained with Base64-embedded images.\n  </p>\n'
        f'  <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;">{links}</div>\n</div>\n\n')
h = replace_section(h, '<div class="section" style="border-top:2px solid var(--border);margin-top:24px;">', arch, stop="<!-- FOOTER -->")

# ---------- footer ----------
h = re.sub(r'(<div class="report-footer">).*?(</div>)', lambda m: m.group(1) + f'\n  Momentum Swing Trading Coach &nbsp;|&nbsp;\n  Data: Yahoo Finance &middot; CNN &middot; Cboe &middot; Finviz &middot; NASDAQ screener &middot; Stockbee public sheet &nbsp;|&nbsp;\n  US session {SESSION} &nbsp;|&nbsp; built {hkt} HKT &nbsp;/&nbsp; {et} ET<br/>\n  For informational purposes only. Not financial advice.\n' + m.group(2), h, count=1, flags=re.S)

assert "{{" not in h
open(OUT, "w", encoding="utf-8").write(h)
print("wrote", OUT, len(h))
