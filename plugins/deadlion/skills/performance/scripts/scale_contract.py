"""Validate the experimental design before starting a process."""

import itertools
import math
from pathlib import Path
from correctness import argv, validate as validate_oracle
from growth_models import candidates

PMU = {"instructions", "cycles", "cache-misses", "branch-misses", "branches"}
METRICS = PMU | {"wall_ns", "peak_rss_kib", "user_cpu_s", "system_cpu_s", "cpu_time_s"}
DEFAULT_MODELS = [
    "constant",
    "log",
    "sqrt",
    "linear",
    "linearithmic",
    "quadratic",
    "quadratic_log",
    "cubic",
    "power",
    "exponential",
    "factorial",
]


def number(value, low, high, integer=False):
    if (
        type(value) not in ((int,) if integer else (float, int))
        or not low <= value <= high
    ):
        raise ValueError(
            f"expected {'integer' if integer else 'number'} in [{low}, {high}]"
        )
    return value


def sizes(spec):
    if isinstance(spec, list):
        if not 1 <= len(spec) <= 128:
            raise ValueError("expected 1..128 values per axis")
        values = [number(v, 1, 2**53, True) for v in spec]
        if values != sorted(set(values)):
            raise ValueError("size values must strictly increase")
        return values
    first = number(spec["min"], 1, 2**53, True)
    last = number(spec["max"], first, 2**53, True)
    growth = number(spec["growth"], 1.000001, 1000)
    values = [first]
    while values[-1] < last and len(values) < 129:
        values.append(min(last, math.ceil(values[-1] * growth)))
    return sizes(values)


def validate(s):
    allowed = {
        "dimensions",
        "generator",
        "implementations",
        "distributions",
        "oracle",
        "models",
        "metrics",
        "limits",
        "confidence",
        "seed",
        "min_repetitions",
        "max_repetitions",
        "relative_precision",
        "model_tolerance",
        "growth_limits",
        "requirements",
        "expected_models",
        "design",
        "allow_inconclusive",
    }
    if unknown := set(s) - allowed:
        raise ValueError(f"unknown scaling keys: {sorted(unknown)}")
    dims = s["dimensions"]
    if (
        not isinstance(dims, dict)
        or not 1 <= len(dims) <= 8
        or not all(k.isidentifier() for k in dims)
    ):
        raise ValueError("declare named dimensions")
    axes = [sizes(v) for v in dims.values()]
    design = s.get("design", "grid")
    if design == "adaptive" and len(axes) != 1:
        raise ValueError("adaptive size selection requires one axis")
    if design not in ("adaptive", "grid", "axes"):
        raise ValueError("design must be grid or axes")
    dist = s["distributions"]
    if (
        not isinstance(dist, list)
        or not dist
        or not all(isinstance(d, str) and d for d in dist)
        or len(set(dist)) != len(dist)
    ):
        raise ValueError("expected distinct distribution names")
    limits = s["limits"]
    if set(limits) != {"seconds", "memory_mib", "max_points"}:
        raise ValueError("limits require seconds, memory_mib and max_points")
    number(limits["seconds"], 0.05, 86400)
    number(limits["memory_mib"], 32, 1048576, True)
    count = (
        math.prod(map(len, axes))
        if design == "grid"
        else 1 + sum(len(v) - 1 for v in axes)
    )
    if count * len(dist) > number(limits["max_points"], 1, 128, True):
        raise ValueError("design exceeds max_points")
    reps = number(s.get("min_repetitions", 7), 1, 128, True)
    number(s.get("max_repetitions", reps), reps, 128, True)
    number(s.get("confidence", 0.95), 0.5, 0.999999)
    number(s.get("relative_precision", 0.1), 0, 1)
    number(s["model_tolerance"], 0, 1)
    number(s.get("seed", 0), 0, 2**63 - 1, True)
    if type(s.get("allow_inconclusive", False)) is not bool:
        raise ValueError("allow_inconclusive must be boolean")
    argv(s["generator"])
    validate_oracle(s.get("oracle", {}))
    impls = s["implementations"]
    if not isinstance(impls, dict) or not 1 <= len(impls) <= 16:
        raise ValueError("declare at least one implementation")
    for spec in impls.values():
        if set(spec) - {"files", "argv", "instrument"}:
            raise ValueError("unknown implementation option")
        argv(spec["argv"])
        if "instrument" in spec:
            argv(spec["instrument"])
        if not isinstance(spec["files"], list) or not all(
            isinstance(f, str)
            and not Path(f).is_absolute()
            and ".." not in Path(f).parts
            for f in spec["files"]
        ):
            raise ValueError("declare relative implementation files")
    metrics = s.get("metrics", ["wall_ns", "peak_rss_kib"])
    if not isinstance(metrics, list) or not metrics or not set(metrics) <= METRICS:
        raise ValueError("unsupported scaling metric")
    models = s.get("models", DEFAULT_MODELS)
    if (
        not isinstance(models, list)
        or not 1 <= len(models) <= 32
        or not all(isinstance(m, str) for m in models)
    ):
        raise ValueError("expected a list of growth models")
    list(candidates(models, dims))
    for metric, names in s.get("expected_models", {}).items():
        if metric not in METRICS or not names or not set(names) <= set(models):
            raise ValueError("invalid expected models")
    for req in s.get("requirements", []):
        if (
            set(req) != {"implementation", "metric", "max"}
            or req["implementation"] not in impls
            or req["metric"] not in METRICS
        ):
            raise ValueError("invalid scaling requirement")
        number(req["max"], 0, 1e300)
    for req in s.get("growth_limits", []):
        if (
            set(req) != {"implementation", "metric", "from", "to", "max_ratio"}
            or req["implementation"] not in impls
            or req["metric"] not in METRICS
            or req["from"] == req["to"]
        ):
            raise ValueError("invalid growth limit")
        for point in (req["from"], req["to"]):
            if point.keys() != dims.keys() or any(
                v not in axis for v, axis in zip((point[k] for k in dims), axes)
            ):
                raise ValueError("growth limit references an unavailable coordinate")
        number(req["max_ratio"], 0, 1e300)
    return axes


def coordinates(s, axes):
    if s.get("design", "grid") == "grid":
        return itertools.product(*axes)
    base = tuple(v[0] for v in axes)
    return [base] + [
        (*base[:i], v, *base[i + 1 :]) for i, axis in enumerate(axes) for v in axis[1:]
    ]
