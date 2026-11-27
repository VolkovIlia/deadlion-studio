"""Collect paired, bounded scaling measurements from a trusted JSON contract."""

import argparse
import base64
from collections import defaultdict
import csv
import hashlib
import json
import math
import os
import platform
import shutil
from pathlib import Path
import random
import resource
import signal
from statistics import median
import subprocess
import tempfile
import time

from candidate_runner import execute
from correctness import checked_run, verify
from growth_models import median_interval
from scale_contract import validate, coordinates, METRICS, PMU
from scale_report import summarize, comparisons


def scheduled(s, axes, costs, deadline):
    if s.get("design") != "adaptive":
        yield from coordinates(s, axes)
        return
    value, upper = axes[0][0], axes[0][-1]
    previous = value
    for _ in range(s["limits"]["max_points"] // len(s["distributions"])):
        yield (value,)
        if value == upper:
            return
        proposed = next(v for v in axes[0] if v > value)
        if len(costs) >= 2:
            slope = max(0.0, math.log(costs[-1] / costs[-2]) / max(1, value - previous))
            if slope:
                remaining = max(1, (deadline - time.monotonic()) / costs[-1])
                step = int(min(math.log(2), math.log(remaining)) / slope)
                if step < 1:
                    raise TimeoutError("no affordable next size")
                proposed = min(proposed, value + step)
        previous, value = value, proposed
    raise TimeoutError("adaptive point budget exhausted")


def generate(command, root, request, memory_mib, deadline):
    limit = memory_mib * 1048576

    def restrict():
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))

    with tempfile.TemporaryFile() as output:
        with subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=output,
            start_new_session=True,
            preexec_fn=restrict,
        ) as child:
            try:
                child.communicate(
                    json.dumps(request).encode(),
                    timeout=max(0, deadline - time.monotonic()),
                )
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                raise
            if child.returncode:
                raise ValueError(f"workload generator exited {child.returncode}")
        output.seek(0)
        generated = json.load(output)
    return tuple(
        base64.b64decode(generated[k + "_base64"], validate=True)
        if k + "_base64" in generated
        else generated[k].encode()
        for k in ("input", "expected")
    )


def collect(s, root, candidate, report):
    axes = validate(s)
    limits = s["limits"]
    deadline = time.monotonic() + limits["seconds"]
    rng = random.Random(s.get("seed", 0))
    impls = s["implementations"]
    requested = set(s.get("metrics", [])) | set(s.get("expected_models", {}))
    requested.update(
        r["metric"] for key in ("requirements", "growth_limits") for r in s.get(key, [])
    )
    counters = requested & PMU
    minimum = s.get("min_repetitions", 7)
    for distribution in s["distributions"]:
        last_costs = []
        peaks = []
        for point in scheduled(s, axes, last_costs, deadline):
            dims = dict(zip(s["dimensions"], point))
            if last_costs and s.get("design") != "adaptive":
                growth = (
                    max(1, last_costs[-1] / max(last_costs[-2], 1e-9))
                    if len(last_costs) > 1
                    else 1
                )
                if time.monotonic() + last_costs[-1] * growth > deadline:
                    raise TimeoutError("predicted next point exceeds remaining time")
            if (
                len(peaks) >= 2
                and peaks[-1] * max(1, peaks[-1] / max(1, peaks[-2]))
                > limits["memory_mib"] * 1024
            ):
                raise TimeoutError("predicted next point exceeds memory budget")
            row_start = len(report["rows"])
            point_start = time.monotonic()
            timings = defaultdict(list)
            maximum = s.get("max_repetitions", minimum)
            exploring = maximum > minimum
            confirmation = 0
            for repetition in range(maximum + (minimum if exploring else 0)):
                seed = rng.randrange(2**53)
                request = dict(dimensions=dims, distribution=distribution, seed=seed)
                data, expected = generate(
                    s["generator"], root, request, limits["memory_mib"], deadline
                )
                order = list(impls)
                rng.shuffle(order)
                for name in order:
                    spec = impls[name]
                    directory = candidate if name == report["choice"] else root
                    metrics = checked_run(
                        directory,
                        spec["files"],
                        spec["argv"],
                        data,
                        expected,
                        s.get("oracle", {}),
                        root,
                        deadline,
                        limits["memory_mib"],
                    )
                    if counters:
                        sample = checked_run(
                            directory,
                            spec["files"],
                            spec["argv"],
                            data,
                            expected,
                            s.get("oracle", {}),
                            root,
                            deadline,
                            limits["memory_mib"],
                            pmu=True,
                        )
                        metrics.update({key: sample[key] for key in counters})
                    report["rows"].append(
                        dict(
                            implementation=name,
                            repetition=repetition,
                            **request,
                            phase="exploration" if exploring else "confirmation",
                            input_sha256=hashlib.sha256(data).hexdigest(),
                            **metrics,
                        )
                    )
                    timings[name].append(metrics["wall_ns"])
                    if "instrument" in spec:
                        payload, _ = execute(
                            directory,
                            spec["files"],
                            spec["instrument"],
                            data,
                            deadline - time.monotonic(),
                            limits["memory_mib"],
                        )
                        observed = json.loads(payload)
                        verify(
                            s.get("oracle", {}),
                            expected,
                            observed["output"].encode(),
                            data,
                            root,
                            max(0, deadline - time.monotonic()),
                        )
                        counters = observed["counters"]
                        if not counters or not all(
                            isinstance(k, str) and type(v) is int and 0 <= v <= 2**53
                            for k, v in counters.items()
                        ):
                            raise ValueError("invalid instrumented operation count")
                        report["rows"][-1].update(
                            {"reported_" + k: v for k, v in counters.items()}
                        )
                if exploring:
                    if repetition + 1 == maximum or (
                        repetition + 1 >= minimum
                        and all(precise(v, s) for v in timings.values())
                    ):
                        exploring = False
                else:
                    confirmation += 1
                    if confirmation == minimum:
                        break
            peaks.append(max(r["peak_rss_kib"] for r in report["rows"][row_start:]))
            last_costs.append(time.monotonic() - point_start)


def precise(values, s):
    interval = median_interval(values, s.get("confidence", 0.95))
    return interval and interval[1] - interval[0] <= median(values) * s.get(
        "relative_precision", 0.1
    )


def experiment(path, contract, candidate=None):
    s = contract["scaling"]
    report = dict(
        schema=1,
        status="NOT VERIFIED",
        correctness="NOT VERIFIED",
        choice=contract["choice"],
        environment=dict(
            platform=platform.platform(), python=platform.python_version()
        ),
        contract_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        rows=[],
        models=[],
        checks=[],
        comparisons=[],
    )
    try:
        if report["choice"] not in s["implementations"]:
            raise ValueError("choice must name a measured implementation")

        def identities():
            from candidate_runner import capsule

            result = {}
            for name, spec in s["implementations"].items():
                directory = (
                    candidate if candidate and name == report["choice"] else path.parent
                )
                capsule(directory, spec["files"])
                result[name] = {
                    f: hashlib.sha256((directory / f).read_bytes()).hexdigest()
                    for f in spec["files"]
                }
            return result

        from correctness import inputs

        report["environment"]["affinity"] = sorted(os.sched_getaffinity(0))
        report["environment"]["cpu_model"] = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            platform.machine(),
        )
        report["revisions"] = {
            name: subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=directory,
                capture_output=True,
                text=True,
            ).stdout.strip()
            or None
            for name, directory in (
                ("evaluator", path.parent),
                ("candidate", candidate or path.parent),
            )
        }

        def file_hash(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

        report["trusted_inputs"] = {
            f: file_hash(path.parent / f)
            for command in [s["generator"], s.get("oracle", {}).get("command", [])]
            for f in inputs(path.parent, command)
        }
        binaries = {}
        for spec in s["implementations"].values():
            binary = (
                shutil.which(spec["argv"][0], path="/usr/bin:/bin")
                if "/" not in spec["argv"][0]
                else None
            )
            if binary:
                binaries[binary] = file_hash(Path(binary))
        report["runtime_binaries"] = binaries
        report["implementations"] = identities()
        report["settings"] = s
        collect(s, path.parent, candidate or path.parent, report)
        if identities() != report["implementations"]:
            raise ValueError("implementation changed during measurement")
        summarize(s, report)
        comparisons(s, report)
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        report.update(status="INCONCLUSIVE", reason=str(exc), complete=False)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        ArithmeticError,
        subprocess.SubprocessError,
    ) as exc:
        report["reason"] = str(exc)
    return report


def decision(report, s):
    if report["status"] == "CONTRADICTED":
        return 1
    return (
        0
        if report["status"] == "MEASURED"
        or (
            report.get("complete", True)
            and report["status"] == "INCONCLUSIVE"
            and s.get("allow_inconclusive") is True
        )
        else 2
    )


def run(args):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument(
        "--replay", type=Path, help="reanalyze a completed local measurement report"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--extrap", type=Path, help="write Extra-P JSON Lines measurements"
    )
    parser.add_argument("--csv", type=Path)
    opts = parser.parse_args(args)
    path = opts.contract.resolve()
    contract = json.loads(path.read_bytes())
    subprocess.run(
        [Path(__file__).with_name("dl-contract"), path],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    if opts.replay:
        report = json.loads(opts.replay.read_bytes())
        if (
            report.get("correctness") != "VERIFIED"
            or not report.get("rows")
            or report["contract_sha256"]
            != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError("replay requires complete evidence for this contract")
        report.update(models=[], checks=[], comparisons=[], replayed=True)
        summarize(contract["scaling"], report)
        comparisons(contract["scaling"], report)
    else:
        report = experiment(path, contract)
    encoded = json.dumps(report, allow_nan=False)
    if opts.output:
        opts.output.write_text(encoded + "\n")
    if opts.extrap:
        with opts.extrap.open("w") as stream:
            for row in report["rows"]:
                if row.get("phase") == "exploration":
                    continue
                for metric in sorted(
                    (METRICS & row.keys())
                    | {k for k in row if k.startswith("reported_")}
                ):
                    print(
                        json.dumps(
                            dict(
                                params=row["dimensions"],
                                callpath=row["implementation"]
                                + "/"
                                + row["distribution"],
                                metric=metric,
                                value=row[metric],
                            )
                        ),
                        file=stream,
                    )
    if opts.csv and report["rows"]:
        with opts.csv.open("w", newline="") as stream:
            rows = [
                {**{k: v for k, v in r.items() if k != "dimensions"}, **r["dimensions"]}
                for r in report["rows"]
            ]
            writer = csv.DictWriter(
                stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row))
            )
            writer.writeheader()
            writer.writerows(rows)
    if opts.json:
        print(encoded)
    else:
        if not opts.output:
            with tempfile.NamedTemporaryFile(
                prefix="dl-scale-", suffix=".json", mode="w", delete=False
            ) as f:
                f.write(encoded)
                opts.output = Path(f.name)
        print(
            f"{report['status']} | {len(report['rows'])} samples | correctness {report['correctness']} | {opts.output}"
        )
        for m in report["models"]:
            fits = m["metrics"]["wall_ns"]
            print(
                m["implementation"],
                m["distribution"],
                fits["status"],
                ", ".join(fits["admissible"]),
            )
        if "reason" in report:
            print(report["reason"])
    return decision(report, contract["scaling"])
