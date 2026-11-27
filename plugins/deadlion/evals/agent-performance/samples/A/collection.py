from collections import Counter


def solve(xs, queries):
    counts = Counter(xs)
    return [counts[q] for q in queries]