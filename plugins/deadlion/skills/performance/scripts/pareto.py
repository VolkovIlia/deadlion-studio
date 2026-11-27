"""Nondominated observations in a cohort of comparable cost vectors."""


def nondominated(costs):
    return [
        name
        for name, x in costs.items()
        if not any(y != x and all(v <= w for v, w in zip(y, x)) for y in costs.values())
    ]
