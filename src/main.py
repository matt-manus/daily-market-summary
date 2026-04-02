import sys
import os
import argparse
from pathlib import Path

# Ensure src is in Python path
sys.path.append(str(Path(__file__).resolve().parent))

from holiday_guard import check_if_trading_day
import data_fetcher
import image_agent
import regime_filter
import html_generator

def main():
    # ── CLI Arguments ───────────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Daily Market Summary Generator")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip holiday/weekend guard and force report generation (for manual runs)",
    )
    args = parser.parse_args()

    # ── Guard: skip on weekends / holidays unless --force ─────────────────
    if args.force:
        print("⚡ --force flag detected: skipping holiday/trading-day guard")
    else:
        check_if_trading_day()
    print("=== Daily Market Summary - Modular Generation ===")
    
    print("\n[1/4] Fetching Market Data...")
    try:
        data_fetcher.fetch_all()
    except Exception as e:
        print(f"Error fetching data: {e}")
        
    print("\n[2/4] Capturing Images & Converting to Base64...")
    try:
        image_agent.capture_and_encode()
    except Exception as e:
        print(f"Error capturing images: {e}")
        
    print("\n[3/4] Processing Regime Logic & Expert Notes...")
    logic_data = regime_filter.process_logic()
    regime_info = logic_data.get("regime_info", {}) if logic_data else {}
    expert_insights = logic_data.get("expert_insights", "") if logic_data else ""
    checklist_status = logic_data.get("checklist_status", {}) if logic_data else {}
    
    print("\n[4/4] Rendering HTML Report...")
    try:
        html_generator.render(regime_info=regime_info, expert_insights=expert_insights, checklist_status=checklist_status)
    except Exception as e:
        print(f"Error rendering HTML: {e}")
        
    print("\n=== Process Completed ===")

if __name__ == "__main__":
    main()
