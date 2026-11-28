"""Exercise engineering recovery through real OMP and a loopback scripted provider."""
from http.server import HTTPServer
import json
import queue
import shutil
import time
from pathlib import Path
import subprocess
import tempfile
import threading

from omp_engineering_smoke import PLUGIN, Transport, fixture, trial
from omp_receipt_smoke import transfer
from omp_refactoring_smoke import prepare
from omp_stability_smoke import environment, write


def checks_for(path, length):
    return {"name": f"{path} {length}", "type": "functional", "scope": [path], "argv": [
        "python3", "-c", f"from pathlib import Path; assert len(Path({path!r}).read_text().strip()) >= {length}",
    ]}


def lsp_recovery(root, server, edit_after_diagnostics=False):
    source, env = environment(root, server)
    file = "module.py"
    (source / "pyrightconfig.json").write_text('{"typeCheckingMode":"basic"}')
    (source / ".omp").mkdir()
    (source / ".omp/lsp.json").write_text(json.dumps({"servers": {
        name: {"disabled": True} for name in ("basedpyright", "pylsp", "ruff", "ty")
    }}))
    policy = root / "policy.json"
    policy.write_text(json.dumps({"checks": [checks_for(file, 1)]}))
    env["DL_ENGINEERING_POLICY"] = str(policy)
    inspect = ("lsp", {"action": "diagnostics", "file": file})
    steps = {0: write(file, 'value: int = "wrong"\n'), 1: inspect,
             4: write(file, "value: int = 2\n"), 5: inspect, 6: ("deadlion_verify", {})}
    if edit_after_diagnostics:
        steps[7] = ("bash", {"command": 'printf \'value: int = "wrong again"\\n\' > module.py'})
    expected = "INCOMPLETE" if edit_after_diagnostics else "VERIFIED"
    report = trial(source, env, server, steps, expected, None)
    assert "reportAssignmentType" in server.context[2], server.context[2][-2500:]
    assert "DECOMPOSE" in server.context[4], server.context[4][-2500:]
    tool = next(msg for msg in reversed(json.loads(server.context[7])) if msg["role"] == "tool")
    assert json.loads(tool["content"])["status"] == "PASS", tool
    check, = [item for item in report["checks"] if item["name"] == "lsp " + file]
    assert check["status"] == ("NOT VERIFIED" if edit_after_diagnostics else "PASS"), check


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
                                            4: write("candidate", "a")}, "INCOMPLETE", None)
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
        verdict = run({0: write("broken.txt", "unverified candidate\n")}, "INCOMPLETE")
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

        run(steps, "INCOMPLETE")
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
    pending = "AWAITING_RESTART" if verifier_changed else "INCOMPLETE" if approval_pending else None
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
        assert failed["state"] == (pending or "INCOMPLETE"), failed
        if verifier_changed:
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


def import_recovery(root, server):
    source, env = environment(root, server)
    test = "tests/test_module_discovery_imports.py"
    ratchet = "tests/assertionless-tests-baseline.json"
    common = 'import importlib\nimport pytest\n\nMODULE_NAMES = ["json"] * 1376\n\ndef test_discovery():\n    assert MODULE_NAMES\n\n'
    old = common + '@pytest.mark.parametrize("name", MODULE_NAMES)\ndef test_a_module_imports(name):\n    importlib.import_module(name)\n'
    grouped = "import traceback\n" + common + '''@pytest.mark.parametrize("names", [MODULE_NAMES[i:i+30] for i in range(0, len(MODULE_NAMES), 30)])
def test_a_module_imports(names):
    failures = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception:
            failures.append(traceback.format_exc())
    if failures:
        pytest.fail("\\n".join(failures))
'''
    (source / "tests").mkdir()
    (source / test).write_text(old)
    (source / ratchet).write_text(json.dumps([test + "::test_a_module_imports", "tests/other.py::test_assertionless"]))
    fixture.git(source, "add", "tests")
    fixture.git(source, "-c", "user.name=Smoke", "-c", "user.email=test@fixture", "commit", "-qm", "original import tests")
    prepare_check = ("deadlion_verify", {"action": "characterize_imports", "path": test, "ratchet": ratchet})
    original = {}

    def steps(index, _request):
        if index in (4, 7, 12):
            file, = (root / "state/deadlion").glob("*/task.json")
            state = json.loads(file.read_bytes())
            if index == 4:
                original.update(task=state["id"], baseline=state["baselineHash"])
            return "bash", {"command": state["importCheck"]["command"]}
        return {
            0: write(test, grouped.replace('pytest.fail("\\n".join(failures))', "return")),
            1: write(ratchet, '["tests/other.py::test_assertionless"]'),
            3: prepare_check,
            5: write(test, grouped),
            6: prepare_check,
            8: ("deadlion_verify", {}),
            9: write(test, grouped + "\n# Checkout changed after the first receipt.\n"),
            10: ("deadlion_verify", {}),
            11: prepare_check,
            13: ("deadlion_verify", {}),
        }.get(index)

    report = trial(source, env, server, steps, "VERIFIED", None, "Group the import test and preserve its behavior.")
    assert report["task"] == original["task"] and report["baselineHash"] == original["baseline"], report
    assert "Group body does not match" in server.context[5] and "Establish scoped functional evidence" in server.context[3]
    assert "Establish scoped functional evidence" in json.loads(server.context[11])[-1]["content"]
    check, = [item for item in report["checks"] if item["name"] == "independent import characterization"]
    assert set(check["coverage"]["paths"]) == {test, ratchet}
    assert check["data"]["metrics"] == {"imports": 1376, "groups": 46, "injectedFailures": 2, "passed": 47}


def agent_campaign(root, server):
    source, env = environment(root, server)
    checks = [checks_for(path, 1) for path in ("api.txt", "storage.txt")]
    policy = root / "policy.json"
    policy.write_text(json.dumps({"checks": checks}))
    env["DL_ENGINEERING_POLICY"] = str(policy)
    plan = "# Campaign\nStatus: active\n\n"
    plan += stage("T1", "api.txt", "Implement API", "—", checks[0]["name"])
    plan += "\n" + stage("T2", "storage.txt", "Implement storage", "T1", checks[1]["name"])
    steps = {0: write("plan.md", plan), 1: ("deadlion_verify", {"action": "campaign", "path": "plan.md"}),
             2: write("api.txt", "api\n"), 3: ("deadlion_verify", {}),
             4: write("storage.txt", "storage\n"), 5: ("deadlion_verify", {})}
    goal = "Implement API and storage within the supplied constraints."
    report = trial(source, env, server, steps, "VERIFIED", None, goal)
    directory, = (entry for entry in (root / "state/deadlion/refactoring").iterdir() if entry.is_dir())
    state = json.loads((directory / "plan-state.json").read_bytes())
    initial = json.loads((directory / "global.json").read_bytes())
    assert state["status"] == "COMPLETED" and set(state["results"]) == {"T1", "T2"}
    assert state["goal"] == goal and "plan.md" not in initial["baseline"]["files"]
    assert report["baselineHash"] == state["baseline"] == initial["source"]


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        for name, run in (("productive", productive), ("deferral", campaign),
                          ("replan", lambda root, server: campaign(root, server, True)),
                          ("dirty-checkpoint", lambda root, server: campaign(root, server, dirty=True)),
                          ("budget", budget_resume), ("native-goal", native_goal), ("import-recovery", import_recovery),
                          ("native-goal-scope-gap", lambda root, server: native_goal(root, server, True)),
                          ("native-goal-verifier-upgrade", lambda root, server: native_goal(root, server, verifier_changed=True)),
                          ("verifier-upgrade", verifier_upgrade), ("agent-campaign", agent_campaign)):
            with tempfile.TemporaryDirectory(prefix="slopzero-") as temporary:
                run(Path(temporary), transport)
                print("PASSED", name)
        for case in ("automatic", "explicit", "stale-input", "stale-source", "unrelated", "local-failure"):
            with tempfile.TemporaryDirectory(prefix="deadlion-receipt-") as temporary:
                transfer(Path(temporary), transport, case)
                print("PASSED receipt", case)
        for edit_after_diagnostics in (False, True):
            with tempfile.TemporaryDirectory(prefix="deadlion-lsp-recovery-") as temporary:
                lsp_recovery(Path(temporary), transport, edit_after_diagnostics)
                print("PASSED LSP recovery", "stale snapshot" if edit_after_diagnostics else "fresh diagnostics")
