"""Finite-range predictive models. Hold out whole coordinates before fitting."""

import ast
from collections import defaultdict
import itertools
import math
from statistics import median


def expression(source, dimensions):
    """Compile only arithmetic over named dimensions and positive real functions."""
    tree = ast.parse(source, mode="eval")
    if len(list(ast.walk(tree))) > 64:
        raise ValueError("model expression too long")
    funcs = {
        "log": math.log,
        "sqrt": math.sqrt,
        "factorial": lambda x: math.exp(math.lgamma(x + 1)),
    }
    ops = {ast.Add: float.__add__, ast.Mult: float.__mul__, ast.Pow: math.pow}

    def compile_node(node):
        if isinstance(node, ast.Name) and node.id in dimensions:
            return lambda point: float(point[node.id])
        if (
            isinstance(node, ast.Constant)
            and type(node.value) in (float, int)
            and math.isfinite(node.value)
        ):
            return lambda point: float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = compile_node(node.left), compile_node(node.right)
            return lambda point: ops[type(node.op)](left(point), right(point))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in funcs
            and len(node.args) == 1
            and not node.keywords
        ):
            arg = compile_node(node.args[0])
            return lambda point: funcs[node.func.id](arg(point))
        raise ValueError(f"unsupported model expression: {source}")

    return compile_node(tree.body)


def candidates(names, dimensions):
    n = next(iter(dimensions))
    models = {
        "constant": "1",
        "log": f"log({n})",
        "sqrt": f"sqrt({n})",
        "linear": n,
        "linearithmic": f"{n}*log({n})",
        "quadratic": f"{n}**2",
        "quadratic_log": f"{n}**2*log({n})",
        "cubic": f"{n}**3",
        "factorial": f"factorial({n})",
    }
    for name in names:
        if name in ("power", "exponential"):
            # Select the shape on training data only; report the fitted grid parameter.
            for k in (
                [i / 8 for i in range(1, 65)]
                if name == "power"
                else [1.1, 1.25, 1.5, 2, 2.5, 3, 4]
            ):
                source = f"{n}**{k}" if name == "power" else f"{k}**{n}"
                yield name, source, expression(source, dimensions)
        else:
            source = models.get(name, name)
            yield name, source, expression(source, dimensions)


def fit(x, y):
    if max(x) == min(x):
        return median(y), 0.0
    # Median pairwise slope; clamp intercept and refit through origin at boundary.
    slopes = [
        (v - u) / (b - a)
        for (a, u), (b, v) in itertools.combinations(zip(x, y), 2)
        if a != b
    ]
    b = max(0.0, median(slopes))
    a = median(v - b * u for u, v in zip(x, y))
    return (
        (a, b)
        if a >= 0
        else (0.0, max(0.0, median(v / u for u, v in zip(x, y) if u > 0)))
    )


def analyze(rows, names, axes, metric, tolerance, confidence=0.95):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row["dimensions"][k] for k in axes)].append(row[metric])
    coords = sorted(groups)
    result = dict(
        status="INCONCLUSIVE",
        admissible=[],
        fits=[],
        observations=[],
        tested_points=len(coords),
    )
    if len(coords) < 6:
        return result
    # Interleaved unseen coordinates plus largest size; same partition for all models.
    holdout = set(coords[2::3]) | {coords[-1]}
    train = [p for p in coords if p not in holdout]
    test = [p for p in coords if p in holdout]
    result["holdout"] = test
    typical = {p: median(groups[p]) for p in coords}
    if any(v <= 0 for v in typical.values()):
        return result
    if len(axes) == 1:
        slopes = [
            math.log(typical[q] / typical[p]) / math.log(q[0] / p[0])
            for p, q in zip(coords, coords[1:])
        ]
        result["local_exponents"] = slopes
        split = regime(train, test, typical, tolerance)
        if split:
            result["observations"].append(split)
    intervals = [median_interval(groups[p], confidence) for p in test]
    result["holdout_median_intervals"] = intervals
    best = {}
    for name, source, fn in candidates(names, axes):
        try:
            features = {p: fn(dict(zip(axes, p))) for p in coords}
            if not all(math.isfinite(v) and v >= 0 for v in features.values()):
                continue
            a, b = fit([features[p] for p in train], [typical[p] for p in train])
            errors = {p: (a + b * features[p]) / typical[p] - 1 for p in coords}
            if not all(math.isfinite(v) for v in errors.values()):
                continue
            score = median(abs(errors[p]) for p in train)
            if name not in best or score < best[name][0]:
                best[name] = (
                    score,
                    dict(
                        model=name,
                        formula=source,
                        intercept=a,
                        coefficient=b,
                        predictions=[a + b * features[p] for p in test],
                        residuals=[errors[p] for p in test],
                        max_holdout_error=max(abs(errors[p]) for p in test),
                    ),
                )
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
    result["fits"] = sorted(
        (record for _, record in best.values()), key=lambda r: r["max_holdout_error"]
    )
    if any(interval is None for interval in intervals):
        return result
    for record in result["fits"]:
        errors = [
            [pred / hi - 1, pred / lo - 1] if lo > 0 else [-1, None]
            for pred, (lo, hi) in zip(record["predictions"], intervals)
        ]
        possible = all(
            lo <= tolerance and (hi is None or hi >= -tolerance) for lo, hi in errors
        )
        record["within_tolerance"] = all(
            lo >= -tolerance and hi is not None and hi <= tolerance for lo, hi in errors
        )
        if possible:
            result["admissible"].append(record["model"])
    if len(result["admissible"]) == 1 and any(
        r["within_tolerance"] for r in result["fits"]
    ):
        result["status"] = "EMPIRICALLY CONSISTENT"
    return result


def regime(train, test, values, tolerance):
    """Require an improvement on unseen sizes on each side of an estimated split."""

    def line(points):
        xy = [(math.log(p[0]), math.log(values[p])) for p in points]
        slope = median(
            (y2 - y1) / (x2 - x1)
            for (x1, y1), (x2, y2) in itertools.combinations(xy, 2)
        )
        return median(y - slope * x for x, y in xy), slope

    def error(point, model):
        return abs(math.log(values[point]) - model[0] - model[1] * math.log(point[0]))

    if len(train) < 6 or len(test) < 4:
        return
    whole = line(train)
    fits = []
    for i in range(3, len(train) - 2):
        left, right = line(train[:i]), line(train[i:])
        at = math.sqrt(train[i - 1][0] * train[i][0])
        loss = sum(error(p, left if p[0] < at else right) for p in train)
        fits.append((loss, at, left, right))
    _, at, left, right = min(fits)
    for points, model in (
        ([p for p in test if p[0] < at], left),
        ([p for p in test if p[0] >= at], right),
    ):
        if len(points) < 2 or median(
            error(p, whole) - error(p, model) for p in points
        ) <= math.log1p(tolerance):
            return
    return dict(
        kind="observed_slope_change",
        split=at,
        before=left[1],
        after=right[1],
        confirmation="profile the adjacent sizes to investigate the cause",
    )


def median_interval(values, confidence):
    """Exact conservative sign interval for an independent sample's population median."""
    ordered = sorted(values)
    n = len(values)
    tail = 0
    interval = None
    for rank in range((n + 1) // 2):
        tail += math.comb(n, rank)
        if 2 * tail > (1 - confidence) * 2**n:
            break
        interval = [ordered[rank], ordered[-rank - 1]]
    return interval


def quantile_interval(ordered, q, confidence):
    """Distribution-free two-sided quantile interval from binomial order statistics."""
    n = len(ordered)
    tail = (1 - confidence) / 2
    cdf = 0.0
    low, high = None, None
    for k in range(n + 1):
        logp = (
            math.lgamma(n + 1)
            - math.lgamma(k + 1)
            - math.lgamma(n - k + 1)
            + k * math.log(q)
            + (n - k) * math.log1p(-q)
        )
        cdf += math.exp(logp)
        if cdf <= tail and k < n:
            low = ordered[k]
        if cdf >= 1 - tail:
            if k < n:
                high = ordered[k]
            break
    return low, high
