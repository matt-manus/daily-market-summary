"""One-off: which of Grok's data sources can GitHub Actions reach? (27/11/26)"""
import io, json, re, time
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
SHEET = "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE"
out = {}


def test(name, fn):
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {str(e)[:200]}"
    out[name] = {"ok": ok, "detail": detail, "secs": round(time.time() - t0, 1)}
    print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def finviz():
    r = requests.get("https://finviz.com/screener.ashx?v=111&f=idx_sp500,ta_sma50_pa&ft=4", headers={**UA, "Accept": "text/html"}, timeout=25)
    m = re.search(r'"result_count"\s*:\s*(\d+)', r.text) or re.search(r'#1 / (\d[\d,]*)', r.text) or re.search(r'(\d[\d,]*)\s+Total', r.text)
    return bool(m), f"HTTP {r.status_code}, count={m.group(1) if m else None}, {len(r.text)} bytes"


def ishares():
    r = requests.get("https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
                     headers={**UA, "Accept": "text/csv", "Referer": "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf"}, timeout=30)
    lines = r.text.splitlines()
    k = next((i for i, l in enumerate(lines[:30]) if l.startswith("Ticker,")), None)
    return k is not None, f"HTTP {r.status_code}, header row {k}, {len(lines)} lines, starts {r.text[:60]!r}"


def ssga_dia():
    url = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-dia.xlsx"
    r = requests.get(url, headers=UA, timeout=30)
    ok = r.status_code == 200 and r.content[:2] == b"PK"
    detail = f"HTTP {r.status_code}, {len(r.content)} bytes, xlsx={r.content[:2] == b'PK'}"
    if ok:
        import pandas as pd
        df = pd.read_excel(io.BytesIO(r.content), skiprows=4)
        tick = [t for t in df.get("Ticker", []) if isinstance(t, str) and t.strip() and t.strip() != "-"]
        detail += f", tickers={len(tick)} e.g. {tick[:5]}"
        ok = 25 <= len(tick) <= 35
    return ok, detail


def cnn_fg():
    r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={**UA, "Accept": "application/json", "Referer": "https://edition.cnn.com/"}, timeout=25)
    try:
        j = r.json()
        fg = j.get("fear_and_greed", {})
        return "score" in fg, f"HTTP {r.status_code}, score={fg.get('score')}, rating={fg.get('rating')}, ts={fg.get('timestamp')}"
    except Exception:
        return False, f"HTTP {r.status_code}, not JSON, starts {r.text[:80]!r}"


def cboe():
    r = requests.get("https://www.cboe.com/markets/us/options/market-statistics/daily/?dt=2026-11-25", headers={**UA, "Accept": "text/html"}, timeout=30)
    has = "EQUITY PUT/CALL RATIO" in r.text.upper()
    m = re.search(r"EQUITY PUT/CALL RATIO[^0-9]{0,200}?(\d\.\d{2})", r.text, re.I | re.S)
    return has, f"HTTP {r.status_code}, {len(r.text)} bytes, label found={has}, value={m.group(1) if m else None}"


def stockbee_csv():
    for url in (f"https://docs.google.com/spreadsheets/d/{SHEET}/gviz/tq?tqx=out:csv",
                f"https://docs.google.com/spreadsheets/d/{SHEET}/export?format=csv",
                f"https://docs.google.com/spreadsheets/d/{SHEET}/pub?output=csv"):
        r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
        if r.status_code == 200 and "," in r.text[:500] and "<html" not in r.text[:200].lower():
            lines = r.text.splitlines()
            return True, f"{url.split('/')[-1][:30]} → {len(lines)} rows; first: {lines[0][:150]!r}; second: {lines[1][:150] if len(lines) > 1 else ''!r}"
    return False, f"last HTTP {r.status_code}, starts {r.text[:80]!r}"


def yahoo_macro():
    import yfinance as yf
    d = yf.download(["^VIX", "DX-Y.NYB", "^TNX", "GC=F", "CL=F", "BTC-USD"], period="5d", progress=False, auto_adjust=False)["Close"]
    last = d.ffill().iloc[-1].round(2).to_dict()
    return all(v == v for v in last.values()), f"{last}"


for name, fn in [("Finviz screener (4A Dow/R2000, Sec 3 A/D)", finviz), ("iShares IWM holdings (R2000 members)", ishares),
                 ("SSGA DIA holdings xlsx (Dow members)", ssga_dia), ("CNN Fear & Greed", cnn_fg), ("Cboe put/call page", cboe),
                 ("Stockbee sheet as CSV", stockbee_csv), ("Yahoo macro (VIX, DXY, TNX, gold, oil, BTC)", yahoo_macro)]:
    test(name, fn)
json.dump(out, open("data/monitor/source_test.json", "w"), indent=1, ensure_ascii=False)
