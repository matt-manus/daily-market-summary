# evolution.md — System Evolution & Lessons Learned

## Purpose
This file captures improvements, lessons learned, and evolved rules that should be applied to all future sessions. Read this file at the start of every session.

---

## v1.0 → v2.0 Evolution (2026-03-26)

### Architecture Decisions

**Decision 1: Credit Efficient Pipeline**
The system was redesigned around a strict two-script pipeline (`fetch` → `render`) to minimize AI token usage. The AI must never manually scrape data or calculate indicators — all computation happens in Python scripts.

**Decision 2: JSON as Single Source of Truth**
`data/today_market.json` is the canonical data store. All downstream scripts (render, analysis) must read from this file. Schema version tracked in `meta.schema_version`.

**Decision 3: Template + Placeholder Architecture**
`report_template.html` uses `{{TAG}}` placeholders. `render_report.py` performs simple string replacement. This decouples data from presentation — updating the report layout never requires touching data logic, and vice versa.

**Decision 4: Fixed Screenshot Paths**
Screenshots are always saved to `assets/img/today/{fixed_name}.png` at 800×500. The HTML template hardcodes these paths. This prevents broken image links and makes the workflow deterministic.

---

## Lessons Learned

| # | Lesson | Applied Rule |
|:--|:-------|:-------------|
| 1 | `pandas_ta` 0.4.x requires Python ≥ 3.12; sandbox runs 3.11 | Always use native pandas EWM for RSI; do not attempt to install `pandas_ta` |
| 2 | yfinance occasionally fails on individual tickers with TLS errors | Use batch download for all tickers; individual failures are retried automatically |
| 3 | Leaving `{{TAGS}}` in rendered HTML means a placeholder was missed | Always verify: `grep -o '{{[^}]*}}' index.html \| wc -l` must equal 0 |
| 4 | `output/` directory accumulates dated files; `index.html` at root is the live version | Keep `index.html` at root for GitHub Pages compatibility |
| 5 | Browser screenshots without fixed viewport produce inconsistent chart sizes | Lock viewport to exactly 800×500 before every screenshot |

---

## Pending Improvements (Backlog)

- [ ] Add GitHub Actions workflow to auto-run `GENERATE TODAY` at HKT 06:30
- [ ] Add SPY/QQQ options data (Put/Call ratio) to `fetch_all_data.py`
- [ ] Add `scripts/validate_json.py` for pre-render data quality checks
- [ ] Consider adding a `--date` flag to `fetch_all_data.py` for historical backfill
