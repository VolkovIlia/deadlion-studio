import json
import sys

if sys.argv[1:] == ["--comparisons"]:

    class Key(int):
        comparisons = 0

        def __lt__(self, other):
            Key.comparisons += 1
            return super().__lt__(other)

    values = sorted(map(Key, sys.stdin))
    print(
        json.dumps(
            dict(
                output="".join(f"{v}\n" for v in values),
                counters=dict(comparisons=Key.comparisons),
            )
        )
    )
else:
    sys.stdout.write("".join(f"{v}\n" for v in sorted(map(int, sys.stdin))))
