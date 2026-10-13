#!/usr/bin/env python3
"""
Tests for plugins/deadlion/skills/ui-verify/scripts/dl-tui.

Screen tests drive real programs through a private headless tmux server
and are skipped without tmux.

Usage:
    pytest tests/test_dl_tui.py -v
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "plugins" / "deadlion" / "skills" / "ui-verify" / "scripts" / "dl-tui"

needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")


def run(args, cwd, env=None):
    """Run dl-tui without DL_* settings, plus ENV."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("DL_")}
    full_env.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, env=full_env)


@needs_tmux
def test_typed_text_and_output(tmp_path):
    result = run(["-s", "20x4", 'printf "hi\\n"; cat', "text:abc", "key:Enter"],
                 cwd=tmp_path)
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "hi\nabc\nabc\n-- 20x4 running\n"


@needs_tmux
def test_exit_status_footer(tmp_path):
    result = run(["-s", "20x4", "echo hi; exit 3"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "hi\n-- 20x4 exit 3\n")


@needs_tmux
def test_signal_death_footer(tmp_path):
    result = run(["-s", "20x4", "kill -9 $$"], cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "-- 20x4 signal 9\n")


@needs_tmux
def test_ever_changing_screen_stops_at_deadline(tmp_path):
    endless = "i=0; while :; do i=$((i+1)); echo $i; done"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-s", "20x4", endless], cwd=tmp_path,
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "DL_TUI_SETTLE_MS": "300"})
    assert result.returncode == 0
    assert result.stdout.endswith("-- 20x4 running\n")


@needs_tmux
def test_sigterm_kills_tmux_server(tmp_path):
    endless = "while :; do date +%N; sleep 0.01; done"
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "-s", "20x4", endless], cwd=tmp_path,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "DL_TUI_SETTLE_MS": "60000"})
    socket = f"dl-tui-{proc.pid}"
    alive = lambda: subprocess.run(["tmux", "-L", socket, "has-session"],
                                   capture_output=True).returncode == 0
    for _ in range(100):
        if alive():
            break
        time.sleep(0.05)
    assert alive(), "tmux server never started"
    proc.terminate()
    assert proc.wait(timeout=10) == 128 + signal.SIGTERM
    assert not alive(), "tmux server outlived dl-tui"


@needs_tmux
def test_resize_then_snap(tmp_path):
    result = run(["-s", "20x4", "cat", "resize:10x3", "snap"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.split("\n")[0] == "-- 10x3 running"


@needs_tmux
def test_bad_step(tmp_path):
    result = run(["true", "bogus"], cwd=tmp_path)
    assert (result.returncode, result.stderr) == (2, "dl-tui: bad step bogus\n")


@needs_tmux
def test_bad_size(tmp_path):
    result = run(["-s", "0x5", "true"], cwd=tmp_path)
    assert (result.returncode, result.stderr) == (2, "dl-tui: bad size 0x5\n")


@needs_tmux
def test_no_args(tmp_path):
    result = run([], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stderr == "dl-tui: usage: dl-tui [-s COLSxROWS] CMD [STEP...]\n"


def test_tmux_missing(tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    result = run(["true"], cwd=tmp_path, env={"PATH": str(empty)})
    assert (result.returncode, result.stderr) == (2, "dl-tui: tmux not on PATH\n")
