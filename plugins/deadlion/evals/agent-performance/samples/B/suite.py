import csv
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from math import fsum
from operator import index


_CHUNK_SIZE = 65536


def stable_sum(xs):
    return fsum(xs)


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
    total = 0
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            return total
        total += chunk.count(target)


def _read_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(size - len(data), _CHUNK_SIZE))
        if not chunk:
            raise EOFError("connection closed before frame was complete")
        data.extend(chunk)
    return bytes(data)


def read_frame(sock, limit):
    size = int.from_bytes(_read_exact(sock, 4), "big")
    if size > limit:
        raise ValueError("frame length exceeds limit")
    return _read_exact(sock, size)


def totals(conn):
    rows = conn.execute("""
        SELECT accounts.id, COALESCE(tx.amount, 0)
        FROM accounts
        LEFT JOIN tx ON tx.account_id = accounts.id
    """)
    # Accumulate in Python so integer totals can exceed SQLite's 64-bit range.
    result = {}
    for account_id, amount in rows:
        result[account_id] = result.get(account_id, 0) + amount
    return result