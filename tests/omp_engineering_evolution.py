"""Exercise /deadlion evolve and operator acceptance in a native resumed OMP session."""
from http.server import HTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

from omp_engineering_smoke import PLUGIN, Transport, fixture, neighbour, trial


def workloads(directory):
    template = json.loads((PLUGIN / "evals/indexed-membership/contract.json").read_bytes())
    result = {}
    for role in ("design", "train", "holdout"):
        root = directory / role
        root.mkdir()
        (root / "input").write_text(role)
        (root / "expected").write_text("good\n")
        candidate = ["cat", "candidate"] if role != "design" else ["sh", "-c", 'echo "$(cat candidate)"']
        baseline = ["sh", "-c", "sleep .04; echo good"]
        record = dict(template, benchmark=dict(candidate=candidate, candidate_files=["candidate"],
                      baseline=baseline, baseline_files=[], expected="expected"),
                      budget={"peak_rss_kib": 65536} if role == "design" else {"max_wall_ratio": 1.0})
        path = root / "contract.json"
        path.write_text(json.dumps(record))
        result[role] = str(path)
    return result


def exercise(source, profile, directory, server):
    actions = fixture.CALLS.copy()
    contracts = workloads(directory)
    trace = directory / "events.jsonl"
    neighbour(profile, trace)
    (source / "candidate").write_text("good\n\n")
    fixture.git(source, "add", "candidate")
    fixture.git(source, "-c", "user.name=Smoke", "-c", "user.email=test@fixture", "commit", "-qm", "initial solution")
    policy = directory / "policy.json"
    policy.write_text(json.dumps(dict(mode="Evolution", maxCorrections=0, evolution=dict(
        goal="Improve candidate", files=["candidate"], train=contracts["train"], holdout=contracts["holdout"],
        iterations=2, seconds=65))))
    env = {**os.environ, "HOME": str(directory), "PI_CONFIG_DIR": str(directory / ".omp"),
           "PI_CODING_AGENT_DIR": str(profile), "XDG_STATE_HOME": str(directory / "state"),
           "FIXTURE_API_KEY": "unused", "DL_ENGINEERING_POLICY": str(policy), "DL_TEST_TRACE": str(trace),
           "GIT_AUTHOR_NAME": "Smoke", "GIT_COMMITTER_NAME": "Smoke", "GIT_AUTHOR_EMAIL": "smoke@example.invalid",
           "GIT_COMMITTER_EMAIL": "smoke@example.invalid", "DL_PERF_CONTRACT": contracts["design"]}
    subprocess.run(["omp", "plugin", "link", PLUGIN], cwd=source, env=env, check=True, capture_output=True)
    receipt = trial(source, env, server, {0: ("deadlion_verify", {})}, "BLOCKED", 2)
    session = next(row[3] for row in map(json.loads, trace.read_text().splitlines()) if row[0] == "before_agent_start")
    server.steps, server.calls, server.context, server.contracts = dict(enumerate(actions)), 0, [], True
    # After task approval only the frozen holdout may affect this experiment.
    (directory / "holdout/expected").write_text("later edit\n")
    cmd = ["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p", "/deadlion evolve"]
    run = subprocess.run(cmd, cwd=source, env=env, capture_output=True, text=True, timeout=80)
    path = directory / "state/deadlion" / receipt["task"]
    task = json.loads((path / "task.json").read_bytes())
    if "experiment" not in task:
        log = path / "evolution.json"
        raise AssertionError((run.returncode, run.stdout[-1200:], run.stderr[-1200:], log.read_text()[-1200:] if log.exists() else str(path)))
    assert (source / "candidate").read_bytes() == b"good\n\n"
    accepted = subprocess.check_output(["git", "show", task["experiment"]["commit"] + ":candidate"], cwd=path / "experiment/repo")
    (source / "candidate").write_bytes(accepted)
    server.steps, server.calls, server.contracts = {}, 0, False
    result = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "20",
                             "Verify my accepted revision."], cwd=source, env=env, capture_output=True, text=True, timeout=25)
    verdict = json.loads(result.stdout)
    assert verdict["state"] == "VERIFIED" and verdict["task"] == task["id"], verdict
    checks = json.loads(Path(verdict["report"]["receipt"]).read_bytes())["checks"]
    assert any(c["name"] == "accepted Evolution candidate" and c["status"] == "PASS" for c in checks)
    print("Verified native slash command, pinned holdout, explicit promotion, ledger commit and final parent gate.")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as server:
        directory = Path(tmp)
        profile, source = fixture.setup(directory, server.server_port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        exercise(source, profile, directory, server)
