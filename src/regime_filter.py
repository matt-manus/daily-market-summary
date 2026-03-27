"""
regime_filter.py — Market Regime Logic Engine v1.0
---------------------------------------------------
Determines market regime based on SPY vs 20MA / 50MA relationships.
Also reads expert_notes.txt and provides summarized insights.

Regime Rules:
  - SPY < 20MA                   → 'Correction'
  - SPY > 20MA but < 50MA        → 'Caution'
  - SPY > 20MA and > 50MA        → 'Normal'
  - SPY > 20MA, > 50MA, > 200MA  → 'Uptrend'
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPERT_NOTES_PATH = BASE_DIR / "expert_notes.txt"


# ─── Regime Determination ──────────────────────────────────────────────────

def determine_regime(data: dict) -> dict:
    """
    Determine market regime based on SPY vs 20MA/50MA/200MA.

    Returns:
        {
            "regime":     str,    # 'Correction' | 'Caution' | 'Normal' | 'Uptrend'
            "spy_price":  float,
            "spy_ma20":   float,
            "spy_ma50":   float,
            "spy_ma200":  float,
            "vs_ma20_pct": float,
            "vs_ma50_pct": float,
            "label":      str,    # Human-readable label
            "color":      str,    # CSS color class: 'text-red' | 'text-amber' | 'text-green'
            "description": str,   # Short description for display
        }
    """
    indices = data.get("indices", {})
    spy_data = indices.get("SPY", {})

    spy_price = spy_data.get("price")
    spy_ma20  = spy_data.get("ma20")
    spy_ma50  = spy_data.get("ma50")
    spy_ma200 = spy_data.get("ma200")
    vs_ma20   = spy_data.get("vs_ma20_pct", 0.0)
    vs_ma50   = spy_data.get("vs_ma50_pct", 0.0)

    # Default
    regime      = "Normal"
    color       = "text-amber"
    label       = "Normal Market"
    description = "SPY is above key moving averages."

    if spy_price is not None and spy_ma20 is not None:
        if spy_price < spy_ma20:
            # Primary rule: SPY below 20MA → Correction
            regime      = "Correction"
            color       = "text-red"
            label       = "⚠ Market Correction"
            description = (
                f"SPY (${spy_price:.2f}) is BELOW the 20MA (${spy_ma20:.2f}), "
                f"currently {vs_ma20:+.2f}% from 20MA. "
                "Defensive posture recommended. See Correction Checklist below."
            )
        elif spy_ma50 is not None and spy_price < spy_ma50:
            # SPY above 20MA but below 50MA → Caution
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


# ─── Expert Notes Interface ────────────────────────────────────────────────

def get_expert_insights() -> str:
    """
    Read expert_notes.txt and return content if not empty.
    If the file is empty or does not exist, returns an empty string.

    Usage:
        Create a file at the project root named 'expert_notes.txt'.
        Add any expert commentary, trade ideas, or market notes.
        The content will be displayed in the 'Expert Insights' section of the report.
    """
    if not EXPERT_NOTES_PATH.exists():
        return ""

    with open(EXPERT_NOTES_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        return ""

    return content


# ─── Correction Checklist HTML ─────────────────────────────────────────────

CORRECTION_CHECKLIST_ITEMS = [
    ("🔴 Cut losers immediately",                 "Exit any position down >7-8% from entry. No averaging down."),
    ("🔴 Reduce overall exposure",                "Scale down to 25-50% invested. Cash is a position."),
    ("🟡 Identify true market leaders",           "Which stocks are holding up best? These lead the next rally."),
    ("🟡 Monitor VIX for capitulation",           "VIX spike >35-40 often signals a tradeable low."),
    ("🟡 Watch for volume climax",                "High-volume selling exhaustion = potential reversal signal."),
    ("🟢 Build a watchlist of strong stocks",     "Stocks near highs or with tight bases during correction."),
    ("🟢 Wait for Follow-Through Day (FTD)",      "A strong up day (+1.7%+) on higher volume = confirmed rally."),
    ("🟢 Re-enter in small pilot positions",      "Start with 25% of normal size, add only if market confirms."),
]

def build_correction_checklist_html() -> str:
    """
    Build the Market Correction Checklist HTML block.
    Displayed at the top of the report when regime == 'Correction'.
    """
    items_html = ""
    for title, desc in CORRECTION_CHECKLIST_ITEMS:
        items_html += f"""
        <div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid #2a2a2a;">
          <div style="min-width:220px;font-weight:600;font-size:13px;color:#e0e0e0;">{title}</div>
          <div style="font-size:12px;color:#aaaaaa;line-height:1.6;">{desc}</div>
        </div>"""

    return f"""
<div id="correction-checklist" style="
  background: linear-gradient(135deg, #1a0a0a 0%, #1c1010 100%);
  border: 2px solid #f44336;
  border-radius: 10px;
  padding: 20px 24px;
  margin-bottom: 28px;
  box-shadow: 0 0 20px rgba(244,67,54,0.15);
">
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

  <div style="font-size:11px;color:#777;margin-bottom:12px;">
    Follow this protocol systematically. Do not skip steps. Protect capital first.
  </div>

  {items_html}

  <div style="margin-top:16px;padding:10px 14px;background:rgba(244,67,54,0.08);
              border-radius:6px;font-size:11px;color:#ef9a9a;line-height:1.7;">
    <strong style="color:#f44336;">Key Principle:</strong>
    The goal during a correction is <strong>capital preservation</strong>, not profit maximization.
    Wait for a confirmed Follow-Through Day before re-committing capital aggressively.
    Patience is the edge.
  </div>
</div>"""


# ─── Main Logic ────────────────────────────────────────────────────────────

def process_logic() -> dict:
    """
    Main entry point for regime_filter.
    Returns regime_info and expert_insights for use by html_generator.
    """
    json_path = DATA_DIR / "today_market.json"
    if not json_path.exists():
        print("  ⚠  today_market.json not found.")
        return {"regime_info": {}, "expert_insights": ""}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    regime_info     = determine_regime(data)
    expert_insights = get_expert_insights()

    print(f"  ✓  Regime detected: {regime_info['regime']} — {regime_info['label']}")
    if expert_insights:
        print(f"  ✓  Expert notes loaded ({len(expert_insights)} chars)")
    else:
        print("  ℹ  No expert notes found (expert_notes.txt is empty or missing)")

    return {
        "regime_info":     regime_info,
        "expert_insights": expert_insights,
    }


if __name__ == "__main__":
    result = process_logic()
    print(result)
