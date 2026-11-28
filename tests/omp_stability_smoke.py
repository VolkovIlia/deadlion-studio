"""Live OMP regressions for scoped coverage and staging identity."""
from http.server import HTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

from omp_engineering_smoke import PLUGIN, Transport, fixture, trial


def environment(root, server):
    profile, source = fixture.setup(root, server.server_port)
    config = profile / "config.yml"
    config.write_text(config.read_text() + "startup:\n  setupWizard: false\n")
    env = {**os.environ, "HOME": str(root), "PI_CONFIG_DIR": str(root / ".omp"),
           "PI_CODING_AGENT_DIR": str(profile), "XDG_STATE_HOME": str(root / "state"),
           "FIXTURE_API_KEY": "unused"}
    env.pop("DL_ENGINEERING_POLICY", None)
    subprocess.run(["omp", "plugin", "link", PLUGIN], cwd=source, env=env, check=True, capture_output=True)
    return source, env


def make_component(source, component, value):
    path = source / component
    path.mkdir()
    (path / "Makefile").write_text("test:\n\t@node --test --test-reporter=tap behavior.cjs\n")
    (path / "logic.cjs").write_text(f"module.exports = {value};\n")
    (path / "behavior.cjs").write_text("const test = require('node:test');\n"
                                      "const assert = require('node:assert/strict');\n"
                                      f"test('business invariant', () => assert.equal(require('./logic.cjs'), {value}));\n")


def approve(source, env, scopes):
    project = json.loads(subprocess.check_output(["python3", "-I", PLUGIN / "omp/capabilities.py", "--discover"], cwd=source, env=env))
    assert all("testsScope" not in value for value in [project["policy"], *project["suites"]])
    approval = {suite["id"]: [suite["cwd"]] for suite in project["suites"] if suite["cwd"] in scopes}
    command = "/deadlion setup approve " + project["fingerprint"] + " " + json.dumps(approval)
    subprocess.run(["omp", "--offline", "-p", command], cwd=source, env=env, check=True, capture_output=True, timeout=20)


def write(path, data):
    return "write", {"path": path, "content": data}


def coverage(source, env, server):
    make_component(source, "frontend", 1)
    make_component(source, "backend", 42)
    (source / "schemas").mkdir()
    approve(source, env, ["frontend"])
    report = trial(source, env, server, {0: write("backend/logic.cjs", "module.exports = 0;\n")}, "BLOCKED", None)
    assert report["coverage"][0]["status"] == "NOT VERIFIED"
    assert any(c["status"] == "PASS" and c["coverage"]["paths"] == ["frontend"]
               for c in report["checks"] if c["name"].startswith("plan:"))
    (source / "backend/logic.cjs").write_text("module.exports = 42;\n")
    report = trial(source, env, server, {0: write("schemas/shared.proto", 'syntax = "proto3";\n')}, "BLOCKED", None)
    assert report["coverage"][0]["affectedComponents"] == ["backend", "frontend"]
    approve(source, env, ["frontend", "backend"])
    report = trial(source, env, server, {0: write("backend/logic.cjs", "module.exports = 42; // preserved\n")}, "VERIFIED", None)
    assert report["coverage"][0]["status"] == "VERIFIED"
    report = trial(source, env, server, {0: write("schemas/shared.proto", 'syntax = "proto3";\npackage shared;\n')}, "VERIFIED", None)
    assert report["coverage"][0]["status"] == "VERIFIED"
    (source / "backend/behavior.cjs").write_text("require('node:test').skip('not run', () => {});\n")
    report = trial(source, env, server, {0: write("backend/logic.cjs", "module.exports = 42; // new edit\n")}, "BLOCKED", None)
    assert any(c.get("coverage", {}).get("execution", {}).get("incomplete") for c in report["checks"]), report["checks"]


def staged_mismatch(source, env, server):
    (source / "candidate").write_text("staged\n")
    fixture.git(source, "add", "candidate")
    path = source.parent / "operator-policy.json"
    path.write_text(json.dumps({"tests": ["python3", "-c",
        "from pathlib import Path; assert Path('candidate').read_text() == 'working\\n'"],
        "testsScope": ["candidate"], "maxCorrections": 0}))
    report = trial(source, {**env, "DL_ENGINEERING_POLICY": str(path)},
                   server, {0: write("candidate", "working\n")}, "BLOCKED", None)
    assert any(c["name"] == "index differs from tested files" for c in report["checks"])


def ignored_input(source, env, server):
    (source / ".gitignore").write_text("/build/\n")
    (source / "build").mkdir()
    (source / "build/oracle.txt").write_text("original\n")
    path = source.parent / "operator-policy.json"
    path.write_text(json.dumps({"tests": ["python3", "-c",
        "from pathlib import Path; assert Path('backend/logic.cjs').is_file()"],
        "testsScope": ["backend"], "verificationInputs": ["build/oracle.txt"], "maxCorrections": 0}))
    report = trial(source, {**env, "DL_ENGINEERING_POLICY": str(path)}, server,
                   {0: write("build/oracle.txt", "changed\n")}, "BLOCKED", None)
    assert any("verification inputs" in c.get("reason", "") for c in report["checks"]), report["checks"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        source, env = environment(Path(tmp), server)
        coverage(source, env, server)
        staged_mismatch(source, env, server)
        ignored_input(source, env, server)
