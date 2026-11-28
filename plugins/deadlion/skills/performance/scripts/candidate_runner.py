"""Linux candidate execution. The service owns the process tree and resource limits."""

import ctypes
import json
import math
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def runtime():
    mounts = []
    for name in ("bin", "sbin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            mounts.extend(["--symlink", os.readlink(path), str(path)])
        elif path.exists():
            mounts.extend(["--ro-bind", str(path), str(path)])
    for name in ("bin", "sbin", "lib", "lib64", "share"):
        path = Path("/usr") / name
        if path.exists():
            mounts.extend(["--ro-bind", str(path), str(path)])
    return mounts


def capsule(root, files, writable=()):
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LC_ALL",
        "C",
        "--setenv",
        "HOME",
        "/tmp",
        *runtime(),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/work",
    ]
    for name in files:
        path = root / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or path.resolve() != path
            or not path.is_file()
        ):
            raise ValueError(f"expected regular relative input file: {name}")
        command.extend(
            ["--bind" if name in writable else "--ro-bind", str(path), "/work/" + name]
        )
    return [*command, "--chdir", "/work", "--"]


def require_cgroup(limits):
    hierarchy = next(
        (
            line[3:]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        ),
        None,
    )
    if hierarchy is None:
        raise ValueError("cgroup v2 unavailable")
    group = Path("/sys/fs/cgroup") / hierarchy.lstrip("/")
    for name, maximum in (
        ("memory.max", limits["memory_mib"] * 1048576),
        ("memory.swap.max", 0),
        ("pids.max", 32),
    ):
        value = (group / name).read_text().strip()
        if value == "max" or int(value) > maximum:
            raise ValueError(f"required {name} unavailable")
    quota, period = (group / "cpu.max").read_text().split()
    if quota == "max" or int(quota) * 100 > limits["cpu"] * int(period):
        raise ValueError("required cpu.max unavailable")


def worker(directory):
    require_cgroup(json.loads((directory / "limits").read_bytes()))
    argv = json.loads((directory / "argv").read_text())
    # Bubblewrap's PID-namespace init can be reparented to the service manager.
    # Adopt it here so wait4 includes the measured program and its waited children.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot adopt candidate descendants")
    usages = []
    with (
        (directory / "stdin").open("rb") as src,
        (directory / "stdout").open("wb") as out,
    ):
        start = time.perf_counter_ns()
        proc = subprocess.Popen(argv, stdin=src, stdout=out, stderr=subprocess.DEVNULL)
        while True:
            try:
                pid, status, usage = os.wait4(-1, 0)
            except ChildProcessError:
                break
            usages.append(usage)
            if pid == proc.pid:
                proc.returncode = os.waitstatus_to_exitcode(status)
        elapsed = time.perf_counter_ns() - start
    if proc.returncode:
        raise ValueError(f"candidate or sandbox exited {proc.returncode}")
    metrics = dict(
        wall_ns=elapsed,
        user_cpu_s=sum(u.ru_utime for u in usages),
        system_cpu_s=sum(u.ru_stime for u in usages),
        peak_rss_kib=max(u.ru_maxrss for u in usages),
        cpu_time_s=sum(u.ru_utime + u.ru_stime for u in usages),
        voluntary_switches=sum(u.ru_nvcsw for u in usages),
        involuntary_switches=sum(u.ru_nivcsw for u in usages),
    )
    (directory / "metrics").write_text(json.dumps(metrics))


def execute(
    root,
    files,
    argv,
    data,
    timeout,
    memory_mib,
    output_bytes=1048576,
    cpu=100,
    state=None,
    pmu=False,
):
    if "DL_EVALUATOR_DEADLINE" in os.environ:
        timeout = min(timeout, float(os.environ["DL_EVALUATOR_DEADLINE"]) - time.time())
    if timeout <= 0:
        raise TimeoutError("experiment deadline reached")
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "limits").write_text(
            json.dumps(dict(memory_mib=memory_mib, cpu=cpu))
        )
        command = capsule(root, files)[:-1]
        outputs = {}
        for i, name in enumerate(state or {}):
            if not name.isidentifier() or name in files or i >= 16:
                raise ValueError("invalid state output name")
            output = directory / f"state-{i}"
            output.touch()
            outputs[name] = output
            command.extend(["--bind", str(output), "/work/" + name])
        measured = command + ["--remount-ro", "/proc", "--remount-ro", "/", "--"] + argv
        events = ["cycles", "instructions", "branches", "branch-misses", "cache-misses"]
        if pmu:
            binary = shutil.which("perf")
            if not binary:
                raise ValueError("perf missing")
            perf = [
                binary,
                "stat",
                "--all-user",
                "--no-big-num",
                "-x",
                ";",
                "-o",
                str(directory / "perf"),
            ]
            if Path("/sys/bus/event_source/devices/cpu_atom").exists():
                perf.append("--hybrid-merge")
            measured = [*perf, "-e", ",".join(events), "--", *measured]
        (directory / "argv").write_text(json.dumps(measured))
        (directory / "stdin").write_bytes(data)
        command = [
            "systemd-run",
            "--user",
            "--wait",
            "--collect",
            "--pipe",
            "--quiet",
            "--service-type=exec",
            "-p",
            f"MemoryMax={memory_mib}M",
            "-p",
            "MemorySwapMax=0",
            "-p",
            f"CPUQuota={cpu}%",
            "-p",
            "TasksMax=32",
            "-p",
            f"RuntimeMaxSec={timeout:.4f}",
            "-p",
            "TimeoutStopSec=0.1",
            "-p",
            "LimitCORE=0",
            "-p",
            f"LimitFSIZE={output_bytes + 1}",
            "/usr/bin/python3",
            "-I",
            str(Path(__file__).resolve()),
            tmp,
        ]
        if unit := os.environ.get("DL_EVALUATOR_SLICE"):
            command.insert(2, "--slice=" + unit)
        result = subprocess.run(
            command, capture_output=True, timeout=math.ceil(timeout) + 3
        )
        if result.returncode or not (directory / "metrics").exists():
            detail = result.stderr.decode(errors="replace").strip()[-600:]
            message = "candidate service failed or exhausted its budget"
            raise ValueError(message + (". " + detail if detail else ""))
        output = (directory / "stdout").read_bytes()
        if len(output) > output_bytes:
            raise ValueError("candidate exceeded output limit")
        for name, path in outputs.items():
            if path.stat().st_size > output_bytes:
                raise ValueError("state exceeds output limit")
            state[name] = path.read_bytes()
        metrics = json.loads((directory / "metrics").read_text())
        if pmu:
            counters = {}
            for line in (directory / "perf").read_text().splitlines():
                if line and not line.startswith("#"):
                    value, _, name, *_ = line.split(";")
                    counters[name] = float(value)
            if counters.keys() != set(events) or not all(
                math.isfinite(x) and x >= 0 for x in counters.values()
            ):
                raise ValueError("missing PMU counters")
            metrics.update(counters)
        return output, metrics


if __name__ == "__main__":
    worker(Path(sys.argv[1]))
