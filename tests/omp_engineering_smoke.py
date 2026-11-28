"""Exercise plugin discovery, correction and refusal through the installed omp binary."""
import io
import json
import os
import re
import signal
import shutil
import time
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import HTTPServer

import omp_autoresearch_smoke as fixture

PLUGIN = fixture.ROOT / "plugins/deadlion"


class Transport(fixture.Transport):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        request = json.loads(body)
        if request.get("tools"):
            self.server.context.append(json.dumps(request["messages"]))
        self.rfile = io.BytesIO(body)
        step = self.server.calls
        steps = self.server.steps
        action = None
        if request.get("tools"):
            action = steps(step, request) if callable(steps) else steps.get(step)
        fixture.CALLS = [action] * (step + 1) if action else []
        try:
            super().do_POST()
        except (ConnectionResetError, BrokenPipeError):
            pass


def trial(source, env, server, steps, expected, calls, prompt="Implement the requested edit."):
    server.calls = 0
    server.contracts = False
    server.steps = steps
    server.context = []
    r = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--seconds", "30", prompt],
                       cwd=source, env=env, capture_output=True, text=True, timeout=40)
    verdict = json.loads(r.stdout)
    assert verdict["state"] == expected, (verdict, r.stderr[-1200:], server.calls)
    assert r.returncode == (0 if expected == "VERIFIED" else 2)
    assert calls is None or server.calls == calls, (server.calls, calls, verdict)
    print(expected, "provider requests", server.calls, flush=True)
    return json.loads(Path(verdict["report"]["receipt"]).read_bytes())


def interactive(source, env, server):
    import pexpect

    path = source.parent / "terminal.json"
    server.steps = {}
    server.calls = 0
    process = pexpect.spawn("omp", ["--offline", "--no-judge", "--no-spotlight", "--no-session", "Check this project."],
                            env={**env, "DL_VERDICT_FILE": str(path), "TERM": "xterm-256color"},
                            cwd=str(source), dimensions=(35, 120), encoding="utf-8")
    try:
        deadline = time.monotonic() + 12
        # A real PTY must keep draining frames while the TUI renders.
        frames = ""
        while time.monotonic() < deadline and not path.exists():
            try:
                frames = (frames + process.read_nonblocking(65536, timeout=.2))[-20000:]
            except pexpect.TIMEOUT:
                pass
        assert path.exists(), ("interactive verdict missing", server.calls, re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frames)[-1500:])
        assert json.loads(path.read_bytes())["state"] == "VERIFIED"
    finally:
        process.terminate(force=True)


def policy_scenarios(source, env, server, policy):
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."]}))
    initial = fixture.git(source, "rev-parse", "HEAD")
    command = "echo one > a.txt & echo two > b.txt & wait; git add a.txt b.txt; git -c user.email=a@b -c user.name=a commit -qm change"
    report = trial(source, env, server, {0: ("bash", {"command": command})}, "VERIFIED", 2)
    assert report["baseline"] == initial and {"a.txt", "b.txt"} <= set(report["paths"])
    (source / ".budget").write_text("sloc 0\n")
    report = trial(source, env, server, {0: ("bash", {"command": "echo 'x=1' > example.py"})},
                   "INCOMPLETE", 3)
    assert any(c["name"] == "dl-budget" and c["status"] == "FAIL" for c in report["checks"])
    (source / ".budget").unlink()
    policy.write_text(json.dumps({"tests": ["/usr/bin/sleep", "4"], "analysisSeconds": 1}))
    report = trial(source, env, server, {}, "INCOMPLETE", 1)
    assert any("timeout" in c.get("reason", "") for c in report["checks"])
    policy.write_text(json.dumps({"tests": ["missing-deadlion-check"]}))
    report = trial(source, env, server, {}, "INCOMPLETE", 2)
    assert report["status"] == "NOT VERIFIED", report
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."]}))


def approved_checks(source, env, server, policy):
    rule = "This generated table exceeds the file guideline; the resource and functional gates still apply."
    plan = {"name": "generated table present", "argv": ["/usr/bin/test", "-s", "table.py"]}
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."], "checks": [plan], "maxCorrections": 0,
                                 "sizeExceptions": {"table.py": rule}, "requiredAnalyzers": ["ruff", "ast-grep"]}))
    opts = {**env, "DL_MAX_FILE": "1"}
    steps = {0: ("write", {"path": "table.py", "content": "first = 1\nsecond = 2\nthird = 3\n"})}
    report = trial(source, opts, server, steps, "VERIFIED", 2)
    size = next(c for c in report["checks"] if c["name"] == "dl-size table.py")
    assert size["exception"] == rule and size["status"] == "WARNING" and size["data"]["code"] == 1
    data = next(c["data"] for c in report["checks"] if c["name"] == "dl-analyze")
    assert {"ruff", "ast-grep"} <= set(data["checked_tools"])
    report = trial(source, opts, server, {0: ("bash", {"command": "rm table.py"})}, "INCOMPLETE", 2)
    assert any(c["name"] == "plan: generated table present" and c["status"] == "FAIL" for c in report["checks"])


def contract_scenarios(source, env, server, policy):
    protected = source / ".performance/demo"
    protected.mkdir(parents=True)
    path = protected / "contract.json"
    record = json.loads((PLUGIN / "evals/indexed-membership/contract.json").read_bytes())
    record["benchmark"] = dict(candidate_root=".", candidate=["cat", "candidate"], candidate_files=["candidate"],
                               baseline=["cat"], expected="expected")
    (protected / "input").write_text("good\n")
    (protected / "expected").write_text("good\n")
    policy.write_text(json.dumps({"maxCorrections": 0}))
    def approve(budget):
        record["budget"] = budget
        path.write_text(json.dumps(record))
        fixture.git(source, "add", ".performance")
        fixture.git(source, "-c", "user.name=Smoke", "-c", "user.email=test@fixture", "commit", "-qm", "approve")
    def attempt(contents):
        return trial(source, env, server, {0: ("bash", {"command": f"echo {contents} > candidate"})}, "INCOMPLETE", 2)
    approve({"peak_rss_kib": 100000})
    report = attempt("incorrect")
    assert any(c["name"] == "approved contracts" and c["status"] != "PASS" for c in report["checks"]), report
    (source / "candidate").write_text("good\n")
    report = trial(source, env, server, {0: ("write", {"path": "unrelated.py", "content": "value = 1\n"})},
                   "INCOMPLETE", 2)
    assert any(c["name"] == "approved contracts" and c["status"] == "PASS" for c in report["checks"])
    assert [(c["path"], c["status"]) for c in report["coverage"]] == [("unrelated.py", "NOT VERIFIED")]
    (source / "candidate").write_text("previous\n")
    approve({"allocation_count": 0})
    report = attempt("good")
    assert "allocation" in json.dumps(report["checks"]), report
    approve({"max_wall_ratio": 0.0001})
    (source / "candidate").write_text("previous\n")
    report = attempt("good")
    assert "PERFORMANCE REGRESSION" in json.dumps(report["checks"]), report
    report = trial(source, env, server, {0: ("bash", {"command": "echo '{}' > .performance/demo/contract.json"})},
                   "INCOMPLETE", 2)
    assert any(c["name"] == "approved policy changed" for c in report["checks"])
    fixture.git(source, "restore", ".performance")


def incremental_scenarios(source, env, server, policy):
    target = source / "loops.py"
    target.write_text("pass\n")
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."]}))
    report = trial(source, env, server, {
        0: ("write", {"path": "loops.py", "content": "table = {'a': 1}\nfor k, v in table.items():\n    print(v)\n"}),
        1: ("write", {"path": "loops.py", "content": "table = {'a': 1}\nfor v in table.values():\n    print(v)\n"}),
    }, "VERIFIED", 3)
    assert "PERF102" in server.context[1]
    assert any(c["name"] == "dl-analyze" and not c["data"]["diagnostics"] for c in report["checks"])
    policy.write_text(json.dumps({"tests": ["cat", "required-file"], "maxCorrections": 0}))
    (source / "required-file").touch()
    report = trial(source, env, server, {
        0: ("deadlion_verify", {}), 1: ("bash", {"command": "rm required-file"}),
    }, "INCOMPLETE", 3)
    assert "PASS" in server.context[1] and "gate-" in server.context[1], server.context[1][-900:]
    assert any(c["name"] == "functional tests" and c["status"] == "FAIL" for c in report["checks"])


def analyzer_failures(source, env, server, policy):
    bin_dir = source.parent / "probe-bin"
    bin_dir.mkdir()
    (bin_dir / "omp").symlink_to(shutil.which("omp"))
    probe_env = {**env, "PATH": f"{bin_dir}:/usr/bin:/bin"}
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."], "maxCorrections": 0,
                                 "requiredAnalyzers": ["ruff"], "analysisSeconds": 2}))
    ruff = bin_dir / "ruff"
    for index, body in enumerate([None, "exit 2", "sleep 10"]):
        if body:
            ruff.write_text("#!/bin/sh\n" + body + "\n")
            ruff.chmod(0o755)
        def external_write(step, request):
            if step == 0:
                (source / "external.py").write_text(f"value = {index}\n")
        report = trial(source, probe_env, server, external_write, "INCOMPLETE", 1)
        analyzer = next(c for c in report["checks"] if c["name"] == "dl-analyze")
        assert analyzer["status"] == "NOT VERIFIED", analyzer
        if index == 2:
            assert "timeout" in analyzer["reason"], analyzer
    if shutil.which("memray"):
        profile = {"metric": "allocations", "argv": ["alloc.py"], "max": {"allocation_count": 0}}
        (source / "alloc.py").write_text("buffers = [bytearray(4096) for _ in range(1024)]\n")
        policy.write_text(json.dumps({"profile": profile, "maxCorrections": 0}))
        report = trial(source, env, server, {}, "INCOMPLETE", 1)
        sample = next(c for c in report["checks"] if c["name"] == "trusted profile")
        assert sample["status"] == "FAIL" and sample["data"]["metrics"]["allocation_count"] > 0, sample


def design_scenario(source, env, server, policy):
    approved = source.parent / "approved-fixture"
    approved.mkdir()
    record = json.loads((PLUGIN / "evals/indexed-membership/contract.json").read_bytes())
    record["benchmark"] = dict(candidate=["cat", "candidate"], candidate_files=["candidate"],
                               baseline=["cat"], expected="expected")
    record["budget"] = {"peak_rss_kib": 100000}
    for path in [approved / "input", approved / "expected", source / "candidate"]:
        path.write_text("good\n")
    contract = approved / "contract.json"
    contract.write_text(json.dumps(record))
    policy.write_text(json.dumps({"mode": "Performance"}))
    report = trial(source, {**env, "DL_PERF_CONTRACT": str(contract)}, server, {
        0: ("lsp", {"action": "status"}),
        1: ("bash", {"command": "touch premature"}),
        2: ("deadlion_verify", {}),
        3: ("bash", {"command": "touch approved-edit.md"}),
    }, "VERIFIED", 5)
    assert not (source / "premature").exists() and "approved-edit.md" in report["paths"]
    result = next(m for m in reversed(json.loads(server.context[1])) if m["role"] == "tool")
    assert "server" in str(result["content"]).lower(), result
    assert "initial-measurement.json" in server.context[3], server.context[3][-1200:]


def child_steps(step, request):
    marker = "DL_CHILD_WRITE_FIXTURE"
    if step == 0:
        child_steps.actions = 0
        return "task", {"agent": "implementer", "task": marker, "solutionSpace": "current directory",
                        "name": "ChildWrite"}
    users = [json.dumps(m["content"]) for m in request["messages"] if m["role"] == "user" and isinstance(m["content"], list)]
    child = any("Complete assignment thoroughly:" in text and marker in text for text in users)
    if child and child_steps.actions == 0:
        child_steps.actions += 1
        return "bash", {"command": "echo child > child.txt"}


def parallel_eval(source, env, server, policy, trace):
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."]}))
    sent = set()
    start = len(trace.read_text().splitlines())
    def steps(step, request):
        if step == 0:
            return "eval", {"language": "js", "code":
                "const handles=await Promise.all(['left','right'].map(key=>agent('DL_WORKER_'+key,"
                "{agent:'task', isolated:false}))); await Promise.all(handles.map(handle=>handle.wait()));"}
        for message in request["messages"]:
            if message["role"] != "user" or not isinstance(message["content"], list):
                continue
            body = json.dumps(message["content"])
            for key in ("left", "right"):
                if f"DL_WORKER_{key}" in body and "Complete assignment thoroughly:" in body and key not in sent:
                    sent.add(key)
                    return "bash", {"command": "echo worker > " + key + ".txt"}
    report = trial(source, env, server, steps, "VERIFIED", None)
    events = map(json.loads, trace.read_text().splitlines()[start:])
    assert len({r[3] for r in events if r[:3] == ["tool_call", "sub", "bash"]}) == 2
    assert {"left.txt", "right.txt"} <= set(report["paths"])


def python_hover(source, env, server, policy):
    import site
    if not shutil.which("pylsp"):
        return
    (source / "pyproject.toml").write_text('[tool.pyright]\ntypeCheckingMode="basic"\n')
    config = source / ".omp/lsp.json"
    config.parent.mkdir(exist_ok=True)
    config.write_text(json.dumps({"servers": {"pyright": {"disabled": True}, "basedpyright": {"disabled": True}}}))
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."], "requireLsp": True, "maxCorrections": 0}))
    code = ("def copies(values: list[int]) -> list[list[int]]:\n    result = []\n"
            "    for _ in range(4):\n        result.append(values.copy())\n    return result\n")
    report = trial(source, {**env, "PYTHONUSERBASE": site.getuserbase()}, server,
                   {0: ("write", {"path": "copies.py", "content": code})}, "VERIFIED", 2)
    directory = Path(env["XDG_STATE_HOME"]) / "deadlion" / report["task"]
    rows = [d for p in directory.glob("analysis-*.json") for d in json.loads(p.read_bytes())["diagnostics"]]
    copy = next(d for d in rows if d["rule"] == "dl-py-copy-loop")
    assert copy["evidenceLevel"] == "HEURISTIC" and "list" in copy["typeContext"]["text"].lower()
    assert copy["typeContext"]["source"] == "pylsp" and "typeContext" in server.context[1]


def required_and_simple(source, env, server, policy):
    policy.write_text(json.dumps({"maxCorrections": 0}))
    report = trial(source, env, server, {0: ("bash", {"command": "echo 'enabled = True' > new_module.py"})},
                   "INCOMPLETE", 2)
    assert any(c["name"] == "functional verification" and c["status"] == "NOT VERIFIED" for c in report["checks"]), report["checks"]
    trace = map(json.loads, reversed(Path(env["DL_TEST_TRACE"]).read_text().splitlines()))
    session = next(row[3] for row in trace if row[:2] == ["before_agent_start", "main"])
    server.steps, server.calls = {}, 0
    resumed = subprocess.run([PLUGIN / "omp/dl-omp", "--offline", "--resume", session, "--seconds", "20", "Finish."],
                             cwd=source, env=env, capture_output=True, text=True, timeout=25)
    verdict = json.loads(resumed.stdout)
    assert resumed.returncode == 2 and verdict["task"] == report["task"] and verdict["state"] == "INCOMPLETE"
    assert "new_module.py" in verdict["report"]["paths"] and server.calls == 1
    report = trial(source, env, server, {}, "VERIFIED", 1, prompt="Summarize this project.")
    assert report["checks"] == [] and report["paths"] == []
    policy.write_text(json.dumps({"tests": ["/usr/bin/false"], "maxCorrections": 0}))
    report = trial(source, env, server, {}, "VERIFIED", 1, prompt="Explain the algorithm without changing files.")
    assert report["route"]["scope"] == "read-only" and report["route"]["mode"] == "Standard"
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "maxCorrections": 0}))
    report = trial(source, env, server, {0: ("write", {"path": "unexpected.py", "content": "answer = 42\n"})},
                   "INCOMPLETE", 2, prompt="Explain the algorithm without changing files.")
    assert report["route"]["scope"] == "one file"
    assert any(c["name"] == "functional tests" and c["status"] == "PASS" for c in report["checks"])
    assert not any(c["status"] == "VERIFIED" for c in report["coverage"])


def research_scenario(source, env, server, policy):
    approved = source.parent / "research"
    shutil.copytree(PLUGIN / "evals/scaling-membership", approved)
    contract = approved / "contract.json"
    record = json.loads(contract.read_bytes())
    record["budget"] = {"peak_rss_kib": 65536}
    scaling = record["scaling"]
    scaling.update(dimensions={"n": [8, 16, 32], "q": [4, 8]}, distributions=["uniform"],
                   min_repetitions=9, max_repetitions=9)
    del scaling["growth_limits"]
    contract.write_text(json.dumps(record))
    shutil.copy(approved / "indexed.py", source / "indexed.py")
    policy.write_text(json.dumps({"mode": "Research", "maxCorrections": 0}))
    report = trial(source, {**env, "DL_PERF_CONTRACT": str(contract)}, server,
                   {0: ("deadlion_verify", {}), 1: ("deadlion_verify", {})}, "VERIFIED", 3)
    assert "admissible" in server.context[1] and "admissible" in server.context[2]
    measured = next(c["data"]["scaling"] for c in report["checks"] if c["name"] == "performance contract")
    assert measured["correctness"] == "VERIFIED" and len(measured["rows"]) >= 6


def interrupted(source, env, server, trace, crash):
    """Interrupt a real provider turn after its tool changed disk."""
    entered, release = threading.Event(), threading.Event()
    def steps(step, request):
        if step == 0:
            return "bash", {"command": "echo checkpoint >> restart.txt"}
        entered.set()
        release.wait(10)
    server.steps, server.context, server.calls = steps, [], 0
    before = set((Path(env["XDG_STATE_HOME"]) / "deadlion").iterdir())
    proc = subprocess.Popen(["omp", "--offline", "--mode", "rpc", "--no-judge", "--no-spotlight"],
                            cwd=source, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True, text=True)
    try:
        proc.stdin.write('{"type":"prompt","id":"test","message":"Update the fixture."}\n')
        proc.stdin.flush()
        # Drain RPC updates while the scripted provider waits at its second call.
        threading.Thread(target=lambda: list(proc.stdout), daemon=True).start()
        assert entered.wait(10), "OMP did not apply the tool call"
        state, = set((Path(env["XDG_STATE_HOME"]) / "deadlion").iterdir()) - before
        task = json.loads((state / "task.json").read_bytes())
        session = next(e[3] for e in reversed([json.loads(row) for row in trace.read_text().splitlines()])
                       if e[0] == "before_agent_start" and e[1] == "main")
        if crash:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.stdin.write('{"type":"abort","id":"cancel"}\n')
            proc.stdin.flush()
            time.sleep(.15)
        release.set()
        if not crash:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if json.loads((state / "task.json").read_bytes())["state"] == "CANCELLED":
                    return
                time.sleep(.05)
            raise AssertionError("missing cancellation evidence")
    finally:
        release.set()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    server.steps, server.calls, server.context = {}, 0, []
    run = subprocess.run([PLUGIN / "omp/dl-omp", "--resume", session, "--offline", "--seconds", "20", "Resume the check."],
                         cwd=source, env=env, capture_output=True, text=True, timeout=25)
    verdict = json.loads(run.stdout)
    assert verdict["state"] == "VERIFIED" and verdict["task"] == task["id"], verdict
    assert "restart.txt" in verdict["report"]["paths"]


def neighbour(profile, trace):
    path = profile / "extensions/neighbour.js"
    path.parent.mkdir()
    path.write_text("""
import {appendFileSync} from "node:fs";
export default function(pi) {
  pi.registerCommand("neighbour", {handler:async()=>{}});
  for (const name of ["before_agent_start","agent_start","agent_end","session_stop","before_subagent_spawn",
      "turn_start","turn_end","tool_call","tool_result","user_bash","user_python","before_provider_request","context"]) {
    pi.on(name, (event,ctx) => {
      appendFileSync(process.env.DL_TEST_TRACE, JSON.stringify([name,ctx.agent.kind,event.toolName,ctx.sessionManager.getSessionId()])+"\\n");
    });
  }
}
""")
    return path


def harness_scenarios(source, env, server, policy, trace):
    report = trial(source, env, server, {1: ("bash", {"command": "echo good > candidate"})},
                   "VERIFIED", 3)
    assert "candidate" in report["paths"] and report["status"] == "PASS"
    (source / "candidate").write_text("bad\n")
    report = trial(source, env, server, {}, "INCOMPLETE", 2)
    assert report["checks"][0]["status"] == "FAIL"
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."], "requireLsp": True}))
    (source / ".clangd").write_text("CompileFlags: {Add: [-Wall]}\n")
    # An opaque Bash write bypasses OMP writethrough. The gate must pull clangd diagnostics.
    report = trial(source, env, server, {0: ("bash", {"command": "echo 'int main(){return unknown;}' > main.c"})},
                   "INCOMPLETE", None)
    semantic = next(c for c in report["checks"] if c["name"] == "lsp main.c")
    assert semantic.get("server") and "unknown" in semantic.get("output", ""), semantic
    assert semantic["status"] == "FAIL", semantic
    print("semantic error", semantic["server"], flush=True)
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."]}))
    report = trial(source, env, server, child_steps, "VERIFIED", None)
    assert "child.txt" in report["paths"] and server.calls < 12, [m[-500:] for m in server.context[-4:]]
    assert "unix-design" in server.context[0]
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert any(e[:3] == ["tool_call", "sub", "bash"] for e in events), events[-50:]
    assert not any(e[:2] == ["session_stop", "sub"] for e in events)
    assert {"before_subagent_spawn", "session_stop", "before_provider_request", "context",
            "agent_start", "agent_end", "before_agent_start", "tool_result", "turn_start", "turn_end"} <= {e[0] for e in events}


def marketplace_installation(plugin, source, env, server):
    marketplace = "deadlion-studio"
    plugin_id = "deadlion@" + marketplace
    catalog_path = Path(".claude-plugin/marketplace.json")
    catalog = json.loads((fixture.ROOT / catalog_path).read_bytes())
    entry = next(item for item in catalog["plugins"] if item["name"] == "deadlion")
    current_version = entry["version"]
    stale = source.parent / "stale-marketplace"
    package = stale / entry["source"]
    shutil.copytree(PLUGIN, package, ignore=shutil.ignore_patterns("__pycache__"))
    for metadata in (package / "package.json", package / ".claude-plugin/plugin.json"):
        record = json.loads(metadata.read_bytes())
        metadata.write_text(json.dumps({**record, "version": "4.6.2"}))
    (stale / catalog_path).parent.mkdir()
    (stale / catalog_path).write_text(json.dumps({**catalog, "plugins": [{**entry, "version": "4.6.2"}]}))

    plugin("marketplace", "add", str(stale))
    plugin("marketplace", "update", marketplace)
    assert "deadlion@4.6.2" in plugin("discover", marketplace).stdout
    duplicate = plugin("marketplace", "add", str(fixture.ROOT), check=False)
    assert duplicate.returncode and "already exists" in duplicate.stderr, duplicate
    collision = plugin("install", "--dry-run", plugin_id, check=False)
    assert collision.returncode and "conflicts with installed package" in collision.stderr, collision
    plugin("uninstall", marketplace)
    plugin("install", plugin_id)
    assert "4.6.2" in plugin("list").stdout

    plugin("marketplace", "remove", marketplace)
    plugin("marketplace", "add", str(fixture.ROOT))
    assert f"deadlion@{current_version}" in plugin("discover", marketplace).stdout
    plugin("upgrade", plugin_id)
    installed = json.loads(plugin("list", "--json").stdout)
    assert not installed["npm"] and len(installed["marketplace"]) == 1, installed
    installed_plugin, = installed["marketplace"]
    assert installed_plugin["id"] == plugin_id and installed_plugin["scope"] == "user", installed
    installed_entry, = installed_plugin["entries"]
    assert installed_entry["version"] == current_version, installed
    installed_package = Path(installed_entry["installPath"])
    assert json.loads((installed_package / "package.json").read_bytes())["version"] == current_version
    assert (installed_package / "omp/performance.mjs").read_bytes() == (PLUGIN / "omp/performance.mjs").read_bytes()
    trial(source, env, server, {}, "VERIFIED", 1)
    plugin("uninstall", "--scope", "user", plugin_id)


def main():
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as server:
        directory = Path(tmp)
        profile, source = fixture.setup(directory, server.server_port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        policy = directory / "policy.json"
        policy.write_text(json.dumps({"testsScope": ["candidate"], "tests": ["python3", "-c",
            "from pathlib import Path; assert Path('candidate').read_text().strip()=='good'"]}))
        env = {**os.environ, "HOME": tmp, "PI_CONFIG_DIR": str(directory / ".omp"),
               "XDG_STATE_HOME": str(directory / "state"), "PI_CODING_AGENT_DIR": str(profile),
               "DL_ENGINEERING_POLICY": str(policy), "FIXTURE_API_KEY": "unused"}
        with (profile / "config.yml").open("a") as settings:
            settings.write("startup:\n  setupWizard: false\n")
        config = (profile / "config.yml").read_bytes()
        trace = directory / "events.jsonl"
        env["DL_TEST_TRACE"] = str(trace)
        other = neighbour(profile, trace)
        def plugin(*args, check=True):
            return subprocess.run(["omp", "plugin", *args], cwd=source, env=env,
                                  capture_output=True, text=True, check=check)
        plugin("link", str(PLUGIN))
        plugin("link", str(PLUGIN))
        harness_scenarios(source, env, server, policy, trace)
        parallel_eval(source, env, server, policy, trace)
        python_hover(source, env, server, policy)
        incremental_scenarios(source, env, server, policy)
        contract_scenarios(source, env, server, policy)
        # Further scenarios have their own approved policy and no performance contract.
        fixture.git(source, "rm", "-rq", ".performance")
        fixture.git(source, "-c", "user.name=Smoke", "-c", "user.email=test@fixture", "commit", "-qm", "end contract scenarios")
        analyzer_failures(source, env, server, policy)
        design_scenario(source, env, server, policy)
        required_and_simple(source, env, server, policy)
        research_scenario(source, env, server, policy)
        approved_checks(source, env, server, policy)
        policy_scenarios(source, env, server, policy)
        interrupted(source, env, server, trace, crash=True)
        interrupted(source, env, server, trace, crash=False)
        if os.environ.get("DL_TEST_TUI"):
            interactive(source, env, server)
        marketplace_installation(plugin, source, env, server)
        plugin("install", "--scope", "project", "deadlion@deadlion-studio")
        trial(source, env, server, {}, "VERIFIED", 1)
        plugin("upgrade", "deadlion@deadlion-studio")
        trial(source, env, server, {}, "VERIFIED", 1)
        plugin("uninstall", "--scope", "project", "deadlion@deadlion-studio")
        assert other.exists() and config == (profile / "config.yml").read_bytes()


if __name__ == "__main__":
    main()
