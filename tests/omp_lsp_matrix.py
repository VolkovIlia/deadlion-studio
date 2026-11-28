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
    (source / "go.mod").write_text("module example.com/deadlionfixture\n\ngo 1.24.0\n")
    (source / "main.go").write_text("package main\nfunc Value() int { return 42 }\nfunc main() { _ = Value() }\n")
    (source / "Cargo.toml").write_text('[package]\nname = "deadlionfixture"\nversion = "0.1.0"\nedition = "2021"\n[lib]\npath = "lib.rs"\n')
    (source / "lib.rs").write_text('pub fn value() -> usize { 42 }\n')
    (source / ".gitignore").write_text("/target/\n/Cargo.lock\n/.gradle/\n/.idea/\n")
    (source / "settings.gradle.kts").write_text('rootProject.name = "deadlionfixture"\n')
    (source / ".project").write_text('<projectDescription><name>deadlionfixture</name><buildSpec>'
        '<buildCommand><name>org.eclipse.jdt.core.javabuilder</name></buildCommand></buildSpec>'
        '<natures><nature>org.eclipse.jdt.core.javanature</nature></natures></projectDescription>')
    (source / ".classpath").write_text('<classpath><classpathentry kind="src" path=""/>'
        '<classpathentry kind="con" path="org.eclipse.jdt.launching.JRE_CONTAINER"/>'
        '<classpathentry kind="output" path="bin"/></classpath>')
    (source / "Example.java").write_text('class Example { int value = 42; }\n')
    (source / "Example.kt").write_text('val value: Int = 42\n')
    kotlin = os.getenv("DL_TEST_KOTLIN_COMMAND")
    if kotlin:
        (source / ".omp").mkdir(exist_ok=True)
        (source / ".omp/lsp.json").write_text(json.dumps({"servers": {"kotlin-lsp": {"command": kotlin, "args": []}}}))
    policy = root / "policy.json"
    policy.write_text(json.dumps({"tests": ["python3", "-c", "from pathlib import Path; assert Path('candidate').is_file()"], "testsScope": ["."], "requireLsp": True, "maxCorrections": 0}))
    env = {**os.environ, "HOME": str(root), "PI_CONFIG_DIR": str(root / ".omp"), "PI_CODING_AGENT_DIR": str(profile),
           "XDG_STATE_HOME": str(root / "state"), "DL_ENGINEERING_POLICY": str(policy), "FIXTURE_API_KEY": "unused"}
    subprocess.run(["omp", "plugin", "link", PLUGIN], cwd=source, env=env, check=True, capture_output=True)
    cases = [
        ("C++", "clangd", "main.cpp", "int main() { return unknown_cpp_name; }\n", "unknown_cpp_name"),
        ("TypeScript", "typescript-language-server", "main.ts", 'const value: number = "wrong";\n', "assignable"),
        ("Go", "gopls", "main.go", 'package main\nvar Value int = "wrong"\nfunc main() {}\n', "cannot use"),
        ("Rust", "rust-analyzer", "lib.rs", 'pub fn value() -> usize { let values = vec![1]; values }\n', "expected usize, found Vec"),
        ("Java", "jdtls", "Example.java", 'class Example { int value = "wrong"; }\n', "String"),
        ("Kotlin", "kotlin-lsp", "Example.kt", 'val value: Int = "wrong"\n', "Int"),
    ]
    for language, executable, path, body, text in cases:
        if language == "Kotlin" and kotlin:
            executable = kotlin
        if not shutil.which(executable):
            print(f"NOT VERIFIED {language} — {executable} unavailable")
            if os.getenv("DL_REQUIRE_LSP_MATRIX") and language in {"C++", "TypeScript"}:
                raise RuntimeError("Required LSP fixture unavailable")
            continue
        steps = {0: ("write", {"path": path, "content": body})}
        if language == "Go":
            steps = {0: ("lsp", {"action": "hover", "file": path, "line": 3, "symbol": "Value"}),
                     1: ("lsp", {"action": "definition", "file": path, "line": 3, "symbol": "Value"}),
                     2: steps[0]}
        if language == "Rust":
            steps = {0: ("lsp", {"action": "hover", "file": path, "line": 1, "symbol": "value", "timeout": 8}),
                     1: ("bash", {"command": "sleep 3"}), 2: steps[0],
                     3: ("lsp", {"action": "diagnostics", "file": path, "timeout": 8})}
        if language in {"Java", "Kotlin"}:
            steps = {0: ("lsp", {"action": "hover", "file": path, "line": 1, "symbol": "value", "timeout": 10}),
                     1: steps[0], 2: ("lsp", {"action": "diagnostics", "file": path, "timeout": 10})}
        report = trial(source, env, server, steps, "BLOCKED", None)
        diagnostic = next(row for row in report["checks"] if row["name"] == "lsp " + path)
        if language in {"Rust", "Java", "Kotlin"} and diagnostic["status"] in {"NOT VERIFIED", "INCONCLUSIVE"}:
            print(f"NOT VERIFIED {language} diagnostics — {diagnostic.get('output', diagnostic.get('reason'))}")
            continue
        assert diagnostic["status"] == "FAIL" and text in diagnostic.get("output", ""), diagnostic
        print(f"PASSED {language} diagnostics via {diagnostic['server']}")
        if language == "Go":
            observations = [str(message["content"]) for message in json.loads(server.context[-1]) if message["role"] == "tool"]
            assert any("func Value() int" in item for item in observations), observations
            assert any("main.go:2:6" in item for item in observations), observations
            print("PASSED Go hover type and definition")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp, HTTPServer(("127.0.0.1", 0), Transport) as transport:
        threading.Thread(target=transport.serve_forever, daemon=True).start()
        exercise(Path(temp), transport)
