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
            + R.readout_box(h, latest)
            + part("A", "大市點？")
            + sec(1, "Breadth 總表", R.breadth_section(h, pcts, latest)
                  + '<div class="sub-title">4% 動量脈搏</div>' + R.pulse_svg(h), "v2-s1")
            + sec(2, "動力股走勢", R.momentum_svg(h, pcts), "v2-s2")
            + grok_section(live, "s3-indices", 3, "指數同伸展").replace(
                "Grok 數據（暫借）</span></div>", "Grok 數據（暫借）</span></div>" + atr_line(h), 1)
            + part("B", "邊度強？")
            + sec(4, "全市場組別（水平 + 方向）", s4, "v2-s4")
            + sec(5, "你嘅主題（對 SPY）", s5, "v2-s5")
            + sec(6, "ETF（對 SPY）", R.etf_section(latest.get("themes")), "v2-s6")
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
