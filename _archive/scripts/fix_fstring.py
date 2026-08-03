import subprocess
from pathlib import Path

BASE = Path(__file__).parent
path = BASE / "modules" / "pages" / "weekly_client_report.py"
content = path.read_text(encoding="utf-8")
fixed = content.replace("d.get('BuyBox','\u2014')", "d.get('BuyBox', '\u2014')")
fixed = fixed.replace("'\u2014'", "'—'")
path.write_text(fixed, encoding="utf-8")
print("Fixed!")
subprocess.run(["git", "add", "modules/pages/weekly_client_report.py"], cwd=BASE, check=True)
subprocess.run(["git", "commit", "-m", "fix: f-string backslash Python 3.11"], cwd=BASE, check=True)
subprocess.run(["git", "push"], cwd=BASE, check=True)
print("Push exitoso!")
