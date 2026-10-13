#!/usr/bin/env python3
"""
Tests for plugins/deadlion/skills/commit/scripts/dl-guard.

Regression context: the filename patterns describe secret-bearing DATA files,
but they were matched against the bare filename with re.match and no extension
check, so `^api[_-]?key` also matched the Vue component `ApiKeysModal.vue`.
Because the guard runs over ACMR files, *any* edit to that component was
blocked — for everyone, permanently.

Usage:
    pytest tests/test_dl_guard.py -v
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "commit" / "scripts" / "dl-guard"


def load_guard_module():
    """Import dl-guard despite the missing .py suffix."""
    loader = importlib.machinery.SourceFileLoader("dl_guard", str(SCRIPT))
    spec = importlib.util.spec_from_file_location("dl_guard", SCRIPT, loader=loader)
    assert spec is not None and spec.loader is not None, f"cannot load {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["dl_guard"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return load_guard_module()


def run(args, cwd, stdin="", env=None):
    """Run dl-guard with a DL_*-free environment plus ENV."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("DL_")}
    full_env.update(env or {})
    return subprocess.run(
        [str(SCRIPT), *args], cwd=cwd, input=stdin, capture_output=True,
        text=True, env=full_env,
    )


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    return tmp_path


# ---------------------------------------------------------------------------
# Embedded rule integrity
# ---------------------------------------------------------------------------


class TestRules:
    def test_source_code_extensions_declared(self, guard):
        extensions = guard.SOURCE_CODE_EXTENSIONS
        assert extensions, "SOURCE_CODE_EXTENSIONS must be declared"
        assert ".vue" in extensions
        assert all(e.startswith(".") for e in extensions)

    def test_prose_and_shell_stay_blocked(self, guard):
        """Markdown and shell scripts can carry pasted secrets — keep them in scope."""
        for risky in (".md", ".rst", ".sh", ".bash", ".env"):
            assert risky not in guard.SOURCE_CODE_EXTENSIONS

    def test_rule_tables_are_well_formed(self, guard):
        """Every embedded rule must be usable as written."""
        assert all(e.startswith(".") for e in guard.FORBIDDEN_EXTENSIONS)
        assert all(d.endswith("/") for d in guard.FORBIDDEN_DIRECTORIES)
        for pattern in guard.FORBIDDEN_PATTERNS:
            re.compile(pattern)
        assert all(kb > 0 for _, kb in guard.ALLOWED_PATTERNS)

    def test_secret_patterns_present(self, guard):
        """The patterns the old in-code fallback relied on must still exist."""
        required = {
            r"^\.env.*", r".*\.env$", r"^secrets?\.", r"^credentials?\.",
            r"^api[_-]?key", r"^auth[_-]?token", r".*password.*",
        }
        assert required <= set(guard.FORBIDDEN_PATTERNS)


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------

SECRET_FILES = [
    "api_key.json",
    "apikey.txt",
    "api-key.yaml",
    "config/API_KEYS.json",
    "auth_token.json",
    "authtoken.txt",
    "passwords.json",
    "secrets.yaml",
    "credentials.json",
    ".env",
    ".env.local",
    "docs/api-keys.md",
    "deploy_with_password.sh",
]

SOURCE_FILES = [
    "taska/src/components/modals/ApiKeysModal.vue",
    "src/services/apiKeyService.ts",
    "src/composables/useApiKeys.js",
    "tests/test_password_reset.py",
    "src/auth/AuthTokenProvider.java",
    "src/styles/password-field.scss",
]


class TestForbiddenPatterns:
    @pytest.mark.parametrize("filepath", SECRET_FILES)
    def test_secret_data_files_are_blocked(self, guard, filepath):
        assert guard.forbidden_pattern(filepath) is not None, filepath

    @pytest.mark.parametrize("filepath", SOURCE_FILES)
    def test_source_files_are_not_blocked(self, guard, filepath):
        assert guard.forbidden_pattern(filepath) is None, filepath

    def test_allowed_patterns_override_filename_patterns(self, guard):
        """Allowed patterns override forbidden rules, filename patterns included."""
        allowed = (("fixtures/api_key.json", 10),)
        assert guard.forbidden_pattern("fixtures/api_key.json", allowed) is None
        assert guard.forbidden_pattern("other/api_key.json", allowed) is not None

    def test_api_keys_modal_passes_cli(self, tmp_path):
        """ApiKeysModal.vue regression, end to end through the CLI."""
        modal = tmp_path / "ApiKeysModal.vue"
        modal.write_text("<template><div/></template>\n")
        result = run([modal.name], cwd=tmp_path)
        assert result.returncode == 0, result.stdout
        assert result.stdout == ""


class TestFileChecks:
    def test_forbidden_extension(self, guard):
        assert guard.check_file("v.mp4") == ["forbidden extension .mp4"]

    def test_compound_extension(self, guard):
        assert guard.forbidden_extension("a.tar.gz") == ".tar.gz"

    def test_forbidden_directory(self, guard):
        assert guard.check_file("web/node_modules/x/index.js") == [
            "forbidden directory node_modules/"]

    def test_skill_named_like_output_dir(self, guard):
        assert guard.forbidden_directory("plugins/p/skills/build/SKILL.md") is None
        assert guard.forbidden_directory("skills/dist/scripts/x") is None
        assert guard.forbidden_directory("plugins/p/skills/build/build/a.o") == "build/"
        assert guard.forbidden_directory("build/skills/x.c") == "build/"

    def test_secret_reason_text(self, guard):
        assert guard.check_file(".env.local") == [
            r"matches secret-file pattern ^\.env.*"]

    def test_allowed_pattern_overrides_extension(self, guard):
        assert guard.check_file("favicon.ico") == []

    def test_oversized_file(self, tmp_path):
        big = tmp_path / "big.txt"
        big.write_bytes(b"a" * (501 * 1024))
        result = run([big.name], cwd=tmp_path)
        assert result.returncode == 1
        assert result.stdout == "big.txt:1: exceeds 500 KB\n"

    def test_size_limit_env(self, tmp_path):
        small = tmp_path / "small.txt"
        small.write_bytes(b"a" * 2048)
        result = run([small.name], cwd=tmp_path, env={"DL_GUARD_MAX_KB": "1"})
        assert result.stdout == "small.txt:1: exceeds 1 KB\n"

    def test_binary_file(self, tmp_path):
        blob = tmp_path / "blob"
        blob.write_bytes(b"\x7fELF\x00\x01")
        result = run([blob.name], cwd=tmp_path)
        assert result.returncode == 1
        assert result.stdout == "blob:1: binary file\n"

    def test_missing_file_skipped(self, tmp_path):
        result = run(["gone.mp4"], cwd=tmp_path)
        assert (result.returncode, result.stdout) == (0, "")

    def test_file_count(self, tmp_path):
        names = []
        for i in range(3):
            (tmp_path / f"f{i}.txt").write_text("x\n")
            names.append(f"f{i}.txt")
        result = run(names, cwd=tmp_path, env={"DL_GUARD_MAX_FILES": "2"})
        assert result.returncode == 1
        assert result.stdout == "(commit):1: 3 files exceeds 2\n"

    def test_bad_option(self, tmp_path):
        result = run(["--nope"], cwd=tmp_path)
        assert result.returncode == 2
        assert result.stderr.startswith("dl-guard:")


class TestStagedAndHook:
    def test_staged_check(self, repo):
        (repo / "v.mp4").write_bytes(b"x")
        git(repo, "add", "v.mp4")
        result = run([], cwd=repo)
        assert result.returncode == 1
        assert result.stdout == "v.mp4:1: forbidden extension .mp4\n"

    def test_hook_ignores_non_commit(self, repo):
        payload = json.dumps({"tool_input": {"command": "git status"}})
        result = run(["--hook"], cwd=repo, stdin=payload)
        assert (result.returncode, result.stderr) == (0, "")

    def test_hook_blocks_commit_with_mp4(self, repo):
        (repo / "v.mp4").write_bytes(b"x")
        git(repo, "add", "v.mp4")
        payload = json.dumps({"tool_input": {"command": "git commit -m add"}})
        result = run(["--hook"], cwd=repo, stdin=payload)
        assert result.returncode == 2
        assert "v.mp4:1: forbidden extension .mp4" in result.stderr
        assert result.stdout == ""

    def test_hook_clean_commit(self, repo):
        (repo / "ok.py").write_text("x = 1\n")
        git(repo, "add", "ok.py")
        payload = json.dumps({"tool_input": {"command": "git commit -m ok"}})
        result = run(["--hook"], cwd=repo, stdin=payload)
        assert (result.returncode, result.stderr) == (0, "")

    def test_hook_disabled(self, repo):
        (repo / "v.mp4").write_bytes(b"x")
        git(repo, "add", "v.mp4")
        payload = json.dumps({"tool_input": {"command": "git commit -m add"}})
        result = run(["--hook"], cwd=repo, stdin=payload, env={"DL_HOOKS": "0"})
        assert result.returncode == 0

    def test_hook_malformed_json(self, repo):
        result = run(["--hook"], cwd=repo, stdin="{not json")
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
