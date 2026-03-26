# Evolution: Lessons & Rules

## 2026-03-26 (System Update)
- **Lesson**: AI 直接計算 RSI 誤差極大（約 2-5%），且極度消耗 Credit。
- **Improvement**: 將所有計算邏輯移至 `fetch_all_data.py`，AI 改為讀取 JSON。
- **Rule**: 以後遇到複雜計算（如 MA 交叉、廣度百分比），必須先寫 Python 腳本解決，不准在 Prompt 裡要求 AI 計算。
