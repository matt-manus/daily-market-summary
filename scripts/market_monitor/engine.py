#!/usr/bin/env python3
"""
Market Monitor engine (Kelileo-style breadth + sector momentum).

Data
  - Stock list + industry: NASDAQ stock screener API (api.nasdaq.com)
  - ETF / test-issue flags: NASDAQ Trader symbol directory
  - Daily bars: Yahoo Finance via yfinance
Outputs (data/monitor/)
  - breadth_history.csv : one row per session (kept across runs)
  - latest.json         : today's cards, sector tables, run info
"""
import io
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "monitor")
HIST_CSV = os.path.join(OUT_DIR, "breadth_history.csv")
LATEST_JSON = os.path.join(OUT_DIR, "latest.json")

# ---- rules (match Kelileo where known) ----
MIN_PRICE = 5.0
MIN_VOL = 300_000            # breadth universe: shares traded that day
MIN_DOLLAR_VOL = 5_000_000   # momentum universe: close x volume that day
MOM_LOOKBACK = 63            # trading days (~1 quarter)
MOM_THRESHOLD = 0.20         # +20% over the lookback
DELTA_DAYS = 21              # Δlift / pace comparison window
MIN_BASE = 20                # industries with fewer stocks are not ranked
Z_CUT = 1.96
PREFILTER_PRICE = 2.0        # skip names below $2 today to cut download size

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}

EXCLUDE_NAME = re.compile(
    r"\b(warrants?|rights?|units?|preferred|pfd|notes due|debentures?|subordinated|"
    r"fixed[- ]to[- ]floating|perpetual|cumulative|convertible|fund|municipal|"
    r"closed[- ]end|etn|exchange[- ]traded)\b", re.I)

log_lines = []


def log(msg):
    line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z] {msg}"
    print(line, flush=True)
    log_lines.append(line)


def yahoo_symbol(sym):
    return str(sym).strip().upper().replace("/", "-").replace(".", "-").replace("^", "-P")


# --------------------------------------------------------------------------
# Universe
# --------------------------------------------------------------------------
def fetch_nasdaq_screener():
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0&download=true"
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    rows = r.json()["data"]["rows"]
    df = pd.DataFrame(rows)
    df["symbol"] = df["symbol"].astype(str).str.strip()
    return df


def fetch_symdir():
    frames = []
    for url, symcol in [
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "Symbol"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "ACT Symbol"),
    ]:
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        txt = "\n".join(l for l in r.text.splitlines() if not l.startswith("File Creation Time"))
        d = pd.read_csv(io.StringIO(txt), sep="|", dtype=str, keep_default_na=False)
        d = d.rename(columns={symcol: "symbol"})
        frames.append(d[["symbol", "Security Name", "ETF", "Test Issue"]])
    return pd.concat(frames, ignore_index=True)


def build_universe():
    info = {"screener_ok": False, "symdir_ok": False}
    scr = sd = None
    try:
        scr = fetch_nasdaq_screener()
        info["screener_ok"] = True
        log(f"NASDAQ screener rows: {len(scr)}")
    except Exception as e:  # noqa: BLE001
        log(f"NASDAQ screener FAILED: {e!r}")
    try:
        sd = fetch_symdir()
        info["symdir_ok"] = True
        log(f"NASDAQ Trader symbol directory rows: {len(sd)}")
    except Exception as e:  # noqa: BLE001
        log(f"NASDAQ Trader symbol directory FAILED: {e!r}")
    if scr is None and sd is None:
        raise SystemExit("No stock list source reachable — stopping.")

    if sd is not None:
        sd = sd[(sd["ETF"] == "N") & (sd["Test Issue"] == "N")].copy()
        # Name filter uses the screener's names (26/11/26). NASDAQ Trader labels
        # NASDAQ-listed BDCs "- Closed End Fund", which wrongly dropped them while
        # NYSE-listed BDCs stayed. Symbol-directory names are only used as a fallback.
        sd_name_hit = sd["Security Name"].fillna("").str.contains(EXCLUDE_NAME)
        if scr is None:
            sd = sd[~sd_name_hit]
        else:
            sd_dropped_before = set(sd.loc[sd_name_hit, "symbol"])
        sd["ysym"] = sd["symbol"].map(yahoo_symbol)

    if scr is not None:
        scr = scr[~scr["name"].fillna("").str.contains(EXCLUDE_NAME)].copy()
        scr["ysym"] = scr["symbol"].map(yahoo_symbol)
        scr["lastsale_num"] = pd.to_numeric(
            scr["lastsale"].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
        if sd is not None:
            scr = scr[scr["ysym"].isin(set(sd["ysym"]))]
        scr = scr[scr["lastsale_num"].fillna(0) >= PREFILTER_PRICE]
        if sd is not None:
            back = scr[scr["symbol"].isin(sd_dropped_before)]
            log(f"Kept by screener name but flagged by symbol-directory name: {len(back)} "
                + "; ".join(f"{r.symbol}={r['name']}" for _, r in back.head(40).iterrows()))
        uni = scr[["ysym", "name", "sector", "industry"]].copy()
    else:
        uni = sd[["ysym", "Security Name"]].rename(columns={"Security Name": "name"})
        uni["sector"] = ""
        uni["industry"] = ""

    # simple symbols only (drop odd share classes / test tickers Yahoo can't price)
    uni = uni[uni["ysym"].str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?")]
    uni = uni.drop_duplicates("ysym").reset_index(drop=True)
    uni["industry"] = uni["industry"].fillna("").replace("", "Unclassified")
    uni["sector"] = uni["sector"].fillna("")
    info["candidates"] = int(len(uni))
    log(f"Candidate tickers after filters: {len(uni)}")
    return uni, info


# --------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------
def download_bars(tickers, start, batch=200, pause=2.0):
    import yfinance as yf
    closes, vols, failed = [], [], []
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        for attempt in range(3):
            try:
                df = yf.download(chunk, start=start, auto_adjust=False, group_by="column",
                                 threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001
                log(f"batch {i // batch} attempt {attempt + 1} failed: {e!r}")
                time.sleep(10 * (attempt + 1))
                df = None
        if df is None or df.empty:
            failed += chunk
            continue
        c = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": chunk[0]})
        v = df["Volume"] if isinstance(df.columns, pd.MultiIndex) else df[["Volume"]].rename(columns={"Volume": chunk[0]})
        closes.append(c)
        vols.append(v)
        got = set(c.columns[c.notna().any()])
        failed += [t for t in chunk if t not in got]
        if (i // batch) % 5 == 0:
            log(f"downloaded {min(i + batch, len(tickers))}/{len(tickers)}")
        time.sleep(pause)
    close = pd.concat(closes, axis=1) if closes else pd.DataFrame()
    vol = pd.concat(vols, axis=1) if vols else pd.DataFrame()
    close = close.loc[:, ~close.columns.duplicated()]
    vol = vol.loc[:, ~vol.columns.duplicated()]
    return close, vol, failed


def wilder_atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def index_atr_distance(start):
    import yfinance as yf
    out = {}
    for sym in ["SPY", "QQQ", "^GSPC"]:
        df = yf.download(sym, start=start, auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        out[sym] = df
    res = pd.DataFrame(index=out["SPY"].index)
    for sym in ["SPY", "QQQ"]:
        d = out[sym]
        ema50 = d["Close"].ewm(span=50, adjust=False, min_periods=50).mean()
        pc = d["Close"].shift(1)
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
        atr_sma = tr.rolling(14, min_periods=14).mean()
        atr_w = wilder_atr(d["High"], d["Low"], d["Close"], 14)
        res[f"{sym.lower()}_atr"] = (d["Close"] - ema50) / atr_sma
        res[f"{sym.lower()}_atr_w"] = (d["Close"] - ema50) / atr_w
    res["sp500"] = out["^GSPC"]["Close"].reindex(res.index)
    now_et = pd.Timestamp.now(tz="America/New_York")
    if len(res) and res.index[-1].date() == now_et.date() and (now_et.hour, now_et.minute) < (16, 45):
        log(f"Dropping {res.index[-1].date()}: US session not closed yet (ET {now_et:%H:%M})")
        res = res.iloc[:-1]
    return res


# --------------------------------------------------------------------------
# Breadth (pure functions — unit-testable)
# --------------------------------------------------------------------------
def compute_breadth(close, vol):
    close = close.sort_index()
    vol = vol.reindex_like(close)
    prev = close.shift(1)
    ret1 = close / prev - 1
    ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    ret_mom = close / close.shift(MOM_LOOKBACK) - 1

    valid = close.notna() & prev.notna()
    b_uni = valid & (close >= MIN_PRICE) & (vol >= MIN_VOL)
    m_uni = valid & (close >= MIN_PRICE) & (vol >= MIN_VOL) & (close * vol >= MIN_DOLLAR_VOL) & ret_mom.notna()

    up4 = (b_uni & (ret1 >= 0.04)).sum(axis=1)
    dn4 = (b_uni & (ret1 <= -0.04)).sum(axis=1)
    e20 = b_uni & ema20.notna()
    e50 = b_uni & sma50.notna()
    pct20 = 100 * (e20 & (close > ema20)).sum(axis=1) / e20.sum(axis=1).replace(0, np.nan)
    pct50 = 100 * (e50 & (close > sma50)).sum(axis=1) / e50.sum(axis=1).replace(0, np.nan)
    mom_n = (m_uni & (ret_mom >= MOM_THRESHOLD)).sum(axis=1)
    mom_u = m_uni.sum(axis=1)

    h = pd.DataFrame({
        "universe": b_uni.sum(axis=1),
        "up4": up4, "dn4": dn4,
        "pct20": pct20, "pct50": pct50,
        "mom_n": mom_n, "mom_univ": mom_u,
    })
    h["ratio10"] = h["up4"].rolling(10).sum() / h["dn4"].rolling(10).sum().replace(0, np.nan)
    h["mom_pct"] = 100 * h["mom_n"] / h["mom_univ"].replace(0, np.nan)
    # drop sessions with too few stocks priced (warm-up, or a partial bar)
    good = h["universe"] >= 0.5 * h["universe"].rolling(20, min_periods=1).median()
    h = h[good & (h["mom_univ"] > 0)]
    return h


def compute_sectors(close, vol, uni, asof, keyfn=None):
    """Kelileo-style industry table for session `asof`."""
    close = close.sort_index()
    i = close.index.get_loc(asof)
    if i < MOM_LOOKBACK + DELTA_DAYS:
        return None
    c0 = close.iloc[i]
    v0 = vol.reindex_like(close).iloc[i]
    r63 = c0 / close.iloc[i - MOM_LOOKBACK] - 1
    r21 = c0 / close.iloc[i - DELTA_DAYS] - 1
    prev = close.iloc[i - 1]
    in_u = c0.notna() & prev.notna() & (c0 >= MIN_PRICE) & (v0 >= MIN_VOL) & (c0 * v0 >= MIN_DOLLAR_VOL) & r63.notna()
    U = in_u[in_u].index
    raw_ind = uni.set_index("ysym")["industry"].reindex(U).fillna("Unclassified")
    ind = raw_ind
    unmapped = []
    if keyfn is not None:
        ind = raw_ind.map(lambda x: keyfn(x) or "Unclassified")
        unmapped = sorted({str(x).strip() for x, g in zip(raw_ind, ind)
                           if g == "Unclassified" and str(x).strip() not in ("", "Unclassified", "nan")})

    mom = (r63[U] >= MOM_THRESHOLD)
    N, K = len(U), int(mom.sum())
    p = K / N if N else float("nan")

    # 21 sessions ago, same fixed set of stocks (Kelileo: "固定同一批股票")
    r63_then = close.iloc[i - DELTA_DAYS] / close.iloc[i - DELTA_DAYS - MOM_LOOKBACK] - 1
    has_then = r63_then[U].notna()
    mom_then = (r63_then[U] >= MOM_THRESHOLD) & has_then
    p_then = mom_then.sum() / has_then.sum() if has_then.sum() else float("nan")

    rows = []
    for g, idx in ind.groupby(ind).groups.items():
        n = len(idx)
        k = int(mom[idx].sum())
        share = k / n
        lift = share / p if p else float("nan")
        z = (k - n * p) / math.sqrt(n * p * (1 - p)) if 0 < p < 1 else float("nan")
        med63 = float(np.nanmedian(r63[idx])) * 100
        med21 = float(np.nanmedian(r21[idx])) * 100
        n_then = int(has_then[idx].sum())
        lift_then = ((mom_then[idx].sum() / n_then) / p_then) if n_then and p_then else float("nan")
        mom_idx = [t for t in idx if mom[t]]
        mom_list = sorted(mom_idx, key=lambda t: -float(r63[t]))
        rows.append({
            "industry": g, "base": n, "mom": k, "share": 100 * share, "lift": lift, "z": z,
            "median63": med63, "median21": med21, "pace": med21 - med63 / 3,
            "lift_then": lift_then, "dlift": lift - lift_then,
            "mom_list": [[t, 100 * float(r63[t])] for t in mom_list],
            "members": ([[str(k).strip(), int(v)] for k, v in raw_ind[idx].value_counts().items()]
                        if keyfn is not None else None),
        })
    t = pd.DataFrame(rows)
    corr = float(t.loc[t["base"] >= MIN_BASE, ["dlift", "pace"]].corr().iloc[0, 1]) if len(t) > 2 else float("nan")
    return {
        "asof": str(pd.Timestamp(asof).date()),
        "N": N, "K": K, "p": 100 * p, "p_then": 100 * p_then,
        "n_groups": int((t["industry"] != "Unclassified").sum()),
        "n_ranked": int(((t["base"] >= MIN_BASE) & (t["industry"] != "Unclassified")).sum()),
        "n_small": int(((t["base"] < MIN_BASE) & (t["industry"] != "Unclassified")).sum()),
        "unclassified": t[t["industry"] == "Unclassified"].to_dict("records"),
        "dlift_pace_corr": corr,
        "unmapped": unmapped,
        "rows": t[t["industry"] != "Unclassified"].to_dict("records"),
    }


def clean(o):
    """Make an object JSON-safe: NaN/inf -> None, numpy scalars -> Python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    return o


# --------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    started = datetime.now(timezone.utc)
    start = (started - timedelta(days=760)).strftime("%Y-%m-%d")

    uni, info = build_universe()
    close, vol, failed = download_bars(uni["ysym"].tolist(), start)
    log(f"Bars: {close.shape[1]} tickers x {close.shape[0]} days; no data for {len(failed)}")
    if close.empty:
        raise SystemExit("No price data — stopping.")

    # retry tickers that have history but no bar on the latest session
    last = close.index[-1]
    miss = [t for t in close.columns if pd.isna(close.at[last, t]) and close[t].notna().any()]
    log(f"Missing latest bar ({pd.Timestamp(last).date()}): {len(miss)} tickers, e.g. {miss[:15]}")
    if miss:
        rstart = (pd.Timestamp(last) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        rc, rv, _ = download_bars(miss, rstart, batch=50)
        if not rc.empty:
            rc.index = pd.to_datetime(rc.index)
            close.index = pd.to_datetime(close.index)
            vol.index = pd.to_datetime(vol.index)
            for t in rc.columns:
                ok = rc[t].dropna()
                ok = ok[ok.index.isin(close.index)]
                close.loc[ok.index, t] = ok
                vol.loc[ok.index, t] = rv[t].reindex(ok.index)
        still = [t for t in miss if pd.isna(close.at[last, t])]
        log(f"Retry recovered {len(miss) - len(still)}; still missing {len(still)}, e.g. {still[:15]}")
    # diagnostics: how many tickers are priced on the last few sessions
    for d in close.index[-3:]:
        log(f"Stocks priced on {pd.Timestamp(d).date()}: {int(close.loc[d].notna().sum())}")
    idx = index_atr_distance(start)
    log(f"SPY/QQQ/^GSPC last session: {pd.Timestamp(idx.index[-1]).date()}")
    close = close.reindex(idx.index)
    vol = vol.reindex(idx.index)

    h = compute_breadth(close, vol).join(idx, how="left")
    # export the latest session's universe, one row per candidate ticker
    try:
        d = h.index[-1]
        di = close.index.get_indexer([pd.Timestamp(d)])[0]
        c0, v0 = close.iloc[di], vol.iloc[di]
        pc = close.iloc[di - 1]
        old = close.iloc[di - MOM_LOOKBACK] if di >= MOM_LOOKBACK else pd.Series(np.nan, index=close.columns)
        ind = uni.set_index("ysym")["industry"]
        ex = pd.DataFrame({"close": c0, "volume": v0, "dollar_vol": c0 * v0,
                           "close_63d_ago": old, "ret_63d_pct": 100 * (c0 / old - 1)})
        ex["has_bar"] = c0.notna() & pc.notna()
        ex["breadth_universe"] = ex.has_bar & (c0 >= MIN_PRICE) & (v0 >= MIN_VOL)
        ex["momentum_universe"] = ex.breadth_universe & (c0 * v0 >= MIN_DOLLAR_VOL) & old.notna()
        ex["momentum_stock"] = ex.momentum_universe & (c0 / old - 1 >= MOM_THRESHOLD)
        ex["industry"] = ind.reindex(ex.index)
        ex.index.name = "ticker"
        ex.sort_index().round(4).to_csv(os.path.join(OUT_DIR, "universe_latest.csv"))
        log(f"Universe export {d}: breadth {int(ex.breadth_universe.sum())}, momentum universe "
            f"{int(ex.momentum_universe.sum())}, momentum {int(ex.momentum_stock.sum())}")
    except Exception as e:  # noqa: BLE001
        log(f"Universe export failed: {e!r}")
    # diagnostics: volume near the 300k line on the latest session
    try:
        d = close.index[-1]
        c0, v0 = close.loc[d], vol.loc[d]
        for t in ["CWT", "NTGR", "INDB"]:
            if t in close.columns:
                log(f"Diag {pd.Timestamp(d).date()} {t}: close {c0[t]:.2f} volume {v0[t]:,.0f}")
        near = ((c0 >= MIN_PRICE) & (c0 * v0 >= MIN_DOLLAR_VOL) & (v0 < MIN_VOL)).sum()
        log(f"Diag: pass $5 and $5M but volume < 300k: {int(near)}")
    except Exception as e:  # noqa: BLE001
        log(f"Diag failed: {e!r}")
    dropped = [str(pd.Timestamp(d).date()) for d in close.index[-5:] if d not in h.index]
    if dropped:
        log(f"Sessions dropped by breadth filter (too few stocks priced): {dropped}")
    h.index = pd.to_datetime(h.index).date
    h.index.name = "date"

    # keep older rows from previous runs, overwrite overlapping dates
    if os.path.exists(HIST_CSV):
        old = pd.read_csv(HIST_CSV, index_col="date")
        old.index = pd.to_datetime(old.index).date
        old = old[old.index < min(h.index)]
        h = pd.concat([old, h]).sort_index()
    h.index.name = "date"
    h.round(4).to_csv(HIST_CSV)

    asof = close.index[close.index.get_indexer([pd.Timestamp(h.index[-1])])[0]]
    sectors = compute_sectors(close, vol, uni, asof)
    groups = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from groups import group_of
        groups = compute_sectors(close, vol, uni, asof, keyfn=group_of)
        log(f"Groups: {groups['n_ranked']} ranked; unmapped industries {groups['unmapped']}")
    except Exception as e:  # noqa: BLE001
        log(f"Groups failed: {e!r}")

    themes = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import themes as th_mod
        tc, etf_g, stk_g = th_mod.run(start)
        themes = th_mod.compute_themes(tc, asof, etf_g, stk_g)
        log(f"Themes: {themes['n_etf']} ETFs, {themes['n_theme']} stock themes; missing {themes['missing']}")
    except Exception as e:  # noqa: BLE001
        log(f"Themes failed: {e!r}")

    latest = {
        "run_utc": started.strftime("%Y-%m-%d %H:%M"),
        "session": str(h.index[-1]),
        "rules": {
            "breadth_universe": f"US common stocks + ADRs (no ETFs/funds/preferreds/warrants/units), close >= ${MIN_PRICE:.0f}, volume >= {MIN_VOL:,} shares that day",
            "momentum_universe": f"close >= ${MIN_PRICE:.0f}, volume >= {MIN_VOL:,} shares, dollar volume >= ${MIN_DOLLAR_VOL/1e6:.0f}M that day; momentum stock = up >= {int(MOM_THRESHOLD*100)}% over {MOM_LOOKBACK} trading days",
            "ma": "% above 20-day EMA and 50-day SMA",
            "atr": "SPY/QQQ: (close - 50-day EMA) / 14-day ATR (simple average of true range)",
            "prefilter": f"tickers priced below ${PREFILTER_PRICE:.0f} today are skipped",
        },
        "universe_info": info,
        "no_data_tickers": len(failed),
        "sectors": sectors,
        "groups": groups,
        "themes": themes,
        "log": log_lines,
    }
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(clean(latest), f, ensure_ascii=False, indent=1, allow_nan=False)
    log(f"Done. Session {latest['session']}; history rows {len(h)}")


if __name__ == "__main__":
    sys.exit(main())
