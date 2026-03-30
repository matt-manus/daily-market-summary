"""
regime_filter.py — Intelligent Regime Engine v1.1 (Grok Lead Consultant)
-------------------------------------------------------------------------
Dual interface:
  1. RegimeFilter class  — accepts pre-built data dict, used by unit tests / direct calls
  2. process_logic()     — module-level entry point called by main.py
                           reads today_market.json, returns regime_info + checklist_status

Regime Rules (class):
  🟢 Uptrend     : VIX < 20 AND SPY > 20MA AND %Above20MA > 40%
  🟡 Correction  : VIX 20–30 OR SPY between 20MA–50MA OR %Above20MA 25–40%
  🔴 Bear Market : all other conditions

Regime Rules (module-level determine_regime, for build_regime_banner):
  Correction  : SPY < 20MA
  Caution     : SPY > 20MA but < 50MA
  Normal      : SPY > 20MA and > 50MA
  Uptrend     : SPY > 20MA, > 50MA, > 200MA
"""

import json
from datetime import datetime
from pathlib import Path

BASE_DIR          = Path(__file__).resolve().parent.parent
DATA_DIR          = BASE_DIR / "data"
EXPERT_NOTES_PATH = BASE_DIR / "expert_notes.txt"


# ══════════════════════════════════════════════════════════════════════════════
# 1. RegimeFilter CLASS  (v1.1 — real numbers + marginal case support)
# ══════════════════════════════════════════════════════════════════════════════

class RegimeFilter:
    """
    Accepts a pre-built data dict with the following structure:
        {
            'SPY':              {'close': float, 'ma20': float, 'ma50': float, 'rsi': float},
            'VIX':              float,
            'AD_RATIO':         float,
            'percent_above_20ma': float,
        }
    """
    def __init__(self, data: dict):
        self.data = data

    def determine_regime(self):
        spy                = self.data.get('SPY', {})
        vix                = self.data.get('VIX', 0)
        ad_ratio           = self.data.get('AD_RATIO', 0)
        percent_above_20ma = self.data.get('percent_above_20ma', 0)
        rsi                = spy.get('rsi', 0)

        spy_close = spy.get('close', 0)
        ma20      = spy.get('ma20', 0)
        ma50      = spy.get('ma50', 0)

        # Regime 判斷
        if vix < 20 and spy_close > ma20 and percent_above_20ma > 40:
            regime = "🟢 Uptrend"
            score  = 85
        elif (20 <= vix <= 30) or (ma20 > spy_close > ma50) or (25 < percent_above_20ma < 40):
            regime = "🟡 Correction"
            score  = 55
        else:
            regime = "🔴 Bear Market"
            score  = 25

        checklist = self._generate_checklist(spy, vix, ad_ratio, percent_above_20ma, rsi, ma20)

        return {
            "regime":       regime,
            "regime_score": score,
            "checklist":    checklist,
            "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            "raw_numbers": {
                "VIX":               round(vix, 1),
                "SPY_vs_20MA":       round(spy_close - ma20, 2),
                "percent_above_20ma": round(percent_above_20ma, 1),
                "A/D_Ratio":         round(ad_ratio, 3),
                "RSI":               round(rsi, 1),
            }
        }

    def _generate_checklist(self, spy, vix, ad_ratio, percent_above_20ma, rsi, ma20):
        spy_close = spy.get('close', 0)

        green = {
            "S&P 500 Correction Target":    {"value": "Y" if spy_close > ma20 else "N", "actual": f"SPY {spy_close:.1f}"},
            "Downward momentum 減弱":        {"value": "Y" if rsi > 50 else "N",         "actual": f"RSI {rsi:.1f}"},
            "Base formation & breakout":    {"value": "Y" if spy_close > ma20 else "N", "actual": f"SPY vs 20MA {spy_close - ma20:.1f}"},
            "Technical indicators improving": {"value": "Y" if rsi > 50 else "N",       "actual": f"RSI {rsi:.1f}"},
            "Market breadth improving":     {"value": "Y" if ad_ratio > 1.0 else "N",   "actual": f"A/D {ad_ratio:.3f}"},
            "VIX < 20 或 collapse":          {"value": "Y" if vix < 20 else "N",         "actual": f"VIX {vix:.1f}"},
        }
        green_total = sum(1 for v in green.values() if v["value"] == "Y")

        red = {
            "Downward momentum 增強":           {"value": "Y" if rsi < 50 else "N",       "actual": f"RSI {rsi:.1f}"},
            "Top range breakdown":              {"value": "Y" if spy_close < ma20 else "N", "actual": f"SPY vs 20MA {spy_close - ma20:.1f}"},
            "Technical indicators deteriorating": {"value": "Y" if rsi < 50 else "N",     "actual": f"RSI {rsi:.1f}"},
            "Market breadth worsening":         {"value": "Y" if ad_ratio < 1.0 else "N", "actual": f"A/D {ad_ratio:.3f}"},
            "VIX > 20 或 spike":                {"value": "Y" if vix > 20 else "N",        "actual": f"VIX {vix:.1f}"},
        }
        red_total = sum(1 for v in red.values() if v["value"] == "Y")

        return {
            "green_checklist": green,
            "green_total":     green_total,
            "red_checklist":   red,
            "red_total":       red_total,
            "active_checklist": "green" if green_total >= red_total else "red",
        }


# ══════════════════════════════════════════════════════════════════════════════
# 2. MODULE-LEVEL FUNCTIONS  (called by main.py and html_generator.py)
# ══════════════════════════════════════════════════════════════════════════════

def determine_regime(data: dict) -> dict:
    """
    Module-level regime determination based on SPY vs MA relationships.
    Used by build_regime_banner() in html_generator.py.
    Returns a dict compatible with build_regime_banner().
    """
    indices   = data.get("indices", {})
    spy_data  = indices.get("SPY", {})
    spy_price = spy_data.get("price")
    spy_ma20  = spy_data.get("ma20")
    spy_ma50  = spy_data.get("ma50")
    spy_ma200 = spy_data.get("ma200")
    vs_ma20   = spy_data.get("vs_ma20_pct", 0.0)
    vs_ma50   = spy_data.get("vs_ma50_pct", 0.0)

    regime      = "Normal"
    color       = "text-amber"
    label       = "Normal Market"
    description = "SPY is above key moving averages."

    if spy_price is not None and spy_ma20 is not None:
        if spy_price < spy_ma20:
            regime      = "Correction"
            color       = "text-red"
            label       = "⚠ Market Correction"
            description = (
                f"SPY (${spy_price:.2f}) is BELOW the 20MA (${spy_ma20:.2f}), "
                f"currently {vs_ma20:+.2f}% from 20MA. "
                "Defensive posture recommended."
            )
        elif spy_ma50 is not None and spy_price < spy_ma50:
            regime      = "Caution"
            color       = "text-amber"
            label       = "⚡ Caution Zone"
            description = (
                f"SPY (${spy_price:.2f}) is above 20MA but BELOW 50MA (${spy_ma50:.2f}), "
                f"currently {vs_ma50:+.2f}% from 50MA. "
                "Selective exposure, reduce risk."
            )
        elif spy_ma50 is not None and spy_price > spy_ma50:
            if spy_ma200 is not None and spy_price > spy_ma200:
                regime      = "Uptrend"
                color       = "text-green"
                label       = "✅ Confirmed Uptrend"
                description = (
                    f"SPY (${spy_price:.2f}) is above 20MA, 50MA, and 200MA. "
                    "Full risk-on posture supported."
                )
            else:
                regime      = "Normal"
                color       = "text-green"
                label       = "🟢 Normal / Recovery"
                description = (
                    f"SPY (${spy_price:.2f}) is above 20MA and 50MA. "
                    "Market in recovery or normal uptrend."
                )

    return {
        "regime":      regime,
        "spy_price":   spy_price,
        "spy_ma20":    spy_ma20,
        "spy_ma50":    spy_ma50,
        "spy_ma200":   spy_ma200,
        "vs_ma20_pct": vs_ma20,
        "vs_ma50_pct": vs_ma50,
        "label":       label,
        "color":       color,
        "description": description,
    }


def get_expert_insights() -> str:
    """
    Read expert_notes.txt and return content.
    Returns empty string if file is missing or empty.
    """
    if not EXPERT_NOTES_PATH.exists():
        return ""
    with open(EXPERT_NOTES_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()
    return content if content else ""


def build_correction_checklist_html() -> str:
    """
    Static fallback Correction Checklist HTML block.
    Used when no dynamic checklist data is available.
    """
    items = [
        ("🔴 Cut losers immediately",          "Exit any position down >7-8% from entry. No averaging down."),
        ("🔴 Reduce overall exposure",          "Scale down to 25-50% invested. Cash is a position."),
        ("🟡 Identify true market leaders",     "Which stocks are holding up best? These lead the next rally."),
        ("🟡 Monitor VIX for capitulation",     "VIX spike >35-40 often signals a tradeable low."),
        ("🟡 Watch for volume climax",          "High-volume selling exhaustion = potential reversal signal."),
        ("🟢 Build a watchlist of strong stocks", "Stocks near highs or with tight bases during correction."),
        ("🟢 Wait for Follow-Through Day (FTD)", "A strong up day (+1.7%+) on higher volume = confirmed rally."),
        ("🟢 Re-enter in small pilot positions", "Start with 25% of normal size, add only if market confirms."),
    ]
    items_html = ""
    for title, desc in items:
        items_html += (
            f'<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid #2a2a2a;">'
            f'<div style="min-width:220px;font-weight:600;font-size:13px;color:#e0e0e0;">{title}</div>'
            f'<div style="font-size:12px;color:#aaaaaa;line-height:1.6;">{desc}</div>'
            f'</div>'
        )
    return f"""
<div id="correction-checklist" style="
  background:linear-gradient(135deg,#1a0a0a 0%,#1c1010 100%);
  border:2px solid #f44336;border-radius:10px;
  padding:20px 24px;margin-bottom:28px;
  box-shadow:0 0 20px rgba(244,67,54,0.15);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
    <span style="font-size:24px;">🚨</span>
    <div>
      <div style="font-size:16px;font-weight:700;color:#f44336;letter-spacing:0.5px;">
        MARKET CORRECTION MODE ACTIVE
      </div>
      <div style="font-size:11px;color:#aaaaaa;margin-top:2px;">
        SPY is trading BELOW the 20-Day Moving Average — Defensive Protocol Engaged
      </div>
    </div>
  </div>
  <div style="font-size:11px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;
    color:#f44336;border-left:3px solid #f44336;padding-left:10px;margin-bottom:12px;">
    Market Correction Checklist
  </div>
  {items_html}
</div>"""


def process_logic() -> dict:
    """
    Main entry point called by main.py [3/4].
    Reads today_market.json, runs RegimeFilter, returns:
        {
            "regime_info":      dict,   # for build_regime_banner()
            "expert_insights":  str,    # for Expert Insights block
            "checklist_status": dict,   # full RegimeFilter.determine_regime() output
                                        # html_generator v1.2 detects 'checklist'+'raw_numbers' keys
                                        # and renders the dynamic section automatically
        }
    """
    json_path = DATA_DIR / "today_market.json"
    if not json_path.exists():
        print("  ⚠  today_market.json not found — skipping regime logic.")
        return {"regime_info": {}, "expert_insights": "", "checklist_status": {}}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ── Module-level regime_info (for banner) ─────────────────────────────
    regime_info = determine_regime(data)

    # ── Expert notes ──────────────────────────────────────────────────────
    expert_insights = get_expert_insights()

    # ── Build RegimeFilter input from today_market.json ───────────────────
    indices   = data.get("indices", {})
    macro     = data.get("macro", {})
    breadth   = data.get("breadth", {})
    spy_data  = indices.get("SPY", {})
    sp500_b   = breadth.get("sp500", {})
    nyse_ad   = breadth.get("market_wide_advance_decline", {}).get("NYSE", {})

    rf_input = {
        "SPY": {
            "close": spy_data.get("price", 0),
            "ma20":  spy_data.get("ma20", 0),
            "ma50":  spy_data.get("ma50", 0),
            "rsi":   spy_data.get("rsi14", 0),
        },
        "VIX":               float(macro.get("VIX", {}).get("price", 99) or 99),
        "AD_RATIO":          float(nyse_ad.get("ad_ratio", 0) or 0),
        "percent_above_20ma": float(sp500_b.get("pct_above_20ma", 0) or 0),
    }

    rf             = RegimeFilter(rf_input)
    checklist_status = rf.determine_regime()   # full dict with 'checklist' + 'raw_numbers'

    print(f"  ✓  Regime (banner): {regime_info['regime']} — {regime_info['label']}")
    print(f"  ✓  Regime (engine): {checklist_status['regime']}  Score={checklist_status['regime_score']}")
    print(f"  ✓  Raw numbers: VIX={checklist_status['raw_numbers']['VIX']}  "
          f"SPY vs 20MA={checklist_status['raw_numbers']['SPY_vs_20MA']}  "
          f"%>20MA={checklist_status['raw_numbers']['percent_above_20ma']}%")
    active = checklist_status['checklist']['active_checklist']
    total  = checklist_status['checklist'][f'{active}_total']
    max_n  = len(checklist_status['checklist'][f'{active}_checklist'])
    print(f"  ✓  Active checklist: {active}  ({total}/{max_n})")

    if expert_insights:
        print(f"  ✓  Expert notes loaded ({len(expert_insights)} chars)")
    else:
        print("  ℹ  No expert notes (expert_notes.txt empty or missing)")

    return {
        "regime_info":      regime_info,
        "expert_insights":  expert_insights,
        "checklist_status": checklist_status,
    }


if __name__ == "__main__":
    result = process_logic()
    import pprint
    pprint.pprint(result)
