#!/usr/bin/env python3
"""
Tests for plugins/deadlion/skills/ux-design/scripts/dl-contrast.

Fixtures live under pytest's tmp_path, outside any git repository.

Usage:
    pytest tests/test_dl_contrast.py -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "ux-design" / "scripts" / "dl-contrast"
PALETTE = (PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "scaffold" / "templates"
           / "rust-tui" / "src" / "config.def.rs")

GREY = 'pub const FG: &str = "#ffffff";\npub const BG: &str = "#777777";\n'


def run(args, cwd, env=None, stdin=None):
    """Run dl-contrast with only python3 on PATH and no DL_* settings, plus ENV."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("DL_")}
    full_env["PATH"] = str(Path(sys.executable).parent)
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, input=stdin,
        capture_output=True, text=True, env=full_env,
    )


def test_pair_below_default_min(tmp_path):
    (tmp_path / "cfg.rs").write_text(GREY + "// dl-contrast: FG BG\n")
    result = run(["cfg.rs"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "cfg.rs:3: contrast FG/BG is 4.48:1 (min 4.5)\n"


def test_explicit_min_passes(tmp_path):
    (tmp_path / "cfg.rs").write_text(GREY + "// dl-contrast: FG BG 3\n")
    result = run(["cfg.rs"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")


def test_css_tokens_short_hex(tmp_path):
    (tmp_path / "a.css").write_text(":root { --fg: #222; --bg: #fff; }\n"
                                    "/* dl-contrast: --fg --bg */\n")
    result = run(["a.css"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "")


def test_unknown_token(tmp_path):
    (tmp_path / "x.rs").write_text(GREY + "// dl-contrast: FG NOPE\n")
    result = run(["x.rs"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "x.rs:3: unknown token NOPE\n"


def test_directory_reports_only_failing_file(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "a.css").write_text(":root { --fg: #777; --bg: #fff; }\n"
                                          "/* dl-contrast: --fg --bg */\n")
    (tmp_path / "d" / "b.rs").write_text(GREY + "// dl-contrast: FG BG 3\n")
    result = run(["d"], cwd=tmp_path)
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith("d/a.css:")


def hook_input(path):
    return json.dumps({"tool_input": {"file_path": str(path)}})


def test_hook_mode(tmp_path):
    bad = tmp_path / "cfg.rs"
    bad.write_text(GREY + "// dl-contrast: FG BG\n")
    result = run(["--hook"], cwd=tmp_path, stdin=hook_input(bad))
    assert result.returncode == 2
    assert "contrast FG/BG" in result.stderr
    off = run(["--hook"], cwd=tmp_path, stdin=hook_input(bad), env={"DL_HOOKS": "0"})
    assert (off.returncode, off.stdout, off.stderr) == (0, "", "")
    plain = tmp_path / "plain.rs"
    plain.write_text(GREY)
    assert run(["--hook"], cwd=tmp_path, stdin=hook_input(plain)).returncode == 0


def test_missing_path(tmp_path):
    result = run(["nope"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("dl-contrast:")


def test_shipped_palette_passes(tmp_path):
    result = run([str(PALETTE)], cwd=tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_marker_mid_line_is_not_a_directive(tmp_path):
    (tmp_path / "notes.md").write_text(
        "Every pair gets a `dl-contrast: FG BG [MIN]` line.\n"
        'print("dl-contrast: usage: dl-contrast [--hook]")\n'
        "- dl-contrast: FG BG\n")
    result = run(["notes.md"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == "notes.md:3: unknown token FG\n"
