# Evolution: Lessons & Rules

## 2026-03-26 (System Update)
- **Lesson**: AI 直接計算 RSI 誤差極大（約 2-5%），且極度消耗 Credit。
- **Improvement**: 將所有計算邏輯移至 `fetch_all_data.py`，AI 改為讀取 JSON。
- **Rule**: 以後遇到複雜計算（如 MA 交叉、廣度百分比），必須先寫 Python 腳本解決，不准在 Prompt 裡要求 AI 計算。

## 2026-03-27 (Stage 2 — Iframe & Screenshot Handling)
- **Lesson 1 (Iframe Nesting)**: Stockbee MM 頁面有雙層 iframe。外層是 Google Sheets widget wrapper，內層才是真實 sheet HTML。必須用 JS console 提取 `#pageswitcher-content` 的 `src`，再直接導航到內層 URL 才能讀取數據。
- **Rule 1**: 遇到 Google Sheets 嵌入時，永遠先用 `document.querySelector('#pageswitcher-content').src` 找到真實 sheet URL，再用 Playwright 直接訪問該 URL 截圖。
- **Lesson 2 (StockCharts Timeout)**: StockCharts 的 `networkidle` 等待策略對 IWM 會 timeout（30s）。原因是頁面有持續的 background network activity。
- **Rule 2**: StockCharts 截圖應使用 `wait_until='domcontentloaded'` + `wait_for_selector('#chartImg')` 組合，而非 `networkidle`。若仍失敗，用 PIL 從 full-page screenshot 裁切 chart 區域（從 y=370 開始）。
- **Lesson 3 (T2108 Schema)**: T2108 數據屬於「外部視覺數據源」，不在 `fetch_all_data.py` 的自動化範圍內（需要截圖），應放入 `stockbee_mm` 頂層 key，與 `sentiment`/`breadth` 並列。
- **Rule 3**: 每次 Stage 2 執行後，`today_market.json` 的 `stockbee_mm.latest_date` 必須與最近交易日吻合，否則數據過期。
