import pandas as pd
from datetime import datetime
from pathlib import Path

class RegimeFilter:
    def __init__(self, data: dict):
        self.data = data

    def determine_regime(self):
        spy = self.data.get('SPY', {})
        vix = self.data.get('VIX', 0)
        ad_ratio = self.data.get('AD_RATIO', 0)
        percent_above_20ma = self.data.get('percent_above_20ma', 0)
        rsi = spy.get('rsi', 0)

        spy_close = spy.get('close', 0)
        ma20 = spy.get('ma20', 0)
        ma50 = spy.get('ma50', 0)

        # Regime 判斷
        if vix < 20 and spy_close > ma20 and percent_above_20ma > 40:
            regime = "🟢 Uptrend"
            score = 85
        elif (20 <= vix <= 30) or (ma20 > spy_close > ma50) or (25 < percent_above_20ma < 40):
            regime = "🟡 Correction"
            score = 55
        else:
            regime = "🔴 Bear Market"
            score = 25

        checklist = self._generate_checklist(spy, vix, ad_ratio, percent_above_20ma, rsi, ma20)

        return {
            "regime": regime,
            "regime_score": score,
            "checklist": checklist,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "raw_numbers": {
                "VIX": round(vix, 1),
                "SPY_vs_20MA": round(spy_close - ma20, 2),
                "percent_above_20ma": round(percent_above_20ma, 1),
                "A/D_Ratio": round(ad_ratio, 3),
                "RSI": round(rsi, 1)
            }
        }

    def _generate_checklist(self, spy, vix, ad_ratio, percent_above_20ma, rsi, ma20):
        spy_close = spy.get('close', 0)
        green = {
            "S&P 500 Correction Target": {"value": "Y" if spy_close > ma20 else "N", "actual": f"SPY {spy_close:.1f}"},
            "Downward momentum 減弱": {"value": "Y" if rsi > 50 else "N", "actual": f"RSI {rsi:.1f}"},
            "Base formation & breakout": {"value": "Y" if spy_close > ma20 else "N", "actual": f"SPY vs 20MA {spy_close - ma20:.1f}"},
            "Technical indicators improving": {"value": "Y" if rsi > 50 else "N", "actual": f"RSI {rsi:.1f}"},
            "Market breadth improving": {"value": "Y" if ad_ratio > 1.0 else "N", "actual": f"A/D {ad_ratio:.3f}"},
            "VIX < 20 或 collapse": {"value": "Y" if vix < 20 else "N", "actual": f"VIX {vix:.1f}"},
        }
        green_total = sum(1 for v in green.values() if v["value"] == "Y")

        red = {
            "Downward momentum 增強": {"value": "Y" if rsi < 50 else "N", "actual": f"RSI {rsi:.1f}"},
            "Top range breakdown": {"value": "Y" if spy_close < ma20 else "N", "actual": f"SPY vs 20MA {spy_close - ma20:.1f}"},
            "Technical indicators deteriorating": {"value": "Y" if rsi < 50 else "N", "actual": f"RSI {rsi:.1f}"},
            "Market breadth worsening": {"value": "Y" if ad_ratio < 1.0 else "N", "actual": f"A/D {ad_ratio:.3f}"},
            "VIX > 20 或 spike": {"value": "Y" if vix > 20 else "N", "actual": f"VIX {vix:.1f}"},
        }
        red_total = sum(1 for v in red.values() if v["value"] == "Y")

        return {
            "green_checklist": green,
            "green_total": green_total,
            "red_checklist": red,
            "red_total": red_total,
            "active_checklist": "green" if green_total >= red_total else "red"
        }