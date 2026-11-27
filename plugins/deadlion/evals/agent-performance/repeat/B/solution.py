import csv
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from math import fsum
from operator import index


def stable_sum(xs):
    return fsum(xs)


def distances(edges, start):
    neighbors = defaultdict(list)
    for source, target in edges:
        neighbors[source].append(target)

    hops = {start: 0}
    queue = deque([start])
    while queue:
        vertex = queue.popleft()
        for target in neighbors.get(vertex, ()):
            if target not in hops:
                hops[target] = hops[vertex] + 1
                queue.append(target)
    return hops


def parse_rows(lines):
    for row in csv.reader(lines):
        yield tuple(row)


def parallel_map(fn, xs, workers):
    workers = index(workers)
    pending = deque()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        try:
            for item in xs:
                pending.append(executor.submit(fn, item))
                if len(pending) == workers:
                    yield pending.popleft().result()

            while pending:
                yield pending.popleft().result()
        finally:
            for future in pending:
                future.cancel()


def count_bytes(stream, needle):
    target = bytes((needle,))
    count = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            return count
        count += chunk.count(target)


def _read_exactly(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(size - len(data), 65536))
        if not chunk:
            raise EOFError("truncated frame")
        data.extend(chunk)
    return bytes(data)


def read_frame(sock, limit):
    size = int.from_bytes(_read_exactly(sock, 4), "big")
    if size > limit:
        raise ValueError("frame length exceeds limit")
    return _read_exactly(sock, size)


def totals(conn):
    query = """
        SELECT a.id, COALESCE(t.amount, 0)
        FROM accounts AS a
        LEFT JOIN tx AS t ON t.account_id = a.id
    """
    # Python integers keep totals exact beyond SQLite's 64-bit SUM limit.
    balances = {}
    for account_id, amount in conn.execute(query):
        balances[account_id] = balances.get(account_id, 0) + amount
    return balances


def solve(xs, queries):
    counts = Counter(xs)
    return [counts[query] for query in queries]