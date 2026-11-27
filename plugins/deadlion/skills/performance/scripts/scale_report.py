"""Compare confirmation observations within each implementation and distribution."""

import itertools
import math
from collections import defaultdict
from statistics import median
from growth_models import analyze, median_interval
from scale_contract import DEFAULT_MODELS


def summarize(s, report):
    strata = defaultdict(list)
    for row in report["rows"]:
        if row.get("phase") == "exploration":
            continue
        strata[row["implementation"], row["distribution"]].append(row)
    uncertain, violated = False, False
    for (name, dist), rows in strata.items():
        metrics = {}
        for metric in sorted(
            {"wall_ns", "peak_rss_kib"}
            | set(s.get("metrics", []))
            | set(s.get("expected_models", {}))
            | {k for k in rows[0] if k.startswith("reported_")}
        ):
            model = analyze(
                rows,
                s.get("models", DEFAULT_MODELS),
                s["dimensions"],
                metric,
                s["model_tolerance"],
                s.get("confidence", 0.95),
            )
            metrics[metric] = model
            expected = s.get("expected_models", {}).get(metric)
            if expected and name == report["choice"]:
                uncertain |= not any(
                    f.get("within_tolerance") for f in model["fits"]
                ) or not set(model["admissible"]) <= set(expected)
        report["models"].append(
            dict(implementation=name, distribution=dist, metrics=metrics)
        )
        for requirement in s.get("requirements", []):
            if requirement["implementation"] != name:
                continue
            groups = defaultdict(list)
            for r in rows:
                groups[tuple(r["dimensions"].values())].append(r[requirement["metric"]])
            for coord, values in groups.items():
                # Family-wise error across the predeclared quantitative gate checks.
                tests = len(groups) * len(s["distributions"]) * len(s["requirements"])
                interval = median_interval(
                    values, 1 - (1 - s.get("confidence", 0.95)) / tests
                )
                status = (
                    "INCONCLUSIVE"
                    if not interval
                    else (
                        "CONTRADICTED"
                        if interval[0] > requirement["max"]
                        else "VERIFIED"
                        if interval[1] <= requirement["max"]
                        else "INCONCLUSIVE"
                    )
                )
                report["checks"].append(
                    dict(
                        **requirement,
                        distribution=dist,
                        point=coord,
                        interval=interval,
                        status=status,
                    )
                )
                violated |= status == "CONTRADICTED"
                uncertain |= status == "INCONCLUSIVE"
        for req in s.get("growth_limits", []):
            if req["implementation"] != name:
                continue
            confidence = 1 - (1 - s.get("confidence", 0.95)) / (
                2 * len(s["growth_limits"]) * len(s["distributions"])
            )
            ranges = [
                median_interval(
                    [
                        row[req["metric"]]
                        for row in rows
                        if row["dimensions"] == req[key]
                    ],
                    confidence,
                )
                for key in ("from", "to")
            ]
            interval = None
            if all(ranges) and ranges[0][0] > 0:
                interval = [ranges[1][0] / ranges[0][1], ranges[1][1] / ranges[0][0]]
            status = (
                "INCONCLUSIVE"
                if interval is None
                else (
                    "CONTRADICTED"
                    if interval[0] > req["max_ratio"]
                    else "VERIFIED"
                    if interval[1] <= req["max_ratio"]
                    else "INCONCLUSIVE"
                )
            )
            report["checks"].append(
                dict(**req, distribution=dist, interval=interval, status=status)
            )
            violated |= status == "CONTRADICTED"
            uncertain |= status == "INCONCLUSIVE"
    report["status"] = (
        "CONTRADICTED" if violated else "INCONCLUSIVE" if uncertain else "MEASURED"
    )
    report["correctness"] = "VERIFIED"
    report["next_experiments"] = []
    if any(
        m["metrics"]["wall_ns"]["status"] == "INCONCLUSIVE" for m in report["models"]
    ):
        report["next_experiments"].append(
            "Measure additional independent sizes or operation counts within budget."
        )
    if any(m["metrics"]["wall_ns"]["observations"] for m in report["models"]):
        report["next_experiments"].append(
            "Profile both sides of the observed slope change."
        )


def comparisons(s, report):
    by_point = defaultdict(dict)
    for r in report["rows"]:
        if r.get("phase") == "exploration":
            continue
        key = (r["distribution"], tuple(r["dimensions"].values()), r["repetition"])
        by_point[key][r["implementation"]] = r["wall_ns"]
    from pareto import nondominated

    cohort = defaultdict(lambda: defaultdict(list))
    for row in report["rows"]:
        if row.get("phase") != "exploration":
            cohort[row["distribution"], tuple(row["dimensions"].values())][
                row["implementation"]
            ].append(row)
    report["pareto"] = []
    for (dist, coord), group in cohort.items():
        costs = {
            name: tuple(median(r[m] for r in rows) for m in ("wall_ns", "peak_rss_kib"))
            for name, rows in group.items()
        }
        report["pareto"].append(
            dict(
                distribution=dist,
                point=coord,
                median_wall_ns_rss_kib=costs,
                frontier=nondominated(costs),
            )
        )
    for a, b in itertools.combinations(s["implementations"], 2):
        samples = defaultdict(list)
        for (dist, coord, _), times in by_point.items():
            if a in times and b in times:
                samples[dist, coord].append(times[a] / times[b])
        previous = {}
        for (dist, coord), ratios in sorted(samples.items()):
            bounds = median_interval(
                ratios,
                1
                - (1 - s.get("confidence", 0.95))
                / (len(samples) * math.comb(len(s["implementations"]), 2)),
            )
            faster = (
                a
                if bounds and bounds[1] < 1
                else b
                if bounds and bounds[0] > 1
                else None
            )
            record = dict(
                pair=[a, b],
                distribution=dist,
                point=coord,
                median_ratio=median(ratios),
                interval=bounds,
            )
            if faster and len(coord) == 1:
                if dist in previous and previous[dist][0] != faster:
                    record["crossover_bracket"] = [previous[dist][1], coord]
                previous[dist] = (faster, coord)
            report["comparisons"].append(record)
