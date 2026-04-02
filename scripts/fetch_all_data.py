"""
fetch_all_data.py  — Credit-Efficient Market Data Fetcher  v4.1
---------------------------------------------------------------
Changes from v4.0:
  1. BREADTH FIX: fetch_finviz_count() now tries multiple URL patterns and
     parses both JSON and HTML fallback to eliminate N/A in Section 4b.
  2. ADR LOGIC: compute_etf_ad_ratio() now uses BOTH above_20ma AND above_50ma
     for a more robust breadth-based A/D proxy.
  3. RETRY LOGIC: Added retry with backoff for Finviz screener calls.
  4. SECTOR PERF: Improved parsing with additional fallback patterns.

JSON Schema v4.1 (same structure as v4.0):
{
  "meta":      { generated_hkt, generated_et, date, source, schema_version }
  "macro":     { VIX, DXY, TNX_10Y, GOLD, OIL_WTI, BTC }
  "indices":   { SPY, QQQ, DIA, IWM }  ← price, change_1d_pct, rsi14,
                                           ma20/50/200, vs_ma*_pct, status,
                                           ad_ratio (ETF-level A/D Ratio)
  "sentiment": {
      "fear_greed": { score, rating, prev_close, prev_1w, prev_1m, prev_1y }
      "put_call":   { value, rating }
      "naaim":      { value, date, history: [{date, value}, ...] }  ← 3 weeks
  }
  "sectors":   [ { symbol, name, change_1d/1w/1m_pct, rsi14,
                   ma20/50/200, vs_ma*_pct, vs20ma, status } ]  ← sorted by RSI desc
  "industry":  [ { rank, label, num_stocks, change_1d/1w/1m/3m/ytd_pct } ]
  "breadth":   {
      "sp500":      { total, above_20/50/200ma, pct_above_* }
      "nasdaq":     { ... }
      "nyse":       { ... }
      "russell2000":{ ... }
      "market_wide_advance_decline": {
          "NYSE":   { advances, declines, unchanged, total_issues,
                      pct_advancing, pct_declining, adv_vol, dec_vol,
                      ad_ratio (float), new_52w_highs, new_52w_lows }
          "NASDAQ": { ... }
      }
      "volatility_adr": { SPY, QQQ, DIA, IWM }  ← 14-day Avg Daily Range %
                                                     (volatility measure, NOT A/D)
  }
}
"""

import json
import os
import re
import time
import traceback
from datetime import datetime

import pandas as pd
import pytz
import requests
import yfinance as yf
from bs4 import BeautifulSoup

# ─── 配置區 ────────────────────────────────────────────────────────────────────
MACRO_TICKERS = {
    "VIX":     "^VIX",
    "DXY":     "DX-Y.NYB",
    "TNX_10Y": "^TNX",
    "GOLD":    "GC=F",
    "OIL_WTI": "CL=F",
    "BTC":     "BTC-USD",
}

INDEX_ETFS = ["SPY", "QQQ", "DIA", "IWM"]

SECTORS = {
    "XLF":  "Financials",
    "XLK":  "Technology",
    "XLE":  "Energy",
    "XLI":  "Industrials",
    "XLV":  "Health Care",
    "XLP":  "Consumer Staples",
    "XLY":  "Consumer Discretionary",
    "XLB":  "Materials",
    "XLU":  "Utilities",
    "XLC":  "Communication Services",
    "XLRE": "Real Estate",
}

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(_SCRIPT_DIR, "..", "data", "today_market.json")


# ══════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def get_wilder_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's SMMA RSI (EWM alpha=1/window)."""
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def pct_from_ma(price: float, ma: float) -> float:
    if not ma or ma == 0:
        return 0.0
    return round((price - ma) / ma * 100, 2)


def ma_status(price: float, ma20: float, ma50: float, ma200: float) -> str:
    if price > max(ma20, ma50, ma200):
        return "ABOVE ALL"
    if price < min(ma20, ma50, ma200):
        return "BELOW ALL"
    return "MIXED"


def safe_float(val, decimals: int = 4):
    try:
        v = float(val)
        return None if pd.isna(v) else round(v, decimals)
    except Exception:
        return None


def build_full_entry(s: pd.Series, ticker: str) -> dict:
    """Compute full ETF entry: price, change, RSI, MA distances, status."""
    price   = safe_float(s.iloc[-1])
    prev    = safe_float(s.iloc[-2]) if len(s) >= 2 else None
    ma20    = safe_float(s.rolling(20).mean().iloc[-1])
    ma50    = safe_float(s.rolling(50).mean().iloc[-1])
    ma200   = safe_float(s.rolling(200).mean().iloc[-1])
    rsi     = safe_float(get_wilder_rsi(s).iloc[-1])
    chg_pct = round((price - prev) / prev * 100, 2) if price and prev else None

    return {
        "price":          price,
        "change_1d_pct":  chg_pct,
        "rsi14":          rsi,
        "ma20":           ma20,
        "ma50":           ma50,
        "ma200":          ma200,
        "vs_ma20_pct":    pct_from_ma(price, ma20),
        "vs_ma50_pct":    pct_from_ma(price, ma50),
        "vs_ma200_pct":   pct_from_ma(price, ma200),
        "vs20ma":         "Green" if price and ma20 and price > ma20 else "Red",
        "status":         ma_status(price, ma20, ma50, ma200),
    }


# ══════════════════════════════════════════════════════════════════════
# SENTIMENT FETCHERS
# ══════════════════════════════════════════════════════════════════════

def fetch_cnn_fear_greed() -> dict:
    """CNN Fear & Greed Index + Put/Call Ratio."""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent":      HTTP_HEADERS["User-Agent"],
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.cnn.com/markets/fear-and-greed",
        "Origin":          "https://www.cnn.com",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        d  = r.json()
        fg = d.get("fear_and_greed", {})

        fear_greed = {
            "score":      round(fg.get("score", 0), 2),
            "rating":     fg.get("rating", "N/A"),
            "timestamp":  fg.get("timestamp", ""),
            "prev_close": round(fg.get("previous_close", 0), 2),
            "prev_1w":    round(fg.get("previous_1_week", 0), 2),
            "prev_1m":    round(fg.get("previous_1_month", 0), 2),
            "prev_1y":    round(fg.get("previous_1_year", 0), 2),
            "source":     "CNN Fear & Greed API",
        }

        pc_data   = d.get("put_call_options", {})
        pc_pts    = pc_data.get("data", [])
        pc_val    = round(pc_pts[-1]["y"], 4) if pc_pts else None
        pc_rating = pc_pts[-1].get("rating", "N/A") if pc_pts else "N/A"
        put_call  = {
            "value":  pc_val,
            "rating": pc_rating,
            "source": "CNN Fear & Greed (5-day avg equity P/C ratio)",
        }

        return {"fear_greed": fear_greed, "put_call": put_call}

    except Exception as e:
        print(f"  ⚠  CNN Fear & Greed 抓取失敗: {e}")
        return {
            "fear_greed": {"score": None, "rating": "N/A", "source": "CNN (failed)"},
            "put_call":   {"value": None, "rating": "N/A", "source": "CNN (failed)"},
        }


def fetch_naaim() -> dict:
    """
    NAAIM Exposure Index — latest value + last 3 weekly readings as history.
    Returns:
      { value, date, history: [{date, value}, ...], source }
    """
    url = "https://www.naaim.org/programs/naaim-exposure-index/"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()

        idx_start = r.text.find("function drawNaaimChart()")
        idx_end   = r.text.find("function drawSpChart()")
        if idx_start < 0 or idx_end < 0:
            raise ValueError("NAAIM chart function not found")

        naaim_section = r.text[idx_start:idx_end]
        rows = re.findall(
            r"\[new Date\((\d+),\s*(\d+),\s*(\d+)\),\s*([\d.]+)\]",
            naaim_section
        )
        if not rows:
            raise ValueError("No NAAIM data rows found")

        # Build history list (last 3 weeks, newest first)
        history = []
        for raw in reversed(rows[-3:]):
            yr, mo, dy, val = int(raw[0]), int(raw[1]) + 1, int(raw[2]), float(raw[3])
            history.append({
                "date":  f"{yr}-{mo:02d}-{dy:02d}",
                "value": round(val, 2),
            })

        latest = history[0]  # most recent week is first after reverse

        return {
            "value":   latest["value"],
            "date":    latest["date"],
            "history": history,          # [{date, value}, ...] newest first
            "source":  "NAAIM Exposure Index (weekly)",
        }

    except Exception as e:
        print(f"  ⚠  NAAIM 抓取失敗: {e}")
        return {
            "value":   None,
            "date":    None,
            "history": [],
            "source":  "NAAIM (failed)",
        }


# ══════════════════════════════════════════════════════════════════════
# SECTOR PERFORMANCE (Finviz Groups)
# ══════════════════════════════════════════════════════════════════════

def fetch_sector_perf() -> dict:
    """
    Finviz Groups — 11 sectors: 1D / 1W / 1M / 3M / YTD performance.
    Returns: { "XLF": { name, perf_1d, perf_1w, perf_1m, perf_3m, perf_ytd }, ... }
    """
    url = "https://finviz.com/groups.ashx?g=sector&sg=&o=name&p=d"
    sector_map = {
        "basicmaterials":        "XLB",
        "communicationservices": "XLC",
        "consumercyclical":      "XLY",
        "consumerdefensive":     "XLP",
        "energy":                "XLE",
        "financial":             "XLF",
        "financialservices":     "XLF",
        "healthcare":            "XLV",
        "industrials":           "XLI",
        "realestate":            "XLRE",
        "technology":            "XLK",
        "utilities":             "XLU",
    }

    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()

        # Try JSON rows first
        match = re.search(r"var rows = (\[.*?\]);", r.text, re.DOTALL)
        if not match:
            raise ValueError("Finviz sector rows not found")

        rows = json.loads(match.group(1))
        result = {}
        for row in rows:
            key = (row.get("label") or "").lower().replace(" ", "").replace("&", "")
            etf = sector_map.get(key)
            if etf:
                result[etf] = {
                    "name":     row.get("label", etf),
                    "perf_1d":  row.get("perfT"),
                    "perf_1w":  row.get("perfW"),
                    "perf_1m":  row.get("perfM"),
                    "perf_3m":  row.get("perfQ"),
                    "perf_ytd": row.get("perfYtd"),
                }
        return result

    except Exception as e:
        print(f"  ⚠  Finviz Sector 回報率抓取失敗: {e}")
        return {}


# ══════════════════════════════════════════════════════════════════════
# INDUSTRY TOP 15 (Finviz Groups) — with num_stocks
# ══════════════════════════════════════════════════════════════════════

def fetch_industry_top15() -> list:
    """
    Finviz Groups — all industries sorted by 1D return, Top 15.
    Includes 'num_stocks' fetched via each industry's screener URL.
    Note: Finviz Groups JSON does not expose stock count directly;
    we fetch it from the screener result_count for each top-15 industry.
    """
    url = "https://finviz.com/groups.ashx?g=industry&sg=&o=perf1d&p=d"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        match = re.search(r"var rows = (\[.*?\]);", r.text, re.DOTALL)
        if not match:
            raise ValueError("Finviz industry rows not found")

        rows = json.loads(match.group(1))
        rows.sort(key=lambda x: x.get("perfT") or -999, reverse=True)

        top15 = []
        for i, row in enumerate(rows[:15], 1):
            # Fetch stock count via screener URL embedded in each row
            screener_path = row.get("screenerUrl", "")
            num_stocks = None
            if screener_path:
                try:
                    sc_url = f"https://finviz.com/{screener_path}"
                    sc_r   = requests.get(sc_url, headers=HTTP_HEADERS, timeout=10)
                    sc_m   = re.search(r'result_count\":(\d+)', sc_r.text)
                    if sc_m:
                        num_stocks = int(sc_m.group(1))
                    time.sleep(0.3)   # polite delay
                except Exception:
                    num_stocks = None

            top15.append({
                "rank":           i,
                "label":          row.get("label", ""),
                "num_stocks":     num_stocks,
                "change_1d_pct":  row.get("perfT"),
                "change_1w_pct":  row.get("perfW"),
                "change_1m_pct":  row.get("perfM"),
                "change_3m_pct":  row.get("perfQ"),
                "change_ytd_pct": row.get("perfYtd"),
                "source":         "Finviz Groups",
            })
        return top15

    except Exception as e:
        print(f"  ⚠  Finviz Industry Top 15 抓取失敗: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════
# BREADTH (Finviz Screener) — v4.1: Multiple URL patterns + retry
# KEY FIX: Eliminates N/A in Section 4b by using robust parsing
# ══════════════════════════════════════════════════════════════════════

def fetch_finviz_count(filters: str, retries: int = 3) -> int | None:
    """
    Fetch stock count from Finviz screener with retry logic.
    Tries JSON result_count first, then HTML table count as fallback.
    """
    url = f"https://finviz.com/screener.ashx?v=111&f={filters}&ft=4"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=25)
            r.raise_for_status()

            # Method 1: JSON result_count (fastest)
            match = re.search(r'"result_count"\s*:\s*(\d+)', r.text)
            if match:
                return int(match.group(1))

            # Method 2: HTML table count string "X Total" or "X Stocks"
            match2 = re.search(r'(\d[\d,]*)\s+(?:Total|Stocks|total|stocks)', r.text)
            if match2:
                return int(match2.group(1).replace(",", ""))

            # Method 3: Parse the count from the pagination text
            match3 = re.search(r'of\s+(\d[\d,]*)\s+results', r.text, re.IGNORECASE)
            if match3:
                return int(match3.group(1).replace(",", ""))

            # Method 4: BeautifulSoup parse for result count
            soup = BeautifulSoup(r.text, "html.parser")
            count_el = soup.find("td", {"class": "count-text"})
            if count_el:
                m = re.search(r'(\d+)', count_el.get_text())
                if m:
                    return int(m.group(1))

            print(f"  ⚠  Finviz count parse failed for filters={filters} (attempt {attempt+1})")
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))

        except Exception as e:
            print(f"  ⚠  Finviz count error for filters={filters}: {e} (attempt {attempt+1})")
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))

    return None


def fetch_breadth() -> dict:
    """
    % of stocks above 20/50/200 MA for S&P500, NASDAQ, NYSE, Russell 2000.
    v4.1: Uses retry logic and multiple parse methods to ensure non-N/A results.
    """
    def pct(above, total):
        if above is None or total is None or total == 0:
            return None
        return round(above / total * 100, 1)

    print("  正在抓取 S&P 500 廣度數據…")
    sp500_total = fetch_finviz_count("idx_sp500");                time.sleep(0.6)
    sp500_a200  = fetch_finviz_count("idx_sp500,ta_sma200_pa");   time.sleep(0.6)
    sp500_a50   = fetch_finviz_count("idx_sp500,ta_sma50_pa");    time.sleep(0.6)
    sp500_a20   = fetch_finviz_count("idx_sp500,ta_sma20_pa");    time.sleep(0.6)
    print(f"     SP500: total={sp500_total}, >20MA={sp500_a20}, >50MA={sp500_a50}, >200MA={sp500_a200}")

    # ── QQQ: NASDAQ 100 only (idx_ndx ≈ 101 stocks) — NOT the full NASDAQ exchange ──
    print("  正在抓取 QQQ (NASDAQ 100 = idx_ndx) 廣度數據…")
    nasd_total  = fetch_finviz_count("idx_ndx");                  time.sleep(0.6)
    nasd_a200   = fetch_finviz_count("idx_ndx,ta_sma200_pa");     time.sleep(0.6)
    nasd_a50    = fetch_finviz_count("idx_ndx,ta_sma50_pa");      time.sleep(0.6)
    nasd_a20    = fetch_finviz_count("idx_ndx,ta_sma20_pa");      time.sleep(0.6)
    print(f"     QQQ (NASDAQ100): total={nasd_total}, >20MA={nasd_a20}, >50MA={nasd_a50}, >200MA={nasd_a200}")
    # Sanity check: NASDAQ 100 should have ~100 stocks, NOT 4000+
    if nasd_total and nasd_total > 500:
        print(f"     ⚠  SANITY FAIL: nasd_total={nasd_total} > 500 — idx_ndx returned exchange-wide data!")
        nasd_total = nasd_a20 = nasd_a50 = nasd_a200 = None

    # ── DIA: Dow Jones 30 via yfinance (exact 30 components) ──
    print("  正在計算 DIA (Dow Jones 30) 廣度數據 via yfinance…")
    try:
        import yfinance as yf
        dji_tickers = yf.download(DJI_COMPONENTS, period='1y', interval='1d', progress=False)
        dji_close = dji_tickers['Close'] if 'Close' in dji_tickers else dji_tickers
        dia_above_20 = dia_above_50 = dia_above_200 = 0
        dia_valid = 0
        for sym in DJI_COMPONENTS:
            if sym not in dji_close.columns: continue
            s = dji_close[sym].dropna()
            if len(s) < 200: continue
            price = float(s.iloc[-1])
            dia_valid += 1
            if price > float(s.tail(20).mean()): dia_above_20 += 1
            if price > float(s.tail(50).mean()): dia_above_50 += 1
            if price > float(s.tail(200).mean()): dia_above_200 += 1
        nyse_total = dia_valid
        nyse_a20   = dia_above_20
        nyse_a50   = dia_above_50
        nyse_a200  = dia_above_200
        print(f"     DIA (DJI30): total={nyse_total}, >20MA={nyse_a20}, >50MA={nyse_a50}, >200MA={nyse_a200}")
    except Exception as e:
        print(f"     ⚠  DIA yfinance 計算失敗: {e}")
        nyse_total = nyse_a20 = nyse_a50 = nyse_a200 = None

    print("  正在抓取 Russell 2000 廣度數據…")
    rut_total   = fetch_finviz_count("idx_rut");                  time.sleep(0.6)
    rut_a200    = fetch_finviz_count("idx_rut,ta_sma200_pa");     time.sleep(0.6)
    rut_a50     = fetch_finviz_count("idx_rut,ta_sma50_pa");      time.sleep(0.6)
    rut_a20     = fetch_finviz_count("idx_rut,ta_sma20_pa")
    print(f"     RUT:   total={rut_total}, >20MA={rut_a20}, >50MA={rut_a50}, >200MA={rut_a200}")

    return {
        "sp500": {
            "total":           sp500_total,
            "above_20ma":      sp500_a20,
            "above_50ma":      sp500_a50,
            "above_200ma":     sp500_a200,
            "pct_above_20ma":  pct(sp500_a20,  sp500_total),
            "pct_above_50ma":  pct(sp500_a50,  sp500_total),
            "pct_above_200ma": pct(sp500_a200, sp500_total),
        },
        # QQQ = NASDAQ 100 index constituents only (idx_ndx, ~101 stocks)
        "nasdaq100": {
            "total":           nasd_total,
            "above_20ma":      nasd_a20,
            "above_50ma":      nasd_a50,
            "above_200ma":     nasd_a200,
            "pct_above_20ma":  pct(nasd_a20,  nasd_total),
            "pct_above_50ma":  pct(nasd_a50,  nasd_total),
            "pct_above_200ma": pct(nasd_a200, nasd_total),
            "source":          "Finviz idx_ndx (NASDAQ 100 constituents)",
        },
        # DIA = Dow Jones 30 components only (yfinance, exact 30 stocks)
        "dji30": {
            "total":           nyse_total,
            "above_20ma":      nyse_a20,
            "above_50ma":      nyse_a50,
            "above_200ma":     nyse_a200,
            "pct_above_20ma":  pct(nyse_a20,  nyse_total),
            "pct_above_50ma":  pct(nyse_a50,  nyse_total),
            "pct_above_200ma": pct(nyse_a200, nyse_total),
            "source":          "yfinance DJI-30 components",
        },
        "russell2000": {
            "total":           rut_total,
            "above_20ma":      rut_a20,
            "above_50ma":      rut_a50,
            "above_200ma":     rut_a200,
            "pct_above_20ma":  pct(rut_a20,  rut_total),
            "pct_above_50ma":  pct(rut_a50,  rut_total),
            "pct_above_200ma": pct(rut_a200, rut_total),
        },
        "source": "Finviz Screener v4.1 (with retry)",
    }


# ══════════════════════════════════════════════════════════════════════
# VOLATILITY ADR — Average Daily Range % (yfinance High/Low)
# NOTE: This is a VOLATILITY measure, NOT the Advance/Decline Ratio.
#       Stored under breadth["volatility_adr"] to avoid naming confusion.
# ══════════════════════════════════════════════════════════════════════

def fetch_volatility_adr(raw_data: pd.DataFrame, window: int = 14) -> dict:
    """
    14-day Average Daily Range % for SPY/QQQ/DIA/IWM.
    Formula: mean( (High - Low) / midpoint * 100 ) over last 14 days.
    """
    out = {}
    for ticker in INDEX_ETFS:
        try:
            high  = raw_data["High"][ticker].dropna()
            low   = raw_data["Low"][ticker].dropna()
            daily = (high - low) / ((high + low) / 2) * 100
            out[ticker] = safe_float(daily.iloc[-window:].mean(), 2)
        except Exception as e:
            print(f"  ⚠  {ticker} Volatility ADR 計算失敗: {e}")
            out[ticker] = None
    return out


# ══════════════════════════════════════════════════════════════════════
# INDEX-LEVEL ADVANCE/DECLINE RATIO  (v4.2 — ACCURATE)
# Source: Finviz screener (today's up/down stocks) for SPY/QQQ/IWM
#         yfinance 30-component calculation for DIA (Dow Jones)
# Formula: ADR = advancing / declining  (today's price change)
# IMPORTANT: This replaces the old breadth-proxy method which was
#            computing above_20ma/below_20ma — NOT today's A/D.
# ══════════════════════════════════════════════════════════════════════

# Dow Jones 30 components (as of 2026; WBA replaced by AMGN in 2020)
DJI_COMPONENTS = [
    "AAPL", "AMGN", "AXP", "BA",  "CAT", "CRM", "CSCO", "CVX", "DIS", "DOW",
    "GS",   "HD",   "HON", "IBM", "INTC", "JNJ", "JPM",  "KO",  "MCD", "MMM",
    "MRK",  "MSFT", "NKE", "PG",  "TRV", "UNH", "V",    "VZ",  "WMT", "SHW",
]


def fetch_index_ad_ratios(close_df: pd.DataFrame) -> dict:
    """
    Compute TRUE Advance/Decline Ratio for SPY/QQQ/DIA/IWM.

    Method:
      SPY (S&P 500, ~503 stocks)  → Finviz screener idx_sp500 up/down today
      QQQ (NASDAQ 100, ~101 stocks) → Finviz screener idx_ndx up/down today
      IWM (Russell 2000, ~1930 stocks) → Finviz screener idx_rut up/down today
      DIA (Dow Jones 30) → yfinance: count up/down among 30 components

    Returns:
      { "SPY": {advances, declines, unchanged, ad_ratio, source},
        "QQQ": {...}, "DIA": {...}, "IWM": {...} }
    """

    result = {}

    # ── SPY / QQQ / IWM via Finviz screener ──────────────────────────────
    finviz_map = {
        "SPY": ("idx_sp500", "S&P 500"),
        "QQQ": ("idx_ndx",   "NASDAQ 100"),
        "IWM": ("idx_rut",   "Russell 2000"),
    }
    for etf, (idx_filter, idx_name) in finviz_map.items():
        try:
            total = fetch_finviz_count(idx_filter)
            time.sleep(0.5)
            up    = fetch_finviz_count(f"{idx_filter},ta_change_u")
            time.sleep(0.5)
            down  = fetch_finviz_count(f"{idx_filter},ta_change_d")
            time.sleep(0.5)

            if up is not None and down is not None and total is not None:
                unch  = max(0, total - up - down)
                ratio = round(float(up) / float(down), 3) if down > 0 else None
                result[etf] = {
                    "advances":  up,
                    "declines":  down,
                    "unchanged": unch,
                    "total":     total,
                    "ad_ratio":  ratio,
                    "source":    f"Finviz screener ({idx_name})",
                }
                print(
                    f"  ✓  {etf} ({idx_name}): "
                    f"Adv={up:,}  Dec={down:,}  Unch={unch:,}  "
                    f"ADR={ratio}  [source: Finviz]"
                )
            else:
                result[etf] = {"ad_ratio": None, "source": "Finviz (parse failed)"}
                print(f"  ⚠  {etf}: Finviz count parse failed")
        except Exception as e:
            result[etf] = {"ad_ratio": None, "source": f"Finviz (error: {e})"}
            print(f"  ⚠  {etf} Finviz A/D 抓取失敗: {e}")

    # ── DIA (Dow Jones 30) via yfinance ───────────────────────────────────
    # NOTE: DJI components are NOT in close_df (which only has ETFs).
    # We download the 30 components separately with a 5-day window.
    try:
        import yfinance as _yf
        dji_raw = _yf.download(
            DJI_COMPONENTS,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        # Handle both single-ticker and multi-ticker DataFrames
        if isinstance(dji_raw.columns, pd.MultiIndex):
            dji_close = dji_raw["Close"]
        else:
            dji_close = dji_raw[["Close"]]

        adv = dec = unch = 0
        missing = []
        for t in DJI_COMPONENTS:
            if t in dji_close.columns:
                s = dji_close[t].dropna()
                if len(s) >= 2:
                    chg = float(s.iloc[-1]) - float(s.iloc[-2])
                    if chg > 0.001:    adv  += 1
                    elif chg < -0.001: dec  += 1
                    else:              unch += 1
                else:
                    missing.append(t)
            else:
                missing.append(t)
        total = adv + dec + unch
        ratio = round(float(adv) / float(dec), 3) if dec > 0 else None
        result["DIA"] = {
            "advances":  adv,
            "declines":  dec,
            "unchanged": unch,
            "total":     total,
            "ad_ratio":  ratio,
            "source":    "yfinance (DJI 30 components)",
        }
        print(
            f"  ✓  DIA (Dow Jones 30): "
            f"Adv={adv}  Dec={dec}  Unch={unch}  ADR={ratio}  "
            f"[source: yfinance]"
            + (f"  Missing: {missing}" if missing else "")
        )
    except Exception as e:
        result["DIA"] = {"ad_ratio": None, "source": f"yfinance (error: {e})"}
        print(f"  ⚠  DIA yfinance A/D 計算失敗: {e}")

    return result


# ══════════════════════════════════════════════════════════════════════
# BARCHART ADVANCE/DECLINE (NYSE / NASDAQ full market)
# ══════════════════════════════════════════════════════════════════════

def fetch_barchart_advance_decline() -> dict:
    """
    NYSE / NASDAQ full-market Advance/Decline from Barchart.com.
    ad_ratio stored as float (not string).
    """
    API_URL = (
        "https://www.barchart.com/proxies/core-api/v1/momentum/get"
        "?raw=1"
        "&fields=exchange%2Chigh52w%2Clow52w%2CnewHighs%2CnewLows"
        "%2CadvancingVolume%2CunchangedVolume%2CdecliningVolume"
        "%2CadvancingIssues%2CpercentAdvancingIssues"
        "%2CunchangedIssues%2CpercentUnchangedIssues"
        "%2CdecliningIssues%2CpercentDecliningIssues"
        "&exchanges=NASDAQ%2CNYSE"
    )
    REFERER_URL = "https://www.barchart.com/stocks/momentum"

    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent":      HTTP_HEADERS["User-Agent"],
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

        r0   = session.get(REFERER_URL, timeout=20)
        r0.raise_for_status()
        xsrf = requests.utils.unquote(session.cookies.get("XSRF-TOKEN", ""))
        if not xsrf:
            raise ValueError("XSRF-TOKEN not found in cookies")

        session.headers["X-Xsrf-Token"] = xsrf
        session.headers["Referer"]      = REFERER_URL
        r       = session.get(API_URL, timeout=20)
        r.raise_for_status()
        payload = r.json()

        result = {}
        for item in payload.get("data", []):
            raw_item = item.get("raw", {})
            exchange = raw_item.get("exchange", item.get("exchange", ""))
            if exchange not in ("NYSE", "NASDAQ"):
                continue

            advances  = int(raw_item.get("advancingIssues",  0))
            declines  = int(raw_item.get("decliningIssues",  0))
            unchanged = int(raw_item.get("unchangedIssues",  0))
            total     = advances + declines + unchanged
            adv_vol   = int(raw_item.get("advancingVolume",  0))
            dec_vol   = int(raw_item.get("decliningVolume",  0))
            highs     = int(raw_item.get("newHighs", raw_item.get("high52w", 0)))
            lows      = int(raw_item.get("newLows",  raw_item.get("low52w",  0)))

            # ad_ratio stored as float (per knowledge base rule)
            ad_ratio  = round(float(advances) / float(declines), 3) if declines > 0 else None

            result[exchange] = {
                "advances":      advances,
                "declines":      declines,
                "unchanged":     unchanged,
                "total_issues":  total,
                "pct_advancing": round(raw_item.get("percentAdvancingIssues", 0), 1),
                "pct_declining": round(raw_item.get("percentDecliningIssues", 0), 1),
                "adv_vol":       adv_vol,
                "dec_vol":       dec_vol,
                "ad_ratio":      ad_ratio,      # float, e.g. 1.291
                "new_52w_highs": highs,
                "new_52w_lows":  lows,
            }

        result["source"] = "Barchart.com/stocks/momentum (live)"
        return result

    except Exception as e:
        print(f"  ⚠  Barchart A/D 抓取失敗: {e}")
        return {
            "NYSE":   None,
            "NASDAQ": None,
            "source": f"Barchart (failed: {e})",
        }


# ══════════════════════════════════════════════════════════════════════
# MAIN FETCH FUNCTION
# ══════════════════════════════════════════════════════════════════════

def fetch_all() -> dict:
    """Fetch all market data and save to data/today_market.json."""

    # ── Timestamps ───────────────────────────────────────────────────
    # TIMEZONE FIX: Always use America/New_York as canonical trade date.
    # Archive filenames and report dates MUST follow NY calendar, not HKT.
    ny_tz   = pytz.timezone("America/New_York")  # canonical NY tz
    hkt_tz  = pytz.timezone("Asia/Hong_Kong")
    now_et  = datetime.now(ny_tz)
    now_hkt = datetime.now(hkt_tz)
    ts_hkt  = now_hkt.strftime("%Y-%m-%d %H:%M")
    ts_et   = now_et.strftime("%Y-%m-%d %H:%M")
    # NY Trade Date: archive naming ALWAYS follows New York calendar
    date_str = now_et.strftime("%Y-%m-%d")

    print(f"╔══════════════════════════════════════════════╗")
    print(f"  Credit Efficient — Market Data Fetcher v4.1")
    print(f"  HKT: {ts_hkt}   ET: {ts_et}")
    print(f"╚══════════════════════════════════════════════╝\n")

    # ── 1. Download all tickers (2y daily) ───────────────────────────
    all_tickers = list(MACRO_TICKERS.values()) + INDEX_ETFS + list(SECTORS.keys())
    all_tickers = list(dict.fromkeys(all_tickers))

    print(f"[1/8] 正在下載 {len(all_tickers)} 個 ticker 的歷史數據（2y / 1d）…")
    raw = yf.download(
        all_tickers,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    close_df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    print(f"     下載完成，共 {len(close_df)} 個交易日，{close_df.shape[1]} 個標的\n")

    # ── 2. Macro ─────────────────────────────────────────────────────
    print("[2/8] 處理宏觀指標（Macro）…")
    macro_out = {}
    for label, ticker in MACRO_TICKERS.items():
        if ticker not in close_df.columns:
            print(f"  ⚠  {label:12s} 數據缺失，跳過")
            macro_out[label] = {"price": None, "change_1d": None, "change_1d_pct": None}
            continue
        s          = close_df[ticker].dropna()
        price      = safe_float(s.iloc[-1])
        prev_price = safe_float(s.iloc[-2]) if len(s) >= 2 else None
        chg        = round(price - prev_price, 4) if price and prev_price else None
        chg_pct    = round((price - prev_price) / prev_price * 100, 2) if price and prev_price else None
        macro_out[label] = {
            "price":         price,
            "change_1d":     chg,
            "change_1d_pct": chg_pct,
        }
        sign = "+" if chg_pct and chg_pct >= 0 else ""
        print(f"  ✓  {label:12s}  {price}  ({sign}{chg_pct}%)")

    # ── 3. Index ETFs ────────────────────────────────────────────────
    print("\n[3/8] 處理主要指數 ETF（Indices）…")
    indices_out = {}
    for ticker in INDEX_ETFS:
        if ticker not in close_df.columns:
            print(f"  ⚠  {ticker:6s} 數據缺失，跳過")
            continue
        s = close_df[ticker].dropna()
        if len(s) < 200:
            print(f"  ⚠  {ticker:6s} 數據不足 200 天（{len(s)} 天），跳過")
            continue
        entry = build_full_entry(s, ticker)
        indices_out[ticker] = entry
        sign = "+" if entry["change_1d_pct"] and entry["change_1d_pct"] >= 0 else ""
        print(
            f"  ✓  {ticker:6s}  ${entry['price']}  "
            f"({sign}{entry['change_1d_pct']}%)  "
            f"RSI={entry['rsi14']}  "
            f"vs20MA={entry['vs_ma20_pct']}%  "
            f"vs50MA={entry['vs_ma50_pct']}%  "
            f"vs200MA={entry['vs_ma200_pct']}%  "
            f"[{entry['status']}]"
        )

    # ── 4. Sentiment ─────────────────────────────────────────────────
    print("\n[4/8] 抓取市場情緒指標（Sentiment）…")
    print("  正在抓取 CNN Fear & Greed Index…")
    cnn_data   = fetch_cnn_fear_greed()
    print(f"  ✓  Fear & Greed: {cnn_data['fear_greed']['score']} ({cnn_data['fear_greed']['rating']})")
    print(f"  ✓  Put/Call Ratio: {cnn_data['put_call']['value']} ({cnn_data['put_call']['rating']})")

    print("  正在抓取 NAAIM Exposure Index（含最近 3 週歷史）…")
    naaim_data = fetch_naaim()
    if naaim_data["value"]:
        print(f"  ✓  NAAIM: {naaim_data['value']} (as of {naaim_data['date']})")
        for h in naaim_data.get("history", []):
            print(f"     History: {h['date']} → {h['value']}")
    else:
        print("  ⚠  NAAIM 數據不可用")

    sentiment_out = {
        "fear_greed": cnn_data["fear_greed"],
        "put_call":   cnn_data["put_call"],
        "naaim":      naaim_data,
    }

    # ── 5. Sectors ───────────────────────────────────────────────────
    print("\n[5/8] 處理板塊 ETF（Sectors，含 1D/1W/1M 回報）…")
    print("  正在從 Finviz 抓取板塊週/月回報率…")
    finviz_sector_perf = fetch_sector_perf()

    sector_rows = []
    for ticker, name in SECTORS.items():
        if ticker not in close_df.columns:
            print(f"  ⚠  {ticker:6s} 數據缺失，跳過")
            continue
        s = close_df[ticker].dropna()
        if len(s) < 200:
            print(f"  ⚠  {ticker:6s} 數據不足 200 天，跳過")
            continue
        entry = build_full_entry(s, ticker)
        entry["symbol"] = ticker
        entry["name"]   = name

        fv = finviz_sector_perf.get(ticker, {})
        entry["change_1w_pct"]  = fv.get("perf_1w")
        entry["change_1m_pct"]  = fv.get("perf_1m")
        entry["change_3m_pct"]  = fv.get("perf_3m")
        entry["change_ytd_pct"] = fv.get("perf_ytd")

        ordered = {"symbol": ticker, "name": name}
        ordered.update({k: v for k, v in entry.items() if k not in ("symbol", "name")})
        sector_rows.append(ordered)

    # Sort by RSI descending (as requested)
    sector_rows.sort(key=lambda x: x.get("rsi14") or 0, reverse=True)
    print(f"  ✓  共處理 {len(sector_rows)} 個板塊 ETF，已按 RSI 降序排列")

    # ── 6. Industry Top 15 ───────────────────────────────────────────
    print("\n[6/8] 抓取行業 Top 15（Industry，Finviz，含成份股數量）…")
    industry_out = fetch_industry_top15()
    if industry_out:
        print(f"  ✓  共抓取 {len(industry_out)} 個行業")
        for row in industry_out[:3]:
            ns = row.get("num_stocks")
            ns_str = f", {ns} stocks" if ns else ""
            print(f"     #{row['rank']} {row['label']}: {row['change_1d_pct']:+.2f}% (1D){ns_str}")
    else:
        print("  ⚠  Industry 數據不可用")

    # ── 7. Breadth ───────────────────────────────────────────────────
    print("\n[7/8] 抓取市場廣度（Breadth % Above MA）…")
    breadth_data = fetch_breadth()
    print(f"  ✓  S&P 500 Above 200MA: {breadth_data['sp500']['pct_above_200ma']}%")
    print(f"  ✓  QQQ (NASDAQ100) Above 200MA: {breadth_data['nasdaq100']['pct_above_200ma']}%")
    print(f"  ✓  DIA (DJI30) Above 200MA: {breadth_data['dji30']['pct_above_200ma']}%")
    print(f"  ✓  Russell Above 200MA: {breadth_data['russell2000']['pct_above_200ma']}%")

    # ── TRUE Index-Level A/D Ratios (v4.2: Finviz + yfinance) ─────────────
    print("  正在抓取指數層級 A/D Ratio（SPY/QQQ/DIA/IWM 真實漲跌家數）…")
    index_ad_data = fetch_index_ad_ratios(close_df)

    # Inject TRUE ADR into indices (as float) + log for verification
    print("\n  ══ A/D Ratio 核对日誌 ══")
    for sym in ["SPY", "QQQ", "DIA", "IWM"]:
        ad_entry = index_ad_data.get(sym, {})
        ratio    = ad_entry.get("ad_ratio")
        adv      = ad_entry.get("advances", "N/A")
        dec      = ad_entry.get("declines", "N/A")
        src      = ad_entry.get("source", "unknown")
        if sym in indices_out:
            indices_out[sym]["ad_ratio"]  = ratio   # float, not string
            indices_out[sym]["ad_detail"] = ad_entry  # full detail for audit
        print(
            f"  [LOG] {sym}: 漲家數={adv}  跌家數={dec}  "
            f"ADR={ratio}  數據來源={src}"
        )
    print("  ══ A/D Ratio 核对日誌結束 ══\n")

    # Full-market A/D from Barchart (NYSE/NASDAQ exchange-level, for Section 4C)
    print("  正在從 Barchart 抓取 NYSE/NASDAQ 全市場 Advance/Decline 數據（Section 4C）…")
    ad_data = fetch_barchart_advance_decline()
    if ad_data.get("NYSE"):
        nyse_ad = ad_data["NYSE"]
        nasd_ad = ad_data.get("NASDAQ", {})
        print(f"  ✓  NYSE:   Adv={nyse_ad['advances']:,}  Dec={nyse_ad['declines']:,}  ADR={nyse_ad['ad_ratio']}")
        print(f"  ✓  NASDAQ: Adv={nasd_ad['advances']:,}  Dec={nasd_ad['declines']:,}  ADR={nasd_ad['ad_ratio']}")
    else:
        print("  ⚠  Barchart A/D 數據不可用")

    # Volatility ADR (Average Daily Range %) — renamed to avoid confusion
    print("\n[8/8] 計算波動率 ADR（Avg Daily Range，14 天）…")
    vol_adr = fetch_volatility_adr(raw)
    for sym, val in vol_adr.items():
        print(f"  ✓  {sym} Volatility ADR(14): {val}%")

    breadth_out = {
        **breadth_data,
        "market_wide_advance_decline": ad_data,       # Barchart NYSE/NASDAQ A/D (Section 4C)
        "index_ad_ratios":             index_ad_data, # TRUE index-level A/D (Section 2)
        "volatility_adr":              vol_adr,       # 14-day Avg Daily Range % (volatility)
    }

    # ── 8. Assemble output ───────────────────────────────────────────
    output = {
        "meta": {
            "generated_hkt":  ts_hkt,
            "generated_et":   ts_et,
            "date":           date_str,
            "source":         "Yahoo Finance + CNN + NAAIM + Finviz + Barchart",
            "rsi_method":     "Wilder SMMA (EWM alpha=1/14)",
            "schema_version": "4.2",
        },
        "macro":     macro_out,
        "indices":   indices_out,
        "sentiment": sentiment_out,
        "sectors":   sector_rows,
        "industry":  industry_out,
        "breadth":   breadth_out,
    }

    # ── Save JSON ────────────────────────────────────────────────────
    abs_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size_kb = os.path.getsize(abs_path) / 1024
    print(f"\n✅  JSON 已儲存至 {abs_path}  ({size_kb:.1f} KB)")
    print(f"    Schema version: {output['meta']['schema_version']}")
    print(f"    Sectors: {len(sector_rows)}  |  Industries: {len(industry_out)}")
    return output


if __name__ == "__main__":
    try:
        fetch_all()
    except Exception:
        traceback.print_exc()
