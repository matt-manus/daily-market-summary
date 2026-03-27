"""
generate_ai_strategy.py — AI-Driven Hedge Fund Strategy Generator v1.0
-----------------------------------------------------------------------
Uses OpenAI GPT to generate deep hedge fund analysis for Section 6 & 7.
Reads: data/today_market.json
Writes: data/ai_strategy.json (injected by render_report.py)

Analysis framework:
  - Bull/Bear divergence analysis
  - Oversold extremes & mean reversion signals
  - Macro suppression factors
  - False breakout detection
  - Risk Score (x/9) with explicit criteria
  - Technical Triggers with support/resistance levels
"""

import json
import os
from pathlib import Path
from openai import OpenAI

BASE = Path(__file__).resolve().parent.parent
JSON_IN  = BASE / "data" / "today_market.json"
JSON_OUT = BASE / "data" / "ai_strategy.json"

client = OpenAI()


def load_data():
    with open(JSON_IN, encoding="utf-8") as f:
        return json.load(f)


def build_data_summary(data: dict) -> str:
    """Build a concise data summary for the AI prompt."""
    macro   = data.get("macro", {})
    indices = data.get("indices", {})
    sent    = data.get("sentiment", {})
    sectors = data.get("sectors", [])
    breadth = data.get("breadth", {})
    fg      = sent.get("fear_greed", {})
    naaim   = sent.get("naaim", {})
    pc      = sent.get("put_call", {})
    mwad    = breadth.get("market_wide_advance_decline", {})

    lines = []

    # Macro
    lines.append("=== MACRO ===")
    for k, v in macro.items():
        p = v.get("price"); c = v.get("change_1d_pct")
        lines.append(f"  {k}: {p} ({'+' if c and c>0 else ''}{c}%)")

    # Indices
    lines.append("\n=== MAJOR INDICES ===")
    for sym in ["SPY", "QQQ", "DIA", "IWM"]:
        d = indices.get(sym, {})
        lines.append(
            f"  {sym}: ${d.get('price')} ({d.get('change_1d_pct'):+.2f}%) "
            f"RSI={d.get('rsi14'):.1f} "
            f"vs20MA={d.get('vs_ma20_pct'):+.2f}% "
            f"vs50MA={d.get('vs_ma50_pct'):+.2f}% "
            f"vs200MA={d.get('vs_ma200_pct'):+.2f}% "
            f"MA20=${d.get('ma20'):.2f} MA50=${d.get('ma50'):.2f} MA200=${d.get('ma200'):.2f} "
            f"Status={d.get('status')} ADR={d.get('ad_ratio')}"
        )

    # Sentiment
    lines.append("\n=== SENTIMENT ===")
    lines.append(f"  Fear & Greed: {fg.get('score')} ({fg.get('rating')}) | prev_close={fg.get('prev_close')} | prev_1w={fg.get('prev_1w')}")
    lines.append(f"  Put/Call Ratio: {pc.get('value')}")
    naaim_hist = naaim.get("history", [])
    lines.append(f"  NAAIM: {naaim.get('value')} (as of {naaim.get('date')}) | prev_week={naaim_hist[1]['value'] if len(naaim_hist)>1 else 'N/A'}")

    # Breadth
    lines.append("\n=== BREADTH (% Above MA) ===")
    for key, label in [("sp500","S&P500"),("nasdaq","NASDAQ"),("nyse","NYSE"),("russell2000","Russell2000")]:
        b = breadth.get(key, {})
        lines.append(
            f"  {label}: total={b.get('total')} | "
            f">20MA={b.get('pct_above_20ma')}% | "
            f">50MA={b.get('pct_above_50ma')}% | "
            f">200MA={b.get('pct_above_200ma')}%"
        )
    nyse_ad = mwad.get("NYSE", {})
    nasd_ad = mwad.get("NASDAQ", {})
    if nyse_ad:
        lines.append(f"  NYSE A/D: Adv={nyse_ad.get('advances')} Dec={nyse_ad.get('declines')} ADR={nyse_ad.get('ad_ratio')}")
    if nasd_ad:
        lines.append(f"  NASDAQ A/D: Adv={nasd_ad.get('advances')} Dec={nasd_ad.get('declines')} ADR={nasd_ad.get('ad_ratio')}")

    # Top 5 sectors by RSI
    lines.append("\n=== SECTORS (Top 5 by RSI) ===")
    for s in sectors[:5]:
        lines.append(
            f"  {s.get('symbol')} ({s.get('name')}): "
            f"RSI={s.get('rsi14'):.1f} "
            f"Price=${s.get('price'):.2f} "
            f"1D={s.get('change_1d_pct'):+.2f}% "
            f"MA20=${s.get('ma20'):.2f} MA50=${s.get('ma50'):.2f} MA200=${s.get('ma200'):.2f} "
            f"vs20MA={s.get('vs_ma20_pct'):+.2f}% "
            f"Status={s.get('status')}"
        )

    # Bottom 3 sectors by RSI
    lines.append("\n=== SECTORS (Bottom 3 by RSI) ===")
    for s in sectors[-3:]:
        lines.append(
            f"  {s.get('symbol')} ({s.get('name')}): "
            f"RSI={s.get('rsi14'):.1f} "
            f"Price=${s.get('price'):.2f} "
            f"1D={s.get('change_1d_pct'):+.2f}% "
            f"MA20=${s.get('ma20'):.2f} MA50=${s.get('ma50'):.2f} MA200=${s.get('ma200'):.2f} "
            f"Status={s.get('status')}"
        )

    return "\n".join(lines)


def generate_analysis(data_summary: str, data: dict) -> dict:
    """Call OpenAI to generate hedge fund analysis."""

    indices = data.get("indices", {})
    sectors = data.get("sectors", [])
    breadth = data.get("breadth", {})
    macro   = data.get("macro", {})
    sent    = data.get("sentiment", {})
    fg      = sent.get("fear_greed", {})
    naaim   = sent.get("naaim", {})

    # Extract key values for risk scoring
    spy_rsi   = (indices.get("SPY") or {}).get("rsi14", 50)
    qqq_rsi   = (indices.get("QQQ") or {}).get("rsi14", 50)
    vix_price = (macro.get("VIX") or {}).get("price", 20)
    vix_chg   = (macro.get("VIX") or {}).get("change_1d_pct", 0)
    fg_score  = fg.get("score", 50)
    sp_p200   = (breadth.get("sp500") or {}).get("pct_above_200ma", 50)
    sp_p20    = (breadth.get("sp500") or {}).get("pct_above_20ma", 50)
    naaim_val = naaim.get("value", 50)
    naaim_hist = naaim.get("history", [])
    naaim_prev = naaim_hist[1]["value"] if len(naaim_hist) > 1 else naaim_val

    # Build sector map
    sector_map = {s.get("symbol"): s for s in sectors}

    # Compute risk score (0-9 scale, higher = more risk/bearish)
    risk_score = 0
    risk_reasons = []

    if vix_price and float(vix_price) > 25:
        risk_score += 2
        risk_reasons.append(f"VIX={vix_price:.1f} (>25, high fear)")
    elif vix_price and float(vix_price) > 20:
        risk_score += 1
        risk_reasons.append(f"VIX={vix_price:.1f} (>20, elevated)")

    if spy_rsi and float(spy_rsi) < 35:
        risk_score += 1
        risk_reasons.append(f"SPY RSI={spy_rsi:.1f} (<35, oversold)")
    if qqq_rsi and float(qqq_rsi) < 35:
        risk_score += 1
        risk_reasons.append(f"QQQ RSI={qqq_rsi:.1f} (<35, oversold)")

    if fg_score and float(fg_score) < 25:
        risk_score += 1
        risk_reasons.append(f"F&G={fg_score:.0f} (Extreme Fear)")

    if sp_p20 and float(sp_p20) < 25:
        risk_score += 2
        risk_reasons.append(f"SP500 >20MA={sp_p20:.1f}% (<25%, breadth collapse)")
    elif sp_p20 and float(sp_p20) < 40:
        risk_score += 1
        risk_reasons.append(f"SP500 >20MA={sp_p20:.1f}% (<40%, weak breadth)")

    if sp_p200 and float(sp_p200) < 40:
        risk_score += 1
        risk_reasons.append(f"SP500 >200MA={sp_p200:.1f}% (<40%, trend deteriorating)")

    risk_score = min(risk_score, 9)

    # Determine outlook
    if risk_score >= 7:
        outlook = "Risk-off (Defensive)"
        outlook_color = "red"
    elif risk_score >= 5:
        outlook = "Cautious (Selective)"
        outlook_color = "amber"
    elif risk_score >= 3:
        outlook = "Neutral (Wait & See)"
        outlook_color = "amber"
    else:
        outlook = "Risk-on (Constructive)"
        outlook_color = "green"

    # Get watchlist sectors (top 3 by RSI with price data)
    watchlist = []
    for s in sectors[:6]:
        sym = s.get("symbol")
        if sym and s.get("price") and s.get("ma20") and s.get("ma50") and s.get("ma200"):
            watchlist.append(s)
        if len(watchlist) >= 3:
            break

    # Generate AI text via OpenAI
    prompt = f"""You are a top-tier hedge fund strategist at a macro-driven long/short equity fund. 
Analyze today's market data and write a professional market analysis in Traditional Chinese (繁體中文) with English technical terms.

TODAY'S MARKET DATA:
{data_summary}

RISK SCORE COMPUTED: {risk_score}/9
RISK FACTORS: {', '.join(risk_reasons)}

Write TWO sections:

1. BULL CASE (利好邏輯): 
   - Apply concepts: 背離 (divergence), 超賣極值 (oversold extreme), 逆向操作 (contrarian), 均值回歸 (mean reversion)
   - Focus on: Fear & Greed extreme readings, RSI oversold levels, NAAIM positioning changes, any sector showing relative strength
   - Be specific with numbers from the data
   - 3-4 sentences, professional hedge fund language

2. BEAR CASE (利淡邏輯):
   - Apply concepts: 宏觀壓制 (macro suppression), 假突破 (false breakout), 廣度惡化 (breadth deterioration), 趨勢崩潰 (trend breakdown)
   - Focus on: VIX spike, all indices below MAs, breadth collapse, sector concentration risk
   - Be specific with numbers from the data
   - 3-4 sentences, professional hedge fund language

IMPORTANT: 
- Use exact numbers from the data (RSI values, MA levels, percentages)
- Write in Traditional Chinese with English technical terms in parentheses
- Be analytical and specific, not generic
- Format: Just the paragraph text, no headers"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800,
    )

    ai_text = response.choices[0].message.content.strip()

    # Parse bull/bear from AI response
    bull_text = ""
    bear_text = ""

    # Try to split on common separators
    if "BEAR CASE" in ai_text or "利淡邏輯" in ai_text:
        parts = ai_text.replace("**BEAR CASE**", "|||").replace("**BULL CASE**", "").replace("BEAR CASE", "|||").replace("利淡邏輯", "|||")
        split = parts.split("|||")
        if len(split) >= 2:
            bull_text = split[0].strip().replace("BULL CASE", "").replace("利好邏輯", "").strip(" :\n")
            bear_text = split[1].strip().strip(" :\n")
        else:
            bull_text = ai_text
            bear_text = ""
    else:
        # Split roughly in half
        mid = len(ai_text) // 2
        # Find a sentence boundary near the middle
        for i in range(mid, min(mid + 200, len(ai_text))):
            if ai_text[i] in "。\n":
                bull_text = ai_text[:i+1].strip()
                bear_text = ai_text[i+1:].strip()
                break
        if not bull_text:
            bull_text = ai_text
            bear_text = ""

    # Generate watchlist technical triggers
    watchlist_rows = []
    for s in watchlist:
        sym   = s.get("symbol")
        name  = s.get("name")
        price = s.get("price")
        ma20  = s.get("ma20")
        ma50  = s.get("ma50")
        ma200 = s.get("ma200")
        rsi   = s.get("rsi14")
        chg   = s.get("change_1d_pct")
        status = s.get("status", "")

        # Generate trigger based on MA position
        if status == "ABOVE ALL":
            entry_cond = f"守住 20MA (${ma20:.2f}) 可繼續看多"
            stop_cond  = f"跌破 ${ma20:.2f} 止損"
            thesis     = f"唯一突破所有均線的板塊，相對強度領先，資金明顯輪入。RSI={rsi:.1f}，趨勢最強。"
        elif status == "MIXED":
            # Find which MA is closest below
            below_mas = [(abs(price - ma20), "20MA", ma20), (abs(price - ma50), "50MA", ma50), (abs(price - ma200), "200MA", ma200)]
            below_mas = [(d, n, v) for d, n, v in below_mas if price > v]
            if below_mas:
                closest = min(below_mas, key=lambda x: x[0])
                entry_cond = f"守住 {closest[1]} (${closest[2]:.2f}) 支撐"
                stop_cond  = f"跌破 ${closest[2]:.2f} 止損"
            else:
                entry_cond = f"需回升至 20MA (${ma20:.2f}) 以上確認"
                stop_cond  = f"跌破 ${ma50:.2f} 止損"
            thesis = f"防禦屬性強，市場恐慌時相對抗跌。RSI={rsi:.1f}，需關注 MA 支撐。"
        else:  # BELOW ALL
            entry_cond = f"需回升並站穩 20MA (${ma20:.2f}) 以上"
            stop_cond  = f"跌破 ${ma50:.2f} 止損"
            thesis = f"趨勢偏弱，但 RSI={rsi:.1f} 接近超賣，存在技術性反彈機會。"

        watchlist_rows.append({
            "symbol":    sym,
            "name":      name,
            "price":     price,
            "rsi":       rsi,
            "change_1d": chg,
            "ma20":      ma20,
            "ma50":      ma50,
            "ma200":     ma200,
            "status":    status,
            "thesis":    thesis,
            "entry":     entry_cond,
            "stop":      stop_cond,
            "trigger":   f"{entry_cond}；{stop_cond}。",
        })

    return {
        "risk_score":    risk_score,
        "risk_reasons":  risk_reasons,
        "outlook":       outlook,
        "outlook_color": outlook_color,
        "bull_text":     bull_text,
        "bear_text":     bear_text,
        "watchlist":     watchlist_rows,
        "vix_price":     vix_price,
        "vix_chg":       vix_chg,
        "fg_score":      fg_score,
        "sp_p20":        sp_p20,
        "sp_p200":       sp_p200,
        "naaim_val":     naaim_val,
        "naaim_prev":    naaim_prev,
        "spy_rsi":       spy_rsi,
        "qqq_rsi":       qqq_rsi,
    }


def main():
    print("╔══════════════════════════════════════════════╗")
    print("  AI Strategy Generator v1.0 (GPT-4.1-mini)")
    print("╚══════════════════════════════════════════════╝\n")

    data = load_data()
    print("  ✓  Loaded today_market.json")

    summary = build_data_summary(data)
    print("  ✓  Built data summary")
    print("\n--- DATA SUMMARY ---")
    print(summary)
    print("--- END SUMMARY ---\n")

    print("  正在呼叫 OpenAI GPT-4.1-mini 生成策略分析…")
    result = generate_analysis(summary, data)

    print(f"\n  ✓  Risk Score: {result['risk_score']}/9")
    print(f"  ✓  Outlook: {result['outlook']}")
    print(f"  ✓  Bull text: {result['bull_text'][:80]}…")
    print(f"  ✓  Bear text: {result['bear_text'][:80]}…")
    print(f"  ✓  Watchlist: {len(result['watchlist'])} items")

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✅  AI strategy saved to {JSON_OUT}")


if __name__ == "__main__":
    main()
