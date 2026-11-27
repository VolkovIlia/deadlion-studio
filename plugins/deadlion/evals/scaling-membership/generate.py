"""Generate the same keys/probes and independent expected count for every implementation."""

import json
import random
import sys

request = json.load(sys.stdin)
rng = random.Random(request["seed"])
n, q = (request["dimensions"][k] for k in ("n", "q"))
distribution = request["distribution"]
keys = list(range(n))
if distribution == "duplicates":
    keys = [rng.randrange(max(1, n // 16)) for _ in keys]
elif distribution == "reverse":
    keys.reverse()
elif distribution == "nearly_sorted":
    for _ in range(n // 100):
        i, j = rng.randrange(n), rng.randrange(n)
        keys[i], keys[j] = keys[j], keys[i]
elif distribution == "skewed":
    keys = [min(n - 1, int(rng.paretovariate(1.5)) - 1) for _ in keys]
elif distribution == "sparse":
    keys = [k * 16 for k in keys]
elif distribution == "dense":
    keys = [k // 2 for k in keys]
elif distribution == "uniform":
    rng.shuffle(keys)
elif distribution not in ("sorted", "degenerate", "boundary", "all_miss"):
    raise ValueError("unknown distribution")
if distribution == "degenerate":
    keys = [0] * n
probes = [rng.randrange(2 * n) for _ in range(q)]
if distribution == "all_miss":
    probes = [-1] * q
elif distribution == "boundary":
    probes = [rng.choice([-1, 0, n - 1, n]) for _ in probes]
# Count probes by key then sum their multiplicities over distinct present keys.
from collections import Counter

counts = Counter(probes)
answer = sum(counts[key] for key in set(keys))
print(json.dumps(dict(input=json.dumps([keys, probes]), expected=str(answer) + "\n")))
