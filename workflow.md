# Daily Market Summary — Workflow SOP v2.0
> Updated: 2026-03-27 | Modular Architecture Refactor

---

## Architecture Overview

```
src/
├── main.py            ← Entry point (orchestrates all modules)
├── data_fetcher.py    ← Wraps fetch_all_data.py + generate_ai_strategy.py
├── image_agent.py     ← Screenshot capture + Base64 encoding
├── regime_filter.py   ← SPY vs 20/50MA logic + expert_notes.txt reader
└── html_generator.py  ← Template rendering + archiving
```

---

## Daily Generation Command (GENERATE TODAY)

```bash
# Full automated run (fetch + screenshots + render + archive)
python3 src/main.py

# Render only (skip data fetch, use existing data)
python3 src/main.py --render-only

# Fetch only (no render)
python3 src/main.py --fetch-only
```

---

## Step-by-Step Manual Flow

### Step 1 — Fetch Market Data
```bash
python3 scripts/fetch_all_data.py
# writes: data/today_market.json

python3 scripts/generate_ai_strategy.py
# writes: data/ai_strategy.json
```

### Step 2 — Capture Screenshots (Manual)
Place screenshots in `assets/img/today/` with these exact filenames:
- `spy_ma.png`               — SPY daily chart with 20/50/200 MA
- `qqq_ma.png`               — QQQ daily chart with 20/50/200 MA
- `sector_heatmap.png`       — Sector heatmap (Finviz)
- `finviz_map.png`           — Full market heatmap (Finviz)
- `market_heatmap.png`       — Market heatmap (Section 5)
- `stockbee_mm.png`          — Stockbee Market Monitor
- `industry_performance.png` — Industry performance chart

### Step 3 — Render Report
```bash
python3 src/main.py --render-only
```
Output:
- `index.html`              — Live report (GitHub Pages)
- `archive/YYYY-MM-DD.html` — Date-stamped archive copy

### Step 4 — Push to GitHub
```bash
git add -A
git commit -m "Daily report YYYY-MM-DD"
git push
```

---

## Regime Logic (regime_filter.py)

| Condition | Regime | Banner Color |
|---|---|---|
| SPY > 20MA AND SPY > 50MA | Confirmed Uptrend | Green |
| SPY > 20MA BUT SPY < 50MA | Caution Zone | Yellow |
| SPY < 20MA | Market Correction | Red |
| SPY < 20MA AND SPY < 200MA | Bear Market | Dark Red |

When **Correction** is detected, the Market Correction Checklist is injected at the top of the HTML report automatically.

---

## Expert Notes Interface

Edit `expert_notes.txt` to inject analyst commentary into the report.
Lines starting with `#` are treated as comments and ignored.
Non-empty content will appear in the **Expert Insights** block at the top of the report.

---

## File Structure

```
daily-market-summary/
├── src/                    ← Modular Python source (NEW)
│   ├── main.py
│   ├── data_fetcher.py
│   ├── image_agent.py
│   ├── regime_filter.py
│   └── html_generator.py
├── scripts/                ← Legacy scripts (still functional)
│   ├── fetch_all_data.py
│   ├── render_report.py
│   ├── generate_ai_strategy.py
│   └── screenshot_trends.py
├── templates/
│   └── report_template.html
├── data/
│   ├── today_market.json
│   └── ai_strategy.json
├── assets/img/today/       ← Screenshots go here
├── archive/                ← Date-stamped HTML archives
├── expert_notes.txt        ← Expert commentary (optional)
├── index.html              ← Live GitHub Pages report
└── workflow.md             ← This file
```
