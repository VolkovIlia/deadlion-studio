#!/usr/bin/env python3
"""
Tests for plugins/deadlion/skills/suckless-code/scripts/dl-size.

Fixtures live under pytest's tmp_path, outside any git repository, so
directory arguments exercise the os.walk enumeration. PATH is an empty
directory, so results do not depend on lizard being installed; a pip install
puts lizard next to python3, so "only python3's directory" would not hide it.

Usage:
    pytest tests/test_dl_size.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

LIZARD = shutil.which("lizard")

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "suckless-code" / "scripts" / "dl-size"
# dl-size is started through sys.executable, so it needs nothing on PATH.
EMPTY_PATH = tempfile.TemporaryDirectory()


def run(args, cwd, stdin="", env=None):
    """Run dl-size with an empty PATH and no DL_* settings, plus ENV."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("DL_")}
    full_env["PATH"] = EMPTY_PATH.name
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, input=stdin,
        capture_output=True, text=True, env=full_env,
    )


def write_function(path, body_lines):
    """Write a Python file holding `def f():` with BODY_LINES statements."""
    body = "".join(f"    a{i} = {i}\n" for i in range(body_lines))
    path.write_text(f'def f():\n    """Docstring."""\n\n    # comment\n{body}')
    return path


def test_function_over_limit(tmp_path):
    write_function(tmp_path / "big.py", 51)
    result = run(["big.py"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "big.py:1: function f has 51 lines (max 50)\n"


def test_function_at_limit(tmp_path):
    write_function(tmp_path / "ok.py", 50)
    result = run(["ok.py"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")


def test_decorated_function_reports_def_line(tmp_path):
    src = tmp_path / "deco.py"
    body = "".join(f"    a{i} = {i}\n" for i in range(51))
    src.write_text(f"import functools\n\n@functools.cache\nasync def g():\n{body}")
    result = run(["deco.py"], cwd=tmp_path)
    assert result.stdout == "deco.py:4: function g has 51 lines (max 50)\n"


def test_long_js_file(tmp_path):
    (tmp_path / "big.js").write_text("x;\n" * 501)
    result = run(["."], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "./big.js:1: file has 501 lines (max 500)\n"


def test_walk_skips_vendored_and_non_source(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "big.js").write_text("x;\n" * 501)
    (tmp_path / "notes.txt").write_text("x\n" * 501)
    result = run([str(tmp_path)], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")


def test_func_limit_env(tmp_path):
    write_function(tmp_path / "mid.py", 11)
    result = run(["mid.py"], cwd=tmp_path, env={"DL_MAX_FUNC": "10"})
    assert result.returncode == 1
    assert result.stdout == "mid.py:1: function f has 11 lines (max 10)\n"


def test_syntax_error_skips_function_check(tmp_path):
    (tmp_path / "bad.py").write_text("def f(:\n" + "    x = 1\n" * 60)
    result = run(["bad.py"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")


def test_hook_reports_on_stderr(tmp_path):
    big = write_function(tmp_path / "big.py", 51)
    payload = json.dumps({"tool_input": {"file_path": str(big)}})
    result = run(["--hook"], cwd=tmp_path, stdin=payload)
    assert result.returncode == 2
    assert result.stdout == ""
    assert f"{big}:1: function f has 51 lines (max 50)" in result.stderr


def test_hook_ignores_non_source_and_missing(tmp_path):
    (tmp_path / "notes.txt").write_text("x\n" * 600)
    for target in (tmp_path / "notes.txt", tmp_path / "gone.py"):
        payload = json.dumps({"tool_input": {"file_path": str(target)}})
        result = run(["--hook"], cwd=tmp_path, stdin=payload)
        assert (result.returncode, result.stderr) == (0, "")


def test_hook_disabled(tmp_path):
    big = write_function(tmp_path / "big.py", 51)
    payload = json.dumps({"tool_input": {"file_path": str(big)}})
    result = run(["--hook"], cwd=tmp_path, stdin=payload, env={"DL_HOOKS": "0"})
    assert (result.returncode, result.stderr) == (0, "")


def test_hook_malformed_json(tmp_path):
    result = run(["--hook"], cwd=tmp_path, stdin="{not json")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_missing_path(tmp_path):
    result = run(["nope.py"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("dl-size:")
    assert result.stdout == ""


def test_extensionless_shell_script_is_source(tmp_path):
    (tmp_path / "tool").write_text("#!/bin/sh\n" + "echo x\n" * 500)
    result = run(["tool"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "tool:1: file has 501 lines (max 500)\n"


def test_extensionless_python_script_function_checked(tmp_path):
    body = "".join(f"    a{i} = {i}\n" for i in range(51))
    (tmp_path / "tool").write_text(f"#!/usr/bin/env python3\ndef f():\n{body}")
    result = run(["tool"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "tool:2: function f has 51 lines (max 50)\n"


def test_lizard_absent_notice(tmp_path):
    (tmp_path / "a.c").write_text("int main(void) { return 0; }\n")
    result = run(["a.c"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")
    assert "lizard not on PATH" in result.stderr


@pytest.mark.skipif(LIZARD is None, reason="lizard not installed")
def test_lizard_reports_long_c_function(tmp_path):
    body = "".join(f"    int a{i} = {i};\n" for i in range(60))
    (tmp_path / "a.c").write_text(f"int\nbigfunc(void)\n{{\n{body}    return 0;\n}}\n")
    lizard_dir = str(Path(LIZARD or "").parent)
    path = os.pathsep.join([str(Path(sys.executable).parent), lizard_dir])
    result = run(["a.c"], cwd=tmp_path, env={"PATH": path})
    assert result.returncode == 1
    assert "bigfunc" in result.stdout
