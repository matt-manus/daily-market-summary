"""
10-year momentum share, same definition as the daily engine:
  universe  : close >= $5, volume >= 300k, close*volume >= $5M, has a close 63 sessions back
  momentum  : close >= 1.2 x close 63 sessions back
Sampled at each week's last session. Uses *today's* candidate list for the
whole history (Yahoo has no delisted stocks), so it carries survivorship bias:
read it as a rough long-run picture, not exact history.
Output: data/monitor/mom10y.csv (date, mom_pct, univ, mom_n). Run on demand.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E  # noqa: E402


def main():
    uni = E.build_universe()
    start = (datetime.now(timezone.utc) - timedelta(days=int(365.25 * 10) + 120)).strftime("%Y-%m-%d")
    close, vol, failed = E.download_bars(uni["ysym"].tolist(), start)
    E.log(f"10y bars: {close.shape[1]} tickers x {close.shape[0]} days; failed {len(failed)}")
    close = close.sort_index()
    vol = vol.reindex_like(close)
    old = close.shift(E.MOM_LOOKBACK)
    univ = ((close >= E.MIN_PRICE) & (vol >= E.MIN_VOL) & (close * vol >= E.MIN_DOLLAR_VOL) & old.notna())
    mom = univ & (close / old - 1 >= E.MOM_THRESHOLD)
    n_u, n_m = univ.sum(axis=1), mom.sum(axis=1)
    d = pd.DataFrame({"univ": n_u, "mom_n": n_m})
    d = d[d.univ >= 300]  # skip thin early / holiday rows
    d["mom_pct"] = (100 * d.mom_n / d.univ).round(2)
    d.index = pd.to_datetime(d.index)
    wk = d.groupby(d.index.to_period("W")).tail(1)
    wk.index.name = "date"
    out = os.path.join(E.OUT_DIR, "mom10y.csv")
    wk[["mom_pct", "univ", "mom_n"]].to_csv(out)
    E.log(f"Wrote {out}: {len(wk)} weeks {wk.index[0].date()} → {wk.index[-1].date()}")


if __name__ == "__main__":
    sys.exit(main())
