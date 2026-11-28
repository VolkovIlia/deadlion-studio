"""Test observed semantic diagnostics in additional installed language servers."""
from http.server import HTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from omp_engineering_smoke import fixture, PLUGIN, Transport, trial


def exercise(root, server):
    profile, source = fixture.setup(root, server.server_port)
    (profile / "config.yml").write_text((profile / "config.yml").read_text() + "startup:\n  setupWizard: false\n")
    (source / ".clangd").write_text("CompileFlags: {Add: [-Wall]}\n")
    (source / "tsconfig.json").write_text('{"compilerOptions":{"strict":true},"include":["*.ts"]}')
    policy = root / "policy.json"
    policy.write_text(json.dumps({"tests": ["/usr/bin/true"], "testsScope": ["."], "requireLsp": True, "maxCorrections": 0}))
    env = {**os.environ, "HOME": str(root), "PI_CONFIG_DIR": str(root / ".omp"), "PI_CODING_AGENT_DIR": str(profile),
           "XDG_STATE_HOME": str(root / "state"), "DL_ENGINEERING_POLICY": str(policy), "FIXTURE_API_KEY": "unused"}
    subprocess.run(["omp", "plugin", "link", PLUGIN], cwd=source, env=env, check=True, capture_output=True)
    cases = [
        ("C++", "clangd", "main.cpp", "int main() { return unknown_cpp_name; }\n", "unknown_cpp_name"),
        ("TypeScript", "typescript-language-server", "main.ts", 'const value: number = "wrong";\n', "assignable"),
    ]
    for language, executable, path, body, text in cases:
        if not shutil.which(executable):
            print(f"NOT VERIFIED {language} — {executable} unavailable")
            if os.getenv("DL_REQUIRE_LSP_MATRIX"):
                raise RuntimeError("Required LSP fixture unavailable")
            continue
        report = trial(source, env, server, {0: ("write", {"path": path, "content": body})}, "BLOCKED", None)
        diagnostic = next(row for row in report["checks"] if row["name"] == "lsp " + path)
        assert diagnostic["status"] == "FAIL" and text in diagnostic.get("output", ""), diagnostic
        print(f"PASSED {language} diagnostics via {diagnostic['server']}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp, HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        exercise(Path(temp), transport)
