#!/usr/bin/env python3
"""
Build market-monitor.html = today's index.html (all existing sections kept)
+ new Kelileo-style sections (Section 8 onward) inserted before History Archive.
"""
import html
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SRC = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "market-monitor.html")
HIST = os.path.join(ROOT, "data", "monitor", "breadth_history.csv")
LATEST = os.path.join(ROOT, "data", "monitor", "latest.json")

TABLE_DAYS = 40
PULSE_DAYS = 40

CSS = """
<style>
.mm-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:14px}
.mm-card{background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:10px 12px}
.mm-card .k{font-size:10px;color:var(--text-muted);letter-spacing:.6px;text-transform:uppercase}
.mm-card .v{font-size:22px;font-weight:700;color:#fff;margin-top:2px}
.mm-card .s{font-size:11px;color:var(--text-muted)}
.mm-t{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}
.mm-t th{background:var(--bg-head);color:var(--text-label);font-weight:600;font-size:10px;padding:6px 8px;text-align:right;border-bottom:1px solid var(--border);white-space:nowrap}
.mm-t th:first-child,.mm-t td:first-child{text-align:left}
.mm-t td{padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-lt);white-space:nowrap}
.mm-daily tr:first-child td{font-weight:700}
.g2{background:#1b5e20;color:#fff}.g1{background:rgba(76,175,80,.22)}
.r2{background:#8e1b1b;color:#fff}.r1{background:rgba(244,67,54,.22)}
.mm-note{font-size:11px;color:var(--text-muted);line-height:1.6;margin:8px 0}
.mm-box{background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:10px 14px;margin:10px 0;font-size:12px;line-height:1.7;color:var(--text-label)}
.mm-legend span{display:inline-block;margin:0 10px 4px 0;font-size:10px;color:var(--text-muted)}
.mm-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.mm-wrap{overflow-x:auto}
.mm-readout{background:var(--bg-card);border:1px solid var(--amber);border-radius:8px;padding:12px 14px;margin:0 0 18px 0}
.mm-rt{font-size:13px;font-weight:700;color:#fff;margin-bottom:8px}
.mm-rl{display:flex;gap:10px;font-size:13px;line-height:1.6;color:var(--text-label);padding:5px 0;border-top:1px solid var(--border-lt)}
.mm-rl>span{flex:0 0 36px;font-weight:700;color:var(--amber)}
.mm-rn{font-size:10px;color:var(--text-muted);line-height:1.5;margin-top:8px}
.a1{background:rgba(255,193,7,.22)}
.mm-tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:3px;background:var(--amber-bg);color:var(--amber);margin-left:6px;vertical-align:2px}
</style>
"""


def esc(s):
    return html.escape(str(s))


def f(v, nd=1, sign=False, pct=False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    s = f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"
    return s + ("%" if pct else "")


def ddmm(d):
    d = pd.Timestamp(d)
    return d.strftime("%d/%m")


def section(num, title, body, sid):
    return (f'\n<div class="section" id="{sid}">\n'
            f'  <div class="section-title">Section {num} — {esc(title)}<span class="mm-tag">NEW · preview</span></div>\n'
            f'{body}\n</div>\n')


# --------------------------------------------------------------------------
def breadth_section(h, pcts, latest):
    last = h.iloc[-1]
    prev = h.iloc[-2] if len(h) > 1 else last
    cards = f"""
<div class="mm-cards">
 <div class="mm-card"><div class="k">Up 4% / Down 4%</div><div class="v"><span class="text-green">{int(last.up4)}</span> / <span class="text-red">{int(last.dn4)}</span></div><div class="s">10 日比率 {f(last.ratio10,2)}</div></div>
 <div class="mm-card"><div class="k">% 高過 20 日 EMA</div><div class="v">{f(last.pct20)}</div><div class="s">前一日 {f(prev.pct20)}（{f(last.pct20-prev.pct20,1,True)}）</div></div>
 <div class="mm-card"><div class="k">% 高過 50 日 SMA</div><div class="v">{f(last.pct50)}</div><div class="s">前一日 {f(prev.pct50)}（{f(last.pct50-prev.pct50,1,True)}）</div></div>
 <div class="mm-card"><div class="k">動力股比例</div><div class="v">{f(last.mom_pct,1,pct=True)}</div><div class="s">{int(last.mom_n)} 隻 · 前一日 {f(prev.mom_pct,1,pct=True)}（{f(last.mom_pct-prev.mom_pct,1,True)}）</div></div>
</div>"""

    rows = []
    t = h.iloc[::-1].head(TABLE_DAYS)
    for d, r in t.iterrows():
        cu = "g2" if r.up4 >= 300 else ("g1" if r.up4 > r.dn4 else "")
        cd = "r2" if r.dn4 >= 300 else ("r1" if r.dn4 > r.up4 else "")
        cr = "r2" if (r.ratio10 == r.ratio10 and r.ratio10 < 1) else ""
        c20 = "g2" if r.pct20 <= 10 else ("g1" if r.pct20 <= 30 else ("r2" if r.pct20 >= 90 else ("r1" if r.pct20 >= 70 else "")))
        c50 = "g2" if r.pct50 <= 20 else ("g1" if r.pct50 <= 30 else ("r2" if r.pct50 >= 80 else ("r1" if r.pct50 >= 70 else "")))
        def atrc(v):
            if v != v:
                return ""
            return "r2" if v >= 5 else ("g2" if v <= -5 else "")
        m = r.mom_pct
        cm = ("r2" if m <= pcts["p5"] else "r1" if m <= pcts["p10"] else
              "g2" if m >= pcts["p95"] else "g1" if m >= pcts["p90"] else "")
        rows.append(
            f"<tr><td>{ddmm(d)}</td><td class='{cu}'>{int(r.up4)}</td><td class='{cd}'>{int(r.dn4)}</td>"
            f"<td class='{cr}'>{f(r.ratio10,2)}</td><td class='{c20}'>{f(r.pct20)}</td><td class='{c50}'>{f(r.pct50)}</td>"
            f"<td class='{atrc(r.spy_atr)}'>{f(r.spy_atr,2,True)}</td><td class='{atrc(r.qqq_atr)}'>{f(r.qqq_atr,2,True)}</td>"
            f"<td class='{cm}'>{f(m)}</td><td>{int(r.mom_n)}</td><td>{int(r.universe):,}</td>"
            f"<td>{f(r.sp500,2) if r.sp500 == r.sp500 else '—'}</td></tr>")
    table = f"""
<div class="mm-wrap"><table class="mm-t mm-daily">
<thead><tr><th>日期</th><th>Up 4%</th><th>Dn 4%</th><th>10 日比率</th><th>% &gt; 20EMA</th><th>% &gt; 50SMA</th>
<th>SPY ATR</th><th>QQQ ATR</th><th>動力股 %</th><th>動力股</th><th>股票總數</th><th>S&amp;P 500</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<div class="mm-legend" style="margin-top:8px">
<span><i class="g2"></i>Up 4% ≥ 300</span><span><i class="r2"></i>Dn 4% ≥ 300 / 10 日比率 &lt; 1</span>
<span><i class="g2"></i>% 線上極低（20 日 ≤10・50 日 ≤20）</span><span><i class="r2"></i>% 線上極高（20 日 ≥90・50 日 ≥80）</span>
<span><i class="r2"></i>ATR ≥ +5 過度伸展</span><span><i class="g2"></i>ATR ≤ −5 過度超賣</span>
<span><i class="r2"></i>動力股 ≤ 第 5 百分位（{f(pcts['p5'])}%）</span><span><i class="r1"></i>≤ 第 10（{f(pcts['p10'])}%）</span>
<span><i class="g1"></i>≥ 第 90（{f(pcts['p90'])}%）</span><span><i class="g2"></i>≥ 第 95（{f(pcts['p95'])}%）</span>
</div>
<p class="mm-note">SPY／QQQ 一欄 =（收市 − 50 日 EMA）÷ 14 日 ATR。動力股百分位用本站自己 {pcts['n']} 個交易日嘅歷史計（{ddmm(pcts['from'])}/{pd.Timestamp(pcts['from']).year} 起），唔係 10 年。表顯示最近 {TABLE_DAYS} 個交易日，完整歷史喺 data/monitor/breadth_history.csv。</p>"""
    return cards + table


def pulse_svg(h):
    t = h.tail(PULSE_DAYS)
    W, H, pad_l, pad_r = 1000, 280, 46, 50
    mid = H / 2
    vmax = max(600, int(t[["up4", "dn4"]].max().max() * 1.1))
    sc = (mid - 24) / vmax
    bw = (W - pad_l - pad_r) / len(t)
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px">']
    for y, lab in [(mid - 300 * sc, "+300"), (mid + 300 * sc, "−300")]:
        parts.append(f'<line x1="{pad_l}" x2="{W-pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="#555" stroke-dasharray="4 4"/>'
                     f'<text x="{pad_l-6}" y="{y+4:.1f}" fill="#888" font-size="11" text-anchor="end">{lab}</text>')
    parts.append(f'<line x1="{pad_l}" x2="{W-pad_r}" y1="{mid}" y2="{mid}" stroke="#444"/>')
    for k, (d, r) in enumerate(t.iterrows()):
        x = pad_l + k * bw + bw * 0.15
        w = bw * 0.7
        cu = "#2e7d32" if r.up4 >= 300 else "#66bb6a"
        cd = "#c62828" if r.dn4 >= 300 else "#e57373"
        parts.append(f'<rect x="{x:.1f}" y="{mid - r.up4*sc:.1f}" width="{w:.1f}" height="{r.up4*sc:.1f}" fill="{cu}"><title>{ddmm(d)} Up4% {int(r.up4)}</title></rect>')
        parts.append(f'<rect x="{x:.1f}" y="{mid:.1f}" width="{w:.1f}" height="{r.dn4*sc:.1f}" fill="{cd}"><title>{ddmm(d)} Dn4% {int(r.dn4)}</title></rect>')
        if k % 5 == 0 or k == len(t) - 1:
            parts.append(f'<text x="{x + w/2:.1f}" y="{H-6}" fill="#888" font-size="10" text-anchor="middle">{ddmm(d)}</text>')
    last = t.iloc[-1]
    xl = pad_l + (len(t) - 1) * bw + bw / 2
    parts.append(f'<text x="{xl+10:.1f}" y="{mid - last.up4*sc - 4:.1f}" fill="#66bb6a" font-size="12" font-weight="700">{int(last.up4)}</text>')
    parts.append(f'<text x="{xl+10:.1f}" y="{mid + last.dn4*sc + 14:.1f}" fill="#ef5350" font-size="12" font-weight="700">{int(last.dn4)}</text>')
    parts.append("</svg>")
    note = ('<p class="mm-note">軸上 = 當日收市比前一日升 ≥4% 嘅股票數，軸下 = 跌 ≥4%。深色 = ≥300；虛線 = ±300。'
            f'範圍同監察表一樣（收市 ≥ $5、成交 ≥ 30 萬股）。顯示最近 {PULSE_DAYS} 個交易日。</p>')
    return "".join(parts) + note


def momentum_svg(h, pcts):
    t = h.dropna(subset=["mom_pct"])
    W, H, pl, pr, pt, pb = 1000, 300, 46, 60, 16, 30
    vmax = max(50, float(t.mom_pct.max()) * 1.1)
    def Y(v): return pt + (H - pt - pb) * (1 - v / vmax)
    def X(i): return pl + (W - pl - pr) * i / max(1, len(t) - 1)
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px">']
    parts.append(f'<rect x="{pl}" y="{Y(vmax):.1f}" width="{W-pl-pr}" height="{Y(pcts["p95"])-Y(vmax):.1f}" fill="rgba(76,175,80,.16)"/>')
    parts.append(f'<rect x="{pl}" y="{Y(pcts["p95"]):.1f}" width="{W-pl-pr}" height="{Y(pcts["p90"])-Y(pcts["p95"]):.1f}" fill="rgba(76,175,80,.08)"/>')
    parts.append(f'<rect x="{pl}" y="{Y(pcts["p10"]):.1f}" width="{W-pl-pr}" height="{Y(pcts["p5"])-Y(pcts["p10"]):.1f}" fill="rgba(244,67,54,.10)"/>')
    parts.append(f'<rect x="{pl}" y="{Y(pcts["p5"]):.1f}" width="{W-pl-pr}" height="{Y(0)-Y(pcts["p5"]):.1f}" fill="rgba(244,67,54,.20)"/>')
    for v in range(0, int(vmax) + 1, 10):
        parts.append(f'<line x1="{pl}" x2="{W-pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#222"/>'
                     f'<text x="{pl-6}" y="{Y(v)+4:.1f}" fill="#888" font-size="10" text-anchor="end">{v}%</text>')
    parts.append(f'<line x1="{pl}" x2="{W-pr}" y1="{Y(pcts["p50"]):.1f}" y2="{Y(pcts["p50"]):.1f}" stroke="#999" stroke-dasharray="6 4"/>'
                 f'<text x="{pl+4}" y="{Y(pcts["p50"])-4:.1f}" fill="#999" font-size="10">median {f(pcts["p50"])}%</text>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(t.mom_pct))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#42a5f5" stroke-width="2"/>')
    step = max(1, len(t) // 8)
    ticks = [i for i in range(0, len(t), step) if len(t) - 1 - i > step * 0.6] + [len(t) - 1]
    for i in ticks:
        d = t.index[i]
        parts.append(f'<text x="{X(i):.1f}" y="{H-8}" fill="#888" font-size="10" text-anchor="middle">{pd.Timestamp(d).strftime("%d/%m/%y")}</text>')
    lv = float(t.mom_pct.iloc[-1])
    parts.append(f'<circle cx="{X(len(t)-1):.1f}" cy="{Y(lv):.1f}" r="4" fill="#ef5350"/>'
                 f'<text x="{X(len(t)-1)+8:.1f}" y="{Y(lv)+4:.1f}" fill="#fff" font-size="12" font-weight="700">{f(lv)}%</text>')
    parts.append("</svg>")
    note = (f'<p class="mm-note">動力股 = 收市 ≥ $5、當日成交 ≥ 30 萬股及成交額 ≥ $5M、過去 63 個交易日升 ≥ 20%。'
            f'色帶 = 本站歷史百分位：紅 ≤ 第 5／10（{f(pcts["p5"])}%／{f(pcts["p10"])}%），綠 ≥ 第 90／95（{f(pcts["p90"])}%／{f(pcts["p95"])}%）。'
            f'灰虛線 = median。歷史得 {pcts["n"]} 個交易日，所以百分位會隨日子累積而變。</p>')
    return "".join(parts) + note


def sector_tables(sec):
    if not sec:
        return '<div class="mm-box">行業數據今日計唔到（資料不足）。</div>', '<div class="mm-box">—</div>'
    rows = pd.DataFrame(sec["rows"])
    ranked = rows[rows.base >= 20]
    strong = ranked[ranked.z > 1.96].sort_values("lift", ascending=False)
    weak = ranked[ranked.z < -1.96].sort_values("z")
    mid = ranked[(ranked.z <= 1.96) & (ranked.z >= -1.96)].sort_values("lift", ascending=False)

    def cls_med(v):
        return "g2" if v >= 5 else ("g1" if v >= 0 else ("r1" if v > -10 else "r2"))

    def cls_d(v):
        return "g2" if v >= 0.3 else ("g1" if v > 0 else ("r1" if v > -0.3 else "r2"))

    def cls_pace(v):
        return "g2" if v >= 5 else ("g1" if v > 0 else ("r1" if v > -5 else "r2"))

    def tbl(df, zcls):
        if df.empty:
            return '<p class="mm-note">（今日冇）</p>'
        tr = []
        for k, r in enumerate(df.itertuples(), 1):
            bar = min(100, r.lift / 4.5 * 100) if r.lift == r.lift else 0
            tr.append(
                f"<tr><td>{k}</td><td style='text-align:left'>{esc(r.industry)}</td>"
                f"<td style='text-align:left;min-width:110px'><div style='background:#42a5f5;height:8px;width:{bar:.0f}%;border-radius:2px'></div></td>"
                f"<td class='{'g2' if r.lift >= 1.5 else ('r2' if r.lift < 0.5 else '')}'>{f(r.lift,2)}</td>"
                f"<td class='{cls_med(r.median63)}'>{f(r.median63,1,True,True)}</td>"
                f"<td class='{cls_d(r.dlift)}'>{f(r.dlift,2,True)}</td>"
                f"<td class='{cls_pace(r.pace)}'>{f(r.pace,1,True,True)}</td>"
                f"<td>{f(r.share)}</td><td>{int(r.mom)}</td><td>{int(r.base)}</td>"
                f"<td class='{zcls(r.z)}'>{f(r.z,2,True)}{' ✓' if abs(r.z) > 1.96 else ''}</td></tr>")
        return ("<div class='mm-wrap'><table class='mm-t'><thead><tr><th>#</th><th style='text-align:left'>行業</th><th style='text-align:left'>Lift</th>"
                "<th>倍數</th><th>季度 median</th><th>Δlift 21 日</th><th>Pace</th><th>滲透率 %</th><th>動力股</th><th>Base</th><th>z</th></tr></thead>"
                f"<tbody>{''.join(tr)}</tbody></table></div>")

    zc = lambda z: "g1" if z > 1.96 else ("r1" if z < -1.96 else "")
    top = ranked.sort_values("lift", ascending=False).head(1)
    topmed = ranked.sort_values("median63", ascending=False).head(1)
    unc = sec["unclassified"][0] if sec["unclassified"] else None
    cards = f"""
<div class="mm-cards">
 <div class="mm-card"><div class="k">過關行業數</div><div class="v">{len(strong)}</div><div class="s">{sec['n_ranked']} 個行業之中（z &gt; 1.96）</div></div>
 <div class="mm-card"><div class="k">最闊（lift 最高）</div><div class="v">{f(top.lift.iloc[0],2) + 'x' if len(top) else '—'}</div><div class="s">{esc(top.industry.iloc[0]) if len(top) else ''}</div></div>
 <div class="mm-card"><div class="k">最深（median 最高）</div><div class="v">{f(topmed.median63.iloc[0],1,True,True) if len(topmed) else '—'}</div><div class="s">{esc(topmed.industry.iloc[0]) if len(topmed) else ''}</div></div>
 <div class="mm-card"><div class="k">未分類</div><div class="v">{(unc['base'] if unc else 0)}</div><div class="s">隻冇行業分類，唔參與排名</div></div>
</div>"""
    level = (cards
             + '<div class="sub-title">統計上顯著偏強（z &gt; 1.96，按 lift 排）</div>' + tbl(strong, zc)
             + '<div class="sub-title">未達顯著（base ≥ 20）</div>' + tbl(mid, zc)
             + '<div class="sub-title">統計上顯著偏弱（z &lt; −1.96）</div>' + tbl(weak, zc)
             + f"""<div class="mm-box"><b>定義</b><br>
滲透率 = 行業入面有幾多 % 股票係動力股；全市場今日 {f(sec['p'])}%（{sec['K']} / {sec['N']} 隻）。<br>
lift（倍數）= 滲透率 ÷ 全市場滲透率。1.00 = 同大市一樣。<br>
z = 實際動力股數減「隨機應該有幾多」，再除以正常隨機波動。|z| &gt; 1.96 先當訊號（✓）。<br>
季度 median = 行業內<b>全部</b>股票 63 日回報嘅 median（量度深度）。<br>
Δlift = 今日 lift 減 21 個交易日前 lift（固定今日同一批股票）。pace = 21 日 median 回報 − 季度 median ÷ 3（絕對步速有冇加快）。<br>
同時檢驗 {sec['n_ranked']} 個行業，單靠運氣預期大約 {sec['n_ranked']*0.05:.1f} 個會過關；base 少過 20 隻嘅 {sec['n_small']} 個行業已剔除。行業分類用 NASDAQ industry。</div>""")

    up = ranked.sort_values("dlift", ascending=False).head(7)
    dn = ranked.sort_values("dlift").head(7)

    def dtbl(df):
        tr = []
        for k, r in enumerate(df.itertuples(), 1):
            tr.append(f"<tr><td>{k}</td><td style='text-align:left'>{esc(r.industry)}</td>"
                      f"<td class='{cls_d(r.dlift)}'>{f(r.dlift,2,True)}</td><td>{f(r.lift_then,2)}</td><td>{f(r.lift,2)}</td>"
                      f"<td class='{cls_pace(r.pace)}'>{f(r.pace,1,True,True)}</td><td>{f(r.median21,1,True,True)}</td>"
                      f"<td>{f(r.median63,1,True,True)}</td><td>{int(r.base)}</td></tr>")
        return ("<div class='mm-wrap'><table class='mm-t'><thead><tr><th>#</th><th style='text-align:left'>行業</th><th>Δlift</th><th>21 日前</th><th>今日</th>"
                "<th>Pace</th><th>21 日 median</th><th>季度 median</th><th>Base</th></tr></thead>"
                f"<tbody>{''.join(tr)}</tbody></table></div>")

    corr = sec.get("dlift_pace_corr")
    direction = (f'<p class="mm-note">對照 21 個交易日前 · 固定同一批 {sec["N"]} 隻 · 動力股比例 {f(sec["p_then"])}% → {f(sec["p"])}%</p>'
                 + '<div class="sub-title">動能明顯變強（Δlift 最高 7 個）</div>' + dtbl(up)
                 + '<div class="sub-title">動能明顯變弱（Δlift 最低 7 個）</div>' + dtbl(dn)
                 + f"""<div class="mm-box">Δlift 係<b>相對</b>份額變化（抽走大市潮汐）；pace 係<b>絕對</b>步速。今日兩者相關系數 {f(corr,2)}，數值低代表各講各話，要一齊睇。<br>
Δlift 用今日股票名單倒推 21 日前，有輕微 look-ahead，適合睇相對轉動，唔好當回測訊號。單一個 21 日比較只係兩點連線。</div>""")
    return level, direction


# --------------------------------------------------------------------------
# 今日讀數 (draft rules) + Section 13 theme ETF relative strength
# --------------------------------------------------------------------------
STATUS_CLS = {"領先": "g1", "冒起": "a1", "轉弱": "r1", "落後": "r1", "其他": ""}


def readout_box(h, latest):
    last = h.iloc[-1]
    back = h.iloc[-6] if len(h) > 5 else h.iloc[0]
    m = h["mom_pct"].dropna()
    pctile = 100 * (m <= last.mom_pct).mean()
    part = "闊" if last.pct50 >= 60 else ("一般" if last.pct50 >= 40 else "窄")
    mom = ("極低" if pctile <= 10 else "偏低" if pctile <= 50 else "過熱" if pctile >= 90 else "正常")
    d20 = last.pct20 - back.pct20
    dirw = "改善緊" if d20 >= 5 else ("轉差緊" if d20 <= -5 else "冇明顯變化")
    l1 = (f"參與度<b>{part}</b>（{f(last.pct50)}% 高過 50 日線）· 動力股<b>{mom}</b>"
          f"（{f(last.mom_pct)}%，本站歷史第 {pctile:.0f} 百分位）· 5 日<b>{dirw}</b>（20 日線上 {f(d20,1,True)} pp）")

    th = latest.get("themes") or {}
    srows = th.get("stock_rows") or []
    erows = th.get("etf_rows") or []
    lead = [r for r in srows if r["status"] == "領先"][:4]
    rise = [r for r in srows if r["status"] == "冒起"][:3]
    l2 = "主題：" + ("、".join(esc(r["theme"]) for r in lead) if lead else "冇主題同時 21 日同 63 日跑贏 SPY")
    if rise:
        l2 += "　冒起：" + "、".join(esc(r["theme"]) for r in rise)
    elead = [r for r in erows if r["status"] == "領先" and r["group"] != "SECTOR"][:4]
    if elead:
        l2 += "<br>ETF：" + "、".join(f'{esc(r["etf"])}（{esc(r["group"])}）' for r in elead)
    sec = latest.get("sectors") or {}
    sig = sorted([r for r in sec.get("rows", []) if r["base"] >= 20 and (r.get("z") or 0) > 1.96],
                 key=lambda r: -r["lift"])[:3]
    if sig:
        l2 += "<br>全市場動力股集中：" + "、".join(f'{esc(r["industry"])}（{f(r["lift"],1)}x）' for r in sig)

    top_now = {r["theme"] for r in srows if r["rank"] <= 5}
    top_then = {r["theme"] for r in srows if (r.get("rank_then") or 99) <= 5}
    ins = sorted(top_now - top_then)
    outs = sorted(top_then - top_now)
    new_lead = [r["theme"] for r in srows if r["status"] == "領先" and r.get("status_then") != "領先"]
    lost_lead = [r["theme"] for r in srows if r.get("status_then") == "領先" and r["status"] != "領先"]
    parts = []
    if ins: parts.append("新入前 5：" + "、".join(map(esc, ins)))
    if outs: parts.append("跌出前 5：" + "、".join(map(esc, outs)))
    if new_lead: parts.append("新變領先：" + "、".join(map(esc, new_lead)))
    if lost_lead: parts.append("唔再領先：" + "、".join(map(esc, lost_lead)))
    l3 = ("；".join(parts) if parts else "主題排名前 5 冇變") + \
         f"<br>50 日線上 {f(last.pct50-back.pct50,1,True)} pp · 動力股 {f(last.mom_pct-back.mom_pct,1,True)} pp"
    then = ddmm(th["then"]) if th.get("then") else ddmm(h.index[-6] if len(h) > 5 else h.index[0])

    return f"""
<!-- ═══ TODAY'S READOUT (market_monitor, preview) ═══ -->
<div class="mm-readout">
 <div class="mm-rt">今日讀數 · {ddmm(h.index[-1])}<span class="mm-tag">NEW · 規則係草稿</span></div>
 <div class="mm-rl"><span>大市</span><div>{l1}</div></div>
 <div class="mm-rl"><span>領先</span><div>{l2}</div></div>
 <div class="mm-rl"><span>變化</span><div>對比 {then}（5 個交易日前）：{l3}</div></div>
 <div class="mm-rn">規則（草稿，可以改）：參與度 = % 高過 50 日 SMA，≥60 闊／40–60 一般／&lt;40 窄。動力股 = 本站歷史百分位，≤10 極低／≤50 偏低／≥90 過熱。
 方向 = % 高過 20 日 EMA 對比 5 日前，±5 pp。領先 = 你嘅主題（成份股 median）21 日同 63 日都跑贏 SPY（Section 13）；ETF 一行唔計 SPDR sector（Section 14）；動力股集中 = Section 11 z &gt; 1.96。數字用 Section 8–14 嗰套。描述市況，唔係買賣訊號。</div>
</div>
"""


def _chg(r):
    rt = r.get("rank_then")
    if rt is None or rt != rt:
        return "—"
    rt = int(rt)
    arrow = ' <span class="text-green">▲</span>' if r["rank"] < rt else (' <span class="text-red">▼</span>' if r["rank"] > rt else "")
    return f"{rt} → {r['rank']}{arrow}"


def _st(r):
    return f'<td class="{STATUS_CLS.get(r["status"], "")}" style="text-align:center">{esc(r["status"])}</td>'


def stock_themes_section(th):
    rows = (th or {}).get("stock_rows") or []
    if not rows:
        return '<p class="mm-note">今次攞唔到主題數據。</p>'
    tr = []
    for r in rows:
        n = f'{r["n"]}' + (f'/{r["n_list"]}' if r["n"] != r["n_list"] else "")
        best = "、".join(f'{esc(t)} {f(v,0,True)}' for t, v in r["best"])
        tr.append(f'<tr><td>{r["rank"]}</td><td><b>{esc(r["theme"])}</b></td>{_st(r)}'
                  f'<td>{f(r["ex5"],1,True)}</td><td>{f(r["ex21"],1,True)}</td><td>{f(r["ex63"],1,True)}</td>'
                  f'<td>{f(r["pct50"],0)}%</td><td>{r["mom"]}/{n}</td><td>{_chg(r)}</td><td style="text-align:left">{best}</td></tr>')
    return (f'<p class="mm-note">你 TradingView watchlist 嘅股票分組 · 交易日 {ddmm(th["asof"])} · 主題嘅 5／21／63 日 = 成份股超額回報（減 SPY，pp）嘅 median · 對比 {ddmm(th["then"])}</p>'
            '<div class="mm-wrap"><table class="mm-t"><tr><th>#</th><th>主題</th><th>狀態</th><th>5 日</th><th>21 日</th><th>63 日</th>'
            '<th>50 日線上</th><th>動力股</th><th>排名變化</th><th style="text-align:left">21 日最強 2 隻</th></tr>'
            + "".join(tr) + "</table></div>"
            + f"""<div class="mm-box">排名 = 21 日同 63 日 median 超額回報嘅平均百分位。動力股 = 63 日升 ≥ 20% 嘅成份股數目 / 成份股數。<br>
狀態：<b>領先</b> = 21 日同 63 日都跑贏 SPY；<b>冒起</b> = 5 日同 21 日跑贏、63 日仲落後；<b>轉弱</b> = 63 日跑贏但 21 日落後；<b>落後</b> = 21 日同 63 日都跑輸；其他 = 混合。<br>
每個主題得 2–19 隻股票，數字會俾一兩隻帶住走，睇方向為主。上市未夠 63 日嘅股票唔計（「n/總數」）。Yahoo 冇數據：{esc("、".join(th.get("missing") or []) or "冇")}。</div>""")


def etf_section(th):
    rows = (th or {}).get("etf_rows") or []
    if not rows:
        return '<p class="mm-note">今次攞唔到 ETF 數據。</p>'
    tr = []
    for r in rows:
        a50 = "—" if r.get("above50") is None else ("✓" if r["above50"] else "✗")
        tr.append(f'<tr><td>{r["rank"]}</td><td><b>{esc(r["etf"])}</b></td><td style="text-align:left">{esc(r["group"])}</td>{_st(r)}'
                  f'<td>{f(r["ex5"],1,True)}</td><td>{f(r["ex21"],1,True)}</td><td>{f(r["ex63"],1,True)}</td>'
                  f'<td style="text-align:center">{a50}</td><td>{_chg(r)}</td></tr>')
    return (f'<p class="mm-note">你 watchlist 嘅 SECTOR、GATE 同 ARK 分組 · 回報減 SPY（pp，含股息）· 對比 {ddmm(th["then"])}</p>'
            '<div class="mm-wrap"><table class="mm-t"><tr><th>#</th><th>ETF</th><th style="text-align:left">分組</th><th>狀態</th><th>5 日</th><th>21 日</th><th>63 日</th><th>50 日線上</th><th>排名變化</th></tr>'
            + "".join(tr) + "</table></div>"
            + '<div class="mm-box">狀態同排名規則同 Section 13 一樣。ETF 反映成個籃子，唔等於入面最強嗰幾隻。大市跌嘅時候，防守 sector（XLP、XLV、XLU）會自動「跑贏 SPY」，所以今日讀數嘅 ETF 一行唔計 SPDR sector。</div>')

def notes_box(latest, h):
    info = latest.get("universe_info", {})
    r = latest.get("rules", {})
    src_ok = ("NASDAQ screener ✓" if info.get("screener_ok") else "NASDAQ screener ✗（行業分類攞唔到）") + \
             " · " + ("NASDAQ Trader 名單 ✓" if info.get("symdir_ok") else "NASDAQ Trader 名單 ✗")
    return f"""<div class="mm-box"><b>數據來源同限制（Section 8–14）</b><br>
來源：股票名單 + 行業 = NASDAQ；每日股價 = Yahoo Finance（免費、非官方，有機會改動或者擋）。{src_ok}。<br>
監察表範圍：{esc(r.get('breadth_universe',''))}。<br>
動力股範圍：{esc(r.get('momentum_universe',''))}。<br>
均線：{esc(r.get('ma',''))}。{esc(r.get('atr',''))}。<br>
名單用<b>今日</b>上市嘅股票倒推歷史，已除牌嘅股票唔喺入面（survivorship bias），舊日子嘅數會偏好少少；{esc(r.get('prefilter',''))}。<br>
同 Kelileo（Massive／Polygon 數據）數字唔會完全一樣，睇方向同極端值為主。<br>
今次：候選 {info.get('candidates','—')} 隻，Yahoo 冇數據 {latest.get('no_data_tickers','—')} 隻；最新交易日 {ddmm(latest['session'])}/{pd.Timestamp(latest['session']).year}；運行時間 {esc(latest.get('run_utc',''))} UTC。
全部係市場結構嘅客觀量度，唔係買賣訊號。</div>"""


def main():
    if not os.path.exists(SRC):
        raise SystemExit("index.html not found")
    page = open(SRC, encoding="utf-8").read()
    h = pd.read_csv(HIST, index_col="date", parse_dates=True)
    latest = json.load(open(LATEST, encoding="utf-8"))

    m = h["mom_pct"].dropna()
    pcts = {"p5": m.quantile(.05), "p10": m.quantile(.10), "p50": m.quantile(.50),
            "p90": m.quantile(.90), "p95": m.quantile(.95), "n": len(m), "from": m.index[0]}

    level, direction = sector_tables(latest.get("sectors"))
    block = (CSS
             + "\n<!-- ═══ NEW SECTIONS 8–12 (market_monitor, preview) ═══ -->\n"
             + section(8, "市寬與動能監察表", breadth_section(h, pcts, latest), "s8-mm-breadth")
             + section(9, "4% 動量脈搏", pulse_svg(h), "s9-mm-pulse")
             + section(10, "動力股數目走勢", momentum_svg(h, pcts), "s10-mm-momentum")
             + section(11, "行業動力（水平表）", level, "s11-mm-industry")
             + section(12, "行業動能（變強同變弱）", direction, "s12-mm-direction")
             + section(13, "你嘅主題相對強弱（對 SPY）", stock_themes_section(latest.get("themes")), "s13-mm-themes")
             + section(14, "你嘅 ETF 相對強弱（對 SPY）", etf_section(latest.get("themes")), "s14-mm-etf")
             + notes_box(latest, h) + "\n")

    pos = page.find("<!-- ═══ HISTORY ARCHIVE")
    if pos < 0:
        # live page (dev-3.9): no comment marker; insert before the
        # <div class="section"...> that holds the History Archive title
        t = page.find("History Archive</div>")
        if t >= 0:
            pos = page.rfind('<div class="section"', 0, t)
    if pos < 0:
        pos = page.rfind("</body>")
    page = page[:pos] + block + page[pos:]
    # readout box at the top of the page body
    ro = readout_box(h, latest)
    k = page.find('<div class="page-wrap">')
    if k >= 0:
        k += len('<div class="page-wrap">')
        page = page[:k] + ro + page[k:]
    page = page.replace("<title>", "<title>[Preview] ", 1)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {OUT} ({len(page)/1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
