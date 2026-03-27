import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TMPL = BASE / "templates" / "report_template.html"
RENDER = BASE / "scripts" / "render_report.py"

# Clean up HTML template
with open(TMPL, "r", encoding="utf-8") as f:
    html = f.read()

# Remove all <th>Status</th>
html = html.replace("<th>Status</th>", "")

with open(TMPL, "w", encoding="utf-8") as f:
    f.write(html)

# Clean up render_report.py
with open(RENDER, "r", encoding="utf-8") as f:
    code = f.read()

# Remove {badge} from indices rows if still there
code = code.replace("<td>{badge}</td>", "")
code = re.sub(r'f\'<td>\{badge\}</td></tr>\'', r"f'</tr>'", code)

with open(RENDER, "w", encoding="utf-8") as f:
    f.write(code)

print("Status columns fully cleaned.")
