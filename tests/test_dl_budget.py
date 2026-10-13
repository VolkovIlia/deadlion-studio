#!/usr/bin/env python3
"""
Tests for plugins/deadlion/skills/suckless-code/scripts/dl-budget.

Fixtures live under pytest's tmp_path, outside any git repository.

Usage:
    pytest tests/test_dl_budget.py -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "suckless-code" / "scripts" / "dl-budget"


def run(args, cwd, env=None):
    """Run dl-budget with only python3 on PATH and no DL_* settings, plus ENV."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("DL_")}
    full_env["PATH"] = str(Path(sys.executable).parent)
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd,
        capture_output=True, text=True, env=full_env,
    )


def project(tmp_path, files):
    """Create tmp_path/proj holding FILES {relative path: content}."""
    root = tmp_path / "proj"
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def test_sloc_over_default(tmp_path):
    project(tmp_path, {"a.c": "x;\n" * 2001})
    result = run(["proj"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "proj:1: project has 2001 SLOC (max 2000)\n"


def test_comments_and_blanks_not_counted(tmp_path):
    src = "// line\n/*\n * block\n */\n\n   \n" + "x;\n" * 10
    project(tmp_path, {"a.c": src})
    result = run(["proj"], cwd=tmp_path, env={"DL_MAX_SLOC": "9"})
    assert result.stdout == "proj:1: project has 10 SLOC (max 9)\n"


def test_budget_file_raises_limit(tmp_path):
    project(tmp_path, {"a.c": "x;\n" * 2001, ".budget": "# own budget\nsloc 3000\n"})
    result = run(["proj"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")


def test_test_code_not_counted(tmp_path):
    project(tmp_path, {"a.c": "x;\n" * 5, "tests/x.c": "x;\n" * 50,
                       "test.sh": "echo\n" * 50, "b_test.go": "x\n" * 50})
    result = run(["proj"], cwd=tmp_path, env={"DL_MAX_SLOC": "5"})
    assert (result.returncode, result.stdout) == (0, "")


def test_cargo_direct_deps(tmp_path):
    cargo = """[package]
name = "p"

[dependencies]
serde = "1"
libc = "0.2"
memchr = "2"
regex = { version = "1" }

[dependencies.foo]
version = "1"

[build-dependencies]
cc = "1"

[dev-dependencies]
a = "1"
b = "1"
c = "1"
"""
    project(tmp_path, {"Cargo.toml": cargo})
    result = run(["proj"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == ("proj:1: project has 6 direct dependencies (max 5): "
                             "cc, foo, libc, memchr, regex, serde\n")


def test_configmk_libs(tmp_path):
    project(tmp_path, {"config.mk": "LIBS = -lX11 -lc -lfontconfig\nLDFLAGS = -lm\n"})
    result = run(["proj"], cwd=tmp_path, env={"DL_MAX_DEPS": "1"})
    assert result.stdout == ("proj:1: project has 2 direct dependencies (max 1): "
                             "X11, fontconfig\n")


def deps_line(tmp_path, files):
    project(tmp_path, files)
    return run(["proj"], cwd=tmp_path, env={"DL_MAX_DEPS": "0"}).stdout


def test_package_json_deps(tmp_path):
    pkg = {"dependencies": {"left-pad": "1", "chalk": "5"}, "devDependencies": {"x": "1"}}
    out = deps_line(tmp_path, {"package.json": json.dumps(pkg)})
    assert out == "proj:1: project has 2 direct dependencies (max 0): chalk, left-pad\n"


def test_pyproject_deps(tmp_path):
    toml = '[project]\nname = "p"\ndependencies = ["requests>=2", "rich[jupyter]", "tomli; python_version<\'3.11\'"]\n'
    out = deps_line(tmp_path, {"pyproject.toml": toml})
    assert out == "proj:1: project has 3 direct dependencies (max 0): requests, rich, tomli\n"


def test_gomod_deps(tmp_path):
    gomod = ("module m\n\ngo 1.22\n\nrequire example.com/one v1.0.0\n\nrequire (\n"
             "\texample.com/two v1.2.0\n\texample.com/three v0.1.0 // indirect\n)\n")
    out = deps_line(tmp_path, {"go.mod": gomod})
    assert out == ("proj:1: project has 2 direct dependencies (max 0): "
                   "example.com/one, example.com/two\n")


def test_default_dirs_are_projects(tmp_path):
    (tmp_path / "projects" / "a").mkdir(parents=True)
    (tmp_path / "projects" / "b").mkdir()
    (tmp_path / "projects" / "a" / "a.c").write_text("x;\n" * 11)
    (tmp_path / "projects" / "b" / "b.c").write_text("x;\n")
    result = run([], cwd=tmp_path, env={"DL_MAX_SLOC": "10"})
    assert result.returncode == 1
    assert result.stdout == "projects/a:1: project has 11 SLOC (max 10)\n"


def test_bad_budget_line(tmp_path):
    project(tmp_path, {".budget": "slocc 5\n"})
    result = run(["proj"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr == "dl-budget: proj/.budget:1: bad line\n"


def test_missing_dir(tmp_path):
    result = run(["nope"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("dl-budget:")


def test_invalid_cargo_toml(tmp_path):
    project(tmp_path, {"Cargo.toml": "[dependencies\n"})
    result = run(["proj"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("dl-budget: proj/Cargo.toml:")
