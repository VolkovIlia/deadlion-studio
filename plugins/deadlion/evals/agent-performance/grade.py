"""Independent grader. Run reviewed generated modules in an isolated process."""
import argparse
import collections
import io
import itertools
import json
import math
from pathlib import Path
import random
import runpy
import sqlite3
import statistics
import threading
import time
import tracemalloc


def collection(f):
    xs = list(range(-5000, 5000)) * 2
    qs = [0, 0, 123456] + xs
    assert f(xs, qs) == [2, 2, 0] + [2] * len(xs)
    assert f([], []) == []


def numeric(f):
    values = [1e16, 1., -1e16] * 6000
    assert f(values) == math.fsum(values)
    assert f([]) == 0


def graph(f):
    edges = [(i, i + 1) for i in range(5000)] + [(1, 0), (10000, 10001)]
    assert f(edges * 2, 0) == {i: i for i in range(5001)}
    assert f([], 12) == {12: 0}


def parsing(f):
    lines = iter(['"x,y","z""w"\n', '"a\n', 'b",c\n'])
    rows = iter(f(lines))
    assert next(rows) == ("x,y", 'z"w')
    assert next(rows) == ("a\nb", "c")
    assert list(rows) == []


def concurrency(f):
    tracker = collections.Counter()
    guard = threading.Lock()

    def source():
        for x in itertools.count():
            tracker["submitted"] += 1
            if tracker["submitted"] - tracker["returned"] > 4:
                raise ValueError("unbounded prefetch")
            yield x

    def work(x):
        with guard:
            tracker["active"] += 1
            tracker["peak"] = max(tracker["peak"], tracker["active"])
        time.sleep(.001)
        with guard:
            tracker["active"] -= 1
        return x * x

    results = f(work, source(), 4)
    try:
        for i in range(20):
            assert next(results) == i * i
            tracker["returned"] += 1
    finally:
        results.close()
    assert 1 < tracker["peak"] <= 4


class ShortReader(io.BytesIO):
    def read(self, n=-1):
        assert 0 < n <= 65536
        return super().read(min(n, 997))


def files(f):
    data = bytes(range(256)) * 1024
    assert f(ShortReader(data), 255) == 1024


class FragmentedSocket:
    def __init__(self, data):
        self.stream = io.BytesIO(data)

    def recv(self, n):
        return self.stream.read(min(n, 3))

    def recv_into(self, buffer, n=0):
        chunk = self.recv(n or len(buffer))
        buffer[:len(chunk)] = chunk
        return len(chunk)


def network(f):
    sock = FragmentedSocket(b"\x00\x00\x00\x05hello\x00\x00\x00\x00")
    assert f(sock, 5) == b"hello" and f(sock, 5) == b""
    for packet, error in [(b"\xff" * 4, ValueError), (b"\x00", EOFError),
                          (b"\x00\x00\x00\x01", EOFError)]:
        try:
            f(FragmentedSocket(packet), 5)
        except error:
            continue
        raise AssertionError("missing exception")


def database(f):
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript("CREATE TABLE accounts(id INTEGER PRIMARY KEY);"
                           "CREATE TABLE tx(account_id INTEGER, amount INTEGER);"
                           "INSERT INTO accounts VALUES(1),(2); INSERT INTO tx VALUES(2,3),(2,-1);")
        statements = []
        conn.set_trace_callback(statements.append)
        assert f(conn) == {1: 0, 2: 2}
        assert len(statements) == 1
    finally:
        conn.close()


CASES = [(collection, "solve"), (numeric, "stable_sum"), (graph, "distances"),
         (parsing, "parse_rows"), (concurrency, "parallel_map"), (files, "count_bytes"),
         (network, "read_frame"), (database, "totals")]


def evaluate(directory):
    env = {}
    for file in sorted(directory.glob("*.py")):
        env.update(runpy.run_path(str(file)))
    results = {}
    order = list(CASES)
    random.Random(923).shuffle(order)
    for check, symbol in order:
        try:
            check(env[symbol])
            timings = []
            for _ in range(9):
                start = time.perf_counter_ns()
                check(env[symbol])
                timings.append(time.perf_counter_ns() - start)
            tracemalloc.start()
            check(env[symbol])
            _, peak = tracemalloc.get_traced_memory()
            results[symbol] = dict(status="PASS", wall_ns=timings, median_ns=statistics.median(timings),
                                   traced_peak_bytes=peak)
        except Exception as error:
            results[symbol] = dict(status="FAIL", error=repr(error))
        finally:
            tracemalloc.stop()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(json.dumps(evaluate(parser.parse_args().directory), indent=2))
