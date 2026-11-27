import csv
import math
import operator
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor


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
    workers = operator.index(workers)
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
        chunk = stream.read(65536)
        if not chunk:
            return total
        total += chunk.count(target)


def _recv_exactly(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(65536, size - len(data)))
        if not chunk:
            raise EOFError("socket closed before the frame was complete")
        data.extend(chunk)
    return bytes(data)


def read_frame(sock, limit):
    size = int.from_bytes(_recv_exactly(sock, 4), "big")
    if size > limit:
        raise ValueError("frame length exceeds limit")
    return _recv_exactly(sock, size)


def totals(conn):
    rows = conn.execute("""
        SELECT a.id, t.amount
        FROM accounts AS a
        LEFT JOIN tx AS t ON t.account_id = a.id
    """)
    # Python integers preserve totals that exceed SQLite's integer range.
    by_account = {}
    for account_id, amount in rows:
        by_account[account_id] = by_account.get(account_id, 0) + (amount or 0)
    return by_account