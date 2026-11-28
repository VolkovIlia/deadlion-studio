"""Bridge two real OMP tasks using functional evidence from a pinned check."""
from http.server import HTTPServer
import json
from pathlib import Path
import subprocess
import threading

from omp_engineering_smoke import PLUGIN, Transport, fixture, trial
from omp_stability_smoke import environment, write


def fixture_checkout(root, server):
    source, env = environment(root, server)
    paths = ["tests/test_scoped.py", "tests/test_other.py"]
    (source / "tests").mkdir()
    for path in paths:
        (source / path).write_text("def test_existing(): assert 1 == 1\n")
    (source / ".git/info/exclude").write_text("__pycache__/\n.pytest_cache/\n")
    fixture.git(source, "add", "tests")
    fixture.git(source, "-c", "user.name=Smoke", "-c", "user.email=test@fixture", "commit", "-qm", "baseline tests")
    return source, env, paths


def run_donor(root, parent_env, source, scope):
    directory = root / "donor"
    directory.mkdir()
    with HTTPServer(("127.0.0.1", 0), Transport) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _, env = environment(directory, server, plugin=PLUGIN)
        policy = directory / "verification.json"
        policy.write_text(json.dumps({"checks": [{"name": "scoped pytest", "type": "functional", "scope": [scope],
            "argv": ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", scope], "requireTestCount": True}]}))
        env.update(XDG_STATE_HOME=parent_env["XDG_STATE_HOME"], DL_ENGINEERING_POLICY=str(policy))
        server.steps, server.context, server.calls, server.contracts = {0: ("deadlion_verify", {})}, [], 0, False
        result = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--seconds", "24", "Verify the changed tests."],
                                cwd=source, env=env, text=True, capture_output=True, check=True, timeout=30)
        return json.loads(result.stdout), policy


def transfer(root, server, case="automatic"):
    source, env, paths = fixture_checkout(root, server)
    donor = {}
    if case == "local-failure":
        policy = root / "local-policy.json"
        policy.write_text(json.dumps({"checks": [{"name": "local invariant", "type": "functional", "scope": paths[:1],
            "argv": ["python3", "-c", "raise SystemExit(1)"]}]}))
        env["DL_ENGINEERING_POLICY"] = str(policy)

    def steps(index, _request):
        if index == 0:
            return write(paths[0], "def test_existing(): assert 2 > 1\n")
        if index != 1:
            return None
        report, policy = run_donor(root, env, source, paths[case == "unrelated"])
        donor.update(report=report)
        if case == "stale-input":
            policy.write_text(policy.read_text() + "\n")
        if case == "stale-source":
            return write(paths[0], "def test_existing(): assert 3 > 1\n")
        if case in {"explicit", "stale-input"}:
            marker = Path(env["XDG_STATE_HOME"]) / "deadlion/functional-receipts" / (report["report"]["source"] + ".json")
            marker.unlink(missing_ok=True)
            return "deadlion_verify", {"action": "import_receipt", "receipt": report["report"]["receipt"]}

    expected = "VERIFIED" if case in {"automatic", "explicit"} else "INCOMPLETE"
    receipt = trial(source, env, server, steps, expected, None)
    prior = donor["report"]
    assert prior["state"] == "VERIFIED" and receipt["task"] != prior["task"]
    links = [check for check in receipt["checks"] if check.get("borrowed")]
    if case == "local-failure":
        assert receipt["policy"]["checks"][0]["name"] == "local invariant"
        assert any(check["name"] == "plan: local invariant" and check["status"] == "FAIL" for check in receipt["checks"])
    else:
        assert receipt["policy"] == {}
    if expected == "VERIFIED" or case == "local-failure":
        check, = links
        assert check["borrowed"]["receipt"] == prior["report"]["receipt"]
        assert check["borrowed"]["receiptHash"] == prior["report"]["receiptHash"]
        assert receipt["source"] == prior["report"]["source"]
        assert check["coverage"]["paths"] == [paths[0]]
    else:
        assert not links and receipt["coverage"][0]["status"] == "NOT VERIFIED"
        if case == "stale-input":
            assert any("operator policy changed" in check.get("reason", "") for check in receipt["checks"])
