"""Compare strict workspace fingerprints on identical files against 4.5.0."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time

BASE = "25620d1f53d9982de19625ff199bb3591615d620"
SOURCE = "plugins/deadlion/omp/workspace.py"
REPO = Path(__file__).resolve().parents[1]


def measure(command, cwd):
    start = time.perf_counter_ns()
    result = subprocess.run(["/usr/bin/time", "-f", "%M", *command], cwd=cwd, capture_output=True, check=True)
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    return {"wall_ms": round(elapsed, 2), "rss_kib": int(result.stderr), "bytes": len(result.stdout)}, result.stdout


def benchmark(root, baseline, repetitions, sizes, mixed):
    project = root / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", project], check=True)
    if mixed:
        with (project / "binary.dat").open("wb") as file:
            file.truncate(16 << 20)
        (project / "long.txt").write_bytes(b"generated fixture\n" * 200_000)
    previous = 0
    for count in sizes:
        for i in range(previous, count):
            folder = project / str(i // 1000)
            if i % 1000 == 0:
                folder.mkdir()
            suffix = (".py", ".rs", ".kt", ".go")[i % 4] if mixed else ".py"
            (folder / f"{i}{suffix}").write_bytes(b"x = 1\n" * 128)
        previous = count
        readings = {"4.5.0": [], "4.6.0": []}
        scripts = {"4.5.0": baseline, "4.6.0": REPO / SOURCE}
        for index in range(repetitions):
            outputs = {}
            for version in sorted(scripts, reverse=bool(index % 2)):
                row, outputs[version] = measure(["python3", "-I", scripts[version]], project)
                readings[version].append(row)
            if json.loads(outputs["4.5.0"]) != json.loads(outputs["4.6.0"]):
                raise ValueError(f"strict snapshot differs at {count} files")
        yield {"files": count, "mixed": mixed, "samples": readings,
               "median_ms": {name: statistics.median(row["wall_ms"] for row in rows)
                             for name, rows in readings.items()}}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--repetitions", type=int, default=5)
    cli.add_argument("--mixed", action="store_true")
    cli.add_argument("--sizes", type=int, nargs="+", default=[10, 100, 1_000, 10_000, 100_000])
    args = cli.parse_args()
    if args.repetitions <= 0 or any(size <= 0 for size in args.sizes):
        cli.error("sizes and repetitions must be positive")
    with tempfile.TemporaryDirectory() as storage:
        root = Path(storage)
        baseline = root / "baseline.py"
        baseline.write_bytes(subprocess.check_output(["git", "show", BASE + ":" + SOURCE], cwd=REPO))
        print(json.dumps({"kernel": platform.release(), "cpu_count": os.cpu_count(), "baseline": BASE,
                          "rows": list(benchmark(root, baseline, args.repetitions, sorted(set(args.sizes)), args.mixed))},
                         indent=2))


if __name__ == "__main__":
    main()
