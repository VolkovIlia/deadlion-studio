import json
import random
import sys

settings = json.load(sys.stdin)
size = settings["dimensions"]["n"]
rng = random.Random(settings["seed"])
counts = [0] * 513
values = []
for i in range(size):
    if settings["distribution"] == "uniform":
        v = rng.randrange(513)
    elif settings["distribution"] == "reverse":
        v = 512 - 512 * i // size
    else:
        raise ValueError("unsupported distribution")
    counts[v] += 1
    values.append(str(v - 256))
expected = "".join((str(i - 256) + "\n") * count for i, count in enumerate(counts))
print(json.dumps(dict(input="\n".join(values) + "\n", expected=expected)))
