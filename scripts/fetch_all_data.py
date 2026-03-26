"""
fetch_all_data.py
-----------------
Credit-Efficient Market Data Fetcher  v2.0
抓取所有市場數據，整理後儲存至 data/today_market.json。
下次可直接讀取 JSON，無需重新運算。

JSON 結構：
{
  "meta":     { generated_hkt, generated_et, date, source }
  "macro":    { VIX, DXY, TNX_10Y, GOLD, OIL_WTI, BTC }
  "indices":  { SPY, QQQ, DIA, IWM }          ← 主要指數 ETF（含 MA 距離 %）
  "sectors":  [ { symbol, price, change_1d_pct, rsi14,
                  ma20, ma50, ma200,
                  vs_ma20_pct, vs_ma50_pct, vs_ma200_pct,
                  vs20ma, status } ... ]       ← 按 RSI 降序
}
"""

import json
import os
import traceback
from datetime import datetime

import pandas as pd
import pytz
import yfinance as yf

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

# 板塊 ETF
SECTORS = [
    "XLF", "XLK", "XLE", "XLI", "XLV",
    "XLP", "XLY", "XLB", "XLU", "XLC", "XLRE",
]

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
    print(f"  Credit Efficient — Market Data Fetcher v2.0")
    print(f"  HKT: {ts_hkt}   ET: {ts_et}")
    print(f"╚══════════════════════════════════════════════╝\n")

    # ── 1. 一次性下載所有 ticker（2 年日線，確保 200MA 足夠）────────────────
    all_tickers = list(MACRO_TICKERS.values()) + INDEX_ETFS + SECTORS
    all_tickers = list(dict.fromkeys(all_tickers))   # 去重保序

    print(f"[1/4] 正在下載 {len(all_tickers)} 個 ticker 的歷史數據（2y / 1d）…")
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
    print("[2/4] 處理宏觀指標（Macro）…")
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
    print("\n[3/4] 處理主要指數 ETF（Indices）…")
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
            f"vs200MA={entry['vs_ma200_pct']}%  "
            f"[{entry['status']}]"
        )

    # ── 4. Sector ETF RSI 輪動排行 ───────────────────────────────────────────
    print("\n[4/4] 處理板塊 ETF（Sectors）…")
    sector_rows = []
    for ticker in SECTORS:
        if ticker not in close_df.columns:
            print(f"  ⚠  {ticker:6s} 數據缺失，跳過")
            continue
        s = close_df[ticker].dropna()
        if len(s) < 200:
            print(f"  ⚠  {ticker:6s} 數據不足 200 天，跳過")
            continue
        entry = build_full_entry(s, ticker)
        entry["symbol"] = ticker
        # 重新排列 key 順序，symbol 放最前面
        ordered = {"symbol": ticker}
        ordered.update({k: v for k, v in entry.items() if k != "symbol"})
        sector_rows.append(ordered)

    # 按 RSI 降序排列
    sector_rows.sort(key=lambda x: x.get("rsi14") or 0, reverse=True)
    print(f"  ✓  共處理 {len(sector_rows)} 個板塊 ETF，已按 RSI 降序排列")

    # ── 5. 組合完整 JSON 輸出 ────────────────────────────────────────────────
    output = {
        "meta": {
            "generated_hkt": ts_hkt,
            "generated_et":  ts_et,
            "date":          date_str,
            "source":        "Yahoo Finance via yfinance",
            "rsi_method":    "Wilder SMMA (EWM alpha=1/14)",
            "schema_version": "2.0",
        },
        "macro":   macro_out,    # VIX, DXY, 10Y Yield, Gold, Oil, BTC
        "indices": indices_out,  # SPY, QQQ, DIA, IWM（含 MA 距離 %）
        "sectors": sector_rows,  # 11 板塊 ETF，按 RSI 降序
    }

    # ── 6. 儲存 JSON ─────────────────────────────────────────────────────────
    abs_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*50}")
    print(f"✅ JSON 已儲存至: {abs_path}")
    print(f"   大小: {os.path.getsize(abs_path):,} bytes")
    print(f"   結構: meta / macro({len(macro_out)}) / "
          f"indices({len(indices_out)}) / sectors({len(sector_rows)})")
    print(f"{'─'*50}\n")

    return output


# ─── 終端預覽函數 ──────────────────────────────────────────────────────────────
def print_summary(data: dict):
    """將抓取結果以易讀格式輸出到終端"""
    meta = data["meta"]
    print(f"{'═'*60}")
    print(f"  MARKET SUMMARY  {meta['date']}  [{meta['generated_hkt']} HKT]")
    print(f"{'═'*60}")

    # Macro
    print("\n── Macro Indicators ──────────────────────────────────────")
    print(f"  {'Indicator':<14} {'Price':>12}  {'1D Chg%':>8}")
    print(f"  {'─'*14} {'─'*12}  {'─'*8}")
    for k, v in data["macro"].items():
        p   = v.get("price")
        pct = v.get("change_1d_pct")
        p_str   = f"{p:>12,.4f}" if p is not None else f"{'N/A':>12}"
        pct_str = (f"{'+' if pct >= 0 else ''}{pct:.2f}%" if pct is not None else "N/A")
        print(f"  {k:<14} {p_str}  {pct_str:>8}")

    # Indices
    print("\n── Index ETFs (with MA Distance %) ───────────────────────")
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

    # Sectors
    print("\n── Step 4C: Sector ETF Rotation (Sorted by RSI) ─────────")
    df_sec = pd.DataFrame(data["sectors"])
    cols   = ["symbol", "price", "change_1d_pct", "rsi14", "vs20ma", "status"]
    print(df_sec[cols].to_markdown(index=False))
    print()


# ─── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        data = fetch_all()
        print_summary(data)
    except Exception as e:
        traceback.print_exc()
        print(f"\n❌ 錯誤: {e}")
