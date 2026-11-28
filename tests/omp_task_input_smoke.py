"""Exercise draft retention at an explicit budget limit in a real OMP TUI."""
import os
from pathlib import Path
import tempfile
import threading
from http.server import HTTPServer

import pexpect

from omp_engineering_smoke import PLUGIN, Transport, fixture

PROMPT = "Review the work after timeout"


class HeldTransport(Transport):
    def do_POST(self):
        assert isinstance(self.server, LocalServer)
        self.server.release.wait(8)
        super().do_POST()


class LocalServer(HTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), HeldTransport)
        self.calls = 0
        self.context: list[str] = []
        self.steps = {}
        self.release = threading.Event()


def assert_recovery(proc, server, columns):
    proc.expect_exact("Deadlion: working…")
    proc.expect_exact("wall-clock budget exhausted")
    server.release.set()
    proc.send(PROMPT + "\r")
    proc.expect_exact("Deadlion · NOT VERIFIED")
    proc.expect_exact(PROMPT)
    assert "Deadlion: start a new task?" not in proc.before
    assert not any(PROMPT in context for context in server.context), server.context
    print(f"{columns} columns: timed-out task retains the draft without asking for confirmation", flush=True)


def smoke(rows, columns):
    with tempfile.TemporaryDirectory() as tmp, LocalServer() as server:
        directory = Path(tmp)
        profile, source = fixture.setup(directory, server.server_port)
        with (profile / "config.yml").open("a") as config:
            config.write("startup:\n  setupWizard: false\n")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        policy = directory / "policy.json"
        policy.write_text('{"seconds": 2}')
        env = {**os.environ, "HOME": tmp, "PI_CONFIG_DIR": str(directory / ".omp"),
               "PI_CODING_AGENT_DIR": str(profile), "XDG_STATE_HOME": str(directory / "state"),
               "FIXTURE_API_KEY": "fixture", "DL_ENGINEERING_POLICY": str(policy), "TERM": "xterm-256color"}
        args = ["--offline", "--no-judge", "--no-spotlight", "--no-session",
                "-e", str(PLUGIN / "omp/performance.mjs"), "Initial task"]
        proc = pexpect.spawn("omp", args, cwd=str(source), env=env, dimensions=(rows, columns),
                             encoding="utf-8", timeout=6)
        try:
            assert_recovery(proc, server, columns)
        finally:
            server.release.set()
            proc.terminate(force=True)
            server.shutdown()


if __name__ == "__main__":
    smoke(24, 80)
    smoke(12, 40)
