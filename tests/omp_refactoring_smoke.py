"""Exercise an approved refactoring DAG across independent OMP RPC processes."""
from http.server import HTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

from omp_engineering_smoke import fixture, neighbour, PLUGIN, Transport, trial


PLAN = """# Refactor
Status: approved

## Tasks

### T1: Reduce legacy source
Files: legacy.py
Project: —
Change: Reduce lines and preserve behavior.
Test: Existing externally approved functional suite.
Verify: python3 check
Checks: functional tests
Depends: —
- [ ] done

### T2: Preserve the API
Files: api.py
Project: —
Change: Expose the existing answer.
Test: Existing externally approved functional suite.
Verify: python3 check
Checks: functional tests
Depends: T1
- [ ] done
"""


def prepare(root, server):
    profile, source = fixture.setup(root, server.server_port)
    trace = root / "events.jsonl"
    neighbour(profile, trace)
    (profile / "config.yml").write_text((profile / "config.yml").read_text() + "startup:\n  setupWizard: false\n")
    policy = root / "policy.json"
    policy.write_text(json.dumps({
        "tests": ["python3", "-c", "from pathlib import Path; assert 'answer = 42' in Path('legacy.py').read_text()"],
        "testsScope": ["legacy.py", "api.py"], "maxCorrections": 0,
    }))
    env = {**os.environ, "HOME": str(root), "PI_CONFIG_DIR": str(root / ".omp"),
           "PI_CODING_AGENT_DIR": str(profile), "XDG_STATE_HOME": str(root / "state"),
           "DL_ENGINEERING_POLICY": str(policy), "DL_MAX_FILE": "4",
           "DL_TEST_TRACE": str(trace), "FIXTURE_API_KEY": "unused"}
    (source / "legacy.py").write_text("answer = 42\n" + "# legacy\n" * 10)
    (source / "plan.md").write_text(PLAN)
    subprocess.run(["omp", "plugin", "link", PLUGIN], cwd=source, env=env, check=True, capture_output=True)
    trial(source, env, server, {}, "VERIFIED", 1, prompt="Summarize the project.")
    session = next(json.loads(row)[3] for row in trace.read_text().splitlines()
                   if json.loads(row)[0] == "before_agent_start")

    return source, env, session


def exercise(root, server):
    source, env, session = prepare(root, server)

    def command(message):
        result = subprocess.run(["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p", message],
                                cwd=source, env=env, capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stderr[-1200:]
        return result.stdout

    def edit(path, content):
        server.steps = {0: ("write", {"path": path, "content": content})}
        server.context = []
        server.calls = 0
        result = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "20",
                                 "Implement the selected refactoring stage."], cwd=source, env=env, capture_output=True,
                                text=True, timeout=25)
        return json.loads(result.stdout)

    command("/deadlion refactor start plan.md")
    directory, = (root / "state/deadlion/refactoring").iterdir()
    baseline = (directory / "global.json").read_bytes()
    command("/deadlion refactor begin T1")
    first = edit("legacy.py", "answer = 42\n" + "# legacy\n" * 5)
    assert first["state"] == "VERIFIED", first
    fixture.git(source, "add", "legacy.py")
    fixture.git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "operator accepts the first milestone")
    command("/deadlion refactor reconcile")
    command("/deadlion refactor begin T2")
    second = edit("api.py", "from legacy import answer\n")
    assert second["state"] == "VERIFIED" and second["task"] != first["task"], second
    assert (directory / "global.json").read_bytes() == baseline
    command("/deadlion refactor verify")
    report = json.loads((directory / "comparison.json").read_bytes())
    assert report["status"] == "VERIFIED" and set(report["milestones"]) == {"T1", "T2"}, report
    assert report["finalReceipt"]
    (source / "api.py").write_text("answer = 0\n")
    command("/deadlion refactor report")
    assert json.loads((directory / "comparison.json").read_bytes())["status"] == "NOT VERIFIED"
    print("VERIFIED two milestones, original baseline, ratchet and final integration gate")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        exercise(Path(tmp), transport)
