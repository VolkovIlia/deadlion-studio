"""Reproduce the release's local gate, semantic analyzer and overhead probes."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT.parent / "skills/performance/scripts"


def tool(name, *args, cwd=None):
    start = time.perf_counter_ns()
    p = subprocess.run([TOOLS / name, *args], cwd=cwd, capture_output=True)
    return dict(
        code=p.returncode,
        report=json.loads(p.stdout),
        wall_ns=time.perf_counter_ns() - start,
    )


def startup(root):
    sys.path.insert(0, str(TOOLS))
    from candidate_runner import execute

    rows = []
    for _ in range(11):
        start = time.perf_counter_ns()
        subprocess.run(["/usr/bin/true"], check=True)
        direct = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        _, metrics = execute(root, [], ["true"], b"", 3, 96)
        rows.append(
            dict(
                direct_ns=direct,
                isolated_ns=metrics["wall_ns"],
                dispatch_ns=time.perf_counter_ns() - start,
            )
        )
    return rows


def probe(root):
    source = ROOT / "indexed-membership"
    for name in ("scan.py", "indexed.py", "expected", "input"):
        shutil.copy(source / name, root / name)
    record = json.loads((source / "contract.json").read_bytes())
    contract = root / "contract.json"
    evidence = {}
    for name, budget in [
        ("allocations", {"allocation_count": 1000000, "allocated_bytes": 100000000}),
        ("zero_allocations", {"allocation_count": 0}),
        ("pmu", {"instructions": 1e10}),
        ("latency", {"latency_p99_ns": 100000000, "min_requests_per_second": 1}),
    ]:
        record["budget"] = budget
        record["benchmark"]["requests"] = 1000
        contract.write_text(json.dumps(record))
        evidence[name] = tool("dl-perf-gate", contract, cwd=root)
    record["budget"] = {"peak_rss_kib": 98304}
    record["relative_budget"] = {"peak_rss_kib": 3}
    contract.write_text(json.dumps(record))
    evidence["relative_rss"] = tool("dl-perf-gate", contract, "--isolated", cwd=root)
    f = root / "copy.cpp"
    f.write_text(
        "#include <string>\n#include <vector>\nint f(std::vector<std::string> const& v){int n=0;for(const auto s:v)n+=s.size();return n;}\n"
    )
    (root / "compile_commands.json").write_text(
        json.dumps(
            [
                dict(
                    directory=str(root),
                    file=str(f),
                    arguments=["c++", "-std=c++17", "-c", str(f)],
                )
            ]
        )
    )
    evidence["cpp"] = tool("dl-analyze", "--native", "--json", f)
    clean = root / "clean.py"
    clean.write_text("x = 2\n")
    cache = root / "cache"
    evidence["post_edit_ns"] = [
        tool("dl-analyze", "--json", "--cache-dir", cache, clean)["wall_ns"]
        for _ in range(9)
    ]
    evidence["startup"] = startup(root)
    return evidence


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp:
        print(json.dumps(probe(Path(temp)), indent=2))
