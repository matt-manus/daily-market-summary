"""
data_fetcher.py — Market Data Fetcher v1.0
-------------------------------------------
Thin wrapper around the existing fetch_all_data.py script.
Provides a clean fetch_all() entry point for main.py.

All actual data fetching logic lives in scripts/fetch_all_data.py.
This module simply invokes it and reports the result.
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FETCH_SCRIPT = BASE_DIR / "scripts" / "fetch_all_data.py"
AI_SCRIPT    = BASE_DIR / "scripts" / "generate_ai_strategy.py"


def fetch_all():
    """
    Fetch all market data by running fetch_all_data.py.
    Writes output to data/today_market.json.
    """
    if not FETCH_SCRIPT.exists():
        raise FileNotFoundError(f"fetch_all_data.py not found at {FETCH_SCRIPT}")

    print(f"Running: {FETCH_SCRIPT}")
    result = subprocess.run(
        [sys.executable, str(FETCH_SCRIPT)],
        capture_output=False,
        check=False
    )
    if result.returncode != 0:
        print(f"  ⚠  fetch_all_data.py exited with code {result.returncode}")
    else:
        print("  ✓  Market data fetched successfully")


def generate_ai_strategy():
    """
    Generate AI strategy JSON by running generate_ai_strategy.py.
    Writes output to data/ai_strategy.json.
    """
    if not AI_SCRIPT.exists():
        print(f"  ⚠  generate_ai_strategy.py not found at {AI_SCRIPT}, skipping.")
        return

    print(f"Running: {AI_SCRIPT}")
    result = subprocess.run(
        [sys.executable, str(AI_SCRIPT)],
        capture_output=False,
        check=False
    )
    if result.returncode != 0:
        print(f"  ⚠  generate_ai_strategy.py exited with code {result.returncode}")
    else:
        print("  ✓  AI strategy generated successfully")


if __name__ == "__main__":
    fetch_all()
    generate_ai_strategy()
