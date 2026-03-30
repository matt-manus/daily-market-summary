import datetime
import pytz
import sys
from pathlib import Path

def is_us_trading_holiday(ny_date):
    """常見美股假期（2026 年已更新）"""
    holidays = {
        (1, 1), (1, 20), (2, 17), (4, 3), (5, 25),
        (6, 19), (7, 4), (9, 7), (11, 26), (12, 25)
    }
    return (ny_date.month, ny_date.day) in holidays

def check_if_trading_day():
    ny_tz = pytz.timezone('America/New_York')
    ny_time = datetime.datetime.now(ny_tz)
    ny_date = ny_time.date()

    # 1. 週末直接停止
    if ny_time.weekday() >= 5:
        print(f"🛑 系統攔截：紐約時間 {ny_date} {ny_time.strftime('%A')} - 非交易日")
        sys.exit(0)

    # 2. 美股假期停止
    if is_us_trading_holiday(ny_date):
        print(f"🛑 系統攔截：紐約時間 {ny_date} 為美股假期")
        sys.exit(0)

    # 3. 檢查 archive 是否已有今日報告（防止重複）
    archive_dir = Path("archive")
    today_str = ny_date.strftime("%Y-%m-%d")
    if (archive_dir / f"{today_str}.html").exists():
        print(f"🛑 系統攔截：今日報告 {today_str}.html 已存在，無需重複生成")
        sys.exit(0)

    print(f"🟢 紐約時間 {ny_date} {ny_time.strftime('%A')} - 美股交易日確認，繼續執行...")
    return True

if __name__ == "__main__":
    check_if_trading_day()
