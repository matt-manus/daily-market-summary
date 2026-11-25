"""
Theme / sector ETF relative strength vs SPY (draft list).

The list below is a stand-in until the user's own TradingView theme
groups are supplied. Status buckets (RRG-style, simplified):
  領先  : beating SPY over 21 and 63 sessions
  冒起  : beating SPY over 5 and 21 sessions, still behind over 63
  轉弱  : ahead over 63 sessions but behind over 21
  落後  : behind SPY over 21 and 63 sessions
  其他  : anything else (mixed)
"""
import pandas as pd

THEMES = [
    # 11 SPDR sectors
    ("XLK", "科技", "Sector"), ("XLF", "金融", "Sector"), ("XLV", "醫療", "Sector"),
    ("XLY", "非必需消費", "Sector"), ("XLP", "必需消費", "Sector"), ("XLE", "能源", "Sector"),
    ("XLI", "工業", "Sector"), ("XLB", "原材料", "Sector"), ("XLU", "公用", "Sector"),
    ("XLRE", "地產", "Sector"), ("XLC", "通訊", "Sector"),
    # themes
    ("SMH", "半導體", "Theme"), ("IGV", "軟件", "Theme"), ("CIBR", "網絡安全", "Theme"),
    ("SKYY", "雲端", "Theme"), ("BOTZ", "機械人／AI", "Theme"), ("ARKK", "創新科技", "Theme"),
    ("XBI", "生物科技", "Theme"), ("IHI", "醫療器械", "Theme"),
    ("ITA", "航太國防", "Theme"), ("PAVE", "基建", "Theme"), ("IYT", "運輸", "Theme"),
    ("JETS", "航空", "Theme"),
    ("KRE", "地區銀行", "Theme"), ("IAI", "券商", "Theme"),
    ("XHB", "建屋", "Theme"), ("XRT", "零售", "Theme"),
    ("XOP", "油氣開採", "Theme"), ("OIH", "油服", "Theme"), ("URA", "鈾", "Theme"),
    ("TAN", "太陽能", "Theme"),
    ("GDX", "金礦", "Theme"), ("SIL", "銀礦", "Theme"), ("COPX", "銅礦", "Theme"),
    ("KWEB", "中國互聯網", "Theme"), ("IBIT", "比特幣", "Theme"),
]
LOOKBACK_CHANGE = 5  # compare ranking with 5 sessions earlier


def download(start):
    import yfinance as yf
    syms = [t for t, _, _ in THEMES] + ["SPY"]
    df = yf.download(syms, start=start, auto_adjust=True, group_by="column",
                     threads=True, progress=False)
    c = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
    return c


def _table_at(c, i):
    spy = c["SPY"]
    rows = []
    for t, name, kind in THEMES:
        if t not in c or pd.isna(c[t].iloc[i]):
            continue
        s = c[t]
        def ex(n):
            if i - n < 0 or pd.isna(s.iloc[i - n]):
                return float("nan")
            return 100 * ((s.iloc[i] / s.iloc[i - n] - 1) - (spy.iloc[i] / spy.iloc[i - n] - 1))
        sma50 = s.iloc[max(0, i - 49):i + 1].mean() if i >= 49 else float("nan")
        rows.append({"etf": t, "name": name, "kind": kind,
                     "ex5": ex(5), "ex21": ex(21), "ex63": ex(63),
                     "above50": bool(s.iloc[i] > sma50) if sma50 == sma50 else None})
    t = pd.DataFrame(rows)
    # score = average percentile rank of 21- and 63-session excess return
    t["score"] = 100 * (t["ex21"].rank(pct=True) + t["ex63"].rank(pct=True)) / 2
    t["rank"] = t["score"].rank(ascending=False, method="min").astype(int)

    def status(r):
        if r.ex21 > 0 and r.ex63 > 0:
            return "領先"
        if r.ex5 > 0 and r.ex21 > 0:
            return "冒起"
        if r.ex63 > 0 and r.ex21 < 0:
            return "轉弱"
        if r.ex21 < 0 and r.ex63 < 0:
            return "落後"
        return "其他"
    t["status"] = t.apply(status, axis=1)
    return t


def compute_themes(c, asof):
    c = c.sort_index()
    i = c.index.get_indexer([pd.Timestamp(asof)])[0]
    if i < 0:
        i = len(c) - 1
    now = _table_at(c, i)
    then = _table_at(c, i - LOOKBACK_CHANGE)
    now = now.merge(then[["etf", "rank", "status"]].rename(
        columns={"rank": "rank_then", "status": "status_then"}), on="etf", how="left")
    now = now.sort_values("rank")
    return {
        "asof": str(c.index[i].date()),
        "then": str(c.index[i - LOOKBACK_CHANGE].date()),
        "n": int(len(now)),
        "rows": now.to_dict("records"),
    }
