import os
import base64
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IMG_DIR = BASE_DIR / "assets" / "img" / "today"

def img_to_base64(img_path: Path) -> str:
    if not img_path.exists():
        print(f"  ⚠  Base64 encode: file not found: {img_path}")
        return ""
    try:
        with open(img_path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"  ⚠  Base64 encode error for {img_path}: {e}")
        return ""

def capture_and_encode():
    print("Running screenshot scripts...")
    scripts_dir = BASE_DIR / "scripts"
    
    # Run screenshot scripts
    scripts = [
        "screenshot_trends.py",
        "screenshot_finviz.py",
        "screenshot_industry.py",
        "screenshot_stockbee.py"
    ]
    
    for script in scripts:
        script_path = scripts_dir / script
        if script_path.exists():
            print(f"Executing {script}...")
            subprocess.run(["python3", str(script_path)], check=False)
            
    print("Converting images to Base64...")
    images = {
        "stockbee": img_to_base64(IMG_DIR / "stockbee_mm.png"),
        "industry": img_to_base64(IMG_DIR / "industry_performance.png"),
        "heatmap": img_to_base64(IMG_DIR / "market_heatmap.png"),
        "spy_trend": img_to_base64(IMG_DIR / "spy_trend.png"),
        "qqq_trend": img_to_base64(IMG_DIR / "qqq_trend.png"),
        "dia_trend": img_to_base64(IMG_DIR / "dia_trend.png"),
        "iwm_trend": img_to_base64(IMG_DIR / "iwm_trend.png"),
    }
    
    return images

def get_base64_images():
    images = {
        "stockbee": img_to_base64(IMG_DIR / "stockbee_mm.png"),
        "industry": img_to_base64(IMG_DIR / "industry_performance.png"),
        "heatmap": img_to_base64(IMG_DIR / "market_heatmap.png"),
        "spy_trend": img_to_base64(IMG_DIR / "spy_trend.png"),
        "qqq_trend": img_to_base64(IMG_DIR / "qqq_trend.png"),
        "dia_trend": img_to_base64(IMG_DIR / "dia_trend.png"),
        "iwm_trend": img_to_base64(IMG_DIR / "iwm_trend.png"),
    }
    return images
