from collections import Counter


def solve(xs, queries):
    counts = Counter(xs)
    return [counts[query] for query in queries]