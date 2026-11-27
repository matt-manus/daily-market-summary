"""
v3 layout (27/11/26), top-down, based on the original monitor:

  1  Macro indicators            (Grok, borrowed)
  2  Market sentiment            (Grok, borrowed)
  3  Major indices               (Grok, borrowed)
  4  Market breadth
     4A % of index constituents above 20/50/200-day SMA — line charts (own calc)
     4B Stockbee Market Monitor  (Grok, borrowed; was 4C)
     4C Breadth table + 4% pulse + momentum share (recent + 10 years)
  5  Core sector ETFs vs SPY (5/21/63-day excess return)
  6  Momentum by group: level, direction, strengthening groups' leaders + ETF,
     group mapping table
Writes market-monitor-v3.html.
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R  # noqa: E402
import render_v2 as V2  # noqa: E402
from groups import GROUP_ETF  # noqa: E402

OUT3 = os.path.join(R.ROOT, "market-monitor-v3.html")
DATA = os.path.join(R.ROOT, "data", "monitor")
SECTORS = [("XLK", "科技"), ("XLF", "金融"), ("XLV", "醫療"), ("XLY", "非必需消費"), ("XLP", "必需消費"),
           ("XLE", "能源"), ("XLI", "工業"), ("XLB", "原材料"), ("XLU", "公用"), ("XLRE", "地產"), ("XLC", "通訊")]
C20, C50, C200 = "#42a5f5", "#ff9800", "#ce93d8"


# ---------------------------------------------------------------- charts
def line_chart(series, w=340, hgt=150, ymin=0, ymax=100, colors=(), labels=(), title=""):
    """series: list of pd.Series sharing an index."""
    pl, pr, pt, pb = 30, 38, 18, 20
    iw, ih = w - pl - pr, hgt - pt - pb
    idx = series[0].index
    n = len(idx)
    X = lambda k: pl + (k / (n - 1 if n > 1 else 1)) * iw
    Y = lambda v: pt + ih - (v - ymin) / (ymax - ymin) * ih
    g = []
    for v in (ymin, (ymin + ymax) / 2, ymax) if ymax - ymin != 100 else (0, 25, 50, 75, 100):
        g.append(f'<line x1="{pl}" y1="{Y(v):.1f}" x2="{pl+iw}" y2="{Y(v):.1f}" stroke="#2a2a2a"/>'
                 f'<text x="{pl-4}" y="{Y(v)+3:.1f}" text-anchor="end" font-size="9" fill="#888">{v:g}</text>')
    for k in sorted({0, n // 2, n - 1}):
        g.append(f'<text x="{X(k):.1f}" y="{hgt-5}" text-anchor="middle" font-size="9" fill="#888">{R.ddmm(idx[k])}</text>')
    lines = []
    for s, col in zip(series, colors):
        pts = [(X(k), Y(v)) for k, v in enumerate(s.tolist()) if v == v]
        if len(pts) < 2:
            continue
        lines.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="{col}" stroke-width="1.6"/>')
        lv = s.dropna().iloc[-1]
        lines.append(f'<text x="{pl+iw+3}" y="{Y(lv)+3:.1f}" font-size="9" fill="{col}">{lv:.0f}</text>')
    leg = "".join(f'<span style="margin-right:8px;white-space:nowrap"><span style="display:inline-block;width:9px;height:3px;'
                  f'background:{c};vertical-align:middle;margin-right:3px"></span>{R.esc(l)}</span>'
                  for c, l in zip(colors, labels))
    return (f'<div class="mom-chart" style="padding:8px"><div style="font-size:11px;font-weight:700;color:#ccc;margin-bottom:4px">'
            f'{R.esc(title)} <span style="font-weight:400;color:var(--text-muted)">{leg}</span></div>'
            f'<svg viewBox="0 0 {w} {hgt}" xmlns="http://www.w3.org/2000/svg">{"".join(g)}{"".join(lines)}</svg></div>')


def sec4a():
    p = os.path.join(DATA, "index_breadth.csv")
    if not os.path.exists(p):
        return '<div class="mm-box">4A 數據未有（等下一次 run）。</div>'
    d = pd.read_csv(p, index_col="date", parse_dates=True).iloc[-130:]
    try:
        cnt = json.load(open(os.path.join(DATA, "index_members.json")))
    except Exception:  # noqa: BLE001
        cnt = {}
    names = sorted({c.split("|")[0] for c in d.columns},
                   key=lambda x: ["S&P 500", "Nasdaq-100", "Dow 30", "Russell 2000"].index(x)
                   if x in ["S&P 500", "Nasdaq-100", "Dow 30", "Russell 2000"] else 9)
    charts = "".join(
        line_chart([d[f"{nm}|20"], d[f"{nm}|50"], d[f"{nm}|200"]], colors=(C20, C50, C200),
                   labels=("> 20 日", "> 50 日", "> 200 日"), title=f"{nm}（{cnt.get(nm, '?')} 隻）")
        for nm in names)
    missing = [x for x in ["S&P 500", "Nasdaq-100", "Dow 30", "Russell 2000"] if x not in names]
    return (f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px">{charts}</div>'
            f'<p class="mm-note">% 成份股收市高過 20／50／200 日簡單平均線，最近 130 個交易日。成份股名單：S&amp;P 500 用 Wikipedia，Nasdaq-100 用 NASDAQ 官網 API；'
            f'Dow 30 同 Russell 2000 嘅來源未搞掂。全段歷史都用今日嘅名單，所以舊啲嘅數係近似值。價錢 = Yahoo Finance。'
            + (f' 今次攞唔到：{"、".join(missing)}。' if missing else "") + '</p>')


def sec4b(live):
    a = live.find('id="s4-breadth"')
    b = live.find('<div class="section"', a + 10)
    blk = live[a:b] if a >= 0 else ""
    k = blk.find("<!-- 4C")
    if k < 0:
        return '<div class="mm-box">Grok 嘅 Stockbee 部分今日搵唔到。</div>'
    part = blk[k:]
    part = part[:part.rfind("</div>")]  # drop the section's closing div
    part = part.replace("4C — Stockbee", "4B — Stockbee", 1)
    return part.replace("Stockbee Market Monitor</div>",
                        'Stockbee Market Monitor<span class="mm-tag" style="background:#555">Grok 數據（暫借）</span></div>', 1)


def mom10y_chart(h):
    p = os.path.join(DATA, "mom10y.csv")
    if not os.path.exists(p):
        return '<div class="mm-box">10 年動力股比例：數據計緊（另一個 job，第一次要大約一個鐘）。</div>'
    w = pd.read_csv(p, index_col="date", parse_dates=True)["mom_pct"]
    recent = h["mom_pct"].dropna()
    recent = recent[recent.index > w.index[-1]]
    if len(recent):
        recent = recent.groupby(recent.index.to_period("W")).tail(1)
        w = pd.concat([w, recent])
    W, H = 700, 210
    pl, pr, pt, pb = 34, 40, 14, 22
    iw, ih = W - pl - pr, H - pt - pb
    ymax = max(10, (int(w.max() / 10) + 1) * 10)
    n = len(w)
    X = lambda k: pl + k / (n - 1) * iw
    Y = lambda v: pt + ih - v / ymax * ih
    g = [f'<line x1="{pl}" y1="{Y(v):.1f}" x2="{pl+iw}" y2="{Y(v):.1f}" stroke="#2a2a2a"/>'
         f'<text x="{pl-4}" y="{Y(v)+3:.1f}" text-anchor="end" font-size="9" fill="#888">{v}%</text>'
         for v in range(0, ymax + 1, 10)]
    years = sorted({d.year for d in w.index})
    for yr in years:
        k = next(i for i, d in enumerate(w.index) if d.year == yr)
        g.append(f'<line x1="{X(k):.1f}" y1="{pt}" x2="{X(k):.1f}" y2="{pt+ih}" stroke="#222"/>'
                 f'<text x="{X(k)+2:.1f}" y="{H-6}" font-size="9" fill="#888">{yr}</text>')
    pts = " ".join(f"{X(k):.1f},{Y(v):.1f}" for k, v in enumerate(w.tolist()))
    lv = w.iloc[-1]
    pct = 100 * (w <= lv).mean()
    svg = (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{"".join(g)}'
           f'<polyline points="{pts}" fill="none" stroke="#ce93d8" stroke-width="1.4"/>'
           f'<circle cx="{X(n-1):.1f}" cy="{Y(lv):.1f}" r="3" fill="#ce93d8"/>'
           f'<text x="{X(n-1)+4:.1f}" y="{Y(lv)+3:.1f}" font-size="10" fill="#ce93d8">{lv:.1f}%</text></svg>')
    return (f'<div class="sub-title">動力股比例：10 年（每星期最後一個交易日）</div><div class="mom-chart" style="padding:8px">{svg}</div>'
            f'<p class="mm-note">{R.ddmm(w.index[0])}/{w.index[0].year} 至今，{n} 個星期。今日 {lv:.1f}%，'
            f'10 年入面有 {pct:.0f}% 嘅星期等於或者低過今日。定義同每日數字一樣（$5、30 萬股、$500 萬、63 日 ≥ +20%）。'
            '用今日嘅股票名單倒計，冇計已經除牌嘅股票，舊時嘅數會偏高少少：當大概走勢睇，唔好當準確歷史。</p>')


# ---------------------------------------------------------------- interactive momentum charts
HOVER_JS = """
<script>
(function(){
  document.querySelectorAll('table[data-sortable]').forEach(function(t){
    var heads=t.rows[0].cells;
    for(let c=2;c<=4;c++){heads[c].style.cursor='pointer';heads[c].addEventListener('click',function(){
      var rows=Array.prototype.slice.call(t.rows,1), dir=t.getAttribute('data-dir'+c)==='d'?1:-1;
      t.setAttribute('data-dir'+c,dir===-1?'d':'a');
      rows.sort(function(a,b){return dir*(parseFloat(a.cells[c].textContent)-parseFloat(b.cells[c].textContent));});
      rows.forEach(function(r){t.tBodies[0].appendChild(r);});
    });}
  });
})();
</script>
<script>
(function(){
  function fmt(p){return p.d+' · '+p.v.toFixed(1)+'% · 10 年第 '+Math.round(p.p)+' 百分位';}
  document.querySelectorAll('svg[data-pts]').forEach(function(svg){
    var pts=JSON.parse(svg.getAttribute('data-pts'));
    var ns='http://www.w3.org/2000/svg';
    var vb=svg.viewBox.baseVal;
    var line=document.createElementNS(ns,'line');line.setAttribute('stroke','#666');line.setAttribute('y1',0);line.setAttribute('y2',vb.height);line.style.display='none';
    var dot=document.createElementNS(ns,'circle');dot.setAttribute('r',3.5);dot.setAttribute('fill','#fff');dot.style.display='none';
    svg.appendChild(line);svg.appendChild(dot);
    var tip=document.createElement('div');
    tip.style.cssText='position:absolute;pointer-events:none;background:#111;border:1px solid #555;color:#eee;font-size:11px;padding:3px 6px;border-radius:4px;white-space:nowrap;display:none;z-index:9';
    svg.parentNode.style.position='relative';svg.parentNode.appendChild(tip);
    function move(ev){
      var e=ev.touches?ev.touches[0]:ev;var r=svg.getBoundingClientRect();
      var x=(e.clientX-r.left)/r.width*vb.width;var best=pts[0];
      for(var i=1;i<pts.length;i++){if(Math.abs(pts[i].x-x)<Math.abs(best.x-x))best=pts[i];}
      line.setAttribute('x1',best.x);line.setAttribute('x2',best.x);line.style.display='';
      dot.setAttribute('cx',best.x);dot.setAttribute('cy',best.y);dot.style.display='';
      tip.textContent=fmt(best);tip.style.display='';
      var px=best.x/vb.width*r.width, py=best.y/vb.height*r.height;
      tip.style.left=Math.min(Math.max(px-60,0),r.width-170)+'px';tip.style.top=Math.max(py-30,0)+'px';
    }
    function hide(){line.style.display='none';dot.style.display='none';tip.style.display='none';}
    svg.addEventListener('mousemove',move);svg.addEventListener('touchstart',move,{passive:true});
    svg.addEventListener('touchmove',move,{passive:true});svg.addEventListener('mouseleave',hide);
  });
})();
</script>
"""


def mom_chart(series, ref, title, note, W=700, H=210, color="#ce93d8"):
    """series: dated mom_pct values to plot; ref: 10y weekly series for percentiles."""
    import json as _json
    series = series.dropna()
    pl, pr, pt, pb = 34, 64, 14, 22
    iw, ih = W - pl - pr, H - pt - pb
    ymax = max(10, (int(max(series.max(), ref.quantile(.95)) / 10) + 1) * 10)
    n = len(series)
    X = lambda k: pl + k / (n - 1 if n > 1 else 1) * iw
    Y = lambda v: pt + ih - v / ymax * ih
    g = [f'<line x1="{pl}" y1="{Y(v):.1f}" x2="{pl+iw}" y2="{Y(v):.1f}" stroke="#2a2a2a"/>'
         f'<text x="{pl-4}" y="{Y(v)+3:.1f}" text-anchor="end" font-size="9" fill="#888">{v}%</text>'
         for v in range(0, ymax + 1, 10)]
    for q, lab, col in [(.05, "第 5", "#c62828"), (.10, "第 10", "#ef5350"), (.50, "中位數", "#9e9e9e"),
                        (.90, "第 90", "#66bb6a"), (.95, "第 95", "#2e7d32")]:
        v = ref.quantile(q)
        g.append(f'<line x1="{pl}" y1="{Y(v):.1f}" x2="{pl+iw}" y2="{Y(v):.1f}" stroke="{col}" stroke-dasharray="4 3" stroke-width="1"/>'
                 f'<text x="{pl+iw+3}" y="{Y(v)+3:.1f}" font-size="9" fill="{col}">{lab} {v:.1f}%</text>')
    idx = series.index
    if (idx[-1] - idx[0]).days > 800:
        for yr in sorted({d.year for d in idx}):
            k = next(i for i, d in enumerate(idx) if d.year == yr)
            g.append(f'<text x="{X(k)+2:.1f}" y="{H-6}" font-size="9" fill="#888">{yr}</text>')
    else:
        for k in sorted({0, n // 4, n // 2, 3 * n // 4, n - 1}):
            g.append(f'<text x="{X(k):.1f}" y="{H-6}" text-anchor="middle" font-size="9" fill="#888">{R.ddmm(idx[k])}</text>')
    refv = ref.values
    pts = [{"x": round(X(k), 1), "y": round(Y(v), 1), "v": float(v), "d": d.strftime("%d/%m/%Y"),
            "p": float(100 * (refv <= v).mean())} for k, (d, v) in enumerate(series.items())]
    poly = " ".join(f"{p['x']},{p['y']}" for p in pts)
    lv, lp = pts[-1]["v"], pts[-1]["p"]
    svg = (f"<svg viewBox=\"0 0 {W} {H}\" xmlns=\"http://www.w3.org/2000/svg\" style=\"touch-action:pan-y;cursor:crosshair\" "
           f"data-pts='{_json.dumps(pts, separators=(',', ':'))}'>{''.join(g)}"
           f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.4"/>'
           f'<circle cx="{pts[-1]["x"]}" cy="{pts[-1]["y"]}" r="3" fill="{color}"/></svg>')
    return (f'<div class="sub-title">{R.esc(title)}</div><div class="mom-chart" style="padding:8px">{svg}</div>'
            f'<p class="mm-note">今日 {lv:.1f}%，係 10 年入面第 {lp:.0f} 百分位（即係 {lp:.0f}% 嘅星期等於或者低過今日）。'
            f'將游標放喺線上（手機用手指撳住）就見到嗰日嘅數值、日期同百分位。{note}</p>')


def momentum_charts(h):
    p = os.path.join(DATA, "mom10y.csv")
    if not os.path.exists(p):
        return '<div class="mm-box">10 年動力股比例：數據計緊。</div>'
    w = pd.read_csv(p, index_col="date", parse_dates=True)["mom_pct"].dropna()
    daily = h["mom_pct"].dropna()
    recent = daily.iloc[-260:]
    after = daily[daily.index > w.index[-1]]
    if len(after):
        after = after.groupby(after.index.to_period("W")).tail(1)
        w10 = pd.concat([w, after])
    else:
        w10 = w
    ref = w10
    return (mom_chart(recent, ref, "動力股比例：最近 260 個交易日（每日）",
                      "百分位線用 10 年每星期數據計。")
            + mom_chart(w10, ref, "動力股比例：10 年（每星期最後一個交易日）",
                        "定義同每日數字一樣（$5、30 萬股、$500 萬、63 日 ≥ +20%）。用今日嘅股票名單倒計，冇計已經除牌嘅股票，"
                        "舊時嘅數會偏高少少：當大概走勢睇，唔好當準確歷史。"))


# ---------------------------------------------------------------- 4A extra: 20-session trend charts (hover)
MULTI_JS = """
<script>
(function(){
  document.querySelectorAll('svg[data-multi]').forEach(function(svg){
    var D=JSON.parse(svg.getAttribute('data-multi')), ns='http://www.w3.org/2000/svg', vb=svg.viewBox.baseVal;
    var line=document.createElementNS(ns,'line');line.setAttribute('stroke','#666');line.setAttribute('y1',0);line.setAttribute('y2',vb.height);line.style.display='none';svg.appendChild(line);
    var tip=document.createElement('div');
    tip.style.cssText='position:absolute;pointer-events:none;background:#111;border:1px solid #555;color:#eee;font-size:11px;padding:3px 6px;border-radius:4px;white-space:nowrap;display:none;z-index:9';
    svg.parentNode.style.position='relative';svg.parentNode.appendChild(tip);
    function move(ev){
      var e=ev.touches?ev.touches[0]:ev, r=svg.getBoundingClientRect(), x=(e.clientX-r.left)/r.width*vb.width, k=0;
      for(var i=1;i<D.x.length;i++){if(Math.abs(D.x[i]-x)<Math.abs(D.x[k]-x))k=i;}
      line.setAttribute('x1',D.x[k]);line.setAttribute('x2',D.x[k]);line.style.display='';
      var h='<b>'+D.d[k]+'</b>';
      D.s.forEach(function(s){var v=s.v[k];h+='<br><span style="color:'+s.c+'">■</span> '+s.n+': '+(v===null?'—':(v>0&&s.sign?'+':'')+v.toFixed(s.nd)+s.u);});
      tip.innerHTML=h;tip.style.display='';
      var px=D.x[k]/vb.width*r.width;tip.style.left=Math.min(Math.max(px-70,0),r.width-150)+'px';tip.style.top='4px';
    }
    function hide(){line.style.display='none';tip.style.display='none';}
    svg.addEventListener('mousemove',move);svg.addEventListener('touchstart',move,{passive:true});
    svg.addEventListener('touchmove',move,{passive:true});svg.addEventListener('mouseleave',hide);
  });
})();
</script>
"""


def multi_chart(dates, series, title, unit="%", nd=1, sign=False, zero=False, W=360, H=190):
    """series: list of (name, values list, color)."""
    import json as _json
    pl, pr, pt, pb = 30, 12, 10, 20
    iw, ih = W - pl - pr, H - pt - pb
    vals = [v for _, vs, _ in series for v in vs if v == v]
    lo, hi = min(vals), max(vals)
    if zero:
        lo, hi = min(lo, 0), max(hi, 0)
    pad = (hi - lo) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    if unit == "%" and not sign:
        lo, hi = max(0, lo), min(100, hi)
    n = len(dates)
    X = lambda k: pl + k / (n - 1 if n > 1 else 1) * iw
    Y = lambda v: pt + ih - (v - lo) / (hi - lo) * ih
    step = [1, 2, 5, 10, 20, 25, 50][min(6, max(0, int((hi - lo) / 5).bit_length() - 1))]
    g = []
    v0 = int(lo // step + 1) * step
    while v0 <= hi:
        g.append(f'<line x1="{pl}" y1="{Y(v0):.1f}" x2="{pl+iw}" y2="{Y(v0):.1f}" stroke="{"#555" if v0 == 0 else "#2a2a2a"}"/>'
                 f'<text x="{pl-4}" y="{Y(v0)+3:.1f}" text-anchor="end" font-size="9" fill="#888">{("+" if sign and v0 > 0 else "")}{v0:g}</text>')
        v0 += step
    for k in sorted({0, n // 2, n - 1}):
        g.append(f'<text x="{X(k):.1f}" y="{H-5}" text-anchor="middle" font-size="9" fill="#888">{R.ddmm(dates[k])}</text>')
    lines = []
    for name, vs, col in series:
        pts = [(X(k), Y(v)) for k, v in enumerate(vs) if v == v]
        lines.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="{col}" stroke-width="1.6"/>')
        lines += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" fill="{col}"/>' for x, y in pts]
    data = {"x": [round(X(k), 1) for k in range(n)], "d": [d.strftime("%d/%m") for d in dates],
            "s": [{"n": nm, "c": col, "u": (" pp" if sign else unit), "nd": nd, "sign": sign,
                   "v": [round(float(v), 2) if v == v else None for v in vs]} for nm, vs, col in series]}
    leg = "".join(f'<span style="margin-right:8px;white-space:nowrap"><span style="display:inline-block;width:9px;height:3px;'
                  f'background:{c};vertical-align:middle;margin-right:3px"></span>{R.esc(nm)}</span>' for nm, _, c in series)
    return (f'<div class="mom-chart" style="padding:8px"><div style="font-size:11px;font-weight:700;color:#ccc;margin-bottom:4px">'
            f'{R.esc(title)} <span style="font-weight:400;color:var(--text-muted)">{leg}</span></div>'
            f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="touch-action:pan-y;cursor:crosshair" '
            f"data-multi='{_json.dumps(data, separators=(',', ':'))}'>{''.join(g)}{''.join(lines)}</svg></div>")


def trend20(h, latest, n=20):
    t = h.iloc[-n:]
    c1 = multi_chart(list(t.index), [("> 20 日 EMA", t.pct20.tolist(), C20), ("> 50 日 SMA", t.pct50.tolist(), C50),
                                     ("動力股", t.mom_pct.tolist(), C200)],
                     "% 高過均線同動力股比例（全市場）")
    rel = ((latest.get("themes") or {}).get("rel_closes")) or {}
    if all(k in rel for k in ("SPY", "RSP", "IWM")):
        df = pd.DataFrame({k: pd.Series({pd.Timestamp(d): v for d, v in rel[k]}) for k in ("SPY", "RSP", "IWM")}).dropna()
        df = df.iloc[-(n + 1):]
        base = df.iloc[0]
        ret = (df / base - 1) * 100
        sp = ret.iloc[1:]
        c3 = multi_chart(list(sp.index), [("RSP − SPY", (sp.RSP - sp.SPY).tolist(), "#42a5f5"),
                                          ("IWM − SPY", (sp.IWM - sp.SPY).tolist(), "#ff9800")],
                         f"參與度：{R.ddmm(df.index[0])} 收市至今累計跑贏 SPY（pp）", sign=True, zero=True, nd=2)
        note3 = (f'右圖：由 {R.ddmm(df.index[0])} 收市起計，RSP（S&amp;P 500 等權重）同 IWM（Russell 2000）嘅累計回報減 SPY，'
                 '單位係百分點；高過 0 = 跑贏 SPY，即係參與度闊過大型股。')
    else:
        c3, note3 = '<div class="mm-box">RSP／IWM 數據等下一次 run。</div>', ""
    return (f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px">{c1}{c3}</div>'
            f'<p class="mm-note">最近 {n} 個交易日。左圖：全市場（同 4C 一樣嘅宇宙同定義）% 高過 20 日 EMA、50 日 SMA，同動力股比例。'
            f'{note3}游標放喺圖上（手機用手指撳住）會顯示嗰日每條線嘅數值。</p>')


# ---------------------------------------------------------------- 5 / 6
def sec5(latest):
    ex = ((latest.get("themes") or {}).get("extra_ex")) or {}
    rows = [(t, nm, ex[t]) for t, nm in SECTORS if t in ex]
    if not rows:
        return '<div class="mm-box">Sector ETF 數據今次攞唔到。</div>'
    df = pd.DataFrame([{"etf": t, "name": nm, **v} for t, nm, v in rows])
    df["rank"] = df.ex5.rank(ascending=False, method="min").astype(int)
    if "ex5_then" in df and df.ex5_then.notna().all():
        df["rank_then"] = df.ex5_then.rank(ascending=False, method="min").astype(int)
    else:
        df["rank_then"] = None
    df = df.sort_values("rank")
    tr = "".join(
        f'<tr><td>{r.rank}</td><td style="text-align:left"><b>{r.etf}</b> {R.esc(r.name)}</td>'
        f'<td>{R.f(r.ex5,1,True)}</td><td>{R.f(r.ex21,1,True)}</td><td>{R.f(r.ex63,1,True)}</td>'
        f'<td style="text-align:center">{"✓" if r.above50 else "✗"}</td><td>{(V2._arrow(-r.rank, -r.rank_then) + " " + str(int(r.rank_then)) + " → " + str(r.rank)) if r.rank_then == r.rank_then and r.rank_then is not None else "—"}</td></tr>'
        for r in df.itertuples())
    return ('<p class="mm-note">每隻 sector ETF 嘅回報減 SPY 同期回報（百分點，含股息）。正數 = 跑贏 SPY。'
            '預設按 5 日排。排名變化 = 5 個交易日前嗰陣嘅 5 日排名 → 今日。</p>'
            '<div class="mm-wrap"><table class="mm-t" data-sortable="1"><tr><th>#</th><th style="text-align:left">Sector</th><th>5 日 ⇅</th><th>21 日 ⇅</th><th>63 日 ⇅</th>'
            '<th>50 日線上</th><th>排名變化</th></tr>' + tr + '</table></div>'
            '<p class="mm-note">撳「5 日／21 日／63 日」嘅欄名，可以改用嗰一欄排（再撳一次反轉）。</p>')


def leaders_box(latest):
    g = (latest.get("sectors") or {}).get("rows", [])
    g = [r for r in g if r["base"] >= 20 and r.get("dlift") == r.get("dlift")]
    top = sorted(g, key=lambda r: -r["dlift"])[:7]
    ex = ((latest.get("themes") or {}).get("extra_ex")) or {}
    tr = []
    for r in top:
        etf = GROUP_ETF.get(r["industry"])
        if etf and etf in ex:
            e = ex[etf]
            etf_s = f'<b>{etf}</b> {R.f(e["ex21"],1,True)} / {R.f(e["ex63"],1,True)}'
        elif etf:
            etf_s = f"<b>{etf}</b> —"
        else:
            etf_s = '<span style="color:var(--text-muted)">冇</span>'
        names = "、".join(f"{R.esc(t)} {R.f(v,0,True)}%" for t, v in (r.get("mom_list") or [])[:5]) or "—"
        tr.append(f'<tr><td style="text-align:left">{R.esc(r["industry"])}</td><td>{R.f(r["dlift"],2,True)}</td>'
                  f'<td>{R.f(r["lift_then"],2)} → {R.f(r["lift"],2)}</td><td style="text-align:left">{names}</td>'
                  f'<td style="text-align:left">{etf_s}</td></tr>')
    return ('<div class="sub-title">動能變強最多嘅組別：頭幾隻股票同代表 ETF</div>'
            '<p class="mm-note">按 21 日 Δlift 排頭 7 個組別。股票 = 組入面 63 日升幅最大嘅 5 隻動力股（括號係 63 日升幅）。'
            'ETF 後面兩個數 = 21 日／63 日跑贏 SPY 幾多百分點；「冇」= 冇一隻乾淨對應嘅 ETF。</p>'
            '<div class="mm-wrap"><table class="mm-t"><tr><th style="text-align:left">組別</th><th>Δlift</th><th>lift 21 日前 → 今日</th>'
            '<th style="text-align:left">頭 5 隻（63 日）</th><th style="text-align:left">代表 ETF（21／63 日 vs SPY）</th></tr>'
            + "".join(tr) + '</table></div>')


def renumber3(html):
    for a, b in [("Section 8–14", "Section 4C–6"), ("Section 8–13", "Section 4C–6"), ("Section 11 ", "Section 6 "),
                 ("（Section 13）", "（Section 6）"), ("Section 1–6", "Section 4C–6")]:
        html = html.replace(a, b)
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

    s4 = ('<div class="sub-title">4A — % 指數成份股高過 20／50／200 日線</div>' + sec4a()
          + '<div class="sub-title">4A — 最近 20 日 breadth 同參與度</div>' + trend20(h, latest)
          + sec4b(live)
          + '<div class="sub-title" style="margin-top:20px">4C — 全市場 breadth 同動力股</div>'
          + R.breadth_section(h, pcts, latest)
          + '<div class="sub-title">4% 動量脈搏</div>' + R.pulse_svg(h)
          + momentum_charts(h))
    s6 = (level + '<div class="sub-title" style="margin-top:18px">方向：21 日內變強同變弱</div>' + direction
          + leaders_box(latest) + R.group_map_box(latest.get("sectors")))

    body = (R.CSS
            + V2.grok_section(live, "s1-macro", 1, "Macro indicators")
            + V2.grok_section(live, "s2-sentiment", 2, "Market sentiment")
            + V2.grok_section(live, "s3-indices", 3, "Major indices")
            + V2.sec(4, "Market breadth", s4, "v3-s4")
            + V2.sec(5, "Core sector ETF 對比 SPY", sec5(latest), "v3-s5")
            + V2.sec(6, "Momentum stock breadth（組別）", s6, "v3-s6")
            + R.notes_box(latest, h)
            + HOVER_JS + MULTI_JS)
    body = renumber3(body)
    head_end = live.find('<div class="page-wrap">')
    page = live[:head_end] + '<div class="page-wrap">\n' + body + "\n</div>\n</body>\n</html>\n"
    page = re.sub(r"<title>.*?</title>", "<title>[Preview v3] Market Monitor</title>", page, count=1, flags=re.S)
    with open(OUT3, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {OUT3} ({len(page)/1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
