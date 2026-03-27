import sys
import os
from pathlib import Path

# Ensure src is in Python path
sys.path.append(str(Path(__file__).resolve().parent))

import data_fetcher
import image_agent
import regime_filter
import html_generator

def main():
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
    
    print("\n[4/4] Rendering HTML Report...")
    try:
        html_generator.render(regime_info=regime_info, expert_insights=expert_insights)
    except Exception as e:
        print(f"Error rendering HTML: {e}")
        
    print("\n=== Process Completed ===")

if __name__ == "__main__":
    main()
