# Momentum Swing Trading Coach - 系統狀態快照 v3.5

Project： Momentum Swing Trading Coach
主 repo： https://matt-manus.github.io/daily-market-summary/

## 1. 系統架構與分工：
* Lead Consultant: Gemini (負責邏輯、把關、審核 Grok 代碼)
* Co-Lead Consultant + Coder: Grok (負責撰寫代碼與優化建議)
* Executor: Manus (負責 Git、執行測試；嚴禁自己諗 Code，超過 3 次 Loop 必須攞 Permission)
* 管理模式: A/B 分支 (main = 穩定版, dev = 開發版)；嚴禁直接喺 main 做 Development。

## 2. 目前進度：
* Phase 3: ✅ 完成數據同步與時區修復。
* Phase 3.5: 🔄 Active (Layout 重構與手機適配，原則：Desktop 零犧牲)。

## 3. 核心約束指令：
* 先確認現狀：行動前必確認身處 main 定 dev。
* 小步前進：做一步等一次 「OK」。
* 發現 Bug 即澄清：唔好扮解決。
* 代碼審核流程：Grok 產出 -> Gemini 審核 -> Manus 部署至 dev。
* Responsive 原則：任何 UI 改動必須確保 Desktop 高密度體驗不受損。

## 🏗️ Daily Market Summary – 最終版新架構 (2026-04-04 修正版)

| Section | 內容要點 | 顯示與邏輯備註 |
|---|---|---|
| 1. Macro | 原有數據表格 | Impact Comment: 必考慮 VIX；Oil 視催化作用而定。 |
| 2. Sentiment | F&G, NAAIM, Put/Call | 寫 Comment 時同時考慮 VIX。 |
| 3. Index | SPY / QQQ / DIA / IWM | 保持現有格式。 |
| 4. Breadth | A/D, % above MA, Stockbee | % above MA 第一欄改為 "Symbol"；整合 Heatmap。 |
| 5. Sector | Core Sectors | 移除 Description；改用 Visual Tags (綠點/紅字) 顯示 vs MA。 |
| 6. Sub-sector | Sub-sector ETFs | 改用 Visual Tags；依據 etf_correlation_map.json 進行分組。 |
| 7. Industry | RS Leaderboard | 欄位 align 返 Sector/Sub-sector。 |
| 8. Summary | Bull/Bear, Regime, Checklist | 維持於底部，作為 Build-up 閱讀流嘅總結。 |
| 9. Event | 3-star events only | 需實作 Python Strict Filtering。 |

> AI Comment Roadmap Note:
> * 每個 Section 預留 `<div class="impact-comment-placeholder">`。
> * Phase 4 目標：Grok API + flexible reasoning。
> * 核心原則：Context-dependent、趨勢為主、實戰 Actionable，唔硬套舊相關性。
