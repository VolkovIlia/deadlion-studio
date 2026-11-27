import csv
import math
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from operator import index


_CHUNK_SIZE = 65536


def stable_sum(xs):
    return math.fsum(xs)


def distances(edges, start):
    outgoing = defaultdict(list)
    for source, target in edges:
        outgoing[source].append(target)

    hops = {start: 0}
    queue = deque([start])
    while queue:
        source = queue.popleft()
        for target in outgoing.get(source, ()):
            if target in hops:
                continue
            hops[target] = hops[source] + 1
            queue.append(target)
    return hops


def parse_rows(lines):
    for row in csv.reader(lines):
        yield tuple(row)


def parallel_map(fn, xs, workers):
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
    target = bytes([needle])
    total = 0
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            return total
        total += chunk.count(target)


def _recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(size - len(data), _CHUNK_SIZE))
        if not chunk:
            raise EOFError("truncated frame")
        data.extend(chunk)
    return bytes(data)


def read_frame(sock, limit):
    size = int.from_bytes(_recv_exact(sock, 4), "big")
    if size > limit:
        raise ValueError("frame length exceeds limit")
    return _recv_exact(sock, size)


def totals(conn):
    query = """
        SELECT a.id, COALESCE(t.amount, 0)
        FROM accounts AS a
        LEFT JOIN tx AS t ON t.account_id = a.id
    """
    # Accumulate in Python so totals can exceed SQLite's integer range.
    balances = {}
    for account_id, amount in conn.execute(query):
        balances[account_id] = balances.get(account_id, 0) + amount
    return balances