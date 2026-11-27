"""Independent system fixtures with exchanged order and exact checksum oracles."""

import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "skills/performance/scripts"))
from candidate_runner import execute


def exercise():
    rows = []
    rng = random.Random(436261)
    for kernel in ("allocate", "traverse", "layout", "accumulate", "read_file"):
        for n in (4096, 16384, 65536, 262144):
            oracle = (n // 256) * sum(range(256)) + sum(range(n % 256))
            for repeat in range(3):
                order = [0, 1]
                rng.shuffle(order)
                for variant in order:
                    out, metrics = execute(
                        ROOT,
                        ["work.py"],
                        ["python3", "work.py", kernel, str(variant)],
                        str(n).encode(),
                        10,
                        160,
                    )
                    if int(out) != oracle:
                        raise ValueError(f"checksum failed for {kernel}")
                    rows.append(
                        dict(
                            kernel=kernel,
                            n=n,
                            variant=variant,
                            repeat=repeat,
                            **metrics,
                        )
                    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cpus = sorted(os.sched_getaffinity(0))
        chosen = []
        for cpu in cpus:
            core = (
                Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list")
                .read_text()
                .strip()
            )
            if core not in [k for k, _ in chosen]:
                chosen.append((core, cpu))
            if len(chosen) == 2:
                break
        if len(chosen) == 2:
            for stride in (1, 8):
                subprocess.run(
                    [
                        "cc",
                        "-O2",
                        "-std=c11",
                        "-pthread",
                        f"-DSTRIDE={stride}",
                        ROOT.parent / "false-sharing/counters.c",
                        "-o",
                        root / "kernel",
                    ],
                    check=True,
                )
                out, metrics = execute(
                    root,
                    ["kernel"],
                    ["./kernel", *[str(i) for _, i in chosen]],
                    b"",
                    5,
                    128,
                    cpu=200,
                )
                if int(out) != 2000000:
                    raise ValueError("incorrect relaxed counter total")
                rows.append(
                    dict(kernel="false-sharing", stride=stride, cpus=chosen, **metrics)
                )
    return rows


if __name__ == "__main__":
    print(json.dumps(exercise()))
