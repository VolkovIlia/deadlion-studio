import json
import sys

keys, probes = json.load(sys.stdin)
index = set(keys)
print(sum(probe in index for probe in probes))
