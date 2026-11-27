#!/usr/bin/env python3
"""Compute every number for the US close report from files fetched this run.
Usage: compute.py RUN_DIR SESSION(YYYY-MM-DD)  -> RUN_DIR/results.json"""
import json, os, sys, math
import numpy as np

RUN, SESSION = sys.argv[1], sys.argv[2]
CACHE = os.path.join(RUN, "cache")
WINDOW = 65

def load(sym):
    p = os.path.join(CACHE, sym.replace("/", "_").replace("^", "IDX_").replace("=", "_") + ".json")
    if not os.path.exists(p): return None
    d = json.load(open(p))
    if d.get("error"): return None
    bars = [b for b in d["bars"] if b["d"] <= SESSION]
    return bars or None

def ema_series(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n: return out
    k = 2 / (n + 1); e = float(np.mean(x[:n])); out[n - 1] = e
    for i in range(n, len(x)):
        e = x[i] * k + e * (1 - k); out[i] = e
    return out

def sma_series(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n: return out
    c = np.cumsum(np.insert(x, 0, 0.0)); out[n - 1:] = (c[n:] - c[:-n]) / n
    return out

def rsi_series(x, n=14):
    out = np.full(len(x), np.nan)
    if len(x) < n + 1: return out
    d = np.diff(x); g = np.maximum(d, 0); l = np.maximum(-d, 0)
    ag, al = g[:n].mean(), l[:n].mean()
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n; al = (al * (n - 1) + l[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

def atr_series(h, l, c, n=14):
    out = np.full(len(c), np.nan)
    if len(c) < n + 1 or np.isnan(h).any() or np.isnan(l).any(): return out
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    a = tr[:n].mean(); out[n] = a
    for i in range(n, len(tr)):
        a = (a * (n - 1) + tr[i]) / n; out[i + 1] = a
    return out

def last_on(bars, key="c"):
    if not bars or bars[-1]["d"] != SESSION: return None
    return bars

res = {"session": SESSION}

# ---------- macro ----------
macro = {}
for key, sym in (("VIX", "^VIX"), ("DXY", "DX-Y.NYB"), ("TNX", "^TNX"), ("GOLD", "GC=F"), ("OIL", "CL=F"), ("BTC", "BTC-USD")):
    b = load(sym)
    if not b or b[-1]["d"] != SESSION or len(b) < 2:
        macro[key] = None; continue
    macro[key] = {"sym": sym, "date": b[-1]["d"], "price": b[-1]["c"], "prev": b[-2]["c"], "prev_date": b[-2]["d"], "chg": b[-1]["c"] / b[-2]["c"] - 1}
res["macro"] = macro

# ---------- index ETFs and sector ETFs ----------
def etf_stats(sym):
    b = load(sym)
    if not b or b[-1]["d"] != SESSION: return None
    a = np.array([x["a"] for x in b], float); c = b[-1]["c"]
    s20, s50, s200 = sma_series(a, 20)[-1], sma_series(a, 50)[-1], sma_series(a, 200)[-1]
    return {"sym": sym, "close": c, "chg": a[-1] / a[-2] - 1, "rsi": float(rsi_series(a)[-1]),
            "ma20": float(s20), "ma50": float(s50), "ma200": float(s200),
            "vs20": a[-1] / s20 - 1, "vs50": a[-1] / s50 - 1, "vs200": a[-1] / s200 - 1, "bars": len(b)}
res["indices"] = {s: etf_stats(s) for s in ("SPY", "QQQ", "DIA", "IWM")}
# ---------- participation row (Section 3): SPY vs RSP (equal weight) vs IWM, 1-day change ----------
# Same basis as the Section 3 1D change: dividend-adjusted close vs the prior adjusted close (etf_stats "chg").
_rsp = etf_stats("RSP")
_p = {"SPY": res["indices"].get("SPY"), "RSP": _rsp, "IWM": res["indices"].get("IWM")}
_c = {k: (v["chg"] if v else None) for k, v in _p.items()}
res["participation"] = {"chg": _c,
                        "rsp_minus_spy": (_c["RSP"] - _c["SPY"]) if _c["RSP"] is not None and _c["SPY"] is not None else None,
                        "iwm_minus_spy": (_c["IWM"] - _c["SPY"]) if _c["IWM"] is not None and _c["SPY"] is not None else None,
                        "rsp": _rsp}
res["sectors"] = sorted([x for x in (etf_stats(s) for s in ("XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLU")) if x], key=lambda r: -r["rsi"])

# ---------- Dow 30 from Yahoo (Finviz has no Dow filter) ----------
cons = json.load(open(os.path.join(RUN, "constituents.json")))
dj = {"total": 0, "a20": 0, "a50": 0, "a200": 0, "up": 0, "down": 0, "unch": 0}
for s in cons.get("DJIA", {}).get("syms", []):
    b = load(s.replace(".", "-"))
    if not b or b[-1]["d"] != SESSION or len(b) < 200: continue
    c = np.array([x["c"] for x in b], float)
    dj["total"] += 1
    dj["a20"] += c[-1] > c[-20:].mean(); dj["a50"] += c[-1] > c[-50:].mean(); dj["a200"] += c[-1] > c[-200:].mean()
    if c[-1] > c[-2]: dj["up"] += 1
    elif c[-1] < c[-2]: dj["down"] += 1
    else: dj["unch"] += 1
res["dow"] = {k: int(v) for k, v in dj.items()}
res["finviz"] = json.load(open(os.path.join(RUN, "finviz.json")))

# ---------- section 7 tape (note-rule momentum) ----------
# Momentum definition (only): close >= close from 63 SPY sessions earlier * 1.20.
# Universe: today's NASDAQ screener common/ordinary shares and ADRs listed on US exchanges (including foreign-registered issuers).
# On the session: close >= $5, volume >= 300,000, dollar volume >= $5,000,000.
# Breadth (+4%/-4%, above 20-day EMA, above 50-day SMA) counted in that same universe.
uni = json.load(open(os.path.join(RUN, "universe.json")))
spy = load("SPY"); cal = [x["d"] for x in spy]
win = cal[-WINDOW:]
assert win[-1] == SESSION
lookback = {d: cal[cal.index(d) - 63] for d in win}
per = {d: {"n": 0, "up": 0, "down": 0, "a20": 0, "a20d": 0, "a50": 0, "a50d": 0, "mom": 0, "ind_pool": {}, "ind_mom": {}} for d in win}
winset = set(win)
for y, meta in uni.items():
    b = load(y)
    if not b: continue
    c = np.array([x["c"] for x in b], float); v = np.array([x["v"] or 0 for x in b], float)
    dates = [x["d"] for x in b]
    date_to_i = {d: i for i, d in enumerate(dates)}
    e20 = ema_series(c, 20); s50 = sma_series(c, 50)
    ind = meta["industry"]
    for i, d in enumerate(dates):
        if d not in winset: continue
        if not (c[i] >= 5 and v[i] >= 300000 and c[i] * v[i] >= 5_000_000): continue
        P = per[d]; P["n"] += 1
        P["ind_pool"][ind] = P["ind_pool"].get(ind, 0) + 1
        if i >= 1:
            r = c[i] / c[i - 1] - 1
            if r >= 0.04: P["up"] += 1
            elif r <= -0.04: P["down"] += 1
        if not np.isnan(e20[i]):
            P["a20d"] += 1; P["a20"] += c[i] > e20[i]
        if not np.isnan(s50[i]):
            P["a50d"] += 1; P["a50"] += c[i] > s50[i]
        j = date_to_i.get(lookback[d])
        if j is not None and c[j] and c[i] >= 1.20 * c[j]:
            P["mom"] += 1; P["ind_mom"][ind] = P["ind_mom"].get(ind, 0) + 1
daily = []
for d in win:
    P = per[d]
    daily.append({"date": d, "n": P["n"], "up": P["up"], "down": P["down"], "a20": int(P["a20"]), "a20d": P["a20d"], "a50": int(P["a50"]), "a50d": P["a50d"], "mom": P["mom"]})
res["daily"] = daily
# ---------- breadth vs 5 sessions ago (top-of-page line), from the same Section 7 daily series ----------
def _bvals(d):
    return {"a20": d["a20"] / d["a20d"] * 100 if d["a20d"] else None,
            "a50": d["a50"] / d["a50d"] * 100 if d["a50d"] else None,
            "mom": d["mom"] / d["n"] * 100 if d["n"] else None,
            "up": d["up"], "down": d["down"]}
if len(daily) >= 6:
    _t, _b = daily[-1], daily[-6]
    res["breadth_vs5"] = {"date": _t["date"], "ref_date": _b["date"], "today": _bvals(_t), "ref": _bvals(_b)}
else:
    res["breadth_vs5"] = None
L = per[SESSION]; share = L["mom"] / L["n"]
inds = []
for ind, m in L["ind_mom"].items():
    pool = L["ind_pool"][ind]
    inds.append({"industry": ind, "mom": m, "pool": pool, "pen": m / pool, "excess": m / pool - share})
inds.sort(key=lambda r: (-r["mom"], r["industry"]))
res["industries_all"] = inds
shown = [r for r in inds if r["mom"] >= 5]
res["industries"] = shown
top5 = [r["industry"] for r in shown[:5]]
ex = {}
for ind in top5:
    s = []
    for d in win:
        P = per[d]; pool = P["ind_pool"].get(ind, 0)
        s.append(None if pool == 0 else (P["ind_mom"].get(ind, 0) / pool - P["mom"] / P["n"]) * 100)
    ex[ind] = s
res["excess_top5"] = {"industries": top5, "dates": win, "series": ex}

# ---------- participation trend (top-of-page chart): SPY / RSP / IWM over the last TREND_N SPY sessions ----------
# Daily change = adjusted close vs prior adjusted close (same basis as Section 3). Cumulative = adjusted close vs the
# adjusted close of the session just before the window (base), so the first shown session's cumulative = its daily change.
TREND_N = 20
_tw = cal[-(TREND_N + 1):]
_maps = {}
for _s in ("SPY", "RSP", "IWM"):
    _b = load(_s); _maps[_s] = {x["d"]: x["a"] for x in _b} if _b else {}
_rows = []
for _k in range(1, len(_tw)):
    _d, _pd, _b0 = _tw[_k], _tw[_k - 1], _tw[0]
    _r = {"date": _d}
    for _s, _m in _maps.items():
        _r[_s] = (_m[_d] / _m[_pd] - 1) if (_d in _m and _pd in _m) else None
        _r[_s + "_cum"] = (_m[_d] / _m[_b0] - 1) if (_d in _m and _b0 in _m) else None
    _rows.append(_r)
res["participation_series"] = {"base_date": _tw[0], "rows": _rows}

# ---------- 10-year note-rule share, latest session (same definition as Section 7) ----------
# Keep the historical mom_universe_syms pass as a cross-check; headline numbers come from Section 7.
ten = json.load(open("/workspace/market-report/state/mom_universe_syms.json"))
back = lookback[SESSION]
nu = nm = 0
for s in ten:
    b = load(s.replace("/", "-").replace(".", "-"))
    if not b or b[-1]["d"] != SESSION: continue
    c, v = b[-1]["c"], b[-1]["v"] or 0
    if not (c >= 5 and v >= 300000 and c * v >= 5_000_000): continue
    nu += 1
    prev = next((x["c"] for x in b if x["d"] == back), None)
    if prev and c >= 1.20 * prev: nm += 1
# The static cross-check list can lag today's NASDAQ screener (new listings/renames).
# On 2026-11-27 the list and the historical month-end series were restated to include
# US-listed foreign-registered ordinary shares (same include_row rule as Section 7).
# Allow universe gaps that come only from screener names absent from the list or from
# static-list names that left the screener; momentum must still match (nm <= Section 7 mom).
# Section 7 remains the headline.
tset = {s.replace("/", "-").replace(".", "-") for s in ten}
newnames = [y for y in uni if y not in tset]
def _q(y):
    b = load(y)
    if not b or b[-1]["d"] != SESSION: return False
    c, v = b[-1]["c"], b[-1]["v"] or 0
    return c >= 5 and v >= 300000 and c * v >= 5_000_000
gap = [y for y in newnames if _q(y)]
# Also tolerate static-list names that no longer appear on today's screener (e.g. TCBI on 2026-10-08).
static_only = [s.replace("/", "-").replace(".", "-") for s in ten
               if s.replace("/", "-").replace(".", "-") not in uni and _q(s.replace("/", "-").replace(".", "-"))]
assert nu - len(static_only) + len(gap) == L["n"] and nm <= L["mom"], (nu, L["n"], nm, L["mom"], gap, static_only)
res["crosscheck_note"] = {"static_list_universe": nu, "static_list_momentum": nm,
                          "screener_names_not_in_list_qualifying": gap,
                          "static_list_names_not_on_screener_qualifying": static_only}
res["ten_year_latest"] = {"date": SESSION, "universe": L["n"], "momentum": L["mom"], "share": share, "lookback_date": back, "symbols": len(uni), "crosscheck_symbols": len(ten)}
json.dump(res, open(os.path.join(RUN, "results.json"), "w"), indent=1, default=float)
print(json.dumps({k: res[k] for k in ("macro", "dow", "ten_year_latest")}, indent=1, default=float))
print(daily[-5:]); print(shown[:6]); print([ (r["sym"], round(r["rsi"],1)) for r in res["sectors"]])
for k, v in res["indices"].items(): print(k, v)
print("participation_series", res["participation_series"]["base_date"], res["participation_series"]["rows"][-1]); print("participation", {k: v for k, v in res["participation"].items() if k != "rsp"}); print("breadth_vs5", res["breadth_vs5"])
