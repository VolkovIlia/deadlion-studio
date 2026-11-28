"""Exercise engineering recovery through real OMP and a loopback scripted provider."""
from hashlib import sha256
from http.server import HTTPServer
import json
import queue
import shutil
import time
from pathlib import Path
import subprocess
import tempfile
import threading

from omp_engineering_smoke import PLUGIN, Transport, trial
from omp_refactoring_smoke import prepare
from omp_stability_smoke import environment, write


def checks_for(path, length):
    return {"name": f"{path} {length}", "type": "functional", "scope": [path], "argv": [
        "python3", "-c", f"from pathlib import Path; assert len(Path({path!r}).read_text().strip()) >= {length}",
    ]}


def productive(root, server):
    source, env = environment(root, server)
    policy = root / "policy.json"
    policy.write_text(json.dumps({"checks": [checks_for("candidate", length) for length in (1, 2, 3)]}))
    options = {**env, "DL_ENGINEERING_POLICY": str(policy)}
    steps = {i: write("candidate", text + "\n") for i, text in [(0, ""), (2, "a"), (4, "ab"), (6, "abc")]}
    report = trial(source, options, server, steps, "VERIFIED", 8)
    task_path = root / "state/deadlion" / report["task"] / "task.json"
    task = json.loads(task_path.read_bytes())
    assert task["deadline"] is None and task["analysisMs"] is None and task["maxCorrections"] is None
    assert task["corrections"] == 3 and sum(r["progress"] for r in task["recovery"]["recent"]) == 2
    assert (source / "candidate").read_text() == "abc\n"

    policy.write_text(json.dumps({"checks": [checks_for("candidate", 10)]}))
    report = trial(source, options, server, {0: write("candidate", "a"), 2: write("candidate", "b"),
                                            4: write("candidate", "a")}, "BLOCKED", None)
    task = json.loads((root / "state/deadlion" / report["task"] / "task.json").read_bytes())
    assert task["recovery"]["recent"][-1]["cycle"], task["recovery"]

    check = checks_for("candidate", 4)
    check["argv"][2] = ("from pathlib import Path; import time; text = Path('candidate').read_text(); "
                        "time.sleep(3 if text != 'correct' else 0); assert text == 'correct'")
    policy.write_text(json.dumps({"operationSeconds": 1, "checks": [check]}))
    trial(source, options, server, {0: write("candidate", "bad"), 2: write("candidate", "correct")}, "VERIFIED", 4)
    assert "VERIFY_WITH_TOOL" in "".join(server.context)


def stage(identifier, scope, title, depends, check):
    return f"""### {identifier}: {title}
Files: {scope}
Change: {title}
Test: Verify {scope}.
Verify: Run the approved check.
Required: plan: {check}
Depends: {depends}
"""


def campaign(root, server, replan=False, dirty=False):
    installed = installed_copy(root) if replan else PLUGIN
    source, env, session = prepare(root, server, installed)

    def command(message):
        result = subprocess.run(["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p", message],
                                cwd=source, env=env, capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stderr[-1400:]
        return result.stdout

    def run(steps, expected):
        server.steps, server.context, server.calls = steps, [], 0
        result = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "28",
                                 "Continue the approved engineering mission."],
                                cwd=source, env=env, text=True, capture_output=True, timeout=35)
        verdict = json.loads(result.stdout)
        assert verdict["state"] == expected, (verdict, server.context[-2:], result.stderr[-1000:])
        return verdict

    head = "# Recovery\nGoal: Preserve the answer across independent changes\nStatus: approved\n\n"
    unavailable = {"name": "external suite", "type": "functional", "scope": ["broken.txt"],
                   "argv": ["missing-slopzero-fixture"]}
    good = checks_for("good.txt", 1)
    configuration = {"checks": [unavailable, good], "protectedPaths": ["storage-contract.json"]}
    first = stage("T1", "broken.txt", "Verify the blocked component", "—", unavailable["name"])
    second = stage("T2", "good.txt", "Improve the independent component", "—", good["name"])
    waiting = stage("T3", "later.txt", "Integrate dependencies", "T1, T2", good["name"])
    text = head + first + "\n" + second + "\n" + waiting
    if replan:
        first = stage("T1", "parts", "Integrate scalable computation", "—", "parts")
        text = head + first
        configuration["checks"] = [{"name": "parts", "scope": ["parts"], "type": "functional",
                                    "argv": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"]}]
    Path(env["DL_ENGINEERING_POLICY"]).write_text(json.dumps(configuration))
    (source / "plan.md").write_text(text)
    (source / "operator-notes.txt").write_text("uncommitted user changes\n")
    command("/deadlion refactor start plan.md")
    directory, = (p for p in (root / "state/deadlion/refactoring").iterdir() if p.is_dir())
    baseline = (directory / "global.json").read_bytes()
    initial = json.loads((directory / "plan-state.json").read_bytes())
    command("/deadlion refactor run")

    if replan:
        prerequisite = stage("T4", "parts/kernel.txt", "Measure the isolated kernel", "—", "parts")
        proposal = text.replace("Depends: —", "Depends: T4") + "\n" + prerequisite
        steps = {1: ("deadlion_verify", {"action": "replan", "plan": proposal, "reason": "Isolate the kernel first"}),
                 2: write("parts/kernel.txt", "bounded kernel\n"),
                 4: write("parts/wrapper.txt", "preserves behavior\n")}
        verdict = run(steps, "VERIFIED")
        current = json.loads((directory / "plan-state.json").read_bytes())
        assert current["status"] == "COMPLETED" and set(current["results"]) == {"T1", "T4"}, current
        assert current["revision"] == 2 and (directory / "final-receipt.json").is_file()
        assert verdict["report"]["status"] == "PASS"
        check_campaign_upgrade(command, installed, directory)
    elif dirty:
        verdict = run({0: write("broken.txt", "unverified candidate\n")}, "BLOCKED")
        current = json.loads((directory / "plan-state.json").read_bytes())
        assert current["results"] == {} and (directory / "active.json").is_file()
        assert "Unverified milestone edits remain" in verdict["reason"]
        assert (source / "broken.txt").read_text() == "unverified candidate\n"
    else:
        sent = False

        def steps(_step, request):
            nonlocal sent
            if not sent and "Same mission" in json.dumps(request["messages"]):
                sent = True
                return write("good.txt", "good independent result\n")

        run(steps, "BLOCKED")
        current = json.loads((directory / "plan-state.json").read_bytes())
        assert current["status"] == "ACTIVE" and set(current["results"]) == {"T2"}, current
        assert current["milestones"]["T1"] == "DEFERRED" and "T3" not in current["results"]
        assert not (directory / "final-receipt.json").exists()
    assert initial["id"] == current["id"] and initial["baseline"] == current["baseline"]
    assert (directory / "global.json").read_bytes() == baseline
    assert (source / "operator-notes.txt").read_text() == "uncommitted user changes\n"


def budget_resume(root, server):
    source, env, session = prepare(root, server)
    policy = Path(env["DL_ENGINEERING_POLICY"])
    policy.write_text(json.dumps({"seconds": 1, "checks": [checks_for("candidate", 4)]}))
    launch = [PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "22"]
    server.steps, server.context, server.calls = {0: ("bash", {"command": "sleep 4"})}, [], 0
    process = subprocess.run([*launch, "Implement the requested edit."], cwd=source, env=env,
                             text=True, capture_output=True, timeout=27)
    paused = json.loads(process.stdout)
    assert paused["state"] in {"INCOMPLETE", "CANCELLED"} and paused.get("task"), paused
    path = root / "state/deadlion" / paused["task"] / "task.json"
    original = json.loads(path.read_bytes())
    command = ["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p"]
    subprocess.run([*command, "/deadlion budget seconds 15"], cwd=source, env=env,
                   capture_output=True, check=True, timeout=15)
    refreshed = json.loads(path.read_bytes())
    assert refreshed["deadline"] > original["deadline"] and refreshed["budgetChanges"]
    server.steps, server.context, server.calls = {0: write("candidate", "good recovery\n")}, [], 0
    process = subprocess.run([*launch, "Continue the same engineering task."], cwd=source, env=env,
                             text=True, capture_output=True, timeout=27)
    verdict = json.loads(process.stdout)
    assert verdict["state"] == "VERIFIED" and verdict["task"] == paused["task"], verdict
    final = json.loads(path.read_bytes())
    assert final["baselineHash"] == original["baselineHash"] and final["goal"] == original["goal"]


def installed_copy(root):
    return shutil.copytree(PLUGIN, root / "installed-plugin", ignore=shutil.ignore_patterns("__pycache__"))


def update_installation(plugin):
    adapter = plugin / "omp/commands.mjs"
    adapter.write_text(adapter.read_text() + "\n// Test verifier installation change\n")


def check_campaign_upgrade(command, installed, directory):
    comparison = directory / "comparison.json"
    update_installation(installed)
    command("/deadlion refactor report")
    stale = json.loads(comparison.read_bytes())
    assert stale["status"] == "NOT VERIFIED" and "predates the loaded verifier" in stale["staleInputs"], stale
    command("/deadlion refactor verify")
    refreshed = json.loads(comparison.read_bytes())
    assert refreshed["status"] == "VERIFIED" and refreshed["finalReceipt"] != stale["finalReceipt"], refreshed


def native_goal(root, server, approval_pending=False, verifier_changed=False):
    plugin = installed_copy(root) if verifier_changed else PLUGIN
    source, env = environment(root, server, plugin)
    profile = Path(env["PI_CODING_AGENT_DIR"]) / "config.yml"
    with profile.open("a") as stream:
        stream.write("goal:\n  enabled: true\n  continuationModes: [rpc]\n")
    policy = root / "policy.json"
    policy.write_text(json.dumps({} if approval_pending else {"checks": [checks_for("candidate", 4)]}))
    verdict = root / "verdict.json"
    options = {**env, "DL_ENGINEERING_POLICY": str(policy), "DL_VERDICT_FILE": str(verdict)}
    server.contracts = False
    server.steps, server.context, server.calls = {0: write("candidate", "bad")}, [], 0
    if verifier_changed:
        def update(_index, _request):
            if not server.calls:
                update_installation(plugin)
                return write("candidate", "bad")
        server.steps = update
    pending = "AWAITING_RESTART" if verifier_changed else "AWAITING_APPROVAL" if approval_pending else None
    process = subprocess.Popen(["omp", "--mode", "rpc", "--offline", "--no-judge", "--no-spotlight"],
                               cwd=source, env=options, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    messages = queue.Queue()

    def receive():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue

    def send(**fields):
        process.stdin.write(json.dumps(fields) + "\n")
        process.stdin.flush()

    def until(predicate):
        deadline = time.monotonic() + 16
        while time.monotonic() < deadline:
            event = messages.get(timeout=max(.01, deadline - time.monotonic()))
            if predicate(event):
                return event
        raise AssertionError("No matching OMP event")

    threading.Thread(target=receive, daemon=True).start()
    try:
        until(lambda event: event.get("type") == "ready")
        send(type="goal", op="create", id="create", objective="Implement the candidate and prove its required behavior.")
        first = until(lambda event: event.get("id") == "create" and event.get("type") == "response")
        assert first["success"]
        until(lambda event: event.get("type") == "session_settled" and verdict.exists())
        failed = json.loads(verdict.read_bytes())
        assert failed["state"] == (pending or "BLOCKED"), failed
        if pending:
            stored = root / "state/deadlion" / failed["task"] / "task.json"
            assert json.loads(stored.read_bytes())["corrections"] == 0, failed
        send(type="goal", op="get", id="goal")
        goal = until(lambda event: event.get("id") == "goal" and event.get("type") == "response")["data"]["goal"]
        assert goal["status"] == "active" and goal["id"] == first["data"]["goal"]["id"]
        task = write("notes.md", "# Independent work\n") if pending else write("candidate", "correct")
        server.steps = {server.calls: task}
        send(type="prompt", id="continue", message="Continue the existing OMP goal.")
        until(lambda event: event.get("type") == "session_settled")
        finished = json.loads(verdict.read_bytes())
        assert finished["state"] == (pending or "VERIFIED"), finished
        assert finished["task"] == failed["task"]
        if pending:
            assert (source / "notes.md").is_file() and finished["report"]["status"] == "NOT VERIFIED"
            send(type="goal", op="get", id="still-active")
            live = until(lambda event: event.get("id") == "still-active" and event.get("type") == "response")
            assert live["data"]["goal"]["status"] == "active"
            assert live["data"]["goal"]["id"] == goal["id"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def verifier_upgrade(root, server):
    installed = installed_copy(root)
    source, env, session = prepare(root, server, installed)
    approval = Path(env["DL_ENGINEERING_POLICY"])
    oracle = root / "oracle.txt"
    oracle.write_text("correct")
    check = checks_for("candidate", 1)
    check["argv"][2] = f"from pathlib import Path; assert Path('candidate').read_text() == Path({str(oracle)!r}).read_text()"
    check["argv"].append(str(oracle))
    approval.write_text(json.dumps({"checks": [check]}))
    verdict = root / "verdict.json"
    options = {**env, "DL_VERDICT_FILE": str(verdict)}
    command = ["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p"]

    def steps(index, _request):
        if index == 0:
            return write("candidate", "correct")
        if index == 1:
            return "deadlion_verify", {}
        if index == 2:
            update_installation(installed)

    def run(actions, state, calls):
        server.steps, server.context, server.calls = actions, [], 0
        result = subprocess.run([*command, "Implement the candidate."], cwd=source, env=options,
                                text=True, capture_output=True, timeout=24)
        report = json.loads(verdict.read_bytes())
        assert result.returncode == 0 and report["state"] == state and server.calls == calls, (report, result.stderr, server.calls)
        return report

    stale = run(steps, "AWAITING_RESTART", 3)
    assert stale["report"]["failures"][0]["restartRequired"]
    path = root / "state/deadlion" / stale["task"]
    original = json.loads((path / "task.json").read_bytes())
    baseline = (path / "baseline.json").read_bytes()
    valid = run({}, "VERIFIED", 1)
    evidence = json.loads(Path(valid["report"]["receipt"]).read_bytes())
    assert valid["task"] == stale["task"] and evidence["paths"] == ["candidate"]
    assert evidence["baselineHash"] == original["baselineHash"] and (path / "baseline.json").read_bytes() == baseline
    assert evidence["integration"]["baseline"] == original["tools"]["integration"] != evidence["integration"]["verified"]
    assert any(check["name"] == "plan: candidate 1" and check["status"] == "PASS" for check in evidence["checks"])
    assert stale["report"]["receipt"] != valid["report"]["receipt"]

    oracle.write_text("changed")
    result = subprocess.run([*command, "/deadlion verify"], cwd=source, env=options,
                            text=True, capture_output=True, check=True, timeout=20)
    last = max(path.glob("gate-*.json"), key=lambda file: file.stat().st_mtime_ns)
    evidence = json.loads(last.read_bytes())
    assert evidence["status"] == "NOT VERIFIED" and "verification inputs" in evidence["checks"][0]["reason"], result


def scope_approval(root, server):
    source, env, session = prepare(root, server)
    Path(env["DL_ENGINEERING_POLICY"]).write_text("{}")
    test = source / "tests/test_candidate.py"
    test.parent.mkdir()
    test.write_text("from pathlib import Path\nassert Path('candidate').read_text() == 'correct'\n")
    launch = [PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "24"]
    command = ["omp", "--offline", "--no-judge", "--no-spotlight", "--resume", session, "-p"]

    def run(steps, state, requests):
        server.steps, server.context, server.calls = steps, [], 0
        result = subprocess.run([*launch, "Implement the scoped engineering task."], cwd=source, env=env,
                                text=True, capture_output=True, timeout=29)
        verdict = json.loads(result.stdout)
        assert verdict["state"] == state and server.calls == requests, (verdict, server.calls, result.stderr)
        return verdict

    def approve(approval, digest=None):
        policy = root / "reviewed-checks.json"
        policy.write_text(json.dumps(approval))
        token = digest or sha256(policy.read_bytes()).hexdigest()
        subprocess.run([*command, f"/deadlion approve-tests {token} {policy}"], cwd=source, env=env,
                       capture_output=True, check=True, timeout=15)

    run_shell = ("bash", {"command": "printf correct > candidate; printf '\n# Reviewed test revision\n' >> tests/test_candidate.py; python3 tests/test_candidate.py"})
    waiting = run({0: run_shell}, "AWAITING_APPROVAL", 2)
    assert waiting["report"]["status"] == "NOT VERIFIED"
    assert waiting["report"]["failures"][0]["approval"]["kind"] == "functional-scope"
    path = root / "state/deadlion" / waiting["task"] / "task.json"
    original = json.loads(path.read_bytes())

    continued = run({0: write("notes.md", "# Independent work\n")}, "AWAITING_APPROVAL", 2)
    assert continued["task"] == waiting["task"] and (source / "notes.md").is_file()
    check = {"name": "reviewed candidate suite", "type": "functional", "scope": ["candidate", "tests"],
             "argv": ["python3", "-c", "import runpy; runpy.run_path('tests/test_candidate.py')"]}
    approve({"checks": [check]}, digest="0" * 64)
    assert not json.loads(path.read_bytes()).get("testApprovals")
    approve({"checks": [check]})
    pending = run({}, "AWAITING_APPROVAL", 1)
    assert pending["report"]["failures"][0]["approval"]["kind"] == "test-revision"

    revision = {"testRevision": {"tests/test_candidate.py": sha256(test.read_bytes()).hexdigest()}}
    approve(revision)
    final = run({}, "VERIFIED", 1)
    assert final["task"] == waiting["task"]
    saved = json.loads(path.read_bytes())
    assert saved["baselineHash"] == original["baselineHash"] and saved["goal"] == original["goal"]
    assert len(saved["testApprovals"]) == 2
    test.write_text(test.read_text() + "# Subsequent unreviewed edit\n")
    command_result = subprocess.run([*command, "/deadlion verify"], cwd=source, env=env,
                                    text=True, capture_output=True, check=True, timeout=20)
    gate_files = sorted(path.parent.glob("gate-*.json"), key=lambda file: file.stat().st_mtime_ns)
    latest = json.loads(gate_files[-1].read_bytes())
    assert any(row.get("approval", {}).get("kind") == "test-revision" for row in latest["checks"]), command_result
    assert latest["status"] != "PASS"


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        for name, run in (("productive", productive), ("deferral", campaign),
                          ("replan", lambda root, server: campaign(root, server, True)),
                          ("dirty-checkpoint", lambda root, server: campaign(root, server, dirty=True)),
                          ("budget", budget_resume), ("native-goal", native_goal), ("scope-approval", scope_approval),
                          ("native-goal-awaiting-approval", lambda root, server: native_goal(root, server, True)),
                          ("native-goal-verifier-upgrade", lambda root, server: native_goal(root, server, verifier_changed=True)),
                          ("verifier-upgrade", verifier_upgrade)):
            with tempfile.TemporaryDirectory(prefix="slopzero-") as temporary:
                run(Path(temporary), transport)
                print("PASSED", name)
