import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


TOOLS = Path(__file__).resolve().parents[1] / "plugins/deadlion/skills/performance/scripts"


def run_tool(name, *args, **kwargs):
    result = subprocess.run([sys.executable, TOOLS / name, *args], capture_output=True,
                            text=True, **kwargs)
    return result.returncode, json.loads(result.stdout)


@pytest.mark.parametrize(("values", "expected"), [
    ([0.7] * 16, "VERIFIED"),
    ([1.3] * 16, "PERFORMANCE REGRESSION"),
    ([0.5, 1.5] * 8, "INCONCLUSIVE"),
])
def test_paired_interval(values, expected):
    compare = runpy.run_path(str(TOOLS / "dl-perf"))["compare"]
    assert compare([(100, 100 * v) for v in values], 0.1)["status"] == expected


def test_wrong_output(tmp_path):
    data = tmp_path / "answer"
    data.write_bytes(b"0.99999999\n")
    code, report = run_tool("dl-perf", "--baseline", "cat", "--candidate", "echo 1.0",
                            "--input", data, "--expected", data, "--build", "native",
                            "--tolerance", ".05")
    assert (code, report["status"], report["wall_ns"]) == (2, "NOT VERIFIED", [])


def test_python_diagnostics(tmp_path):
    target = tmp_path / "loops.py"
    target.write_text("def f(mapping):\n    for key, value in mapping.items():\n        print(value)\n")
    code, report = run_tool("dl-analyze", "--json", target)
    assert code == 0
    assert [(d["rule"], d["line"]) for d in report["diagnostics"]] == [("PERF102", 2)]


def test_dense_output_no_warning(tmp_path):
    target = tmp_path / "pairs.py"
    target.write_text("def pairs(xs):\n    for x in xs:\n        for y in xs:\n            yield x, y\n")
    code, report = run_tool("dl-analyze", "--json", target)
    assert (code, report["diagnostics"]) == (0, [])


def test_missing_analyzer(tmp_path):
    target = tmp_path / "empty.py"
    target.touch()
    code, report = run_tool("dl-analyze", "--json", target, env={**os.environ, "PATH": ""})
    assert (code, report["status"]) == (2, "NOT VERIFIED")


def test_incomplete_contract(tmp_path):
    contract = tmp_path / "contract.json"
    contract.write_text('{"mode":"Performance"}')
    code, report = run_tool("dl-contract", contract)
    assert code == 2
    assert "invariant" in report["reason"]


def test_broken_analyzer(tmp_path):
    analyzer = tmp_path / "ruff"
    analyzer.write_text("#!/bin/sh\necho 'garbled output'\n")
    analyzer.chmod(0o755)
    target = tmp_path / "empty.py"
    target.touch()
    code, report = run_tool("dl-analyze", "--json", target, env={**os.environ, "PATH": str(tmp_path)})
    assert (code, report["status"]) == (2, "NOT VERIFIED")


def test_changed_scan_observes_shell_edit(tmp_path):
    subprocess.run(["git", "init", "-q", tmp_path], check=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                    "commit", "--allow-empty", "-qm", "base"], cwd=tmp_path, check=True)
    (tmp_path / "new.py").write_text("for key,val in table.items():\n    print(val)\n")
    code, report = run_tool("dl-analyze", "--changed", "--json", cwd=tmp_path)
    assert code == 0
    assert report["diagnostics"][0]["rule"] == "PERF102"


def test_syntax_error_is_unverified(tmp_path):
    target = tmp_path / "bad.py"
    target.write_text("def invalid(:\n")
    code, report = run_tool("dl-analyze", "--json", target)
    assert (code, report["status"]) == (2, "NOT VERIFIED")


def test_cache_invalidates_same_length_same_mtime(tmp_path):
    path = tmp_path / "loop.py"
    cache = tmp_path / "cache"
    path.write_text("for k,v in tab.items():\n print(k,v)\n")
    before = path.stat()
    flags = ("--json", "--cache-dir", cache, path)
    assert run_tool("dl-analyze", *flags)[1]["diagnostics"] == []
    assert len(list(cache.glob("*.clean"))) == 1
    path.write_text("for k,v in tab.items():\n print(  v)\n")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert run_tool("dl-analyze", *flags)[1]["diagnostics"][0]["rule"] == "PERF102"


def test_pareto_preserves_tradeoffs(tmp_path):
    path = tmp_path / "trials.json"
    rows = {"fast": (1, 3), "small": (2, 1), "dominated": (2, 3), "wrong": (0, 0)}
    path.write_text(json.dumps(dict(directions=dict(time="min", bytes="min"), candidates={
        name: dict(status="NOT VERIFIED" if name == "wrong" else "VERIFIED",
                   metrics=dict(time=t, bytes=b)) for name, (t, b) in rows.items()
    })))
    code, report = run_tool("dl-perf", "frontier", path)
    assert code == 0
    assert set(report["frontier"]) == {"fast", "small"}
    assert report["rejected"] == {"wrong": "NOT VERIFIED"}


@pytest.mark.skipif(not Path("/usr/bin/time").exists(), reason="GNU time required")
def test_memory_ceiling_distinguishes_retention_and_reuse():
    flags = ("--max", "peak_rss_kib=45000", "resources", "--", sys.executable, "-c")
    code, retained = run_tool("dl-profile", *flags, "items=[bytearray(1024*1024) for _ in range(64)]")
    assert (code, retained["exceeded"]) == (1, ["peak_rss_kib"])
    code, reused = run_tool("dl-profile", *flags, "buf=bytearray(1024*1024)\nfor i in range(64): buf[0]=i")
    assert (code, reused["exceeded"]) == (0, [])


def test_structural_complexity_is_informational(tmp_path):
    scan = runpy.run_path(str(TOOLS / "dl-analyze"))["inspect"]
    source = tmp_path / "branches.py"
    source.write_text("def f(x, y):\n    if x:\n        if y:\n            return 1\n")
    assert [(d["rule"], d["severity"]) for d in scan(["--", source], deep=True)] == [("SIM102", "INFO")]
    source.write_text("def f(x):\n    if x:\n        return 1\n    return 0\n")
    assert list(scan(["--", source], deep=True)) == []


def test_experiment_budgets_persist(tmp_path):
    cls = runpy.run_path(str(TOOLS.parents[2] / "omp/experiment_budget.py"))["ExperimentBudget"]
    limits = dict(tokens=50, patience=2)
    event = dict(type="message_end", message=dict(role="assistant", usage=dict(totalTokens=26)))
    assert cls(tmp_path, limits).observe(event) is None
    assert "token budget" in cls(tmp_path, limits).observe(event)
    budget = cls(tmp_path, dict(tokens=0, patience=2))
    for i in range(2):
        assert budget.observe(dict(type="tool_execution_start", toolName="log_experiment",
                                   toolCallId=str(i), args=dict(status="discard"))) is None
        reason = budget.observe(dict(type="tool_execution_end", toolName="log_experiment",
                                     toolCallId=str(i), isError=False))
    assert reason == "no independently verified improvement"


def test_contract_gate_refuses_unmeasured_budget(tmp_path):
    source = TOOLS.parents[2] / "evals/indexed-membership/contract.json"
    record = json.loads(source.read_text())
    record["budget"]["unknown_metric"] = 1
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(record))
    code, report = run_tool("dl-perf-gate", contract)
    assert (code, report["status"]) == (2, "NOT VERIFIED")


def test_contract_gate_checks_current_candidate(tmp_path):
    source = TOOLS.parents[2] / "evals/indexed-membership/contract.json"
    record = json.loads(source.read_text())
    record["benchmark"] = dict(baseline=["cat"], candidate=["echo", "wrong"], expected="input")
    (tmp_path / "input").write_text("correct\n")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(record))
    code, report = run_tool("dl-perf-gate", contract)
    assert code == 2 and report["status"] == "NOT VERIFIED"
    assert "stdout" in report["reason"]


def test_gate_retains_approved_oracle_across_checkouts(tmp_path):
    source = TOOLS.parents[2] / "evals/indexed-membership"
    base = tmp_path / "approved"
    candidate = tmp_path / "candidate"
    base.mkdir()
    candidate.mkdir()
    for path in ("contract.json", "input", "expected", "scan.py"):
        (base / path).write_bytes((source / path).read_bytes())
    (candidate / "indexed.py").write_text('print("weakened")')
    (candidate / "expected").write_text("weakened\n")
    code, report = run_tool("dl-perf-gate", base / "contract.json", "--candidate-dir", candidate)
    assert code == 2 and "stdout" in report["reason"]


def test_required_provider_cap_stops_before_clone(tmp_path):
    workspace = tmp_path / "experiment"
    launcher = TOOLS.parents[2] / "omp/dl-evolve"
    result = subprocess.run([launcher, workspace, "--require-hard-token-cap"], capture_output=True)
    assert result.returncode and b"NOT VERIFIED" in result.stderr
    assert not workspace.exists()


def test_load_checks_every_response(tmp_path):
    expected = tmp_path / "fixture"
    expected.write_text("verified\n")
    flags = ("load", "--requests", "100", "--workers", "3", "--input", expected, "--expected", expected, "--")
    code, result = run_tool("dl-perf", *flags, "cat")
    assert code == 0 and result["requests"] == len(result["raw_latency_ns"]) == 100
    latency = result["latency_ns"]
    assert 0 < latency["p50"] <= latency["p95"] <= latency["p99"]
    code, result = run_tool("dl-perf", *flags, "echo", "incorrect")
    assert code != 0 and result["status"] == "NOT VERIFIED"
