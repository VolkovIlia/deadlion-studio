import csv
import math
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from operator import index


_CHUNK_SIZE = 65536


def stable_sum(xs):
    return math.fsum(xs)


def distances(edges, start):
    neighbors = defaultdict(list)
    for source, target in edges:
        neighbors[source].append(target)

    hops = {start: 0}
    queue = deque([start])
    while queue:
        source = queue.popleft()
        for target in neighbors.get(source, ()):
            if target not in hops:
                hops[target] = hops[source] + 1
                queue.append(target)
    return hops


def parse_rows(lines):
    for row in csv.reader(lines):
        yield tuple(row)


def parallel_map(fn, xs, workers):
    """Yield in order. Closing cancels queued calls and waits for running calls."""
    workers = index(workers)
    pending = deque()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            for item in xs:
                pending.append(pool.submit(fn, item))
                if len(pending) == workers:
                    yield pending.popleft().result()
            while pending:
                yield pending.popleft().result()
        finally:
            for future in pending:
                future.cancel()


def count_bytes(stream, needle):
    pattern = bytes((needle,))
    count = 0
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            return count
        count += chunk.count(pattern)


def _read_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(_CHUNK_SIZE, size - len(data)))
        if not chunk:
            raise EOFError("unexpected EOF in frame")
        data.extend(chunk)
    return bytes(data)


def read_frame(sock, limit):
    size = int.from_bytes(_read_exact(sock, 4), "big")
    if size > limit:
        raise ValueError("frame length exceeds limit")
    return _read_exact(sock, size)


def totals(conn):
    rows = conn.execute("""
        SELECT a.id, COALESCE(t.amount, 0)
        FROM accounts AS a
        LEFT JOIN tx AS t ON t.account_id = a.id
    """)
    # Accumulate in Python so totals can exceed SQLite's signed integer range.
    result = {}
    for account_id, amount in rows:
        result[account_id] = result.get(account_id, 0) + amount
    return result


def solve(xs, queries):
    counts = Counter(xs)
    return [counts[query] for query in queries]