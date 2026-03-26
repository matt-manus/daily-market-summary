#!/usr/bin/env python3.11
"""
Update today_market.json with Stockbee T2108 / Market Monitor data.
Data extracted from Google Sheets iframe (most recent trading day: 3/25/2026).

Column mapping (from header row):
  Col 2:  Date
  Col 3:  Number of stocks up 4% plus today
  Col 4:  Number of stocks down 4% plus today
  Col 5:  5 day ratio
  Col 6:  10 day ratio
  Col 7:  Number of stocks up 25% plus in a quarter
  Col 8:  Number of stocks down 25% + in a quarter
  Col 9:  Number of stocks up 25% + in a month
  Col 10: Number of stocks down 25% + in a month
  Col 11: Number of stocks up 50% + in a month
  Col 12: Number of stocks down 50% + in a month
  Col 13: Number of stocks up 13% + in 34 days
  Col 14: Number of stocks down 13% + in 34 days
  Col 15: Worden Common stock universe
  Col 16: T2108
  Col 17: S&P
"""

import json
import os

JSON_PATH = "/home/ubuntu/daily-market-summary/data/today_market.json"

# Latest 3 rows from Stockbee MM (extracted via JS from Google Sheets)
# Row 3/25/2026 is the most recent trading day
T2108_DATA = {
    "source": "Stockbee Market Monitor (stockbee.blogspot.com/p/mm.html)",
    "sheet_url": "https://docs.google.com/spreadsheets/d/1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/pub",
    "latest_date": "3/25/2026",
    "t2108": 24.53,
    "sp500_close": 6591.90,
    "up_4pct_today": 320,
    "down_4pct_today": 113,
    "ratio_5day": 0.79,
    "ratio_10day": 0.67,
    "up_25pct_quarter": 996,
    "down_25pct_quarter": 1393,
    "up_25pct_month": 106,
    "down_25pct_month": 164,
    "up_50pct_month": 26,
    "down_50pct_month": 25,
    "up_13pct_34days": 1211,
    "down_13pct_34days": 2068,
    "worden_universe": 6401,
    "prev_day": {
        "date": "3/24/2026",
        "t2108": 22.97,
        "up_4pct": 223,
        "down_4pct": 285,
        "ratio_5day": 0.50,
        "ratio_10day": 0.63
    },
    "signal": {
        "t2108_zone": "Oversold (<25%)",
        "primary_ratio_5d": "Bearish (<1.0)",
        "primary_ratio_10d": "Bearish (<1.0)",
        "interpretation": "Market in oversold territory. T2108 at 24.53% (below 25% threshold). 5-day ratio 0.79 and 10-day ratio 0.67 both indicate more stocks declining than advancing on momentum basis."
    }
}

def update_json():
    with open(JSON_PATH, 'r') as f:
        data = json.load(f)
    
    # Add stockbee_mm section
    data["stockbee_mm"] = T2108_DATA
    
    # Update schema version note
    data["meta"]["schema_version"] = "3.3"
    data["meta"]["stage2_updated"] = "2026-03-27"
    
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Updated {JSON_PATH}")
    print(f"   T2108: {T2108_DATA['t2108']}% ({T2108_DATA['signal']['t2108_zone']})")
    print(f"   Up 4%: {T2108_DATA['up_4pct_today']} | Down 4%: {T2108_DATA['down_4pct_today']}")
    print(f"   5-Day Ratio: {T2108_DATA['ratio_5day']} | 10-Day Ratio: {T2108_DATA['ratio_10day']}")
    print(f"   Schema version: {data['meta']['schema_version']}")

if __name__ == "__main__":
    update_json()
