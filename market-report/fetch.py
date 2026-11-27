#!/usr/bin/env python3
"""Fetch inputs for the US close report. Usage: fetch.py RUN_DIR
Writes RUN_DIR/universe.json, RUN_DIR/constituents.json, RUN_DIR/cache/<sym>.json (Yahoo 1y daily OHLCV + adjclose).
Index ETFs fetched: SPY, QQQ, DIA, IWM, plus RSP (Invesco S&P 500 Equal Weight) for the Section 3 participation row.
No full-market NYSE/NASDAQ A/D (old section 4B) is fetched; that section was removed 2026-10-08."""
import json, os, re, sys, time, io
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote
import pandas as pd

RUN = sys.argv[1]
CACHE = os.path.join(RUN, "cache"); os.makedirs(CACHE, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
log = []
def L(k, v):
    log.append({"block": k, "text": v}); print(k, v, flush=True)

def get(url, headers=None, timeout=30):
    h = {"User-Agent": UA, "Accept": "application/json,text/html,text/csv,*/*"}
    if headers: h.update(headers)
    with urlopen(Request(url, headers=h), timeout=timeout) as r:
        return r.read()

def ysym(s): return s.replace("/", "-").replace(".", "-").strip()

FUND_RE = re.compile(r"\bFund\b|Beneficial Interest|Closed[- ]End|\bETF\b|\bETN\b|Exchange[- ]Traded|\bBonds?\b", re.I)
EXCL_RE = re.compile(r"\bWarrants?\b|\bPreferred\b|\bNotes?\b|\bDebentures?\b|\bRights?\b|\bUnits?\b|Mandatory Convertible|1/20|When[- ]Issued", re.I)
COMMON_RE = re.compile(r"Common Stock|Common Shares|Ordinary Shares|Capital Stock|Subordinate Voting", re.I)
ADR_RE = re.compile(r"American Depositary|American Depository|\bADRs?\b|\bADS\b", re.I)
CORP_RE = re.compile(r"\bInc\.?\b|\bCorporation\b|\bCorp\.?\b|\bCompany\b|\bLtd\.?\b|\bPLC\b|\bLimited\b", re.I)
# Share wordings not already in COMMON_RE: singular "Share", and New York / NY
# Registry Shares (US-listed ordinary shares of foreign issuers, e.g. ASML).
# Used only in the final keep test so Trust, Beneficial Interest, blank-country,
# and the "Common  Stock" double-space name quirk stay unchanged.
LISTED_SHARE_RE = re.compile(
    r"\bOrdinary Share\b|\bCommon Share\b|New York Registry Shares|\bNY Registry Shares",
    re.I,
)

def etf_flags():
    etf, test = set(), set()
    def add(sym, e, t):
        for s in (sym, ysym(sym)):
            if e == "Y": etf.add(s)
            if t == "Y": test.add(s)
    for line in open(os.path.join(RUN, "nasdaqlisted.txt"), encoding="utf-8", errors="replace"):
        p = line.strip().split("|")
        if len(p) < 8 or p[0] == "Symbol": continue
        add(p[0].strip(), p[6].strip(), p[3].strip())
    for line in open(os.path.join(RUN, "otherlisted.txt"), encoding="utf-8", errors="replace"):
        p = line.strip().split("|")
        if len(p) < 8 or p[0].startswith("ACT"): continue
        add(p[0].strip(), p[4].strip(), p[6].strip())
        add(p[7].strip(), p[4].strip(), p[6].strip())
    return etf, test

def include_row(r, etf, test):
    name = (r.get("name") or "").strip(); country = (r.get("country") or "").strip()
    ind = (r.get("industry") or "").strip(); sym = r["symbol"]; y = ysym(sym)
    if "^" in sym or sym in etf or y in etf or sym in test or y in test: return False
    if EXCL_RE.search(name) or FUND_RE.search(name): return False
    if ind.startswith("Trusts Except"): return False
    if re.search(r"\bTrust\b", name) and not COMMON_RE.search(name): return False
    if ADR_RE.search(name): return True
    # Keep US-exchange-listed common/ordinary shares regardless of country of
    # registration (2026-11-26). ADRs still included above. Blank country still
    # requires COMMON_RE, as before.
    if country == "" and not COMMON_RE.search(name): return False
    return bool(COMMON_RE.search(name) or CORP_RE.search(name) or LISTED_SHARE_RE.search(name))

def build_universe():
    rows = json.load(open(os.path.join(RUN, "screener.json")))["data"]["rows"]
    etf, test = etf_flags()
    uni = {}
    for r in rows:
        if not include_row(r, etf, test): continue
        y = ysym(r["symbol"])
        uni[y] = {"symbol": r["symbol"], "name": r.get("name"), "industry": (r.get("industry") or "").strip() or "Unclassified",
                  "adr": bool(ADR_RE.search(r.get("name") or ""))}
    L("universe", f"NASDAQ screener rows {len(rows)}; kept {len(uni)} US-exchange-listed common stock / ordinary share / ADR names after ETF, fund, warrant, preferred, unit, right and note filters (including foreign-registered issuers).")
    return uni

def sym_list(vals):
    out, seen = [], set()
    for v in vals:
        s = re.sub(r"\[.*?\]", "", str(v)).strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s) and s not in seen:
            seen.add(s); out.append(s)
    return out

def constituents():
    out = {}
    for label, url in (("SP500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
                       ("DJIA", "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average")):
        try:
            dfs = pd.read_html(io.BytesIO(get(url, {"Accept": "text/html"})))
            got = None
            for df in dfs:
                cols = [str(c).strip().lower() for c in df.columns]
                for key in ("symbol", "ticker"):
                    if key in cols:
                        s = sym_list(df.iloc[:, cols.index(key)].tolist())
                        if (label == "SP500" and len(s) > 450) or (label == "DJIA" and 28 <= len(s) <= 32):
                            got = s; break
                if got: break
            if got:
                out[label] = {"syms": got, "src": url}; L("constituents " + label, f"{url} {len(got)} symbols")
            else:
                L("constituents " + label, f"not found in tables at {url}")
        except Exception as e:
            L("constituents " + label, f"failed {type(e).__name__}: {e}")
    url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
    try:
        d = json.loads(get(url, {"Accept": "application/json"}))
        s = sym_list([r.get("symbol") for r in d["data"]["data"]["rows"]])
        out["NDX"] = {"syms": s, "src": url + " (list date " + str(d["data"].get("date")) + ")"}; L("constituents NDX", f"{len(s)} symbols, date {d['data'].get('date')}")
    except Exception as e:
        L("constituents NDX", f"failed {type(e).__name__}: {e}")
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    try:
        raw = get(url, {"Accept": "text/csv", "Referer": "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf"}).decode("utf-8", "replace")
        lines = raw.splitlines()
        hi = next(i for i, l in enumerate(lines[:20]) if l.startswith("Ticker,"))
        asof = next((l for l in lines[:hi] if "as of" in l.lower()), "")
        df = pd.read_csv(io.StringIO("\n".join(lines[hi:])), on_bad_lines="skip")
        df = df[df.get("Asset Class", "Equity") == "Equity"]
        s = sym_list(df["Ticker"].tolist())
        out["R2000"] = {"syms": s, "src": url + " " + asof.strip()}; L("constituents R2000", f"iShares IWM holdings {len(s)} equity tickers {asof.strip()}")
    except Exception as e:
        L("constituents R2000", f"failed {type(e).__name__}: {str(e)[:120]}")
    return out

def chart_to_bars(r):
    """Parse one Yahoo chart result into {date: bar}.
    Yahoo 1y/5d often leaves the latest session's close (and sometimes adjclose) null while
    volume and meta.regularMarketPrice are set. Fill that session from regularMarketPrice
    (and day high/low/volume from meta when the quote fields are also null). Older bars
    with a real close are unchanged. Returns (name, bars_dict, regular_market_date)."""
    meta = r.get("meta") or {}
    try: tz = ZoneInfo(meta.get("exchangeTimezoneName") or "America/New_York")
    except Exception: tz = ZoneInfo("America/New_York")
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    adj = (((r.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    rmt = meta.get("regularMarketTime")
    rmp = meta.get("regularMarketPrice")
    rm_dt = datetime.fromtimestamp(rmt, tz).date().isoformat() if rmt else None
    bars = {}
    for i, t in enumerate(r.get("timestamp") or []):
        g = lambda k, i=i: (q.get(k) or [None] * (i + 1))[i] if i < len(q.get(k) or []) else None
        c = g("close")
        dt = datetime.fromtimestamp(t, tz).date().isoformat()
        o, h, l, v = g("open"), g("high"), g("low"), g("volume")
        a = adj[i] if i < len(adj) and adj[i] is not None else None
        if c is None and rmp is not None and rm_dt == dt:
            c = float(rmp)
            if h is None: h = meta.get("regularMarketDayHigh")
            if l is None: l = meta.get("regularMarketDayLow")
            if v is None: v = meta.get("regularMarketVolume")
            if a is None: a = c
        if c is None:
            continue
        if a is None: a = c
        bars[dt] = {"d": dt, "o": o, "h": h, "l": l, "c": c, "v": v or 0, "a": a}
    return meta.get("shortName") or "", bars, rm_dt

def fetch(sym, rng="1y"):
    cp = os.path.join(CACHE, sym.replace("/", "_").replace("^", "IDX_").replace("=", "_") + ".json")
    if os.path.exists(cp): return sym, "cached"
    last = ""
    for a in range(6):
        host = "query1" if a % 2 == 0 else "query2"
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{quote(sym, safe='')}?interval=1d&range={rng}&includePrePost=false&events=div%7Csplit"
        try:
            d = json.loads(get(url, timeout=25))
            res = (d.get("chart") or {}).get("result")
            if not res:
                err = (d.get("chart") or {}).get("error") or {}
                if "Not Found" in json.dumps(err):
                    json.dump({"error": "notfound"}, open(cp, "w")); return sym, "notfound"
                last = str(err); time.sleep(0.6 * (a + 1)); continue
            name, bars, rm_dt = chart_to_bars(res[0])
            # If the regular-market session is still missing (1y left it null and meta fill
            # did not apply), merge a range=1d chart, which often carries the settled close.
            if rm_dt and rm_dt not in bars:
                url1 = f"https://{host}.finance.yahoo.com/v8/finance/chart/{quote(sym, safe='')}?interval=1d&range=1d&includePrePost=false&events=div%7Csplit"
                try:
                    d1 = json.loads(get(url1, timeout=25))
                    res1 = (d1.get("chart") or {}).get("result")
                    if res1:
                        n1, b1, _ = chart_to_bars(res1[0])
                        if n1 and not name: name = n1
                        bars.update(b1)
                except Exception as e1:
                    last = f"range=1d {type(e1).__name__}: {e1}"
            if not bars:
                last = "empty bars"; time.sleep(0.6 * (a + 1)); continue
            json.dump({"name": name, "bars": [bars[k] for k in sorted(bars)]}, open(cp, "w"))
            return sym, "ok"
        except HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 404:
                json.dump({"error": "404"}, open(cp, "w")); return sym, "notfound"
            time.sleep(0.8 * (a + 1))
        except Exception as e:
            last = f"{type(e).__name__}: {e}"; time.sleep(0.8 * (a + 1))
    return sym, "fail " + last

def main():
    uni = build_universe()
    json.dump(uni, open(os.path.join(RUN, "universe.json"), "w"))
    cons = constituents()
    json.dump(cons, open(os.path.join(RUN, "constituents.json"), "w"))
    ten = json.load(open("/tmp/mkt/mom_universe_syms.json"))
    extra = ["^VIX", "DX-Y.NYB", "^TNX", "GC=F", "CL=F", "BTC-USD", "SPY", "QQQ", "DIA", "IWM", "RSP",
             "XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLU"]
    allsyms = list(dict.fromkeys(extra + list(uni) + [ysym(s) for s in ten] + [ysym(s) for c in cons.values() for s in c["syms"]]))
    print("symbols", len(allsyms), flush=True)
    stat = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(fetch, s) for s in allsyms]
        for i, f in enumerate(as_completed(futs)):
            s, st = f.result(); stat[s] = st
            if i % 500 == 0: print("progress", i, flush=True)
    fails = [s for s, st in stat.items() if st.startswith("fail")]
    # one retry pass
    for s in fails:
        s2, st = fetch(s); stat[s2] = st
    fails = [s for s, st in stat.items() if st.startswith("fail")]
    L("yahoo", f"symbols {len(allsyms)} ok {sum(1 for v in stat.values() if v in ('ok','cached'))} notfound {sum(1 for v in stat.values() if v=='notfound')} failed {len(fails)} {fails[:30]}")
    json.dump({"log": log, "fails": fails}, open(os.path.join(RUN, "fetch_log.json"), "w"), indent=1)
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
