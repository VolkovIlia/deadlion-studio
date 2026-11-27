from collections import Counter


def solve(xs, queries):
    counts = Counter(xs)
    return [counts.get(query, 0) for query in queries]