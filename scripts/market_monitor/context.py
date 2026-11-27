"""
Sections 1–3 and 4B data (27/11/26), ported from Grok's pipeline definitions:

  1 Macro      : ^VIX, DX-Y.NYB, ^TNX, GC=F, CL=F, BTC-USD — last close vs prior close (Yahoo)
  2 Sentiment  : CNN Fear & Greed graphdata; Cboe EQUITY PUT/CALL RATIO for the session
                 (left empty if Cboe has not published that session — never a prior day)
  3 Indices    : SPY, QQQ, DIA, IWM (+RSP) on dividend-adjusted closes: 1D change, RSI 14 (Wilder),
                 distance from 20/50/200-day SMA; A/D = advancers / decliners among index members
                 (S&P 500, Nasdaq-100, Dow 30 from our own prices; Russell 2000 from Finviz counts)
  4B Stockbee  : public Stockbee Market Monitor Google Sheet read as CSV (latest rows)
Writes data/monitor/context.json. Every block fails independently.
"""
import io
import json
import os
import re

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
STOCKBEE_SHEET = "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE"
MACRO = [("VIX", "^VIX"), ("DXY", "DX-Y.NYB"), ("TNX", "^TNX"), ("GOLD", "GC=F"), ("OIL", "CL=F"), ("BTC", "BTC-USD")]
INDEX_ETF = ["SPY", "QQQ", "DIA", "IWM", "RSP"]


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def rsi_wilder(a, n=14):
    a = np.asarray(a, float)
    if len(a) < n + 1:
        return None
    d = np.diff(a)
    g, l = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = g[:n].mean(), l[:n].mean()
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def macro(asof):
    import yfinance as yf
    d = yf.download([s for _, s in MACRO], period="1mo", progress=False, auto_adjust=False)["Close"]
    out = {}
    for k, s in MACRO:
        col = d[s].dropna() if s in d else pd.Series(dtype=float)
        if len(col) < 2:
            out[k] = None
            continue
        col.index = pd.to_datetime(col.index)
        # use the bar dated on the session (futures / BTC also trade on market holidays), vs the bar before it
        col = col[col.index <= pd.Timestamp(asof)]
        if len(col) < 2:
            out[k] = None
            continue
        last, prev = col.iloc[-1], col.iloc[-2]
        out[k] = {"sym": s, "date": str(col.index[-1].date()), "price": float(last), "prev_date": str(col.index[-2].date()),
                  "chg": float(last / prev - 1)}
    return out


def fear_greed():
    r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                     headers={**UA, "Accept": "application/json", "Referer": "https://edition.cnn.com/"}, timeout=25)
    fg = r.json()["fear_and_greed"]
    keys = ["score", "rating", "timestamp", "previous_close", "previous_1_week", "previous_1_month", "previous_1_year"]
    return {k: fg.get(k) for k in keys}


def cboe_pc(session):
    url = f"https://www.cboe.com/markets/us/options/market-statistics/daily/?dt={session}"
    text = requests.get(url, headers={**UA, "Accept": "text/html"}, timeout=30).text
    text = text.replace('\\"', '"')
    sd = re.search(r'"selectedDate"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})"', text)
    if not sd or sd.group(1) != session:
        return {"ratio": None, "note": f"Cboe page date {sd.group(1) if sd else None} ≠ {session}", "url": url}
    if not re.search(r'"optionsData"\s*:\s*\{', text):
        return {"ratio": None, "note": f"Cboe 未出 {session} 數字", "url": url}
    rm = re.search(r'\{"name":"EQUITY PUT/CALL RATIO","value":"([^"]+)"\}', text)
    vm = re.search(r'"EQUITY OPTIONS":\[\{"name":"VOLUME","call":(\d+),"put":(\d+)', text)
    if not rm or not vm:
        return {"ratio": None, "note": "Cboe 頁面搵唔到 EQUITY PUT/CALL RATIO", "url": url}
    return {"ratio": float(rm.group(1)), "calls": int(vm.group(1)), "puts": int(vm.group(2)), "url": url, "note": ""}


def finviz_count(f):
    r = requests.get(f"https://finviz.com/screener.ashx?v=111&f={f}&ft=4", headers={**UA, "Accept": "text/html"}, timeout=25)
    m = re.search(r'"result_count"\s*:\s*(\d+)', r.text) or re.search(r'#1 / (\d[\d,]*)', r.text) or re.search(r'(\d[\d,]*)\s+Total', r.text)
    return int(m.group(1).replace(",", "")) if m else None


def indices(asof, members, close):
    import yfinance as yf
    d = yf.download(INDEX_ETF, period="2y", progress=False, auto_adjust=True)["Close"]
    d.index = pd.to_datetime(d.index)
    d = d[d.index <= pd.Timestamp(asof)]
    out = {}
    for s in INDEX_ETF:
        a = d[s].dropna() if s in d else pd.Series(dtype=float)
        if len(a) < 201:
            out[s] = None
            continue
        sm = {n: a.iloc[-n:].mean() for n in (20, 50, 200)}
        out[s] = {"date": str(a.index[-1].date()), "close": float(a.iloc[-1]), "chg": float(a.iloc[-1] / a.iloc[-2] - 1),
                  "rsi": _f(rsi_wilder(a.values[-300:])),
                  **{f"vs{n}": float(a.iloc[-1] / sm[n] - 1) for n in sm}}
    # advance / decline among index members, from our own closes on the session
    ad = {}
    cl = close.copy()
    cl.index = pd.to_datetime(cl.index)
    if pd.Timestamp(asof) in cl.index:
        i = cl.index.get_loc(pd.Timestamp(asof))
        for etf, name in (("SPY", "S&P 500"), ("QQQ", "Nasdaq-100"), ("DIA", "Dow 30")):
            cols = [t for t in members.get(name, []) if t in cl.columns]
            if not cols or i < 1:
                continue
            ch = cl[cols].iloc[i] / cl[cols].iloc[i - 1] - 1
            ad[etf] = {"up": int((ch > 0).sum()), "down": int((ch < 0).sum()), "src": f"{name} 成份股（本站價錢）"}
    try:
        up, dn = finviz_count("idx_rut,ta_change_u"), finviz_count("idx_rut,ta_change_d")
        if up is not None and dn is not None:
            ad["IWM"] = {"up": up, "down": dn, "src": "Finviz Russell 2000 screener（執行時嘅數）"}
    except Exception:  # noqa: BLE001
        pass
    for k, v in ad.items():
        if out.get(k):
            out[k]["ad"] = v
    p = {k: (out[k]["chg"] if out.get(k) else None) for k in ("SPY", "RSP", "IWM")}
    out["participation"] = {"chg": p,
                            "rsp_minus_spy": (p["RSP"] - p["SPY"]) if p["RSP"] is not None and p["SPY"] is not None else None,
                            "iwm_minus_spy": (p["IWM"] - p["SPY"]) if p["IWM"] is not None and p["SPY"] is not None else None}
    return out


def stockbee(nrows=25):
    url = f"https://docs.google.com/spreadsheets/d/{STOCKBEE_SHEET}/gviz/tq?tqx=out:csv"
    txt = requests.get(url, headers=UA, timeout=30).text
    df = pd.read_csv(io.StringIO(txt), dtype=str)
    df = df.dropna(how="all")
    df = df[df.iloc[:, 0].fillna("").str.match(r"^\d{1,2}/\d{1,2}/\d{4}$")]
    cols = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    rows = df.head(nrows).fillna("").values.tolist()
    return {"columns": cols, "rows": rows, "src": f"https://docs.google.com/spreadsheets/d/{STOCKBEE_SHEET}"}


def run(asof, close, members, out_dir, log):
    asof = str(pd.Timestamp(asof).date())
    ctx = {"asof": asof, "fetched_utc": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M")}
    for name, fn in (("macro", lambda: macro(asof)), ("fear_greed", fear_greed), ("cboe", lambda: cboe_pc(asof)),
                     ("indices", lambda: indices(asof, members, close)), ("stockbee", stockbee)):
        try:
            ctx[name] = fn()
            log(f"Context {name}: ok")
        except Exception as e:  # noqa: BLE001
            ctx[name] = None
            log(f"Context {name} failed: {e!r}")
    with open(os.path.join(out_dir, "context.json"), "w", encoding="utf-8") as fh:
        json.dump(ctx, fh, ensure_ascii=False, indent=1, default=str)
    return ctx
