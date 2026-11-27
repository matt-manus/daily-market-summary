"""
Relative strength vs SPY using the user's TradingView watchlist groups
(data/monitor/watchlist.txt, TradingView "Export list" format:
 ###GROUP,EXCH:TICKER,...).

  ETF groups   : "SECTOR", "GATE ..." and "ARK" sections
  Stock themes : every other section except REGIME / UNFILED

Status buckets (RRG-style, simplified), on excess return vs SPY:
  領先 : ahead over 21 and 63 sessions
  冒起 : ahead over 5 and 21 sessions, still behind over 63
  轉弱 : ahead over 63 sessions but behind over 21
  落後 : behind over 21 and 63 sessions
  其他 : mixed
For a stock theme the excess returns are the theme's median member.
"""
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
WATCHLIST = os.path.join(ROOT, "data", "monitor", "watchlist.txt")
LOOKBACK_CHANGE = 5
SKIP_GROUPS = {"REGIME", "UNFILED"}
MOM_LOOKBACK, MOM_THRESHOLD = 63, 0.20


def group_name(raw):
    name = re.sub(r"^\d+\s*", "", raw.strip())
    return name


def parse_watchlist(path=WATCHLIST):
    s = open(path, encoding="utf-8").read().strip()
    groups, cur = [], None
    for tok in s.replace("\n", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("###"):
            cur = {"raw": tok[3:].strip(), "name": group_name(tok[3:]), "members": []}
            groups.append(cur)
        elif cur is not None:
            exch, _, sym = tok.partition(":")
            if not sym:
                exch, sym = "", tok
            if exch in ("TVC", "FX", "BITSTAMP", "COINBASE", "ICEUS", "NYMEX", "COMEX", "COMEX_MINI") or "!" in sym:
                continue
            cur["members"].append(sym.replace(".", "-"))
    etf, stock = [], []
    for g in groups:
        if g["name"] in SKIP_GROUPS or not g["members"]:
            continue
        if g["name"] == "SECTOR" or g["name"].startswith("GATE") or g["name"] == "ARK":
            g["label"] = g["name"].replace("GATE ", "")
            etf.append(g)
        else:
            g["label"] = g["name"]
            stock.append(g)
    return etf, stock


def download(start, tickers):
    import yfinance as yf
    syms = sorted(set(tickers) | {"SPY"})
    parts = []
    for i in range(0, len(syms), 150):
        chunk = syms[i:i + 150]
        df = yf.download(chunk, start=start, auto_adjust=True, group_by="column",
                         threads=True, progress=False)
        c = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": chunk[0]})
        parts.append(c)
    c = pd.concat(parts, axis=1)
    return c.loc[:, ~c.columns.duplicated()]


def _ex(c, i, n):
    """Excess return (pp) vs SPY over n sessions ending at row i, per column."""
    if i - n < 0:
        return pd.Series(np.nan, index=c.columns)
    r = c.iloc[i] / c.iloc[i - n] - 1
    return 100 * (r - r["SPY"])


def _status(ex5, ex21, ex63):
    if ex21 > 0 and ex63 > 0:
        return "領先"
    if ex5 > 0 and ex21 > 0:
        return "冒起"
    if ex63 > 0 and ex21 < 0:
        return "轉弱"
    if ex21 < 0 and ex63 < 0:
        return "落後"
    return "其他"


def _rank(t):
    t["score"] = 100 * (t["ex21"].rank(pct=True) + t["ex63"].rank(pct=True)) / 2
    t["rank"] = t["score"].rank(ascending=False, method="min").astype(int)
    t["status"] = [_status(a, b, d) for a, b, d in zip(t.ex5, t.ex21, t.ex63)]
    return t


def _etf_table(c, i, etf_groups):
    e5, e21, e63 = _ex(c, i, 5), _ex(c, i, 21), _ex(c, i, 63)
    sma50 = c.iloc[max(0, i - 49):i + 1].mean()
    rows, seen = [], set()
    for g in etf_groups:
        for t in g["members"]:
            if t in seen or t not in c or pd.isna(c[t].iloc[i]) or pd.isna(e63.get(t)):
                continue
            seen.add(t)
            rows.append({"etf": t, "group": g["label"], "ex5": e5[t], "ex21": e21[t], "ex63": e63[t],
                         "above50": bool(c[t].iloc[i] > sma50[t]) if i >= 49 else None})
    return _rank(pd.DataFrame(rows))


def _stock_table(c, i, stock_groups):
    e5, e21, e63 = _ex(c, i, 5), _ex(c, i, 21), _ex(c, i, 63)
    sma50 = c.iloc[max(0, i - 49):i + 1].mean()
    r63 = c.iloc[i] / c.iloc[i - MOM_LOOKBACK] - 1 if i >= MOM_LOOKBACK else pd.Series(np.nan, index=c.columns)
    rows = []
    for g in stock_groups:
        m = [t for t in g["members"] if t in c and pd.notna(c[t].iloc[i]) and pd.notna(e63.get(t))]
        if not m:
            continue
        lead = e21[m].sort_values(ascending=False)
        rows.append({
            "theme": g["label"], "n": len(m), "n_list": len(g["members"]),
            "ex5": float(e5[m].median()), "ex21": float(e21[m].median()), "ex63": float(e63[m].median()),
            "pct50": 100 * float((c[m].iloc[i] > sma50[m]).mean()) if i >= 49 else None,
            "mom": int((r63[m] >= MOM_THRESHOLD).sum()),
            "best": [[t, float(lead[t])] for t in lead.index[:2]],
        })
    return _rank(pd.DataFrame(rows))


def compute_themes(c, asof, etf_groups, stock_groups, extra=()):
    c = c.sort_index()
    i = c.index.get_indexer([pd.Timestamp(asof)])[0]
    if i < 0:
        i = len(c) - 1
    j = i - LOOKBACK_CHANGE

    def with_then(now, then, key):
        return now.merge(then[[key, "rank", "status"]].rename(
            columns={"rank": "rank_then", "status": "status_then"}), on=key, how="left").sort_values("rank")

    etf = with_then(_etf_table(c, i, etf_groups), _etf_table(c, j, etf_groups), "etf")
    stk = with_then(_stock_table(c, i, stock_groups), _stock_table(c, j, stock_groups), "theme")
    listed = {t for g in etf_groups + stock_groups for t in g["members"]}
    missing = sorted(t for t in listed if t not in c or pd.isna(c[t].iloc[i]))
    e5, e21, e63 = _ex(c, i, 5), _ex(c, i, 21), _ex(c, i, 63)
    j5, j21, j63 = _ex(c, j, 5), _ex(c, j, 21), _ex(c, j, 63)
    sma50 = c.iloc[max(0, i - 49):i + 1].mean()
    extra_ex = {t: {"ex5": float(e5[t]), "ex21": float(e21[t]), "ex63": float(e63[t]),
                    "ex5_then": float(j5[t]), "ex21_then": float(j21[t]), "ex63_then": float(j63[t]),
                    "above50": bool(c[t].iloc[i] > sma50[t])}
                for t in extra if t in c and pd.notna(c[t].iloc[i])}
    rel = {}
    for t in ("SPY", "RSP", "IWM"):
        if t in c:
            seg = c[t].iloc[max(0, i - 80):i + 1]
            rel[t] = [[str(d.date()), float(v)] for d, v in seg.items() if pd.notna(v)]
    return {
        "rel_closes": rel,
        "extra_ex": extra_ex,
        "asof": str(c.index[i].date()),
        "then": str(c.index[j].date()),
        "etf_rows": etf.to_dict("records"),
        "stock_rows": stk.to_dict("records"),
        "missing": missing,
        "n_etf": int(len(etf)), "n_theme": int(len(stk)),
    }


def run(start, extra=()):
    etf_groups, stock_groups = parse_watchlist()
    tickers = [t for g in etf_groups + stock_groups for t in g["members"]] + list(extra)
    c = download(start, tickers)
    return c, etf_groups, stock_groups
