#!/usr/bin/env python3
"""
scripts/full_pipeline.py
Phase 3.9 Trial Run 全自動整合腳本
負責一次過更新所有數據 + 生成最新報告
"""

import subprocess
import os
from datetime import datetime
import pytz

def run_command(cmd, name):
    print(f"🚀 執行 {name}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"⚠️ {name} 警告: {result.stderr}")
    return result.returncode == 0

def main():
    print("=== Momentum Swing Trading Coach Full Pipeline (dev-3.9 Trial) ===")
    hkt = pytz.timezone('Asia/Hong_Kong')
    print(f"開始時間: {datetime.now(hkt).strftime('%Y-%m-%d %H:%M')} HKT\n")

    # 1. 主數據更新
    run_command("python scripts/fetch_all_data.py", "fetch_all_data.py (Macro + Indices)")

    # 2. 4C Stockbee
    run_command("python fetch_stockbee_data.py", "fetch_stockbee_data.py (T2108 + Waffle)")

    # 3. 4D Heatmap
    run_command("python scripts/fetch_finviz_heatmap.py", "fetch_finviz_heatmap.py (Market Heatmap)")

    # 4. 生成最終報告
    run_command("python scripts/render_report.py", "render_report.py (HTML 生成)")

    print("\n🎉 Full Pipeline 執行完成！")
    print(f"報告已更新至 {datetime.now(hkt).strftime('%Y-%m-%d %H:%M')} HKT")

if __name__ == "__main__":
    main()
