# Master Instruction: Daily Market Summary (System 2.0)

## 核心原則
1. **數據一致性**：所有市場數據（RSI, MA, Quotes）必須由 `scripts/fetch_all_data.py` 生成，嚴禁 AI 自行搜尋或計算。
2. **格式固定**：HTML 生成必須使用 `templates/report_template.html`，AI 只准替換占位符。
3. **語言**：報告內容使用繁體中文，技術術語保留英文。

## 數據定義
- **Sector RSI**: 使用 Wilder's SMMA 算法（14日）。
- **Market Regime**: 根據 VIX, SPY 價格與 MA 關係、NAAIM 及市場廣度綜合判定。
- **Macro Assets**: 包含 Gold (GC=F), Oil (CL=F), Bitcoin (BTC-USD)。

## 嚴禁行為
- 嚴禁使用 ~ 估算數據。
- 嚴禁在沒有數據支持的情況下撰寫市場評論。
