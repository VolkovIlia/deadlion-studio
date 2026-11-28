"""Exercise engineering recovery through real OMP and a loopback scripted provider."""
from http.server import HTTPServer
import json
import queue
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
    source, env, session = prepare(root, server)

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


def native_goal(root, server):
    source, env = environment(root, server)
    profile = Path(env["PI_CODING_AGENT_DIR"]) / "config.yml"
    with profile.open("a") as stream:
        stream.write("goal:\n  enabled: true\n  continuationModes: [rpc]\n")
    policy = root / "policy.json"
    policy.write_text(json.dumps({"checks": [checks_for("candidate", 4)]}))
    verdict = root / "verdict.json"
    options = {**env, "DL_ENGINEERING_POLICY": str(policy), "DL_VERDICT_FILE": str(verdict)}
    server.contracts = False
    server.steps, server.context, server.calls = {0: write("candidate", "bad")}, [], 0
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
        assert failed["state"] == "BLOCKED", failed
        send(type="goal", op="get", id="goal")
        goal = until(lambda event: event.get("id") == "goal" and event.get("type") == "response")["data"]["goal"]
        assert goal["status"] == "active" and goal["id"] == first["data"]["goal"]["id"]
        server.steps = {server.calls: write("candidate", "correct")}
        send(type="prompt", id="continue", message="Continue the existing OMP goal.")
        until(lambda event: event.get("type") == "session_settled")
        finished = json.loads(verdict.read_bytes())
        assert finished["state"] == "VERIFIED" and finished["task"] == failed["task"], finished
    finally:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        for name, run in (("productive", productive), ("deferral", campaign),
                          ("replan", lambda root, server: campaign(root, server, True)),
                          ("dirty-checkpoint", lambda root, server: campaign(root, server, dirty=True)),
                          ("budget", budget_resume), ("native-goal", native_goal)):
            with tempfile.TemporaryDirectory(prefix="slopzero-") as temporary:
                run(Path(temporary), transport)
                print("PASSED", name)
