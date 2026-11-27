"""Equivalent checksums for small resource-sensitive kernel pairs."""

from array import array
from concurrent.futures import ThreadPoolExecutor
import os
import sys
import tempfile
import threading


def allocate(n, reuse):
    shared = bytearray(256)
    total = 0
    for i in range(n):
        block = shared if reuse else bytearray(256)
        block[0] = i % 256
        total += block[0]
    return total


def traverse(n, stride):
    values = bytearray(range(256)) * ((n + 255) // 256)
    return sum(values[i] for offset in range(stride) for i in range(offset, n, stride))


def layout(n, soa):
    if soa:
        keys = array("B", (i % 256 for i in range(n)))
        payloads = array("q", range(n))
        assert len(keys) == len(payloads)
        return sum(keys)
    pairs = [(i % 256, i) for i in range(n)]
    return sum(pair[0] for pair in pairs)


def accumulate(n, shared):
    total = 0
    lock = threading.Lock()

    def task(offset):
        nonlocal total
        local = 0
        for i in range(offset, n, 4):
            if shared:
                with lock:
                    total += i % 256
            else:
                local += i % 256
        return local

    with ThreadPoolExecutor(4) as pool:
        parts = list(pool.map(task, range(4)))
    return total + sum(parts)


def read_file(n, parallel):
    with tempfile.TemporaryFile() as f:
        f.write((bytes(range(256)) * ((n + 255) // 256))[:n])
        f.flush()

        def chunk(start):
            return sum(os.pread(f.fileno(), min(4096, n - start), start))

        offsets = range(0, n, 4096)
        if parallel:
            with ThreadPoolExecutor(4) as pool:
                return sum(pool.map(chunk, offsets))
        return sum(map(chunk, offsets))


if __name__ == "__main__":
    kernels = {
        "allocate": allocate,
        "traverse": traverse,
        "layout": layout,
        "accumulate": accumulate,
        "read_file": read_file,
    }
    key, variant = sys.argv[1:]
    n = int(sys.stdin.readline())
    assert 0 < n <= 2**20
    print(
        kernels[key](
            n, (64 if int(variant) else 1) if key == "traverse" else int(variant)
        )
    )
