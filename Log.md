# Log: Session History

## 2026-03-26
### Task: System Reconstruction (Credit Efficient Version)
- **Actions**: 
  - 成功建立 `scripts/fetch_all_data.py`。
  - 確立了「3+1」目錄結構（scripts, templates, data, root）。
  - 測試了第一次自動化渲染並成功 Push 到 GitHub。
- **Decisions**: 棄用 AI 爬蟲模式，全面轉向 Python 腳本驅動以節省 Credit。
- **Status**: 基礎架構已完成，等待補全 Step 7 邏輯。

## 2026-03-26 (Session 2 — GENERATE TODAY)
### Task: Full Daily Report Pipeline
- **Actions**:
  - Cloned repo from GitHub.
  - Executed `fetch_all_data.py` — 21 tickers fetched, no null values.
  - Captured 4 screenshots: SPY MA, QQQ MA, Sector Heatmap, Finviz Map (800×500).
  - Executed `render_report.py` — index.html generated, zero residual `{{...}}` placeholders.
  - Pushed to GitHub.
- **Key Data (2026-03-26 HKT 21:35)**:
  - VIX: 26.95 (+6.40%) — elevated fear
  - SPY: $651.47 (-0.82%) RSI=36.3 BELOW ALL MAs
  - QQQ: $581.55 (-1.07%) RSI=37.8 BELOW ALL MAs
  - Top Sector by RSI: XLE (Energy) RSI=78.9 ABOVE ALL
- **Status**: ✅ Pipeline completed successfully.

## 2026-03-26 (Session 3 — Audit)
### Task: Template & Render Script Alignment Audit
- **Actions**:
  - 完整審計 `templates/report_template.html` 與 `scripts/render_report.py` 的標籤對應關係。
  - 使用 regex 提取模板所有 `{{...}}` 佔位符（共 82 個）。
  - 模擬 runtime 執行 render_report.py，提取實際 `tags` dict 鍵值（共 82 個）。
  - 執行 render_report.py 並確認 index.html 無殘留佔位符。
  - 確認模板中所有數字（14, 20, 50, 200）均為 UI 標籤（如 "20-Day MA"），非寫死數據。
- **Audit Result**: ✅ PASS — 系統完全對齊，無需修復。
  - Template placeholders: 82
  - render_report.py tags keys: 82
  - Residual in output: 0
  - Hardcoded data values: 0
- **Note**: 初步 regex 掃描 render_report.py 源碼只找到 5 個靜態字串，因為其餘 77 個 key 是透過 f-string 動態生成的。需用 runtime 執行才能正確審計。

## 2026-03-27 (Session 5 — Stage 2: Visuals & Specialized Data)
### Task: Stockbee T2108 Capture + Index Trend Screenshots
- **Actions**:
  - Cloned repo and read all 4 core files.
  - Validated `today_market.json` (schema v3.2): all 6 modules complete (Macro/Indices/Sentiment/Sectors/Industry/Breadth).
  - Navigated to `stockbee.blogspot.com/p/mm.html`, identified Google Sheets iframe (double-nested).
  - Extracted inner sheet URL: `gid=1082103394` via JS console.
  - Parsed table headers and latest 3 rows via `document.querySelectorAll('table')`.
  - Captured `stockbee_mm.png` via Playwright headless (1100×800, device_scale=1.5).
  - Captured `spy_trend.png`, `qqq_trend.png`, `dia_trend.png` via StockCharts (800×500, device_scale=2).
  - IWM had networkidle timeout; used `domcontentloaded` fallback + PIL crop to remove nav bar.
  - Updated `today_market.json` → schema v3.3 with `stockbee_mm` section.
  - Committed 11 files and pushed to GitHub: commit `6edd4a4`.
- **Key T2108 Data (2026-03-25)**:
  - T2108: **24.53%** (Oversold zone, below 25% threshold)
  - Up 4%: 320 | Down 4%: 113
  - 5-Day Ratio: **0.79** (Bearish) | 10-Day Ratio: **0.67** (Bearish)
  - S&P reference close: 6,591.90
- **New Scripts Added**: `screenshot_stockbee.py`, `screenshot_trends.py`, `update_t2108.py`, `crop_iwm.py`, `screenshot_iwm_retry.py`
- **Status**: ✅ Stage 2 completed. 9 image assets in `assets/img/today/`.
- **Commit URL**: https://github.com/matt-manus/daily-market-summary/commit/6edd4a4

## 2026-03-26 (Session 4 — System Upgrade Stage 1)
### Task: Data Backend Enhancement (v2.0 → v3.0)
- **Actions**:
  - Cloned repo and read MASTER_INSTRUCTION.md.
  - Analyzed existing `fetch_all_data.py` (v2.0) to identify data gaps.
  - Rewrote `fetch_all_data.py` to v3.0 with 5 new data modules.
  - Executed script, verified all data populated correctly.
  - Fixed Finviz sector ticker mapping (`financial` not `financialservices` for XLF).
  - Pushed to GitHub: commit `2ef097f`.
- **New Modules Added**:
  1. **Sentiment**: CNN Fear & Greed (score=20.15, extreme fear), Put/Call Ratio (0.735), NAAIM Exposure (60.24 as of 2026-03-18)
  2. **Sector 1W/1M**: All 11 sectors now include `change_1w_pct`, `change_1m_pct`, `change_3m_pct`, `change_ytd_pct` via Finviz Groups
  3. **Industry Top 15**: Top 15 industries by 1D return from Finviz (144 total industries scraped)
  4. **Breadth**: % stocks above 20/50/200 MA for S&P500, NASDAQ, NYSE via Finviz Screener
  5. **ADR**: 14-day Average Daily Range for SPY, QQQ, DIA, IWM
- **JSON Schema**: Upgraded from v2.0 to v3.0; new top-level keys: `sentiment`, `industry`, `breadth`
- **Data Sources**: Yahoo Finance (yfinance) + CNN Fear & Greed API + NAAIM.org + Finviz Groups + Finviz Screener
- **Commit URL**: https://github.com/matt-manus/daily-market-summary/commit/2ef097f500789d0670d8124e1eb17bbfa50dd5b0
