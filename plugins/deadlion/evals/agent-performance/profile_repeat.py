"""Optional repeat measurements with Python 3.13 and Memray 1.21."""
import ast
import json
from pathlib import Path
import runpy
import statistics
import tempfile
import time

import memray
from memray._memray import compute_statistics

ROOT = Path(__file__).resolve().parent
CASES = runpy.run_path(str(ROOT / "grade.py"))["CASES"]


def profile(directory):
    source = directory / "solution.py"
    functions = runpy.run_path(str(source))
    result = {}
    for check, name in CASES:
        with tempfile.TemporaryDirectory() as temp:
            capture = Path(temp) / "capture.bin"
            with memray.Tracker(capture, trace_python_allocators=True):
                check(functions[name])
            stats = compute_statistics(str(capture), report_progress=False)
            result[name] = dict(events=stats.total_num_allocations, bytes=stats.total_memory_allocated)
    sizes = {}
    for n in (16, 256, 4096, 65536):
        xs = list(range(n))
        expected = [1] * n
        times = []
        for _ in range(9):
            start = time.perf_counter_ns()
            actual = functions["solve"](xs, xs)
            times.append(time.perf_counter_ns() - start)
            assert actual == expected
        sizes[n] = statistics.median(times)
    branches = (ast.If, ast.IfExp, ast.For, ast.While, ast.ExceptHandler, ast.comprehension)
    return dict(allocations=result, membership_median_ns=sizes,
                branch_sites=sum(isinstance(node, branches) for node in ast.walk(ast.parse(source.read_text()))))


if __name__ == "__main__":
    print(json.dumps({arm: profile(ROOT / "repeat" / arm) for arm in "ABCD"}, indent=2))
