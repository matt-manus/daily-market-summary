# 📄 系統狀態快照文檔 (v3.7 標準格式版)

**Project：** Momentum Swing Trading Coach  
**主 Repo：** https://matt-manus.github.io/daily-market-summary/

---

## 0. 核心約束指令 (嚴格遵守，一字不能少)

- **唔好 over-promise**：只承諾 100% 做到嘅事。
- **先確認現狀**：每次行動前，確認目前身處 main 定 dev 分支。
- **小步前進**：每次只做一個小步驟，做完等我講「OK」先繼續。

### 錯誤與代碼管理

- **發現 Bug 即澄清**：唔好扮已經解決，尤其係數據冇更新嘅時候。
- **保護 Manus Credit**：任何寫 Code 任務必須由 Grok 產出，Manus 負責 Copy & Paste & Run。預計多過 3 次 Loop 必攞 Permission。
- **代碼審核流程**：Grok 產出代碼必經 Gemini 邏輯審核，無誤才交 Manus 部署。
- **數據防呆機制**：必須含 Data Status Tag；失敗或逾 24 小時未更新需顯示紅字「Data Stale」。
- **任何改動前授權**：workflow、script、時間設定等改動必先等我講「OK」。

### 溝通與合作方式 (最重要)

- ✅ 我講完一步後，你必須講「OK」先畀我繼續。
- ✅ 任何改動前，你都講「先確認現狀」或叫我 check live site。
- ✅ 唔需要讚我，我要既係批評同埋改善既建議。
- ✅ 如果 Chat 太長：即刻提醒我「總結目前狀態」。
- ✅ **100% 鏡像原則**：獲外部數據時，禁止 AI 擅自過濾或自創邏輯，必全量抓取或經我 verified OK。

---

## 系統架構與分工

| 角色 | 職責 |
|---|---|
| **Lead Consultant: Gemini** | 負責邏輯、架構、把關、提出質疑、審核 Grok 代碼邏輯 |
| **Co-Lead Consultant + Coder: Grok** | 負責按規格撰寫代碼，並作為共同決策者提供邏輯補充與優化建議 |
| **Executor: Manus** | 負責拉取 Git、執行腳本、測試、截圖、Push 代碼；嚴禁 Manus 自己諗 Code，執行前如預計超過 3 次 Loop 必須先取得 User 同意 |

**管理模式：** A/B 分支 (main = 穩定版, dev = 開發版；Grok 產出代碼必須經 Gemini 審核後才由 Manus 部署至 dev)

---

## 目前進度 (Status Update)

| 階段 | 狀態 | 說明 |
|---|---|---|
| Phase 0–2 | ✅ 全部完成 | 基礎建設 |
| Phase 3 (Hybrid Engine) | ✅ 正式完成 | |
| Phase 3.5 (Responsive UI & Layout) | ✅ **正式完成** | 9-section 乾淨架構、Section 5/6 全新分類 box 設計（10 組 sub-sector + Space & Defense）、vs 20/50/200MA 綠紅著色、RSI 14 水平 bar、Mobile 完美適配。Section 7 已刪除，原 Section 8 & 9 自動向前移為新 Section 7 & 8。所有 N/A 已前置化處理，Data Stale 機制就位。 |

---

## 未來 Roadmap (v3.7)

| 階段 | 項目 | 狀態 | 核心成就 / 目標 |
|---|---|---|---|
| Phase 1–3 | 基礎建設與數據同步 | ✅ | JSON 滾動數據、Stage 4.5 文字同步、時區修復 |
| Phase 3.5 | Responsive UI & Layout | ✅ | 9-section 乾淨架構、Section 5/6 box 分類、Mobile 完美適配、vs MA 綠紅著色 + RSI bar |
| Phase 4 | 動能掃描器 (Scanner) | ⏳ | 自動 Market Signal、高動能警報、AI 短評生成 |
| Phase 5 | 閉環學習系統 | ⏳ | RAG Journal、智能週報 |

---

## 目前待辦事項 (Priority)

- `[ACTION]` T2108 動態抓取（目前仍為硬編碼）
- `[ACTION]` 確認 Data Stale 紅字 banner 正常運作
- Phase 4 正式啟動準備
