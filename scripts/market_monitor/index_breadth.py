"""
4A: % of index constituents above their 20/50/200-day simple moving averages,
as a daily history (for a line chart). Uses *today's* member lists for the
whole history (no point-in-time membership), so older values are approximate.

Members: S&P 500, Nasdaq-100 and Dow 30 from Wikipedia; Russell 2000 from the
iShares IWM holdings file (skipped if it cannot be read).
"""
import io
import os

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (market-monitor; github actions)"}
WIKI = {
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"], (450, 600)),
    "Nasdaq-100": ("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"], (90, 110)),
    "Dow 30": ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", ["Symbol", "Ticker"], (28, 32)),
}
IWM_URL = ("https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax"
           "?fileType=csv&fileName=IWM_holdings&dataType=fund")
HIST_DAYS = 260  # sessions kept in the output


def _ysym(s):
    return str(s).strip().replace(".", "-").replace("/", "-")


def wiki_members(url, cols, expect=(20, 600), log=print):
    html = requests.get(url, headers=UA, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    best = None
    for t in tables:
        if isinstance(t.columns, pd.MultiIndex):
            t.columns = [" ".join(str(x) for x in c if "Unnamed" not in str(x)).strip() for c in t.columns]
        hit = [c for c in t.columns if any(k.lower() in str(c).lower() for k in cols)]
        if hit and expect[0] <= len(t) <= expect[1]:
            if best is None or len(t) > len(best[0]):
                best = (t, hit[0])
    if best is None:
        log(f"4A no matching table at {url}; tables: {[ (len(t), list(map(str, t.columns))[:5]) for t in tables[:6]]}")
        return []
    t, c = best
    vals = [str(x).split(":")[-1].strip() for x in t[c].dropna()]
    return sorted({_ysym(x) for x in vals if x and x.lower() != "nan"})


def iwm_members():
    r = requests.get(IWM_URL, headers=UA, timeout=30)
    lines = r.text.splitlines()
    k = next((i for i, l in enumerate(lines) if l.startswith("Ticker,")), None)
    if k is None:
        raise ValueError(f"no holdings table (HTTP {r.status_code}, {len(r.text)} bytes, starts {r.text[:80]!r})")
    df = pd.read_csv(io.StringIO("\n".join(lines[k:])))
    df = df[df.get("Asset Class", "Equity") == "Equity"]
    return sorted({_ysym(x) for x in df["Ticker"].dropna() if str(x).strip() not in ("-", "")})


def members(log):
    out = {}
    for name, (url, cols, expect) in WIKI.items():
        try:
            out[name] = wiki_members(url, cols, expect, log)
            log(f"4A members {name}: {len(out[name])}")
        except Exception as e:  # noqa: BLE001
            log(f"4A members {name} failed: {e!r}")
    try:
        out["Russell 2000"] = iwm_members()
        log(f"4A members Russell 2000 (IWM holdings): {len(out['Russell 2000'])}")
    except Exception as e:  # noqa: BLE001
        log(f"4A members Russell 2000 failed: {e!r}")
    return out


def compute(close, mem, download, start, log):
    """close: date x ticker closes already downloaded. download(tickers, start)
    -> (close, vol, failed) for any members not in close."""
    need = sorted({t for v in mem.values() for t in v} - set(close.columns))
    if need:
        extra, _, _ = download(need, start)
        extra.index = pd.to_datetime(extra.index)
        close = close.join(extra.reindex(close.index), how="left")
        log(f"4A downloaded {len(need)} extra members")
    rows = []
    for name, tick in mem.items():
        cols = [t for t in tick if t in close.columns]
        if not cols:
            continue
        c = close[cols]
        for n in (20, 50, 200):
            sma = c.rolling(n, min_periods=n).mean()
            ok = c.notna() & sma.notna()
            pct = 100 * ((c > sma) & ok).sum(axis=1) / ok.sum(axis=1).where(ok.sum(axis=1) > 0)
            rows.append(pct.rename(f"{name}|{n}"))
        log(f"4A {name}: {len(cols)}/{len(tick)} members priced")
    if not rows:
        return None
    out = pd.concat(rows, axis=1).iloc[-HIST_DAYS:]
    out.index.name = "date"
    return out.round(2)


def run(close, download, start, out_dir, log):
    mem = members(log)
    df = compute(close, mem, download, start, log)
    if df is not None:
        df.to_csv(os.path.join(out_dir, "index_breadth.csv"))
        counts = {k: len(v) for k, v in mem.items()}
        pd.Series(counts).to_json(os.path.join(out_dir, "index_members.json"))
    return df
