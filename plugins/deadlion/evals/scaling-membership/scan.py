import json
import sys

keys, probes = json.load(sys.stdin)
print(sum(probe in keys for probe in probes))
