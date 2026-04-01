import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Optional
from datetime import datetime
import json
import os
import sys

# Import tickers from fetch_all_data
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
try:
    from fetch_all_data import SECTORS, SECTOR_CATEGORIES
except ImportError:
    print("Failed to import from fetch_all_data")
    SECTORS = {}
    SECTOR_CATEGORIES = {}

class RSEngine:
    """
    Grok 級數 Relative Strength (RS) Engine + Stockbee Style 族群偵測
    專為 56 個 ETF 設計，支援 1m/3m/6m 加權回報 + Hot Cluster 🔥 + Volume Climax。
    
    完全符合你 Order 嘅所有要求：
    • 21/63/126 交易日回報
    • 加權公式 Score = 0.4*1m + 0.4*3m + 0.2*6m
    • 56 個 ETF 百分位排名 (1-99)
    • 按 SECTOR_CATEGORIES 分組，共振檢測 >50% 同時 Price > 20MA 且 RS Rating > 80
    • 成交量 > 1.5×20日平均 = Volume Climax
    """

    def __init__(self, sector_mapping: Optional[Dict[str, str]] = None):
        """
        sector_mapping: 可選 ticker → sector_category 映射字典
        如果唔畀，就假設輸入 DataFrame 已有 'sector_category' 欄位。
        """
        self.sector_mapping = sector_mapping

    def run_analysis(self, df: pd.DataFrame) -> Dict:
        """
        主入口：輸入每日 OHLCV 數據，輸出最新一日完整 RS 分析 + 族群結果。
        
        輸入要求：
        - df 欄位：['date', 'ticker', 'close', 'volume', 'sector_category' (可選)]
        - 至少 126+ 個交易日數據
        - 已按 ['ticker', 'date'] 排序
        """
        if df.empty or len(df['ticker'].unique()) != 56:
            raise ValueError(f"必須提供剛好 56 個 ETF 的數據, 實際有 {len(df['ticker'].unique())} 個")

        # 確保數據類型正確
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

        # 如果有 mapping，就補上 sector_category
        if self.sector_mapping is not None:
            df['sector_category'] = df['ticker'].map(self.sector_mapping)
        if 'sector_category' not in df.columns:
            raise ValueError("必須提供 sector_category 欄位或 mapping")

        # ==================== 1. RS Logic ====================
        # 計算 21/63/126 日回報
        for days, label in [(21, 'ret_1m'), (63, 'ret_3m'), (126, 'ret_6m')]:
            df[label] = df.groupby('ticker')['close'].transform(
                lambda x: (x / x.shift(days)) - 1
            )

        # 加權 RS Score
        df['rs_score'] = (
            df['ret_1m'] * 0.4 +
            df['ret_3m'] * 0.4 +
            df['ret_6m'] * 0.2
        )

        # ==================== 2. 技術指標 ====================
        # 20MA 價格同成交量
        df['ma20'] = df.groupby('ticker')['close'].transform(lambda x: x.rolling(20).mean())
        df['vol_ma20'] = df.groupby('ticker')['volume'].transform(lambda x: x.rolling(20).mean())

        df['above_20ma'] = df['close'] > df['ma20']
        df['volume_climax'] = df['volume'] > (df['vol_ma20'] * 1.5)

        # ==================== 3. 最新一日百分位排名 (RS Rating 1-99) ====================
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date].copy()

        # 跨 56 個 ETF 排名
        latest_df['rs_rating'] = (
            latest_df['rs_score'].rank(pct=True) * 98 + 1
        ).round(0).astype(int)   # 確保 1-99 整數

        # ==================== 4. Cluster Logic (Stockbee Style) ====================
        latest_df['is_strong'] = (latest_df['above_20ma']) & (latest_df['rs_rating'] > 80)

        hot_clusters: List[str] = []
        for sector, group in latest_df.groupby('sector_category'):
            hot_ratio = group['is_strong'].mean()
            if hot_ratio > 0.5:
                hot_clusters.append(f"{sector} 🔥")

        volume_climax_etfs = latest_df[latest_df['volume_climax']]['ticker'].tolist()

        # ==================== 最終輸出 ====================
        result = {
            "analysis_date": latest_date.strftime("%Y-%m-%d"),
            "latest_rs": latest_df[[
                'ticker', 'sector_category', 'rs_score', 'rs_rating',
                'above_20ma', 'volume_climax', 'is_strong'
            ]].reset_index(drop=True),
            "hot_clusters": hot_clusters,
            "volume_climax_etfs": volume_climax_etfs,
            "summary": (
                f"✅ 分析完成 | "
                f"熱門族群：{len(hot_clusters)} 個 🔥 | "
                f"成交量爆發 ETF：{len(volume_climax_etfs)} 個"
            )
        }

        return result


# ====================== 數據橋樑 (Data Bridge) ======================
def build_sector_mapping() -> Dict[str, str]:
    """建立 Ticker -> Sector Category 的對應表"""
    mapping = {}
    for category, tickers_dict in SECTOR_CATEGORIES.items():
        for ticker in tickers_dict.keys():
            mapping[ticker] = category
    return mapping

def fetch_historical_data() -> pd.DataFrame:
    """下載 56 個 ETF 過去 6 個月數據並轉換成 RS Engine 要求的格式"""
    tickers = list(SECTORS.keys())
    print(f"Fetching historical data for {len(tickers)} ETFs...")
    
    # 抓取 130 個交易日（約 6 個月）的數據
    # yfinance batch download
    data = yf.download(tickers, period="7mo", progress=False)
    
    # 整理 DataFrame
    # data 會有 MultiIndex columns (e.g. ('Close', 'AAPL'), ('Volume', 'AAPL'))
    close_df = data['Close'].reset_index()
    vol_df = data['Volume'].reset_index()
    
    # Unpivot / Melt
    close_melted = close_df.melt(id_vars=['Date'], var_name='ticker', value_name='close')
    vol_melted = vol_df.melt(id_vars=['Date'], var_name='ticker', value_name='volume')
    
    # Merge
    merged = pd.merge(close_melted, vol_melted, on=['Date', 'ticker'])
    merged.rename(columns={'Date': 'date'}, inplace=True)
    
    # 確保按 ticker, date 排序，並移除空值（可能有非交易日的 NaN）
    merged = merged.sort_values(['ticker', 'date']).dropna().reset_index(drop=True)
    
    return merged

def run_rs_analysis_and_save():
    """執行分析並將結果儲存到 data/analysis_results.json"""
    df = fetch_historical_data()
    mapping = build_sector_mapping()
    
    engine = RSEngine(sector_mapping=mapping)
    print("Running RS Analysis...")
    result = engine.run_analysis(df)
    
    # 轉換 DataFrame 為 JSON serializable
    result['latest_rs'] = result['latest_rs'].to_dict(orient='records')
    
    # 處理 NaN / Infinity 為 None (null in JSON)
    for row in result['latest_rs']:
        for k, v in row.items():
            if pd.isna(v):
                row[k] = None
    
    # 儲存
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'analysis_results.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    print(result['summary'])
    print(f"Hot Clusters: {result['hot_clusters']}")
    print(f"Result saved to {output_path}")
    
    return result

if __name__ == "__main__":
    run_rs_analysis_and_save()
