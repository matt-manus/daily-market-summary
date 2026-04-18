# 📄 系統狀態快照文檔 (v4.0 標準格式版)

**Project：** Momentum Swing Trading Coach
**主 Repo：** https://matt-manus.github.io/daily-market-summary/

---

## 0. 核心約束指令 (嚴格遵守，一字不能少)

- 唔好 over-promise：只承諾 100% 做到嘅事。
- 先確認現狀：每次行動前，確認目前身處 main 定 dev 分支。
- 小步前進：每次只做一個小步驟，做完等我講「OK」先繼續。

### 錯誤與代碼管理
- 發現 Bug 即澄清：唔好扮已經解決，尤其係數據冇更新嘅時候。
- 保護 Manus Credit：任何寫 Code 任務必須由 Grok 產出，Manus 負責 Copy & Paste & Run。預計多過 3 次 Loop 必攞 Permission。
- 代碼審核流程：Grok 產出代碼必經 Gemini 邏輯審核，無誤才交 Manus 部署。
- 數據防呆機制：必須含 Data Status Tag；失敗或逾 24 小時未更新需顯示紅字「Data Stale」。
- 任何改動前授權：workflow、script、時間設定等改動必先等我講「OK」。

### 溝通與合作方式 (最重要)
- 我講完一步後，你必須講「OK」先畀我繼續。
- 任何改動前，你都講「先確認現狀」或叫我 check live site。
- 唔需要讚我，我要既係批評同埋改善既建議。
- 如果 Chat 太長：即刻提醒我「總結目前狀態」。
- 100% 鏡像原則：獲外部數據時，禁止 AI 擅自過濾或自創邏輯，必全量抓取或經我 verified OK。

### 系統架構與分工：
- **Lead Consultant:** Gemini (負責邏輯、架構、把關、提出質疑、審核 Grok 代碼邏輯)
- **Co-Lead Consultant + Coder:** Grok (負責按規格撰寫代碼，並作為共同決策者提供邏輯補充與優化建議)
- **Executor:** Manus (負責拉取 Git、執行腳本、測試、截圖、Push 代碼；嚴禁 Manus 自己諗 Code，執行前如預計超過 3 次 Loop 必須先取得 User 同意)
- **管理模式:** A/B 分支 (main = 穩定版, dev = 開發版；Grok 產出代碼必須經 Gemini 審核後才由 Manus 部署至 dev)

---

## 1. 目前進度 (Status Update)

| Phase | 項目 | 狀態 |
|-------|------|------|
| Phase 0–2 | 基礎建設與數據同步 | ✅ 全部完成 |
| Phase 3 | Hybrid Engine | ✅ 正式完成 |
| Phase 3.5 | Responsive UI & Layout | ✅ 正式完成 |
| Phase 3.8 | T2108 動態化 + Section 4C 完整升級 | ✅ 正式完成 |
| Phase 3.9 | Section 4D Market Heatmap 動態化 + Section 7/8 清理 | ✅ 正式完成 |

### Phase 3.9 詳細成就：
- 動態 `fetch_finviz_heatmap.py` + `fetch_stockbee_data.py`
- Section 4C / 4D 完整動態化 + 深色 summary box + Last Data
- Section 7（Coach's Action Plan / Regime）已永久刪除
- Section 8（Event Calendar）已永久刪除
- Section 8B（Market Analysis）保留並正常顯示
- 全報告數據更新至 2026-04-18
- `dev-3.9`（trial run 版本）已建立並穩定
- `dev-4.0`（新開發分支）已開啟

---

## 2. 分支架構

| 分支 | 用途 | 狀態 |
|------|------|------|
| `main` | 穩定 live 版本 | ✅ 不動 |
| `dev-3.9` | Phase 3.9 trial run（Section 7/8 已刪，8B 保留）| ✅ 穩定 |
| `dev-4.0` | 新開發分支（Phase 4 起點）| ✅ 已開啟 |

---

## 3. 未來 Roadmap (v4.0)

| 階段 | 項目 | 狀態 | 核心成就 / 目標 |
|------|------|------|----------------|
| Phase 1–3 | 基礎建設與數據同步 | ✅ | JSON 滾動數據、Stage 4.5 文字同步、時區修復 |
| Phase 3.5 | Responsive UI & Layout | ✅ | 9-section 乾淨架構、Section 5/6 box 分類、Mobile 完美適配 |
| Phase 3.8 | T2108 動態化 + Section 4C | ✅ | 完整動態抓取 + 自動截圖 + 動態 summary box |
| Phase 3.9 | Section 4D Market Heatmap + Section 7/8 清理 | ✅ | 動態抓取 + Section 7 刪除 + Section 8B 保留 + dev-3.9 / dev-4.0 分支建立 |
| Phase 4 | 動能掃描器 (Scanner) | ⏳ | 自動 Market Signal、高動能警報、AI 短評生成 |
| Phase 5 | 閉環學習系統 | ⏳ | RAG Journal、智能週報 |

---

## 4. 目前待辦事項 (Priority)

- **[ACTION]** merge `dev-3.9` → `main`（待 trial run 幾日後決定）
- **[ACTION]** 確認 Data Stale 紅字 banner 正常運作
- **[READY]** Phase 4 正式啟動準備（新分支 `dev-4.0` 已開啟）

---

*Last updated: 2026-04-18 | Snapshot version: v4.0*
