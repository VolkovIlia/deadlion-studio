"""Run the approved harness, agent shell, or verifier in separate PID/network namespaces."""

import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/performance/scripts")
)
from candidate_runner import capsule


def run(directory, mode, arguments):
    limits = json.loads((directory / "limits.json").read_text())
    if mode in ("verify", "benchmark") and limits.get("contracts"):
        import socket

        with socket.socket(socket.AF_UNIX) as connection:
            connection.connect(str(directory / "verifier.sock"))
            connection.sendall(b"B" if mode == "benchmark" else b"K")
            receipt = json.load(connection.makefile())
            if receipt["status"] != "VERIFIED":
                raise ValueError(receipt.get("reason", "contract evaluation failed"))
            if mode == "benchmark":
                print(f"METRIC cost={receipt['metric']}")
            else:
                print(json.dumps(receipt))
        return 0
    root = directory / "repo"
    files = limits["candidate_files"]
    prefix = capsule(root, files, files if mode == "shell" else ())[:-1]
    if mode == "shell":
        cmd = ["sh", "-c", arguments[0]]
    else:
        path = directory / ("harness" if mode == "benchmark" else "oracle")
        prefix += ["--ro-bind", str(path), "/entry"]
        cmd = ["/bin/sh", "/entry"] if mode == "benchmark" else ["/entry"]
    remaining = limits["deadline"] / 1000 - time.time()
    if remaining <= 0:
        raise ValueError("experiment deadline reached")

    def restrict():
        resource.setrlimit(resource.RLIMIT_FSIZE, (1048577, 1048577))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with tempfile.TemporaryFile() as output:
        trial = subprocess.run(
            [*prefix, "--remount-ro", "/proc", "--remount-ro", "/", "--", *cmd],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            preexec_fn=restrict,
            timeout=remaining,
        )
        if output.tell() > 1048576:
            raise ValueError("candidate output limit exceeded")
        output.seek(0)
        sys.stdout.buffer.write(output.read(1048576))
        return trial.returncode


if __name__ == "__main__":
    sys.exit(run(Path(os.environ["DL_EXPERIMENT"]), sys.argv[1], sys.argv[2:]))
