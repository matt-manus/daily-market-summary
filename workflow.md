# Workflow: Daily Market Summary SOP

## 每日執行指令：`GENERATE TODAY`
1. **第一階段：數據抓取**
   - 執行 `python3 scripts/fetch_all_data.py`。
   - 檢查 `data/today_market.json` 是否成功生成。
2. **第二階段：視覺分析 (Manual/Visual)**
   - 前往 StockCharts 及 Finviz 進行截圖（800x500）。
   - 檔案存入 `assets/img/today/`，命名必須符合模板要求（如 `sector_heatmap.png`）。
3. **第三階段：內容撰寫 (Step 7)**
   - 根據 JSON 數據撰寫 Bull vs Bear 論點。
4. **第四階段：渲染與發佈**
   - 執行 `python3 scripts/render_report.py`。
   - Commit 並 Push 到 GitHub。
