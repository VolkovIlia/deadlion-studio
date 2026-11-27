"""Score issue-site detection in the annotated holdout; unrelated lines do not count."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
source = root / "cases.py"
config = root.parents[1] / "skills/performance/ast/sgconfig.yml"
run = subprocess.run(["ast-grep", "scan", "-c", config, "--json=compact", str(source)],
                     capture_output=True, text=True, check=True)
hits = {row["range"]["start"]["line"] + 1 for row in json.loads(run.stdout)}
counts = {name: 0 for name in ("TP", "FP", "TN", "FN")}
for number, line in enumerate(source.read_text().splitlines(), 1):
    if "# positive:" in line:
        counts["TP" if number in hits else "FN"] += 1
    elif "# negative:" in line:
        counts["FP" if number in hits else "TN"] += 1
print(json.dumps(dict(**counts, precision=counts["TP"] / (counts["TP"] + counts["FP"]),
                      recall=counts["TP"] / (counts["TP"] + counts["FN"]))))
