"""Measure a single probe on a two-element input, including index preparation."""
import sys

values = [0, 1]
runs = int(input())
if sys.argv[1] == "scan":
    print(sum(1 in values for _ in range(runs)))
elif sys.argv[1] == "index":
    print(sum(1 in set(values) for _ in range(runs)))
else:
    raise ValueError("select scan or index")
