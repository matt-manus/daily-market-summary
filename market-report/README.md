# Daily US close report pipeline

This directory is the live morning-report pipeline (the copy that actually builds the page). Live HTML is published from branch `dev-3.9`; this branch (`grok-pipeline`) holds the pipeline source only. Do not merge or push these files onto `dev-3.9` or `main`.

On this box the job still runs from `/workspace/market-report`, not from a checkout of this folder.

## Files

| File | Role |
| --- | --- |
| `fetch.py` | Builds the session universe from `screener.json` + NASDAQ listing files, pulls index constituents, and downloads Yahoo 1y daily bars into `RUN/cache/`. Writes `universe.json`, `constituents.json`, `fetch_log.json`. |
| `fetch_cboe.py` | Fetches the official Cboe Daily Market Statistics page for `SESSION` and writes `RUN/cboe.json` (`pc` = EQUITY PUT/CALL RATIO plus that session’s equity-options call/put volume). Optional `--html PATH` parses a saved page. If the figures are not yet published, `pc` is left null — never fill in a prior day. Patches `RUN/meta.json` when that file already exists. |
| `finviz_counts.py` | Writes Finviz screener counts to the path given on the command line (usually `RUN/finviz.json`). Used for Section 3 A/D and Section 4A. |
| `compute.py` | Computes every number on the report from the files in `RUN`. Usage: `python3 compute.py RUN SESSION` → `RUN/results.json`. |
| `render.py` | Renders the dark report into the `dev-3.9` page template. Usage: `python3 render.py RUN SESSION TEMPLATE_HTML OUT_HTML ARCHIVE_DIR`. |
| `state/mom_universe_syms.json` | Static symbol list for the 10-year momentum series (current universe rule). |
| `state/mom_share_results.json` | Restated month-end 10-year sample and percentile lines. |
| `state/ten_year_appended.json` | Daily points appended after each session (currently 2026-10-02 through 2026-11-25). |

## How to run a session report

`SESSION` is the US cash session date (`YYYY-MM-DD`). `RUN` is a working directory for that session (for example `/tmp/mr/SESSION`).

1. Put `screener.json` (NASDAQ screener download from `api.nasdaq.com`), `nasdaqlisted.txt`, and `otherlisted.txt` in `RUN`.
2. Copy `state/mom_universe_syms.json` to `/tmp/mkt/mom_universe_syms.json` (`fetch.py` reads that path). `compute.py` reads the live list at `/workspace/market-report/state/mom_universe_syms.json`.
3. `python3 fetch.py RUN` — Yahoo 1y bars and constituents.
4. `python3 finviz_counts.py RUN/finviz.json`. Load DIA holdings from the SSGA xlsx into `RUN/constituents.json` key `DJIA` (the Wikipedia Dow parse is unreliable).
5. Save CNN Fear & Greed graphdata to `RUN/fg.json`. Fetch official Cboe figures with `python3 fetch_cboe.py RUN SESSION` (page: `https://www.cboe.com/markets/us/options/market-statistics/daily/?dt=SESSION`). If Cboe has not published that session yet, leave `pc` null; do not substitute a prior day. Capture the public Stockbee Market Monitor sheet with headless Chrome at 1400×1000 into `RUN/stockbee_mm.png`.
6. `python3 compute.py RUN SESSION`.
7. Append `results.json`’s `ten_year_latest` to `state/ten_year_appended.json`. Write `RUN/meta.json` (Fear & Greed, Cboe `pc`, screenshot timestamps, paths to `state/mom_share_results.json` and `state/ten_year_appended.json`, and related notes). Then:

   `python3 render.py RUN SESSION TEMPLATE OUT ARCHIVE`

   `TEMPLATE` is `index.html` from `origin/dev-3.9`. Typical outputs are `out/market-report-SESSION.html` and the repo `archive/` directory.
8. Copy the rendered page to the site checkout’s `index.html` and `archive/SESSION.html`, then commit and push **`dev-3.9` only** (never `main`, and do not put pipeline source on `dev-3.9`).

## When the daily job runs

Tuesday–Saturday 06:00 Hong Kong Time (`CRON_TZ=Asia/Hong_Kong 0 6 * * 2-6`), covering the US cash session that just finished. Official Cboe equity put/call may still be unpublished at that time; the card is left blank and must not be filled with a prior day.

## Momentum universe rule

US-listed common/ordinary shares and ADRs, including US-listed ordinary shares registered outside the US. No ETFs, funds, warrants, units, or preferred. Session gates: close ≥ $5, volume ≥ 300,000, dollar volume (close × volume) ≥ $5,000,000. A name is in momentum when its close is at least 20% above the close 63 SPY sessions earlier (a missing earlier bar stays in the universe but is not momentum). Share = momentum count / universe count.

The 10-year month-end sample and the daily appended points in `state/` were restated on 2026-11-27 to this rule. Percentile lines come from that restated 117 month-end Yahoo sample.
