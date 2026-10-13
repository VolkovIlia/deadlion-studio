#!/usr/bin/env python3
"""
Tests for plugins/deadlion/skills/scaffold/scripts/dl-new and its templates.

Each template is generated under pytest's tmp_path, built and run through
its own `make test`, then checked with dl-budget.

Usage:
    pytest tests/test_dl_new.py -v
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "scaffold" / "scripts" / "dl-new"
BUDGET = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "suckless-code" / "scripts" / "dl-budget"
TOOLS = {"c": ["cc"], "rust": ["cargo"], "rust-tui": ["cargo", "tmux"], "sh": ["sh"]}
PLACEHOLDERS = ("__NAME__", "__YEAR__", "__AUTHOR__")


def run(args, cwd):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True)


def snapshot(root):
    """Return {relative path: bytes} for every file under ROOT."""
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def skip_without_tools(lang):
    missing = [t for t in TOOLS[lang] if shutil.which(t) is None]
    if missing:
        pytest.skip(f"{' '.join(missing)} not installed")


def generate(tmp_path, lang):
    result = run([lang, "demo"], cwd=tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    return tmp_path / "projects" / "demo"


@pytest.mark.parametrize("lang", sorted(TOOLS))
def test_template_builds_and_passes(tmp_path, lang):
    proj = generate(tmp_path, lang)
    for rel, data in snapshot(proj).items():
        for ph in PLACEHOLDERS:
            assert ph not in str(rel) and ph.encode() not in data, (rel, ph)
    assert (proj / ".gitignore").is_file()
    assert not list(proj.rglob("gitignore"))
    if lang == "sh":
        assert os.access(proj / "demo", os.X_OK)
        assert os.access(proj / "test.sh", os.X_OK)
    skip_without_tools(lang)
    made = subprocess.run(["make", "test"], cwd=proj, capture_output=True, text=True)
    assert made.returncode == 0, made.stdout + made.stderr
    budget = subprocess.run([sys.executable, str(BUDGET), str(proj)],
                            capture_output=True, text=True)
    assert (budget.returncode, budget.stdout) == (0, "")


@pytest.mark.parametrize("lang", sorted(TOOLS))
def test_template_dist(tmp_path, lang):
    proj = generate(tmp_path, lang)
    skip_without_tools(lang)
    made = subprocess.run(["make", "dist"], cwd=proj, capture_output=True, text=True)
    assert made.returncode == 0, made.stdout + made.stderr
    tarballs = list(proj.glob("demo-*.tar.gz"))
    assert len(tarballs) == 1
    top = tarballs[0].name.removesuffix(".tar.gz")
    listed = subprocess.run(["tar", "-tzf", str(tarballs[0])], capture_output=True,
                            text=True, check=True).stdout.split()
    assert all(e == f"{top}/" or e.startswith(f"{top}/") for e in listed), listed
    for member in ("Makefile", "demo.1", "LICENSE"):
        assert f"{top}/{member}" in listed
    assert not [e for e in listed if "/target/" in e]


def test_existing_files_are_not_touched(tmp_path):
    assert run(["sh", "demo"], cwd=tmp_path).returncode == 0
    proj = tmp_path / "projects" / "demo"
    (proj / "README").write_text("mine\n")
    before = snapshot(proj)
    result = run(["sh", "demo"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("dl-new: ") and ": exists" in result.stderr
    assert snapshot(proj) == before


def test_partial_conflict_writes_nothing(tmp_path):
    dest = tmp_path / "projects" / "demo"
    dest.mkdir(parents=True)
    (dest / "Makefile").write_text("mine\n")
    result = run(["c", "demo"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr == "dl-new: projects/demo/Makefile: exists\n"
    assert snapshot(dest) == {Path("Makefile"): b"mine\n"}


def test_bad_name(tmp_path):
    result = run(["c", "Demo_1"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr == "dl-new: bad name Demo_1 (want ^[a-z][a-z0-9-]{0,31}$)\n"
    assert list(tmp_path.iterdir()) == []


def test_unknown_language(tmp_path):
    result = run(["go", "demo"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr == "dl-new: unknown language go (have: c rust rust-tui sh)\n"


def test_wrong_arg_count(tmp_path):
    result = run(["c"], cwd=tmp_path)
    assert (result.returncode, result.stderr) == (2, "dl-new: usage: dl-new LANG NAME [DEST]\n")


def test_dest_dot_in_empty_dir(tmp_path):
    result = run(["c", "demo", "."], cwd=tmp_path)
    assert (result.returncode, result.stderr) == (0, "")
    assert (tmp_path / "demo.c").is_file()
    assert (tmp_path / "demo.1").is_file()
