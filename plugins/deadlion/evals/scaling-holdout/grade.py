"""Independent operation-count fixtures. No timing-dependent assertions."""

import bisect
from collections import deque
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "skills/performance/scripts")
)
from growth_models import analyze


class Ordered:
    def __init__(self, key, counter):
        self.key = key
        self.counter = counter

    def __lt__(self, other):
        self.counter[0] += 1
        return self.key < other.key


def comparisons(n, seed, algorithm):
    count = [0]
    items = [Ordered(i, count) for i in range(n)]
    if algorithm == "sort":
        random.Random(seed).shuffle(items)
        items.sort()
    else:
        bisect.bisect_left(items, Ordered(n, count))
    return count[0]


def walk(n, edges):
    graph = [[] for _ in range(n)]
    for a in range(n - 1):
        graph[a].append(a + 1)
    for i in range(edges - (n - 1)):
        graph[i % n].append((3 * i + 1) % n)
    seen = {0}
    queue = deque([0])
    visits = 0
    while queue:
        v = queue.popleft()
        visits += 1
        for w in graph[v]:
            visits += 1
            if w not in seen:
                seen.add(w)
                queue.append(w)
    return visits


def fibonacci(n, cached):
    memory = {}

    def count(k):
        if k < 2 or k in memory:
            return 1
        cost = 1 + count(k - 1) + count(k - 2)
        if cached:
            memory[k] = True
        return cost

    return count(n)


def grade():
    families = ["constant", "log", "linear", "linearithmic", "quadratic", "cubic"]
    cases = [
        ("binary_search", lambda n, s: comparisons(n, s, "search"), "log", families),
        (
            "random_sort",
            lambda n, s: comparisons(n, s, "sort"),
            "linearithmic",
            families,
        ),
        ("read_once", lambda n, s: sum(1 for _ in range(n)), "linear", families),
        ("one_access", lambda n, s: 1, "constant", families),
        (
            "pairs",
            lambda n, s: sum(1 for _ in range(n) for _ in range(n)),
            "quadratic",
            families,
        ),
        (
            "cubes",
            lambda n, s: sum(1 for _ in range(n) for _ in range(n) for _ in range(n)),
            "cubic",
            families,
        ),
        ("memoized_fib", lambda n, s: fibonacci(n, True), "linear", families),
        (
            "recursive_fib",
            lambda n, s: fibonacci(n, False),
            "1.618**n",
            ["linear", "quadratic", "1.618**n"],
        ),
        ("launch_dominated", lambda n, s: 1000000 + n, "linear", families),
        (
            "outliers",
            lambda n, s: (
                n * (8 if s % 7 == 0 else random.Random(s).uniform(0.96, 1.04))
            ),
            "linear",
            families,
        ),
    ]
    results = {}
    for name, work, truth, models in cases:
        sizes = (
            range(4, 25, 2)
            if "fib" in name or name == "cubes"
            else [4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256]
        )
        rows = [
            dict(dimensions=dict(n=n), ops=work(n, seed))
            for n in sizes
            for seed in range(706, 717)
        ]
        results[name] = score(rows, models, ["n"], truth)
    rows = [
        dict(dimensions=dict(V=v, E=e), ops=walk(v, e))
        for v in (8, 12, 18, 30, 48)
        for e in (50, 80, 160, 320, 640)
        for _ in range(11)
    ]
    results["bfs"] = score(rows, ["V+E", "V*E", "V**2+E", "V", "E"], ["V", "E"], "V+E")
    return results


def score(rows, models, dimensions, truth):
    r = analyze(rows, models, dimensions, "ops", 0.12)
    unique = r["status"] == "EMPIRICALLY CONSISTENT"
    return dict(
        expected=truth,
        status=r["status"],
        models=r["admissible"],
        decision=("correct" if truth in r["admissible"] else "false_positive")
        if unique
        else "abstained",
        samples=len(rows),
        sha256=hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
    )


if __name__ == "__main__":
    print(json.dumps(grade(), indent=2))
