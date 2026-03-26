"""
fetch_all_data.py
-----------------
Credit-Efficient Market Data Fetcher  v3.0
抓取所有市場數據，整理後儲存至 data/today_market.json。
下次可直接讀取 JSON，無需重新運算。

JSON 結構（v3.0）：
{
  "meta":      { generated_hkt, generated_et, date, source, schema_version }
  "macro":     { VIX, DXY, TNX_10Y, GOLD, OIL_WTI, BTC }
  "indices":   { SPY, QQQ, DIA, IWM }   ← 含 1D change & vs 20/50/200 MA %
  "sentiment": {
      "fear_greed":  { score, rating, prev_close, prev_1w, prev_1m, prev_1y, timestamp }
      "put_call":    { value, rating, source }
      "naaim":       { value, date, source }
  }
  "sectors":   [ { symbol, name, change_1d_pct, change_1w_pct, change_1m_pct,
                   rsi14, ma20, ma50, ma200,
                   vs_ma20_pct, vs_ma50_pct, vs_ma200_pct,
                   vs20ma, status } ... ]  ← 按 RSI 降序
  "industry":  [ { rank, label, change_1d_pct, change_1w_pct, change_1m_pct,
                   change_3m_pct, change_ytd_pct } ... ]  ← Top 15 by 1D
  "breadth":   {
      "sp500":      { total, above_20ma, above_50ma, above_200ma,
                       pct_above_20ma, pct_above_50ma, pct_above_200ma }
      "nasdaq":     { ... }
      "nyse":       { ... }
      "russell2000":{ ... }  ← IWM 成份股 % above 20/50/200 MA
      "market_wide_advance_decline": {
          "NYSE":   { advances, declines, unchanged, total_issues,
                      pct_advancing, pct_declining, adv_vol, dec_vol,
                      ad_ratio, new_52w_highs, new_52w_lows }
          "NASDAQ": { ... }
          "source": "Barchart.com/stocks/momentum (live)"
      }  ← 抓取型：Barchart 全市場 Advance/Decline Ratio
      "avg_daily_range": { SPY, QQQ, DIA, IWM }  ← 技術型：14-day Avg Daily Range %
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

# 主要指數 ETF：全部計算 MA 距離百分比
INDEX_ETFS = ["SPY", "QQQ", "DIA", "IWM"]

# 板塊 ETF（對應名稱）
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

# HTTP 請求 Headers
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# 輸出路徑（相對於本腳本所在目錄的上一層）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(_SCRIPT_DIR, "..", "data", "today_market.json")


# ─── 工具函數 ──────────────────────────────────────────────────────────────────
def get_wilder_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """
    Wilder's SMMA RSI（等同 pandas_ta.rsi()）
    使用 EWM alpha=1/window 實作，避免 pandas_ta Python 版本限制。
    """
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def pct_from_ma(price: float, ma: float) -> float:
    """價格距離 MA 的百分比（正值 = 在 MA 上方）"""
    if not ma or ma == 0:
        return 0.0
    return round((price - ma) / ma * 100, 2)


def ma_status(price: float, ma20: float, ma50: float, ma200: float) -> str:
    """判斷價格相對三條均線的位置"""
    if price > max(ma20, ma50, ma200):
        return "ABOVE ALL"
    if price < min(ma20, ma50, ma200):
        return "BELOW ALL"
    return "MIXED"


def safe_float(val, decimals: int = 4):
    """安全轉換為 float，NaN/None 回傳 None"""
    try:
        v = float(val)
        return None if pd.isna(v) else round(v, decimals)
    except Exception:
        return None


def build_full_entry(s: pd.Series, ticker: str) -> dict:
    """
    給定一條收盤價 Series，計算並回傳完整的 ETF 數據字典：
    price, change_1d_pct, rsi14, ma20/50/200,
    vs_ma20/50/200_pct, vs20ma (Green/Red), status
    """
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


# ─── Sentiment 抓取函數 ────────────────────────────────────────────────────────
def fetch_cnn_fear_greed() -> dict:
    """
    從 CNN Fear & Greed API 抓取：
    - Fear & Greed Index（當前分數、評級、歷史對比）
    - Put/Call Ratio（CNN 計算的 5-day average）
    """
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": HTTP_HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        d = r.json()

        # Fear & Greed
        fg = d.get("fear_and_greed", {})
        fear_greed = {
            "score":       round(fg.get("score", 0), 2),
            "rating":      fg.get("rating", "N/A"),
            "timestamp":   fg.get("timestamp", ""),
            "prev_close":  round(fg.get("previous_close", 0), 2),
            "prev_1w":     round(fg.get("previous_1_week", 0), 2),
            "prev_1m":     round(fg.get("previous_1_month", 0), 2),
            "prev_1y":     round(fg.get("previous_1_year", 0), 2),
            "source":      "CNN Fear & Greed API",
        }

        # Put/Call Ratio（CNN 使用 5-day avg equity P/C ratio）
        pc_data = d.get("put_call_options", {})
        pc_pts  = pc_data.get("data", [])
        pc_val  = round(pc_pts[-1]["y"], 4) if pc_pts else None
        pc_rating = pc_pts[-1].get("rating", "N/A") if pc_pts else "N/A"
        put_call = {
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
    從 NAAIM 官網抓取最新的 NAAIM Exposure Index（週度數據）。
    解析 Google Charts DataTable 中的 JavaScript 數組。
    """
    url = "https://www.naaim.org/programs/naaim-exposure-index/"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()

        # 找到 drawNaaimChart 函數定義區段（排除 SP500 數據）
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

        # 取最後一個數據點（最新週）
        last = rows[-1]
        year, month, day, value = int(last[0]), int(last[1]) + 1, int(last[2]), float(last[3])
        date_str = f"{year}-{month:02d}-{day:02d}"

        return {
            "value":  round(value, 2),
            "date":   date_str,
            "source": "NAAIM Exposure Index (weekly, latest survey)",
        }
    except Exception as e:
        print(f"  ⚠  NAAIM 抓取失敗: {e}")
        return {
            "value":  None,
            "date":   None,
            "source": "NAAIM (failed)",
        }


# ─── Sector 週/月回報（Finviz Groups）─────────────────────────────────────────
def fetch_sector_perf() -> dict:
    """
    從 Finviz Groups 頁面抓取 11 個板塊的 1D / 1W / 1M 回報率。
    回傳 dict：{ "XLF": { "name": ..., "perf_1d": ..., "perf_1w": ..., "perf_1m": ... }, ... }
    """
    url = "https://finviz.com/groups.ashx?g=sector&sg=&o=name&p=d"
    # Finviz sector ticker → ETF symbol 映射
    sector_map = {
        "basicmaterials":        "XLB",
        "communicationservices": "XLC",
        "consumercyclical":      "XLY",
        "consumerdefensive":     "XLP",
        "energy":                "XLE",
        "financial":             "XLF",   # Finviz uses 'financial' not 'financialservices'
        "financialservices":     "XLF",   # fallback alias
        "healthcare":            "XLV",
        "industrials":           "XLI",
        "realestate":            "XLRE",
        "technology":            "XLK",
        "utilities":             "XLU",
    }
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        match = re.search(r"var rows = (\[.*?\]);", r.text, re.DOTALL)
        if not match:
            raise ValueError("Finviz sector rows not found")

        rows = json.loads(match.group(1))
        result = {}
        for row in rows:
            ticker_key = row.get("ticker", "").lower()
            etf = sector_map.get(ticker_key)
            if etf:
                result[etf] = {
                    "name":      row.get("label", etf),
                    "perf_1d":   row.get("perfT"),
                    "perf_1w":   row.get("perfW"),
                    "perf_1m":   row.get("perfM"),
                    "perf_3m":   row.get("perfQ"),
                    "perf_ytd":  row.get("perfYtd"),
                }
        return result
    except Exception as e:
        print(f"  ⚠  Finviz Sector 回報率抓取失敗: {e}")
        return {}


# ─── Industry Top 15（Finviz Groups）─────────────────────────────────────────
def fetch_industry_top15() -> list:
    """
    從 Finviz Groups 頁面抓取所有行業，按 1D 回報率降序，回傳 Top 15。
    """
    url = "https://finviz.com/groups.ashx?g=industry&sg=&o=perf1d&p=d"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        match = re.search(r"var rows = (\[.*?\]);", r.text, re.DOTALL)
        if not match:
            raise ValueError("Finviz industry rows not found")

        rows = json.loads(match.group(1))
        # 按 1D 回報率降序排列
        rows.sort(key=lambda x: x.get("perfT", -999), reverse=True)
        top15 = []
        for i, row in enumerate(rows[:15], 1):
            top15.append({
                "rank":          i,
                "label":         row.get("label", ""),
                "change_1d_pct": row.get("perfT"),
                "change_1w_pct": row.get("perfW"),
                "change_1m_pct": row.get("perfM"),
                "change_3m_pct": row.get("perfQ"),
                "change_ytd_pct": row.get("perfYtd"),
                "source":        "Finviz Groups",
            })
        return top15
    except Exception as e:
        print(f"  ⚠  Finviz Industry Top 15 抓取失敗: {e}")
        return []


# ─── Breadth（Finviz Screener）────────────────────────────────────────────────
def fetch_finviz_count(filters: str) -> int | None:
    """從 Finviz Screener 抓取符合條件的股票數量"""
    url = f"https://finviz.com/screener.ashx?v=111&f={filters}&ft=4"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        match = re.search(r'result_count\":(\d+)', r.text)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def fetch_breadth() -> dict:
    """
    從 Finviz Screener 抓取市場廣度數據：
    - S&P 500 / NASDAQ / NYSE / Russell 2000 中高於 20/50/200 MA 的股票百分比
    Finviz 篩選器代碼：idx_sp500 / exch_nasd / exch_nyse / idx_rut
    """
    print("  正在抓取 S&P 500 廣度數據…")
    sp500_total    = fetch_finviz_count("idx_sp500")
    time.sleep(0.5)
    sp500_a200     = fetch_finviz_count("idx_sp500,ta_sma200_pa")
    time.sleep(0.5)
    sp500_a50      = fetch_finviz_count("idx_sp500,ta_sma50_pa")
    time.sleep(0.5)
    sp500_a20      = fetch_finviz_count("idx_sp500,ta_sma20_pa")
    time.sleep(0.5)

    print("  正在抓取 NASDAQ 廣度數據…")
    nasd_total     = fetch_finviz_count("exch_nasd")
    time.sleep(0.5)
    nasd_a200      = fetch_finviz_count("exch_nasd,ta_sma200_pa")
    time.sleep(0.5)
    nasd_a50       = fetch_finviz_count("exch_nasd,ta_sma50_pa")
    time.sleep(0.5)
    nasd_a20       = fetch_finviz_count("exch_nasd,ta_sma20_pa")
    time.sleep(0.5)

    print("  正在抓取 NYSE 廣度數據…")
    nyse_total     = fetch_finviz_count("exch_nyse")
    time.sleep(0.5)
    nyse_a200      = fetch_finviz_count("exch_nyse,ta_sma200_pa")
    time.sleep(0.5)
    nyse_a50       = fetch_finviz_count("exch_nyse,ta_sma50_pa")
    time.sleep(0.5)
    nyse_a20       = fetch_finviz_count("exch_nyse,ta_sma20_pa")
    time.sleep(0.5)

    print("  正在抓取 Russell 2000 (IWM) 廣度數據…")
    rut_total      = fetch_finviz_count("idx_rut")
    time.sleep(0.5)
    rut_a200       = fetch_finviz_count("idx_rut,ta_sma200_pa")
    time.sleep(0.5)
    rut_a50        = fetch_finviz_count("idx_rut,ta_sma50_pa")
    time.sleep(0.5)
    rut_a20        = fetch_finviz_count("idx_rut,ta_sma20_pa")

    def pct(above, total):
        if above is None or total is None or total == 0:
            return None
        return round(above / total * 100, 1)

    return {
        "sp500": {
            "total":           sp500_total,
            "above_20ma":      sp500_a20,
            "above_50ma":      sp500_a50,
            "above_200ma":     sp500_a200,
            "pct_above_20ma":  pct(sp500_a20, sp500_total),
            "pct_above_50ma":  pct(sp500_a50, sp500_total),
            "pct_above_200ma": pct(sp500_a200, sp500_total),
        },
        "nasdaq": {
            "total":           nasd_total,
            "above_20ma":      nasd_a20,
            "above_50ma":      nasd_a50,
            "above_200ma":     nasd_a200,
            "pct_above_20ma":  pct(nasd_a20, nasd_total),
            "pct_above_50ma":  pct(nasd_a50, nasd_total),
            "pct_above_200ma": pct(nasd_a200, nasd_total),
        },
        "nyse": {
            "total":           nyse_total,
            "above_20ma":      nyse_a20,
            "above_50ma":      nyse_a50,
            "above_200ma":     nyse_a200,
            "pct_above_20ma":  pct(nyse_a20, nyse_total),
            "pct_above_50ma":  pct(nyse_a50, nyse_total),
            "pct_above_200ma": pct(nyse_a200, nyse_total),
        },
        "russell2000": {
            "total":           rut_total,
            "above_20ma":      rut_a20,
            "above_50ma":      rut_a50,
            "above_200ma":     rut_a200,
            "pct_above_20ma":  pct(rut_a20, rut_total),
            "pct_above_50ma":  pct(rut_a50, rut_total),
            "pct_above_200ma": pct(rut_a200, rut_total),
        },
        "source": "Finviz Screener",
    }


# ─── ADR 計算（yfinance High/Low）─────────────────────────────────────────────
def fetch_adr(raw_data: pd.DataFrame, window: int = 14) -> dict:
    """
    計算四大指數 ETF 的 ADR（Average Daily Range）。
    ADR = mean( (High - Low) / ((High + Low) / 2) * 100 ) over last `window` days
    此為「技術型 ADR」（Average Daily Range %），用於衡量波動性，
    與「市場廣度 ADR」（Advance/Decline Ratio）不同。
    """
    adr_out = {}
    for ticker in INDEX_ETFS:
        try:
            high  = raw_data["High"][ticker].dropna()
            low   = raw_data["Low"][ticker].dropna()
            daily_range = (high - low) / ((high + low) / 2) * 100
            adr   = safe_float(daily_range.iloc[-window:].mean(), 2)
            adr_out[ticker] = adr
        except Exception as e:
            print(f"  ⚠  {ticker} ADR 計算失敗: {e}")
            adr_out[ticker] = None
    return adr_out


# ─── Barchart Advance/Decline Ratio（抓取型）──────────────────────────────────
def fetch_barchart_advance_decline() -> dict:
    """
    從 Barchart.com 抓取 NYSE / NASDAQ 的 Advance/Decline 數據。
    數據源：https://www.barchart.com/stocks/momentum
    API：  /proxies/core-api/v1/momentum/get

    回傳結構：
    {
      "NYSE":   { advances, declines, unchanged, total_issues,
                  pct_advancing, pct_declining,
                  adv_vol, dec_vol,
                  ad_ratio, new_52w_highs, new_52w_lows },
      "NASDAQ": { ... },
      "source": "Barchart.com/stocks/momentum"
    }
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
            "User-Agent": HTTP_HEADERS["User-Agent"],
            "Accept":     "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # Step 1: 訪問頁面取得 XSRF Token（必須）
        r0 = session.get(REFERER_URL, timeout=20)
        r0.raise_for_status()
        xsrf = requests.utils.unquote(session.cookies.get("XSRF-TOKEN", ""))
        if not xsrf:
            raise ValueError("XSRF-TOKEN not found in cookies")

        # Step 2: 帶 Token 呼叫 API
        session.headers["X-Xsrf-Token"] = xsrf
        session.headers["Referer"] = REFERER_URL
        r = session.get(API_URL, timeout=20)
        r.raise_for_status()
        payload = r.json()

        result = {}
        for item in payload.get("data", []):
            raw_item = item.get("raw", {})
            exchange = raw_item.get("exchange", item.get("exchange", ""))
            if exchange not in ("NYSE", "NASDAQ"):
                continue

            advances  = int(raw_item.get("advancingIssues", 0))
            declines  = int(raw_item.get("decliningIssues", 0))
            unchanged = int(raw_item.get("unchangedIssues", 0))
            total     = advances + declines + unchanged
            adv_vol   = int(raw_item.get("advancingVolume", 0))
            dec_vol   = int(raw_item.get("decliningVolume", 0))
            unc_vol   = int(raw_item.get("unchangedVolume", 0))
            highs     = int(raw_item.get("newHighs", raw_item.get("high52w", 0)))
            lows      = int(raw_item.get("newLows",  raw_item.get("low52w",  0)))

            ad_ratio  = round(advances / declines, 3) if declines > 0 else None

            result[exchange] = {
                "advances":       advances,
                "declines":       declines,
                "unchanged":      unchanged,
                "total_issues":   total,
                "pct_advancing":  round(raw_item.get("percentAdvancingIssues", 0), 1),
                "pct_declining":  round(raw_item.get("percentDecliningIssues", 0), 1),
                "adv_vol":        adv_vol,
                "dec_vol":        dec_vol,
                "unc_vol":        unc_vol,
                "ad_ratio":       ad_ratio,
                "new_52w_highs":  highs,
                "new_52w_lows":   lows,
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


# ─── 主要抓取函數 ──────────────────────────────────────────────────────────────
def fetch_all() -> dict:
    """
    一次性抓取所有市場數據，回傳結構化 dict，
    並同步儲存至 data/today_market.json。
    """
    # ── 時間戳 ───────────────────────────────────────────────────────────────
    et_tz   = pytz.timezone("US/Eastern")
    hkt_tz  = pytz.timezone("Asia/Hong_Kong")
    now_et  = datetime.now(et_tz)
    now_hkt = datetime.now(hkt_tz)
    ts_hkt  = now_hkt.strftime("%Y-%m-%d %H:%M")
    ts_et   = now_et.strftime("%Y-%m-%d %H:%M")
    date_str = now_hkt.strftime("%Y-%m-%d")

    print(f"╔══════════════════════════════════════════════╗")
    print(f"  Credit Efficient — Market Data Fetcher v3.0")
    print(f"  HKT: {ts_hkt}   ET: {ts_et}")
    print(f"╚══════════════════════════════════════════════╝\n")

    # ── 1. 一次性下載所有 ticker（2 年日線，確保 200MA 足夠）────────────────
    all_tickers = list(MACRO_TICKERS.values()) + INDEX_ETFS + list(SECTORS.keys())
    all_tickers = list(dict.fromkeys(all_tickers))   # 去重保序

    print(f"[1/7] 正在下載 {len(all_tickers)} 個 ticker 的歷史數據（2y / 1d）…")
    raw = yf.download(
        all_tickers,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    # 相容 yfinance MultiIndex 結構
    close_df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    print(f"     下載完成，共 {len(close_df)} 個交易日，{close_df.shape[1]} 個標的\n")

    # ── 2. 宏觀指標 ──────────────────────────────────────────────────────────
    print("[2/7] 處理宏觀指標（Macro）…")
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

    # ── 3. 主要指數 ETF（Indices）────────────────────────────────────────────
    print("\n[3/7] 處理主要指數 ETF（Indices）…")
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

    # ── 4. Sentiment（CNN Fear & Greed + NAAIM）──────────────────────────────
    print("\n[4/7] 抓取市場情緒指標（Sentiment）…")
    print("  正在抓取 CNN Fear & Greed Index…")
    cnn_data   = fetch_cnn_fear_greed()
    print(f"  ✓  Fear & Greed: {cnn_data['fear_greed']['score']} ({cnn_data['fear_greed']['rating']})")
    print(f"  ✓  Put/Call Ratio: {cnn_data['put_call']['value']} ({cnn_data['put_call']['rating']})")

    print("  正在抓取 NAAIM Exposure Index…")
    naaim_data = fetch_naaim()
    if naaim_data["value"]:
        print(f"  ✓  NAAIM: {naaim_data['value']} (as of {naaim_data['date']})")
    else:
        print("  ⚠  NAAIM 數據不可用")

    sentiment_out = {
        "fear_greed": cnn_data["fear_greed"],
        "put_call":   cnn_data["put_call"],
        "naaim":      naaim_data,
    }

    # ── 5. Sector ETF（含週/月回報）─────────────────────────────────────────
    print("\n[5/7] 處理板塊 ETF（Sectors，含 1D/1W/1M 回報）…")
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

        # 補充 Finviz 週/月回報率
        fv = finviz_sector_perf.get(ticker, {})
        entry["change_1w_pct"] = fv.get("perf_1w")
        entry["change_1m_pct"] = fv.get("perf_1m")
        entry["change_3m_pct"] = fv.get("perf_3m")
        entry["change_ytd_pct"] = fv.get("perf_ytd")

        # 重新排列 key 順序，symbol/name 放最前面
        ordered = {"symbol": ticker, "name": name}
        ordered.update({k: v for k, v in entry.items()
                        if k not in ("symbol", "name")})
        sector_rows.append(ordered)

    # 按 RSI 降序排列
    sector_rows.sort(key=lambda x: x.get("rsi14") or 0, reverse=True)
    print(f"  ✓  共處理 {len(sector_rows)} 個板塊 ETF，已按 RSI 降序排列")

    # ── 6. Industry Top 15（Finviz）─────────────────────────────────────────
    print("\n[6/7] 抓取行業 Top 15（Industry，Finviz）…")
    industry_out = fetch_industry_top15()
    if industry_out:
        print(f"  ✓  共抓取 {len(industry_out)} 個行業")
        for row in industry_out[:3]:
            print(f"     #{row['rank']} {row['label']}: {row['change_1d_pct']:+.2f}% (1D)")
    else:
        print("  ⚠  Industry 數據不可用")

        # ── 7. Breadth & ADR ─────────────────────────────────────────────────
    print("\n[7/7] 抓取市場廣度（Breadth）及 Advance/Decline Ratio…")
    breadth_data = fetch_breadth()
    print(f"  ✓  S&P 500 Above 200MA: {breadth_data['sp500']['pct_above_200ma']}%")
    print(f"  ✓  NASDAQ  Above 200MA: {breadth_data['nasdaq']['pct_above_200ma']}%")
    print(f"  ✓  NYSE    Above 200MA: {breadth_data['nyse']['pct_above_200ma']}%")

    # 抓取型 ADR：Barchart NYSE/NASDAQ Advance/Decline Ratio
    print("  正在從 Barchart 抓取 NYSE/NASDAQ Advance/Decline 數據…")
    ad_data = fetch_barchart_advance_decline()
    if ad_data.get("NYSE") and ad_data["NYSE"]:
        nyse_ad = ad_data["NYSE"]
        nasd_ad = ad_data.get("NASDAQ", {})
        print(f"  ✓  NYSE:   Advances={nyse_ad['advances']:,}  Declines={nyse_ad['declines']:,}  "
              f"Unchanged={nyse_ad['unchanged']:,}  ADR={nyse_ad['ad_ratio']}")
        print(f"  ✓  NASDAQ: Advances={nasd_ad['advances']:,}  Declines={nasd_ad['declines']:,}  "
              f"Unchanged={nasd_ad['unchanged']:,}  ADR={nasd_ad['ad_ratio']}")
    else:
        print("  ⚠  Barchart A/D 數據不可用")

    # 技術型 ADR：yfinance High/Low Average Daily Range %
    print("  正在計算技術型 ADR（Average Daily Range，14 天）…")
    avg_daily_range = fetch_adr(raw)
    for sym, val in avg_daily_range.items():
        print(f"  ✓  {sym} Avg Daily Range(14): {val}%")

    breadth_out = {
        **breadth_data,
        "market_wide_advance_decline": ad_data,  # 抓取型：Barchart 全市場 A/D Ratio
        "avg_daily_range": avg_daily_range,       # 技術型：yfinance 14-day ADR %
    }

    # ── 8. 組合完整 JSON 輸出 ────────────────────────────────────────────────
    output = {
        "meta": {
            "generated_hkt":  ts_hkt,
            "generated_et":   ts_et,
            "date":           date_str,
            "source":         "Yahoo Finance (yfinance) + CNN + NAAIM + Finviz + Barchart",
            "rsi_method":     "Wilder SMMA (EWM alpha=1/14)",
            "schema_version": "3.2",
        },
        "macro":     macro_out,      # VIX, DXY, 10Y Yield, Gold, Oil, BTC
        "indices":   indices_out,    # SPY, QQQ, DIA, IWM（含 MA 距離 %）
        "sentiment": sentiment_out,  # Fear & Greed, Put/Call, NAAIM
        "sectors":   sector_rows,    # 11 板塊 ETF（含週/月回報），按 RSI 降序
        "industry":  industry_out,   # Finviz Top 15 行業（按 1D 回報）
        "breadth":   breadth_out,    # % above MA + ADR
    }

    # ── 9. 儲存 JSON ─────────────────────────────────────────────────────────
    abs_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*60}")
    print(f"✅ JSON 已儲存至: {abs_path}")
    print(f"   大小: {os.path.getsize(abs_path):,} bytes")
    print(f"   結構: meta / macro({len(macro_out)}) / "
          f"indices({len(indices_out)}) / sentiment(3) / "
          f"sectors({len(sector_rows)}) / industry({len(industry_out)}) / "
          f"breadth(sp500+nasdaq+nyse+adr)")
    print(f"{'─'*60}\n")

    return output


# ─── 終端預覽函數 ──────────────────────────────────────────────────────────────
def print_summary(data: dict):
    """將抓取結果以易讀格式輸出到終端"""
    meta = data["meta"]
    print(f"{'═'*70}")
    print(f"  MARKET SUMMARY  {meta['date']}  [{meta['generated_hkt']} HKT]  v{meta['schema_version']}")
    print(f"{'═'*70}")

    # Macro
    print("\n── Macro Indicators ──────────────────────────────────────────────")
    print(f"  {'Indicator':<14} {'Price':>12}  {'1D Chg%':>8}")
    print(f"  {'─'*14} {'─'*12}  {'─'*8}")
    for k, v in data["macro"].items():
        p   = v.get("price")
        pct = v.get("change_1d_pct")
        p_str   = f"{p:>12,.4f}" if p is not None else f"{'N/A':>12}"
        pct_str = (f"{'+' if pct >= 0 else ''}{pct:.2f}%" if pct is not None else "N/A")
        print(f"  {k:<14} {p_str}  {pct_str:>8}")

    # Indices
    print("\n── Index ETFs (MA Distance %) ────────────────────────────────────")
    hdr = f"  {'Sym':<6} {'Price':>8} {'1D%':>7} {'RSI':>6} {'vs20MA':>8} {'vs50MA':>8} {'vs200MA':>9} {'Status'}"
    print(hdr)
    print(f"  {'─'*6} {'─'*8} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*9} {'─'*10}")
    for sym, v in data["indices"].items():
        pct = v.get("change_1d_pct")
        pct_s = f"{'+' if pct and pct >= 0 else ''}{pct:.2f}%" if pct else "N/A"
        print(
            f"  {sym:<6} {v['price']:>8.2f} {pct_s:>7} "
            f"{v['rsi14']:>6.1f} "
            f"{v['vs_ma20_pct']:>+8.2f}% "
            f"{v['vs_ma50_pct']:>+8.2f}% "
            f"{v['vs_ma200_pct']:>+9.2f}% "
            f"{v['status']}"
        )

    # Sentiment
    print("\n── Sentiment Indicators ──────────────────────────────────────────")
    fg = data["sentiment"]["fear_greed"]
    pc = data["sentiment"]["put_call"]
    na = data["sentiment"]["naaim"]
    print(f"  CNN Fear & Greed:  {fg['score']} ({fg['rating']})")
    print(f"    Prev Close: {fg['prev_close']}  |  1W ago: {fg['prev_1w']}  |  1M ago: {fg['prev_1m']}")
    print(f"  Put/Call Ratio:    {pc['value']} ({pc['rating']})")
    print(f"  NAAIM Exposure:    {na['value']} (as of {na['date']})")

    # Sectors
    print("\n── Sector ETF Rotation (Sorted by RSI) ──────────────────────────")
    df_sec = pd.DataFrame(data["sectors"])
    cols   = ["symbol", "name", "price", "change_1d_pct", "change_1w_pct", "change_1m_pct", "rsi14", "status"]
    available_cols = [c for c in cols if c in df_sec.columns]
    print(df_sec[available_cols].to_markdown(index=False))

    # Industry Top 15
    print("\n── Industry Top 15 (by 1D Return, Finviz) ───────────────────────")
    df_ind = pd.DataFrame(data["industry"])
    if not df_ind.empty:
        cols_ind = ["rank", "label", "change_1d_pct", "change_1w_pct", "change_1m_pct"]
        print(df_ind[cols_ind].to_markdown(index=False))

    # Breadth
    print("\n── Market Breadth (% Stocks Above MA) ─────────────────────────────────")
    print(f"  {'Index':<12} {'Above 20MA':>12} {'Above 50MA':>12} {'Above 200MA':>13}")
    print(f"  {'─'*12} {'─'*12} {'─'*12} {'─'*13}")
    for idx_name in ["sp500", "nasdaq", "nyse", "russell2000"]:
        b = data["breadth"].get(idx_name, {})
        if not b:
            continue
        label = "RUSSELL2000" if idx_name == "russell2000" else idx_name.upper()
        print(
            f"  {label:<12} "
            f"{str(b.get('pct_above_20ma', 'N/A'))+'%':>12} "
            f"{str(b.get('pct_above_50ma', 'N/A'))+'%':>12} "
            f"{str(b.get('pct_above_200ma', 'N/A'))+'%':>13}"
        )

    # Advance/Decline Ratio
    print("\n── NYSE/NASDAQ Market-Wide Advance/Decline Ratio (Barchart Live) ────────")
    ad = data["breadth"].get("market_wide_advance_decline", {})
    for exch in ["NYSE", "NASDAQ"]:
        ex_data = ad.get(exch)
        if ex_data:
            print(
                f"  {exch:<8} Adv={ex_data['advances']:>5,}  "
                f"Dec={ex_data['declines']:>5,}  "
                f"Unch={ex_data['unchanged']:>4,}  "
                f"ADR={ex_data['ad_ratio']}  "
                f"({ex_data['pct_advancing']:.1f}% adv)  "
                f"52wH={ex_data['new_52w_highs']}  52wL={ex_data['new_52w_lows']}"
            )
    print(f"  Source: {ad.get('source', 'N/A')}")

    # Avg Daily Range (Technical)
    print("\n── Avg Daily Range % (14-day, Technical) ──────────────────────────────")
    avg_dr = data["breadth"].get("avg_daily_range", {})
    for sym, val in avg_dr.items():
        print(f"  {sym}: {val}%")
    print()


# ─── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        data = fetch_all()
        print_summary(data)
    except Exception as e:
        traceback.print_exc()
        print(f"\n❌ 錯誤: {e}")
