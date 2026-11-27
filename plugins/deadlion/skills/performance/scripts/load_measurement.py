"""Bounded, closed-loop load measurement for deterministic command requests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import queue
import subprocess
import time


def sample(command, workload, expected, timeout):
    start = time.perf_counter_ns()
    result = subprocess.run(command, input=workload, stdout=subprocess.PIPE, timeout=timeout, check=True)
    elapsed = time.perf_counter_ns() - start
    if hashlib.sha256(result.stdout).digest() != expected:
        raise ValueError("incorrect response during load measurement")
    return elapsed


def run(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not (100 <= args.requests <= 100000 and 1 <= args.workers <= min(args.requests, 128)
                           and 0 < args.timeout <= 3600):
        parser.error("supply a command, 100..100000 requests, 1..128 workers and a finite timeout")
    workload = args.input.read_bytes()
    expected = hashlib.sha256(args.expected.read_bytes()).digest()
    sample(command, workload, expected, args.timeout)
    tickets = queue.SimpleQueue()
    for _ in range(args.requests):
        tickets.put(None)

    def worker():
        timings = []
        while True:
            try:
                tickets.get_nowait()
            except queue.Empty:
                return timings
            timings.append(sample(command, workload, expected, args.timeout))

    start = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker) for _ in range(args.workers)]
        samples = [value for future in futures for value in future.result()]
    elapsed = time.perf_counter_ns() - start
    ordered = sorted(samples)
    percentiles = {f"p{p}": ordered[math.ceil(len(samples) * p / 100) - 1] for p in (50, 95, 99)}
    print(json.dumps(dict(status="MEASURED", requests=len(samples), workers=args.workers,
                          requests_per_second=len(samples) * 1e9 / elapsed, latency_ns=percentiles,
                          raw_latency_ns=samples, input_sha256=hashlib.sha256(workload).hexdigest(),
                          expected_sha256=expected.hex(), elapsed_ns=elapsed, command=command)))
    return 0
