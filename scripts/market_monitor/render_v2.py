"""
Consolidated layout preview (v2, 27/11/26): one page organised by question.

  今日讀數
  A 大市點？      1 Breadth 總表 (+4% pulse)  2 動力股走勢  3 指數同伸展 (Grok S3, borrowed)
  B 邊度強？      4 全市場組別 (level + direction + 你冇跟緊)  5 你嘅主題  6 ETF
  C 背景          7 Macro 同情緒 (Grok S1 + S2, borrowed)

Grok's sections are copied as rendered HTML from the live index.html
(dev-3.9); their code is not in this repo. Writes market-monitor-v2.html.
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R  # noqa: E402

OUT2 = os.path.join(R.ROOT, "market-monitor-v2.html")


def grok_section(page, sid, new_num, new_title):
    a = page.find(f'id="{sid}"')
    if a < 0:
        return f'<div class="section"><div class="mm-box">Grok 嘅 {sid} 今日搵唔到。</div></div>'
    start = page.rfind('<div class="section"', 0, a)
    nxt = page.find('<div class="section"', a)
    end = nxt if nxt > 0 else page.find("</body>")
    block = page[start:end]
    block = re.sub(r"Section\s+\d+\s*(—|&mdash;|-)\s*[^<]*",
                   f"Section {new_num} — {R.esc(new_title)}", block, count=1)
    block = block.replace(f'id="{sid}"', f'id="v2-{sid}"', 1)
    tag = '<span class="mm-tag" style="background:#555">Grok 數據（暫借）</span>'
    block = block.replace("</div>", tag + "</div>", 1)
    return block


def sec(num, title, body, sid):
    return (f'\n<div class="section" id="{sid}">\n'
            f'  <div class="section-title">Section {num} — {R.esc(title)}</div>\n{body}\n</div>\n')


def part(letter, q):
    return (f'<div style="margin:26px 0 8px;padding:6px 10px;border-left:4px solid var(--amber);'
            f'font-size:15px;font-weight:700;color:#fff">{letter}. {R.esc(q)}</div>')


def renumber(html):
    for a, b in [("Section 8–14", "Section 1–6"), ("Section 8–13", "Section 1–6"),
                 ("（Section 13）", "（Section 5）"), ("（Section 14）", "（Section 6）"),
                 ("Section 11 z", "Section 4 z"), ("Section 13 底", "Section 4 底"),
                 ("Section 11 統計上", "Section 4 統計上"), ("同 Section 13 一樣", "同 Section 5 一樣")]:
        html = html.replace(a, b)
    return html


def atr_line(h):
    last = h.iloc[-1]
    return (f'<div class="mm-box">伸展（本站計）：SPY 離 50 日 EMA {R.f(last.spy_atr,2,True)} 個 ATR · '
            f'QQQ {R.f(last.qqq_atr,2,True)} 個 ATR（{R.ddmm(h.index[-1])}）。'
            '正數 = 高過 50 日線，負數 = 低過；數字愈大愈伸展。</div>')


# --------------------------------------------------------------------------
# 趨勢一覽: numbers over time only — no labels, no thresholds (27/11/26)
# --------------------------------------------------------------------------
def spark(vals, w=120, hgt=26, color="#42a5f5"):
    v = [x for x in vals if x == x]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(v) - 1):.1f},{hgt - 2 - (x - lo) / rng * (hgt - 4):.1f}" for i, x in enumerate(v))
    last_y = hgt - 2 - (v[-1] - lo) / rng * (hgt - 4)
    return (f'<svg width="{w}" height="{hgt}" viewBox="0 0 {w} {hgt}" style="vertical-align:middle">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{w}" cy="{last_y:.1f}" r="2" fill="{color}"/></svg>')


def _arrow(now, then):
    if now != now or then != then:
        return ""
    d = now - then
    return '<span class="text-green">▲</span>' if d > 0 else ('<span class="text-red">▼</span>' if d < 0 else "＝")


def trend_box(h, latest):
    n = len(h)
    i5, i21 = max(0, n - 6), max(0, n - 22)
    tail = h.iloc[-40:]
    rows = [("% 高過 20 日線", "pct20", 1), ("% 高過 50 日線", "pct50", 1), ("動力股 %", "mom_pct", 1),
            ("10 日 Up/Down 4% 比率", "ratio10", 2), ("SPY 離 50 日線（ATR）", "spy_atr", 2),
            ("QQQ 離 50 日線（ATR）", "qqq_atr", 2)]
    tr = []
    for label, col, nd in rows:
        now, w5, w21 = h[col].iloc[-1], h[col].iloc[i5], h[col].iloc[i21]
        tr.append(f'<tr><td style="text-align:left">{label}</td><td>{R.f(w21, nd)}</td><td>{R.f(w5, nd)}</td>'
                  f'<td><b>{R.f(now, nd)}</b></td><td>{_arrow(now, w5)} {_arrow(now, w21)}</td>'
                  f'<td>{spark(tail[col].tolist())}</td></tr>')
    up4, dn4 = h["up4"].iloc[-5:].tolist(), h["dn4"].iloc[-5:].tolist()
    days = " · ".join(f"{R.ddmm(d)} {int(u)}/{int(dd)}" for d, u, dd in zip(h.index[-5:], up4, dn4))
    breadth = ('<div class="mm-wrap"><table class="mm-t"><tr><th style="text-align:left">指標</th>'
               f'<th>21 日前<br>{R.ddmm(h.index[i21])}</th><th>5 日前<br>{R.ddmm(h.index[i5])}</th>'
               f'<th>今日<br>{R.ddmm(h.index[-1])}</th><th>對比<br>5 日／21 日</th><th>最近 40 日</th></tr>'
               + "".join(tr) + '</table></div>'
               + f'<p class="mm-note">最近 5 日 Up 4% / Down 4%：{days}</p>')

    g = (latest.get("groups") or latest.get("sectors") or {}).get("rows", [])
    g = [r for r in g if r["base"] >= 20]
    top_l = sorted(g, key=lambda r: -r["lift"])[:5]
    top_d = sorted(g, key=lambda r: -(r["dlift"] if r["dlift"] == r["dlift"] else -99))[:5]
    bot_d = sorted(g, key=lambda r: (r["dlift"] if r["dlift"] == r["dlift"] else 99))[:5]
    li = lambda rs, fn: "、".join(fn(r) for r in rs)
    th = latest.get("themes") or {}
    srows = th.get("stock_rows") or []
    t_top = sorted(srows, key=lambda r: r["rank"])[:5]
    t_up = sorted([r for r in srows if r.get("rank_then") == r.get("rank_then") and r.get("rank_then") is not None],
                  key=lambda r: r["rank"] - r["rank_then"])[:5]
    groups = (
        '<div class="mm-rl"><span>組別</span><div>'
        f'動力股最集中（lift，21 日前 → 今日）：{li(top_l, lambda r: f"{R.esc(r["industry"])} {R.f(r["lift_then"],1)}→{R.f(r["lift"],1)}")}<br>'
        f'21 日內升得最多（Δlift）：{li(top_d, lambda r: f"{R.esc(r["industry"])} {R.f(r["dlift"],2,True)}")}<br>'
        f'21 日內跌得最多：{li(bot_d, lambda r: f"{R.esc(r["industry"])} {R.f(r["dlift"],2,True)}")}</div></div>')
    if srows:
        groups += (
            '<div class="mm-rl"><span>主題</span><div>'
            f'排名最高（你嘅 watchlist）：{li(t_top, lambda r: f"{R.esc(r["theme"])}")}<br>'
            f'5 日內排名升得最多：{li(t_up, lambda r: f"{R.esc(r["theme"])} {int(r["rank_then"])}→{r["rank"]}")}</div></div>')
    return f"""
<div class="mm-readout">
 <div class="mm-rt">趨勢一覽 · {R.ddmm(h.index[-1])}</div>
 {breadth}
 {groups}
 <div class="mm-rn">只顯示數字同排名點樣變，冇標籤、冇門檻。▲▼ = 對比 5 日前／21 日前。組別同主題係排名，唔係判斷。</div>
</div>
"""


def strip_status(html):
    html = html.replace("<th>狀態</th>", "")
    html = re.sub(r'<td class="[^"]*" style="text-align:center">(領先|冒起|轉弱|落後|其他)</td>', "", html)
    html = re.sub(r"狀態：<b>領先</b>.*?其他 = 混合。<br>", "", html, flags=re.S)
    html = html.replace("狀態同排名規則同 Section 13 一樣。", "排名規則同 Section 5 一樣。")
    html = html.replace("狀態同排名規則同 Section 5 一樣。", "排名規則同 Section 5 一樣。")
    return html


def main():
    live = open(R.SRC, encoding="utf-8").read()
    h = pd.read_csv(R.HIST, index_col="date", parse_dates=True)
    latest = json.load(open(R.LATEST, encoding="utf-8"))
    m = h["mom_pct"].dropna()
    pcts = {"p5": m.quantile(.05), "p10": m.quantile(.10), "p50": m.quantile(.50),
            "p90": m.quantile(.90), "p95": m.quantile(.95), "n": len(m), "from": m.index[0]}
    if latest.get("groups"):
        latest["sectors_raw"] = latest["sectors"]
        latest["sectors"] = latest["groups"]

    level, direction = R.sector_tables(latest.get("sectors"))
    s4 = (level
          + '<div class="sub-title" style="margin-top:18px">方向：21 日內變強同變弱</div>' + direction
          + R.not_followed_box(latest)
          + R.group_map_box(latest.get("sectors")))
    # themes section without the not-followed box (moved to Section 4)
    nf = R.not_followed_box
    R.not_followed_box = lambda _l: ""
    s5 = R.stock_themes_section(latest.get("themes"), latest)
    R.not_followed_box = nf

    body = (R.CSS
            + trend_box(h, latest)
            + part("A", "大市點？")
            + sec(1, "Breadth 總表", R.breadth_section(h, pcts, latest)
                  + '<div class="sub-title">4% 動量脈搏</div>' + R.pulse_svg(h), "v2-s1")
            + sec(2, "動力股走勢", R.momentum_svg(h, pcts), "v2-s2")
            + grok_section(live, "s3-indices", 3, "指數同伸展").replace(
                "Grok 數據（暫借）</span></div>", "Grok 數據（暫借）</span></div>" + atr_line(h), 1)
            + part("B", "邊度強？")
            + sec(4, "全市場組別（水平 + 方向）", s4, "v2-s4")
            + sec(5, "你嘅主題（對 SPY）", strip_status(s5), "v2-s5")
            + sec(6, "ETF（對 SPY）", strip_status(R.etf_section(latest.get("themes"))), "v2-s6")
            + part("C", "背景")
            + grok_section(live, "s1-macro", "7A", "Macro")
            + grok_section(live, "s2-sentiment", "7B", "情緒")
            + R.notes_box(latest, h))
    body = renumber(body)

    head_end = live.find('<div class="page-wrap">')
    page = (live[:head_end] + '<div class="page-wrap">\n' + body + "\n</div>\n</body>\n</html>\n")
    page = re.sub(r"<title>.*?</title>", "<title>[Preview v2] Market Monitor — consolidated</title>", page, count=1, flags=re.S)
    with open(OUT2, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {OUT2} ({len(page)/1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
