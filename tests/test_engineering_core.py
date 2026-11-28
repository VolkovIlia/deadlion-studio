"""Regressions in the shared reporting format and task snapshots."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_correlated_reports_keep_origins_and_distinct_expressions():
    directory = ROOT / "plugins/deadlion/skills/performance/scripts"
    hints = load(directory / "python_hints.py").hints
    aggregate = load(directory / "diagnostic_report.py").aggregate
    matches = list(hints("sample.py", "for item in keys: a.copy(); b.copy()"))
    corroboration = dict(matches[0], source="second analyzer", rule="another-rule")
    report = aggregate([*matches, corroboration])
    assert len(report) == 2
    assert [len(d["provenance"]) for d in report] == [2, 1]
    assert all(d["evidenceLevel"] == "HEURISTIC" for d in report)


def test_index_changes_and_user_edits_have_separate_fingerprints(tmp_path, monkeypatch):
    module = load(ROOT / "plugins/deadlion/omp/workspace.py")
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    file = tmp_path / "user.py"
    file.write_text("old")
    subprocess.run(["git", "add", "user.py"], check=True)
    file.write_text("user edit")
    first = module.snapshot()["files"]["user.py"]
    subprocess.run(["git", "add", "user.py"], check=True)
    staged = module.snapshot()["files"]["user.py"]
    assert first[0] != staged[0] and first[1] == staged[1]


def test_non_git_snapshot_finds_move_delete_and_new(tmp_path, monkeypatch):
    module = load(ROOT / "plugins/deadlion/omp/workspace.py")
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "before.py"
    file.write_text("original")
    original = module.snapshot()
    file.rename(tmp_path / "after.py")
    (tmp_path / "generated.py").touch()
    current = module.snapshot()
    assert not current["git"] and set(current["files"]) == {"after.py", "generated.py"}
    assert original["files"]["before.py"] == current["files"]["after.py"]


@pytest.mark.skipif(not shutil.which("cargo-clippy"), reason="cargo-clippy unavailable")
def test_workspace_member_clippy_points_to_source(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers=["member"]\nresolver="2"\n')
    root = tmp_path / "member"
    (root / "src").mkdir(parents=True)
    (root / "Cargo.toml").write_text('[package]\nname="fixture"\nversion="0.1.0"\nedition="2021"\n')
    path = root / "src/lib.rs"
    path.write_text("pub fn copy(x: &[String])->Vec<String> { x.iter().cloned().collect() }")
    native = load(ROOT / "plugins/deadlion/skills/performance/scripts/native_diagnostics.py")
    findings = list(native.review([path], {}))
    assert [(row["file"], row["rule"]) for row in findings] == [(str(path), "clippy::iter_cloned_collect")]


def test_compilation_database_matches_translation_unit(tmp_path, monkeypatch):
    native = load(ROOT / "plugins/deadlion/skills/performance/scripts/native_diagnostics.py")
    file = tmp_path / "translation.c"
    file.touch()
    db = tmp_path / "nonstandard/compile_commands.json"
    db.parent.mkdir()
    db.write_text(json.dumps([dict(file="unrelated.c", directory=str(tmp_path))]))
    monkeypatch.setenv("DL_COMPILE_COMMANDS", str(db))
    assert native.project_for(file) == ("clang-tidy", None)
    db.write_text(json.dumps([dict(file=file.name, directory=str(tmp_path))]))
    assert native.project_for(file) == ("clang-tidy", (db.parent, db.name))
