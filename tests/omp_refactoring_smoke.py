"""Exercise an approved refactoring DAG across independent OMP RPC processes."""
from http.server import HTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

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
Required: functional tests, structural ratchet, trusted profile, protected verification inputs
Depends: —
- [ ] done

### T2: Preserve the API
Files: api.py, storage.py
Project: —
Change: Expose the existing answer.
Test: Existing externally approved functional suite.
Verify: python3 check
Required: functional tests
Depends: T1
Owners: implementer=api.py, task=storage.py
- [ ] done
"""


def prepare(root, server, plugin=PLUGIN):
    profile, source = fixture.setup(root, server.server_port)
    trace = root / "events.jsonl"
    neighbour(profile, trace)
    (profile / "config.yml").write_text((profile / "config.yml").read_text() + "startup:\n  setupWizard: false\ntask:\n  batch: true\n")
    policy = root / "policy.json"
    policy.write_text(json.dumps({
        "tests": ["python3", "-B", "-c", "import runpy; from pathlib import Path; "
                  "assert runpy.run_path('legacy.py')['answer'] == 42; "
                  "assert not Path('api.py').exists() or __import__('api').answer == 42; "
                  "assert not Path('storage.py').exists() or __import__('storage').read() == 42"],
        "testsScope": ["legacy.py", "api.py", "storage.py"], "maxCorrections": 0,
        "protectedPaths": ["storage-contract.json"],
        "profile": {"metric": "resources", "argv": ["python3", "-B", "-c", "import runpy; runpy.run_path('legacy.py')"],
                    "max": {"peak_rss_kib": 524288}},
    }))
    env = {**os.environ, "HOME": str(root), "PI_CONFIG_DIR": str(root / ".omp"),
           "PI_CODING_AGENT_DIR": str(profile), "XDG_STATE_HOME": str(root / "state"),
           "DL_ENGINEERING_POLICY": str(policy), "DL_MAX_FILE": "4",
           "DL_TEST_TRACE": str(trace), "FIXTURE_API_KEY": "unused"}
    (source / "legacy.py").write_text("answer = 42\n" + "# legacy\n" * 10)
    (source / "storage-contract.json").write_text('{"answer":42}\n')
    (source / "plan.md").write_text(PLAN)
    subprocess.run(["omp", "plugin", "link", plugin], cwd=source, env=env, check=True, capture_output=True)
    trial(source, env, server, {}, "VERIFIED", 1, prompt="Summarize the project.")
    session = next(json.loads(row)[3] for row in trace.read_text().splitlines()
                   if json.loads(row)[0] == "before_agent_start")

    return source, env, session


def interrupt(source, env, session, directory, server):
    answering = threading.Event()
    def wait_for_kill(_step, _request):
        answering.wait(15)
    server.steps, server.context, server.calls = wait_for_kill, [], 0
    with subprocess.Popen(["omp", "--mode", "rpc", "--offline", "--no-judge", "--no-spotlight", "--resume", session],
                          cwd=source, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, text=True) as process:
        try:
            process.stdin.write(json.dumps({"type": "prompt", "id": "interrupt", "message": "Implement the selected stage."}) + "\n")
            process.stdin.flush()
            lock = directory / "active.json"
            for _ in range(240):
                owner = json.loads(lock.read_bytes()).get("owner") if lock.exists() else None
                if owner and owner["pid"] == process.pid:
                    return process.pid
                time.sleep(0.05)
            raise AssertionError("OMP never acquired the milestone lease")
        finally:
            process.kill()
            process.wait(timeout=5)
            answering.set()


def exercise(root, server):
    source, env, session = prepare(root, server)

    def command(message):
        result = subprocess.run(["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p", message],
                                cwd=source, env=env, capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stderr[-1200:]
        return result.stdout

    def edit(path, content, delegate=False):
        write = "write", {"path": path, "content": content}
        if delegate:
            assignments = {"DL_REFACTOR_API": write, "DL_REFACTOR_STORAGE": ("write", {
                "path": "storage.py", "content": "from legacy import answer\n\ndef read():\n    return answer\n"})}
            def steps(step, request):
                if step == 0:
                    return "task", {"context": "Integrate two disjoint components", "tasks": [
                        {"agent": "implementer", "task": "DL_REFACTOR_API", "solutionSpace": "current directory"},
                        {"agent": "task", "task": "DL_REFACTOR_STORAGE", "solutionSpace": "current directory"}]}
                for message in request["messages"]:
                    body = str(message.get("content"))
                    if message["role"] != "user" or "Complete assignment thoroughly:" not in body:
                        continue
                    for marker in list(assignments):
                        if marker in body:
                            return assignments.pop(marker)
            server.steps = steps
        else:
            server.steps = {0: write}
        server.context = []
        server.calls = 0
        result = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "20",
                                 "Implement the selected refactoring stage."], cwd=source, env=env, capture_output=True,
                                text=True, timeout=25)
        return json.loads(result.stdout)

    command("/deadlion refactor start plan.md")
    directory, = (path for path in (root / "state/deadlion/refactoring").iterdir() if path.is_dir())
    baseline = (directory / "global.json").read_bytes()
    command("/deadlion refactor begin T1")
    first = edit("legacy.py", "answer = 42\n" + "# legacy\n" * 5)
    assert first["state"] == "VERIFIED", first
    fixture.git(source, "add", "legacy.py")
    fixture.git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "operator accepts the first milestone")
    command("/deadlion refactor reconcile")
    command("/deadlion refactor begin T2")
    refused = edit("unassigned.py", "raise RuntimeError('unexpected')\n")
    assert refused["state"] == "BLOCKED" and not (source / "unassigned.py").exists(), refused
    command("/deadlion refactor cancel")
    assert not (directory / "active.json").exists()
    plan = source / "plan.md"
    plan.write_text(PLAN.replace("Expose the existing answer.", "Expose the existing answer from the legacy component."))
    revision = subprocess.check_output(["node", "--input-type=module", "-e",
        "import {readFileSync} from 'node:fs'; const {parsePlan} = await import(process.argv[1]); "
        "const {digest} = await import(process.argv[2]); console.log(digest(JSON.stringify(parsePlan(readFileSync(process.argv[3], 'utf8')))));",
        str(PLUGIN / "omp/refactor.mjs"), str(PLUGIN / "omp/evidence.mjs"), str(plan)], text=True).strip()
    command(f"/deadlion refactor revise {revision} Clarify the API boundary")
    assert (directory / "plans/2.json").is_file()
    command("/deadlion refactor begin T2")
    owner = interrupt(source, env, session, directory, server)
    lock = directory / "active.json"
    assert json.loads(lock.read_bytes())["owner"]["pid"] == owner
    command("/deadlion refactor recover")
    assert json.loads(lock.read_bytes())["status"] == "PAUSED"
    api = "from storage import read\nanswer = read()\n"
    second = edit("api.py", api, delegate=True)
    assert second["state"] == "VERIFIED" and second["task"] != first["task"], second
    assert {"api.py", "storage.py"} <= set(second["report"]["paths"]), second
    assert (directory / "global.json").read_bytes() == baseline
    command("/deadlion refactor verify")
    report = json.loads((directory / "comparison.json").read_bytes())
    assert report["status"] == "VERIFIED" and set(report["milestones"]) == {"T1", "T2"}, report
    assert report["finalReceipt"]
    (source / "api.py").write_text("answer = 0\n")
    command("/deadlion refactor report")
    assert json.loads((directory / "comparison.json").read_bytes())["status"] == "NOT VERIFIED"
    (source / "api.py").write_text(api)
    policy = Path(env["DL_ENGINEERING_POLICY"])
    original = policy.read_bytes()
    policy.write_bytes(original + b"\n")
    command("/deadlion refactor report")
    stale = json.loads((directory / "comparison.json").read_bytes())
    assert stale["status"] == "NOT VERIFIED" and "operator policy changed" in stale["staleInputs"]
    policy.write_bytes(original)
    command("/deadlion refactor report")
    campaign = json.loads((directory / "plan-state.json").read_bytes())["id"]
    command("/deadlion refactor archive")
    archived = directory.parent / "history" / directory.name / campaign
    assert (archived / "global.json").read_bytes() == baseline
    assert (archived / "receipts/final.json").is_file()
    assert (archived / "plans/2.json").is_file()
    command("/deadlion refactor start plan.md")
    assert json.loads((directory / "plan-state.json").read_bytes())["id"] != campaign
    command("/deadlion refactor cancel campaign")
    command("/deadlion refactor archive")
    plan.write_text(PLAN.replace("trusted profile", "plan: memory budget"))
    config = json.loads(original)
    config["checks"] = [{"name": "memory budget", "argv": ["/usr/bin/true"], "type": "resource"}]
    policy.write_text(json.dumps(config))
    command("/deadlion refactor start plan.md")
    command("/deadlion refactor begin T1")
    unresolved = edit("legacy.py", "answer = 42\n# constraint without a verifier\n")
    assert unresolved["state"] == "INCOMPLETE" and "memory budget" in unresolved.get("reason", ""), unresolved
    assert not (directory / "active.json").exists()
    command("/deadlion refactor cancel campaign")
    command("/deadlion refactor archive")
    plan.write_text(PLAN)
    config.pop("checks")
    config["profile"]["max"]["peak_rss_kib"] = 1
    policy.write_text(json.dumps(config))
    command("/deadlion refactor start plan.md")
    assert json.loads((directory / "global.json").read_bytes())["baselineStatus"] == "FAIL"
    command("/deadlion refactor begin T1")
    exceeded = edit("legacy.py", "answer = 42\n")
    assert exceeded["state"] == "BLOCKED", exceeded
    assert any(check["name"] == "trusted profile" and check["status"] == "FAIL"
               for check in exceeded["report"]["failures"]), exceeded
    print("VERIFIED milestones, operator checkpoint, SIGKILL recovery, stale receipts, archive and new campaign")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        exercise(Path(tmp), transport)
