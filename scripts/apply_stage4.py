import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TMPL = BASE / "templates" / "report_template.html"
RENDER = BASE / "scripts" / "render_report.py"

with open(TMPL, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Dark Mode: ensure pure black #000000 (though #0d0d0d is dark, user asked for "全黑底色專業質感", let's use #000000)
html = html.replace("background-color: #0d0d0d;", "background-color: #000000;")

# 2. Clean up CSS for ADR if it exists
html = re.sub(r'\.adr-card \{.*?\n\s*\}\n', '', html, flags=re.DOTALL)
html = re.sub(r'\.adr-card-head \{.*?\n\s*\}\n', '', html, flags=re.DOTALL)
html = re.sub(r'\.adr-row \{.*?\n\s*\}\n', '', html, flags=re.DOTALL)
html = re.sub(r'\.adr-row:last-child \{.*?\n', '', html)
html = re.sub(r'\.adr-row \.adr-val \{.*?\n', '', html)

# 3. Remove Status column from Section 5A
# Find the table header
html = re.sub(r'<th>Status</th>\s*</tr>\s*</thead>\s*<tbody>\s*\{\{SECTOR_ROWS\}\}', 
              r'</tr>\n      </thead>\n      <tbody>\n        {{SECTOR_ROWS}}', html)

# 4. Add Section 8
if "Section 8" not in html:
    s8_html = """
<!-- ═══ SECTION 8 — EVENT CALENDAR ════════════════════════════════ -->
<div class="section">
  <div class="section-title">Section 8 — Event Calendar (Mar 30 - Apr 3)</div>
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Event / Ticker</th>
          <th>Volatility Risk</th>
        </tr>
      </thead>
      <tbody>
        {{S8_CONTENT}}
      </tbody>
    </table>
  </div>
</div>

<!-- FOOTER -->"""
    html = html.replace("<!-- FOOTER -->", s8_html)

with open(TMPL, "w", encoding="utf-8") as f:
    f.write(html)

with open(RENDER, "r", encoding="utf-8") as f:
    code = f.read()

# Remove Status from build_sector_rows
code = re.sub(r'<td>\{badge\}</td></tr>', r'</tr>', code)
code = re.sub(r'badge = status_badge\(s\.get\("status"\)\)\n\s*rows\.append\(', r'rows.append(', code)

# Prepare S6, S7, S8 contents
s6_content = """
  <table class="data-table" style="margin-bottom: 16px;">
    <thead>
      <tr>
        <th>Indicator</th>
        <th>Value</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>VIX (Volatility)</strong></td>
        <td>27.67</td>
        <td><span class="status-badge badge-below" style="background: var(--red-bg); color: var(--red);">🔴 Bearish</span></td>
      </tr>
      <tr>
        <td><strong>Fear & Greed</strong></td>
        <td>18.55</td>
        <td><span class="status-badge badge-above" style="background: var(--green-bg); color: var(--green);">🟢 Bullish</span></td>
      </tr>
      <tr>
        <td><strong>Put/Call Ratio</strong></td>
        <td>0.73</td>
        <td><span class="status-badge badge-mixed" style="background: var(--amber-bg); color: var(--amber);">🟡 Neutral</span></td>
      </tr>
      <tr>
        <td><strong>S&P 500 > 20MA</strong></td>
        <td>20.5%</td>
        <td><span class="status-badge badge-below" style="background: var(--red-bg); color: var(--red);">🔴 Bearish</span></td>
      </tr>
      <tr>
        <td><strong>NAAIM Exposure</strong></td>
        <td>68.52</td>
        <td><span class="status-badge badge-mixed" style="background: var(--amber-bg); color: var(--amber);">🟡 Neutral</span></td>
      </tr>
    </tbody>
  </table>

  <h4 class="sub-title">Bull Case (利好邏輯)</h4>
  <p style="color: #e0e0e0; font-size: 13px; line-height: 1.6;">目前市場處於「極度恐慌」狀態（Fear & Greed Index 跌至 18.55），這通常是逆向操作的潛在買入信號。SPY 與 QQQ 的 RSI(14) 分別降至 34.15 與 35.67，接近超賣區間。同時，雖然指數持續承壓，但 S&P 500 在 200MA 之上的比例仍有 47.3%，顯示長期支撐仍在。若市場能在此處守住關鍵支撐，配合極致悲觀的情緒，可能醞釀出強勁的超賣反彈。</p>

  <h4 class="sub-title" style="margin-top: 16px;">Bear Case (利淡邏輯)</h4>
  <p style="color: #e0e0e0; font-size: 13px; line-height: 1.6;">市場趨勢明顯轉弱，所有主要指數（SPY, QQQ, DIA）均跌破 20MA 與 50MA，處於全面弱勢。VIX 飆升 9.24% 至 27.67，顯示避險情緒高漲與宏觀壓力加劇。此外，市場廣度極差，S&P 500 僅有 20.5% 的股票維持在 20MA 之上，且強勢板塊過度集中於能源（XLE RSI 高達 80.78），缺乏科技或消費等核心板塊的領漲，這意味著反彈可能缺乏實質性買盤支撐，容易形成無量反彈或假突破。</p>
"""

s7_content = """
  <h4 class="sub-title">Trading Outlook</h4>
  <p style="color: #e0e0e0; font-size: 13px; line-height: 1.6;"><strong>Risk-off (Score: 3/9)</strong><br/>
  當前市場波動率（VIX）高企且趨勢向下，建議保持防守姿態（Risk-off），降低整體倉位（Exposure），耐心等待大盤出現明確的止跌企穩信號或放量突破。</p>

  <h4 class="sub-title" style="margin-top: 16px;">Watchlist (相對強度板塊)</h4>
  <ul style="margin-left: 20px; line-height: 1.8; color: #e0e0e0; font-size: 13px;">
    <li><strong>Energy (XLE)</strong>: RSI 80.78，強勢突破所有均線，油價上漲帶動板塊動能，為目前市場唯一避風港。</li>
    <li><strong>Utilities (XLU)</strong>: 相對抗跌，具備防禦屬性，在市場波動加劇時資金容易流入。</li>
    <li><strong>Materials (XLB)</strong>: 表現優於大盤，近期維持在 200MA 之上，具備一定的相對強度（Relative Strength）。</li>
  </ul>
"""

s8_content = """
        <tr>
          <td>Mar 31 (Tue)</td>
          <td>CB Consumer Confidence / JOLTs</td>
          <td><span class="text-amber" style="font-weight:600;">Medium</span></td>
        </tr>
        <tr>
          <td>Mar 31 (Tue)</td>
          <td>Earnings: NKE, MKC, FDS</td>
          <td><span class="text-amber" style="font-weight:600;">Medium</span></td>
        </tr>
        <tr>
          <td>Apr 1 (Wed)</td>
          <td>ISM Manufacturing PMI / ADP</td>
          <td><span class="text-red" style="font-weight:600;">High</span></td>
        </tr>
        <tr>
          <td>Apr 2 (Thu)</td>
          <td>Initial Jobless Claims</td>
          <td><span class="text-amber" style="font-weight:600;">Medium</span></td>
        </tr>
        <tr>
          <td>Apr 3 (Fri)</td>
          <td>Non Farm Payrolls (NFP) / Unemployment Rate</td>
          <td><span class="text-red" style="font-weight:600;">High</span></td>
        </tr>
        <tr>
          <td>Apr 3 (Fri)</td>
          <td>ISM Services PMI</td>
          <td><span class="text-red" style="font-weight:600;">High</span></td>
        </tr>
"""

# Replace placeholders in render_report.py
replacement_block = f"""
    # Sections 6, 7 & 8: AI Analysis & Calendar
    html = html.replace("{{{{S6_CONTENT}}}}", '''{s6_content}''')
    html = html.replace("{{{{S7_CONTENT}}}}", '''{s7_content}''')
    html = html.replace("{{{{S8_CONTENT}}}}", '''{s8_content}''')
"""

code = re.sub(r'# Sections 6 & 7: AI placeholders.*?(?=# Residual check)', replacement_block, code, flags=re.DOTALL)

with open(RENDER, "w", encoding="utf-8") as f:
    f.write(code)

print("Stage 4 applied successfully!")
