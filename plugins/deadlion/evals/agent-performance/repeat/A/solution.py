import csv
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from operator import index


def stable_sum(xs):
    # Every finite binary64 value is an integer multiple of 2**-1074.
    scale_bits = 1074
    total = 0
    for value in xs:
        numerator, denominator = value.as_integer_ratio()
        denominator_bits = denominator.bit_length() - 1
        total += numerator << (scale_bits - denominator_bits)
    return total / (1 << scale_bits)


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
        chunk = stream.read(65536)
        if chunk == b"":
            return total
        total += chunk.count(target)


def read_frame(sock, limit):
    def read_exactly(size):
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(min(size - len(data), 65536))
            if not chunk:
                raise EOFError("unexpected EOF while reading frame")
            data.extend(chunk)
        return bytes(data)

    length = int.from_bytes(read_exactly(4), "big")
    if length > limit:
        raise ValueError("frame length exceeds limit")
    return read_exactly(length)


def totals(conn):
    rows = conn.execute("""
        SELECT accounts.id, tx.amount
        FROM accounts
        LEFT JOIN tx ON tx.account_id = accounts.id
    """)
    # Python integers keep the sum exact even beyond SQLite's integer range.
    result = {}
    for account_id, amount in rows:
        result[account_id] = result.get(account_id, 0) + (amount or 0)
    return result


def solve(xs, queries):
    counts = Counter(xs)
    return [counts[query] for query in queries]