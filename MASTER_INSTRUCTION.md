# Master Instruction: Self-Evolving Daily Market Summary Report System

## Overview
This document serves as the core foundational directive for the Self-Evolving Daily Market Summary Report System. It outlines the primary objectives, principles, and operational rules that govern all actions within this framework.

## Primary Objective
To construct, manage, and continuously optimize a daily market summary reporting system that adapts to changing market conditions, incorporates lessons learned over time, and aligns with the user's ultimate goals for accurate, timely, and actionable financial insights.

## Core Principles
1. **Credit Efficient Operations**: The system is designed to minimize AI token/credit usage. The AI MUST rely on automated scripts for data processing and avoid manual web scraping or mental calculations.
2. **Continuous Evolution**: The system is not static. It must learn from past decisions, market outcomes, and user feedback to refine data collection and reporting strategies continuously.
3. **Data-Driven Decisions**: All market insights and summaries must be backed by thorough research, quantitative analysis, and verifiable financial data rather than emotion or speculation.
4. **Accuracy Over Speed**: Thorough verification of market data, calculations, and analyses is paramount. It is always better to be correct than to be fast, especially when dealing with financial reporting.
5. **Contextual Awareness**: Every daily session must build upon the previous ones, maintaining continuity through the structured reading and updating of project files.
6. **Formatting Consistency**: Reports must strictly adhere to the established formatting rules, including specific timestamp formats (HKT/ET) and required content sections (e.g., industry leaders, moving averages).

## Operational Rules

### Credit Efficient Workflow (MANDATORY)
To maintain strict credit efficiency, the AI MUST follow this exact sequence for daily reporting:
1. **Fetch Data**: Execute `python3.11 scripts/fetch_all_data.py` to automatically download all market data and generate `data/today_market.json`.
2. **STRICT PROHIBITION**: The AI is **STRICTLY FORBIDDEN** from manually opening browsers to scrape Yahoo Finance/MarketWatch for numerical data, and **FORBIDDEN** from calculating RSI or Moving Averages mentally. Always rely on the JSON output.
3. **Render Report**: Execute `python3.11 scripts/render_report.py` to automatically inject the JSON data into `templates/report_template.html` and generate the final HTML report.
4. **Targeted Screenshots Only**: The AI should ONLY open the browser to take screenshots when specific chart images (e.g., StockCharts, Finviz) are explicitly required. Do not use the browser to verify data that is already in the JSON.

### Session Management
**MANDATORY**: At the start of every session, the AI agent MUST read the following 4 files to refresh context:
1. `Master_instruction.md` (This file)
2. `workflow.md`
3. `Log.md`
4. `evolution.md`

**MANDATORY**: At the end of every task or session, the AI agent MUST update the `Log.md` and `evolution.md` files to capture the latest progress, decisions made, and 'lessons learned'.

## Communication Preferences
- A mix of English and Traditional Chinese is acceptable and encouraged when beneficial for clarity.
- Avoid repetitive confirmation for established preferences or instructions.
- Always communicate risks, market volatility, and data limitations clearly.

## Quick Commands

The following keywords trigger pre-defined automated workflows. When the user inputs one of these commands, the AI MUST execute the full sequence **silently and autonomously**, without asking for confirmation at each step. The AI MUST only interrupt if a step fails with an error.

### `GENERATE TODAY`

Triggers the full daily report generation pipeline in the following fixed order:

**Step 1 — Fetch Data**
Execute `python3.11 scripts/fetch_all_data.py`.
This downloads all market data and writes `data/today_market.json`.
Verify the JSON contains no `null` values before proceeding.

**Step 2 — Capture Chart Screenshots**
Open the browser and navigate to the following URLs in sequence.
For each, set the viewport to exactly **800×500**, capture the chart area, and save to the fixed path:

| Target | URL | Save As |
|:-------|:----|:--------|
| SPY MA Chart | `https://stockcharts.com/h-sc/ui?s=SPY&p=D&yr=1&mn=0&dy=0&id=p94683309306` | `assets/img/today/spy_ma.png` |
| QQQ MA Chart | `https://stockcharts.com/h-sc/ui?s=QQQ&p=D&yr=1&mn=0&dy=0&id=p94683309306` | `assets/img/today/qqq_ma.png` |
| Sector Heatmap | `https://finviz.com/groups.ashx?g=sector&sg=&o=name&p=d` | `assets/img/today/sector_heatmap.png` |
| Market Map | `https://finviz.com/map.ashx?t=sec` | `assets/img/today/finviz_map.png` |

**Step 3 — Render Report**
Execute `python3.11 scripts/render_report.py`.
This injects the JSON data into `templates/report_template.html` and outputs `index.html`.
Verify that the rendered HTML contains zero residual `{{...}}` placeholders.

**Step 4 — Upload to GitHub**
Run the following Git commands to commit and push the updated report:
```bash
git add index.html data/today_market.json assets/img/today/
git commit -m "Daily Market Summary: $(date +%Y-%m-%d)"
git push
```
Verify the push succeeds and report the GitHub commit URL to the user.

**On Completion**: Report a one-line summary to the user: date, number of tickers fetched, and the GitHub commit URL.
**On Error**: Stop at the failed step, report the exact error message, and await user instruction.

---

## Document Maintenance
This Master Instruction file should only be updated when there is a fundamental shift in the core philosophy, primary objectives, or high-level operational rules of the market summary system. Routine procedural changes belong in the `workflow.md` file.
