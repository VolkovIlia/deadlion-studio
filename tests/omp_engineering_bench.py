"""Paired scripted OMP startup-to-settle and model-input size measurements."""
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import threading
import time
from http.server import HTTPServer

from omp_engineering_smoke import PLUGIN, Transport, fixture


def measure():
    rows = []
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as server:
        root = Path(tmp)
        profile, project = fixture.setup(root, server.server_port)
        env = {**os.environ, "HOME": tmp, "PI_CONFIG_DIR": str(root / ".omp"), "XDG_STATE_HOME": str(root / "state"),
               "PI_CODING_AGENT_DIR": str(profile), "FIXTURE_API_KEY": "unused"}
        threading.Thread(target=server.serve_forever, daemon=True).start()
        subprocess.run(["omp", "plugin", "link", PLUGIN], env=env, check=True, stdout=subprocess.DEVNULL)
        for count in [12, 10000]:
            for i in range(count):
                (project / f"file{i}.py").write_text("def answer():\n    return 42\n" * 32)
            for rep in range(5):
                for enabled in ([False, True] if rep % 2 else [True, False]):
                    server.steps, server.context, server.calls = {}, [], 0
                    verdict = root / "outcome.json"
                    verdict.unlink(missing_ok=True)
                    start = time.perf_counter()
                    command = ["omp", "--offline", "--no-judge", "--no-spotlight", "--no-session", "-p"]
                    if not enabled:
                        command.append("--no-extensions")
                    subprocess.run([*command, "Summarize the task."], cwd=project,
                                   env={**env, "DL_VERDICT_FILE": str(verdict)}, capture_output=True,
                                   check=True, timeout=30)
                    elapsed = round(1000 * (time.perf_counter() - start))
                    assert verdict.exists() == enabled and server.calls == 1
                    rows.append(dict(files=count, repeat=rep, enabled=enabled, elapsed_ms=elapsed,
                                     messages_json_chars=len(server.context[0])))
    return dict(kernel=platform.release(), omp=subprocess.check_output(["omp", "--version"], text=True).strip(),
                transport="local scripted, one provider request", rows=rows)


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
