"""Trusted output oracles used by fixed and generated workloads."""

import base64
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
import subprocess


def argv(value):
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(x, str) and x for x in value)
    ):
        raise ValueError("expected a nonempty command argument list")
    return value


def validate(spec):
    mode = spec.get("kind", "exact")
    if set(spec) - {"kind", "atol", "rtol", "command", "state_files", "deterministic"}:
        raise ValueError("unknown oracle option")
    names = spec.get("state_files", [])
    if (
        not isinstance(names, list)
        or len(names) > 16
        or any(not isinstance(k, str) or not k.isidentifier() for k in names)
    ):
        raise ValueError("invalid state file names")
    if names and mode != "external":
        raise ValueError("state verification requires an external oracle")
    if type(spec.get("deterministic", False)) is not bool:
        raise ValueError("deterministic must be boolean")
    if mode not in {"exact", "numeric", "external"}:
        raise ValueError("unknown oracle kind")
    if mode == "external":
        argv(spec["command"])
    if mode == "numeric":
        for name in ("atol", "rtol"):
            value = Decimal(str(spec.get(name, 0)))
            if not value.is_finite() or value < 0:
                raise ValueError(f"invalid {name}")


def verify(spec, expected, actual, data, directory, timeout, state=None):
    mode = spec.get("kind", "exact")
    if mode == "external":
        packet = {
            k: base64.b64encode(v).decode()
            for k, v in (("input", data), ("expected", expected), ("actual", actual))
        }
        packet["state"] = {
            k: base64.b64encode(v).decode() for k, v in (state or {}).items()
        }
        result = subprocess.run(
            spec["command"],
            cwd=directory,
            input=json.dumps(packet).encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        if result.returncode:
            raise ValueError(
                "oracle rejected result"
                if result.returncode == 1
                else "oracle execution failed"
            )
        return
    if mode == "numeric":
        left, right = expected.split(), actual.split()
        if left and len(left) == len(right):
            try:
                pairs = [
                    (Decimal(x.decode()), Decimal(y.decode()))
                    for x, y in zip(left, right)
                ]
                atol, rtol = (Decimal(str(spec.get(k, 0))) for k in ("atol", "rtol"))
                if all(
                    x.is_finite()
                    and y.is_finite()
                    and abs(x - y) <= atol + rtol * abs(x)
                    for x, y in pairs
                ):
                    return
            except (InvalidOperation, UnicodeError):
                pass
        raise ValueError("numeric oracle rejected output")
    if expected != actual:
        raise ValueError("stdout differs from the trusted expected output")


def inputs(root, command, explicit=None):
    files = (
        explicit
        if explicit is not None
        else [
            item
            for item in command
            if not Path(item).is_absolute() and (root / item).is_file()
        ]
    )
    if not isinstance(files, list) or not all(isinstance(s, str) for s in files):
        raise ValueError("files must be a list of relative paths")
    return files


def checked_run(
    root,
    files,
    command,
    data,
    expected,
    oracle,
    evaluator_dir,
    deadline,
    memory,
    pmu=False,
):
    from candidate_runner import execute
    import time

    state = dict.fromkeys(oracle.get("state_files", []))
    actual, metrics = execute(
        root,
        files,
        command,
        data,
        deadline - time.monotonic(),
        memory,
        state=state,
        pmu=pmu,
    )
    verify(
        oracle,
        expected,
        actual,
        data,
        evaluator_dir,
        max(0, deadline - time.monotonic()),
        state,
    )
    if oracle.get("deterministic"):
        next_state = dict.fromkeys(state)
        again, _ = execute(
            root,
            files,
            command,
            data,
            deadline - time.monotonic(),
            memory,
            state=next_state,
        )
        if again != actual or state != next_state:
            raise ValueError("repeated execution changed the observable result")
    return metrics
