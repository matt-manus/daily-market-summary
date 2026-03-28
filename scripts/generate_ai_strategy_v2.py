#!/usr/bin/env python3
"""
generate_ai_strategy_v2.py
使用 OpenAI API 生成 Bull Case / Bear Case 策略分析
"""
import json, os, sys
from pathlib import Path
from openai import OpenAI

BASE = Path(__file__).resolve().parent.parent
JSON_IN  = BASE / "data" / "today_market.json"
JSON_OUT = BASE / "data" / "ai_strategy.json"

def load_market_data():
    with open(JSON_IN, "r", encoding="utf-8") as f:
        return json.load(f)

def build_prompt(d):
    meta = d["meta"]
    idx  = d["indices"]
    sent = d["sentiment"]
    mac  = d["macro"]
    br   = d["breadth"]
    secs = d.get("sectors", [])

    # Build sector summary
    sector_lines = []
    for s in secs:
        sector_lines.append(
            f"  {s['symbol']} ({s.get('name','')}) price={s.get('price')} "
            f"chg={s.get('change_1d_pct')}% RSI={s.get('rsi14','N/A')} status={s.get('status','')}"
        )
    sector_text = "\n".join(sector_lines)

    # Breadth
    sp_p20  = br["sp500"].get("pct_above_20ma", "N/A")
    sp_p200 = br["sp500"].get("pct_above_200ma", "N/A")
    nq_p200 = br["nasdaq100"].get("pct_above_200ma", "N/A")
    mwad    = br.get("market_wide_advance_decline", {})
    nyse_ad = mwad.get("NYSE", {})
    nasd_ad = mwad.get("NASDAQ", {})

    prompt = f"""你是一位專業的美股市場策略師，請根據以下 {meta['date']} 收盤數據，撰寫今日市場復盤分析。

=== 主要指數 ===
SPY: ${idx['SPY']['price']}  {idx['SPY']['change_1d_pct']:+.2f}%  RSI={idx['SPY']['rsi14']:.1f}  vs20MA={idx['SPY']['vs_ma20_pct']:+.2f}%  vs50MA={idx['SPY']['vs_ma50_pct']:+.2f}%  vs200MA={idx['SPY']['vs_ma200_pct']:+.2f}%  A/D={idx['SPY']['ad_ratio']}
QQQ: ${idx['QQQ']['price']}  {idx['QQQ']['change_1d_pct']:+.2f}%  RSI={idx['QQQ']['rsi14']:.1f}  vs20MA={idx['QQQ']['vs_ma20_pct']:+.2f}%  vs50MA={idx['QQQ']['vs_ma50_pct']:+.2f}%  vs200MA={idx['QQQ']['vs_ma200_pct']:+.2f}%  A/D={idx['QQQ']['ad_ratio']}
DIA: ${idx['DIA']['price']}  {idx['DIA']['change_1d_pct']:+.2f}%  RSI={idx['DIA']['rsi14']:.1f}  vs20MA={idx['DIA']['vs_ma20_pct']:+.2f}%  vs50MA={idx['DIA']['vs_ma50_pct']:+.2f}%  vs200MA={idx['DIA']['vs_ma200_pct']:+.2f}%  A/D={idx['DIA']['ad_ratio']}
IWM: ${idx['IWM']['price']}  {idx['IWM']['change_1d_pct']:+.2f}%  RSI={idx['IWM']['rsi14']:.1f}  vs20MA={idx['IWM']['vs_ma20_pct']:+.2f}%  vs50MA={idx['IWM']['vs_ma50_pct']:+.2f}%  vs200MA={idx['IWM']['vs_ma200_pct']:+.2f}%  A/D={idx['IWM']['ad_ratio']}

=== 宏觀數據 ===
VIX: {mac['VIX']['price']}  ({mac['VIX']['change_1d_pct']:+.2f}%)
DXY: {mac['DXY']['price']}  ({mac['DXY']['change_1d_pct']:+.2f}%)
10Y Yield: {mac['TNX_10Y']['price']}%  ({mac['TNX_10Y']['change_1d_pct']:+.2f}%)
Gold: ${mac['GOLD']['price']:,.0f}  ({mac['GOLD']['change_1d_pct']:+.2f}%)
WTI Oil: ${mac['OIL_WTI']['price']}  ({mac['OIL_WTI']['change_1d_pct']:+.2f}%)
BTC: ${mac['BTC']['price']:,.0f}  ({mac['BTC']['change_1d_pct']:+.2f}%)

=== 市場情緒 ===
Fear & Greed: {sent['fear_greed']['score']} ({sent['fear_greed']['rating']})
Put/Call Ratio: {sent['put_call']['value']}
NAAIM Exposure: {sent['naaim']['value']} (prev week: {sent['naaim']['history'][1]['value'] if len(sent['naaim']['history'])>1 else 'N/A'})

=== 市場廣度 ===
SP500 >20MA: {sp_p20}%  |  SP500 >200MA: {sp_p200}%
NASDAQ100 >200MA: {nq_p200}%
NYSE A/D: {nyse_ad.get('advances','N/A')}/{nyse_ad.get('declines','N/A')} (ratio={nyse_ad.get('ad_ratio','N/A')})
NASDAQ A/D: {nasd_ad.get('advances','N/A')}/{nasd_ad.get('declines','N/A')} (ratio={nasd_ad.get('ad_ratio','N/A')})

=== 板塊表現 ===
{sector_text}

請以 JSON 格式輸出以下欄位（不要有任何 markdown 代碼塊，直接輸出 JSON）：
{{
  "risk_score": <整數 1-9，1=最低風險，9=最高風險>,
  "risk_reasons": [<5條簡短的風險評分理由，英文+中文混合，引用具體數值>],
  "outlook": "<市場展望，例如 Risk-off (Defensive) 或 Cautiously Bullish>",
  "outlook_color": "<red/amber/green>",
  "bull_points": [<5條 Bull Case 要點，繁體中文，引用具體數值，Point Form>],
  "bear_points": [<5條 Bear Case 要點，繁體中文，引用具體數值，Point Form>],
  "bull_text": "<Bull Case 完整段落，繁體中文>",
  "bear_text": "<Bear Case 完整段落，繁體中文>",
  "watchlist": [
    {{
      "symbol": "<板塊 ETF 代號>",
      "name": "<板塊名稱>",
      "price": <價格>,
      "rsi": <RSI值>,
      "change_1d": <1日漲跌%>,
      "ma20": <20MA>,
      "ma50": <50MA>,
      "ma200": <200MA>,
      "status": "<ABOVE ALL / BELOW ALL / MIXED>",
      "thesis": "<操作邏輯，繁體中文>",
      "entry": "<進場條件>",
      "stop": "<止損條件>",
      "trigger": "<觸發條件，繁體中文>"
    }}
  ],
  "vix_price": {mac['VIX']['price']},
  "vix_chg": {mac['VIX']['change_1d_pct']},
  "fg_score": {sent['fear_greed']['score']},
  "sp_p20": {sp_p20},
  "sp_p200": {sp_p200},
  "naaim_val": {sent['naaim']['value']},
  "naaim_prev": {sent['naaim']['history'][1]['value'] if len(sent['naaim']['history'])>1 else 0},
  "spy_rsi": {idx['SPY']['rsi14']},
  "qqq_rsi": {idx['QQQ']['rsi14']}
}}

watchlist 請選出 3 個最值得關注的板塊 ETF（可以是強勢板塊或防禦板塊），並提供具體操作邏輯。
"""
    return prompt

def generate_strategy(d):
    client = OpenAI()
    prompt = build_prompt(d)
    
    print("[AI] 正在呼叫 GPT 生成策略分析...")
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "你是一位專業的美股市場策略師，擅長技術分析和市場情緒分析。請嚴格按照 JSON 格式輸出，不要有任何 markdown 代碼塊。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=3000
    )
    
    content = response.choices[0].message.content.strip()
    print(f"[AI] 收到回應 ({len(content)} chars)")
    
    # Clean up potential markdown code blocks
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        content = "\n".join(lines)
    
    # Parse JSON
    strategy = json.loads(content)
    print(f"[AI] Risk Score: {strategy['risk_score']}/9")
    print(f"[AI] Outlook: {strategy['outlook']}")
    print(f"[AI] Bull Points: {len(strategy['bull_points'])}")
    print(f"[AI] Bear Points: {len(strategy['bear_points'])}")
    
    return strategy

def main():
    print("=== AI Strategy Generator v2 ===")
    d = load_market_data()
    print(f"[INFO] 數據日期: {d['meta']['date']}")
    
    strategy = generate_strategy(d)
    
    # Save
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(strategy, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ AI 策略已儲存至 {JSON_OUT}")
    return strategy

if __name__ == "__main__":
    main()
