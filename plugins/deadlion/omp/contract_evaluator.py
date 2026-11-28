"""Evaluate fixed contracts outside OMP. Only training measurements enter agent context."""

import contextlib
import hashlib
import json
import uuid
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import time


def objective(report):
    scale = report.get("scaling")
    if scale is None:
        return report["median_ratio"], report["interval"]
    ratios = []
    for point in scale["comparisons"]:
        if scale["choice"] not in point["pair"]:
            continue
        bounds = point["interval"]
        if not bounds or min(bounds) <= 0:
            raise ValueError("insufficient paired scaling measurements")
        median = point["median_ratio"]
        ratios.append(
            (median, *bounds)
            if point["pair"][0] == scale["choice"]
            else (1 / median, 1 / bounds[1], 1 / bounds[0])
        )
    if not ratios:
        raise ValueError("missing scaling comparison")
    metric, low, high = map(max, zip(*ratios))
    return metric, [low, high]


@contextlib.contextmanager
def experiment_slice(limits):
    """Apply one shared limit to the controller, external grader and candidate services."""
    unit = "dlresearch" + uuid.uuid4().hex + ".slice"
    subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            "StartTransientUnit",
            "ssa(sv)a(sa(sv))",
            unit,
            "fail",
            "4",
            "MemoryMax",
            "t",
            str(limits["memory_mib"] * 1048576),
            "MemorySwapMax",
            "t",
            "0",
            "CPUQuotaPerSecUSec",
            "t",
            str(limits["cpu_percent"] * 10000),
            "TasksMax",
            "t",
            "128",
            "0",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    try:
        yield unit
    finally:
        subprocess.run(["systemctl", "--user", "stop", unit], check=True)


@contextlib.contextmanager
def evaluator(directory, limits, unit=None):
    paths = limits.get("contracts")
    if not paths:
        yield
        return
    gate = (
        Path(__file__).resolve().parents[1] / "skills/performance/scripts/dl-perf-gate"
    )
    repo = directory / "repo"
    receipt = None

    def identity():
        return [
            (name, hashlib.sha256((repo / name).read_bytes()).hexdigest())
            for name in limits["candidate_files"]
        ]

    def evaluate(ordinal):
        contract = Path(paths[ordinal])
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f"evidence-{ordinal}-", suffix=".json", delete=False
        ) as output:
            command = [sys.executable, gate, contract, "--candidate-dir", repo, "--isolated"]
            if unit:
                remaining = max(0.01, limits["deadline"] / 1000 - time.time())
                command = [
                    "systemd-run",
                    "--user",
                    "--wait",
                    "--collect",
                    "--pipe",
                    "--quiet",
                    "--slice=" + unit,
                    "--setenv=PATH=" + str(Path(sys.executable).parent) + ":/usr/local/bin:/usr/bin:/bin",
                    "--setenv=DL_EVALUATOR_SLICE=" + unit,
                    "--setenv=DL_EVALUATOR_DEADLINE=" + str(limits["deadline"] / 1000),
                    "-p",
                    f"RuntimeMaxSec={remaining:.4f}",
                    "-p",
                    "TimeoutStopSec=0.1",
                    "--working-directory=" + str(contract.parent),
                    "--",
                    *command,
                ]
            trial = subprocess.run(
                command,
                cwd=contract.parent,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=max(0.01, limits["deadline"] / 1000 - time.time()),
            )
        try:
            report = json.loads(Path(output.name).read_bytes())
        except ValueError as error:
            raise ValueError(f"approved contract produced no report (exit {trial.returncode})") from error
        if trial.returncode:
            reason = str(report.get("reason", report.get("status", "no status")))
            raise ValueError("approved contract rejected the candidate: " + reason[:400])
        if report["status"] != "VERIFIED":
            raise ValueError("missing verification")
        return report

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            nonlocal receipt
            response = {"status": "NOT VERIFIED"}
            try:
                self.request.settimeout(2)
                operation = self.request.recv(1)
                before = identity()
                if operation == b"B":
                    receipt = None
                    training = evaluate(0)
                    metric, interval = objective(training)
                    seen = {training["input_sha256"]} | {
                        r["input_sha256"]
                        for r in training.get("scaling", {}).get("rows", [])
                    }
                    if before != identity():
                        raise ValueError("candidate changed during training")
                    receipt = before, metric, interval, seen
                elif operation == b"K" and receipt and receipt[0] == before:
                    _, metric, interval, seen = receipt
                    receipt = None
                    holdout = evaluate(1)
                    control = {
                        r["input_sha256"]
                        for r in holdout.get("scaling", {}).get("rows", [])
                    } or {holdout["input_sha256"]}
                    if control & seen:
                        raise ValueError("holdout reuses a training workload")
                    if before != identity():
                        raise ValueError("candidate changed during holdout")
                else:
                    raise ValueError("fresh verified training measurement required")
                response = dict(status="VERIFIED", metric=metric, interval=interval)
            except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
                response["reason"] = str(error)
            try:
                self.request.sendall(json.dumps(response).encode())
            except (BrokenPipeError, ConnectionResetError):
                receipt = None

    address = directory / "verifier.sock"
    address.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(str(address), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield
        finally:
            server.shutdown()
            thread.join()
            address.unlink(missing_ok=True)
