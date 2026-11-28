"""Run paired A/D/E generations through OMP against a separate holdout evaluator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from omp_autoresearch_smoke import ROOT, git

BASE = "25620d1f53d9982de19625ff199bb3591615d620"
PLUGIN = ROOT / "plugins/deadlion"
GATE = PLUGIN / "skills/performance/scripts/dl-perf-gate"
TEMPLATE = PLUGIN / "evals/indexed-membership/contract.json"
TOOLS = "read,write,edit"

MEMBERSHIP = """import json
import sys
values, queries = json.load(sys.stdin)
print(sum(query in values for query in queries))
"""
ACCURACY = """import json
import sys
print(format(sum(json.load(sys.stdin)), ".0f"))
"""
STORAGE = """import json
import sqlite3
import sys

orders, customers = json.load(sys.stdin)
db = sqlite3.connect(":memory:")
db.execute("create table orders (customer integer, amount integer)")
db.executemany("insert into orders values (?, ?)", orders)
print(json.dumps([db.execute("select coalesce(sum(amount),0) from orders where customer=?",
                             (customer,)).fetchone()[0] for customer in customers]))
"""


def tasks():
    rng = random.Random(11731)
    values = rng.sample(range(18_000), 7_000)
    queries = [rng.randrange(23_000) for _ in range(9_000)]
    public = ([1, 2, 2, -1], [2, -1, 3, 2])
    results = set(values)
    yield ("membership", "Refactor solution.py. Count each query present in the values list, preserving duplicate queries. "
           "Handle large inputs efficiently. Preserve the JSON stdin and integer stdout interface.",
           MEMBERSHIP, public, "3", (values, queries), str(sum(q in results for q in queries)))
    yield ("numerical-sum", "Fix solution.py to accurately sum the finite JSON numbers, even with cancellation. "
           "Print the result rounded to zero decimal places.",
           ACCURACY, [1e16, 2.0, -1e16], "2", [1e16, 1.0, -1e16] * 1024, "1024")
    orders = [(rng.randrange(2000), rng.randrange(-22, 80)) for _ in range(18000)]
    customers = [rng.randrange(2500) for _ in range(1600)]
    totals = {}
    for key, amount in orders:
        totals[key] = totals.get(key, 0) + amount
    yield ("sqlite-refactor", "Refactor solution.py to remove the per-customer SQL round trips. "
           "Preserve customer order, duplicates, and zero for missing customers. Preserve JSON I/O.",
           STORAGE, ([(1, 4), (1, -3), (3, 9)], [1, 2, 1, 3]), "[1, 0, 1, 9]",
           (orders, customers), json.dumps([totals.get(customer, 0) for customer in customers]))


def contract(path, data, expected):
    path.parent.mkdir(parents=True)
    (path.parent / "input").write_text(json.dumps(data))
    (path.parent / "expected").write_text(expected + "\n")
    record = json.loads(TEMPLATE.read_bytes())
    command = ["python3", "-I", "solution.py"]
    record["benchmark"] = dict(candidate_root=".", candidate=command, candidate_files=["solution.py"],
                               baseline=command, baseline_files=["solution.py"], expected="expected")
    record["budget"] = {"peak_rss_kib": 131072, "cpu_time_s": 120}
    record["workload"] = "input"
    path.write_text(json.dumps(record))


def profile_for(root, endpoint, model):
    profile = root / "profile"
    profile.mkdir()
    (profile / "models.yml").write_text(
        f"providers:\n  local:\n    baseUrl: {json.dumps(endpoint)}\n    api: openai-completions\n"
        f"    apiKey: LOCAL_OMP_FIXTURE_KEY\n    models:\n      - id: {json.dumps(model)}\n"
        f"        name: {json.dumps(model)}\n        contextWindow: 32768\n        maxTokens: 4096\n")
    (profile / "config.yml").write_text(f"modelRoles:\n  default: {json.dumps('local/' + model)}\n"
                                        "startup:\n  setupWizard: false\n")
    return profile


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def generate(args, plugin, recipe, path):
    key, prompt, source, training, expected, _, _ = recipe
    checkout = path / "project"
    checkout.mkdir(parents=True)
    profile = profile_for(path, args.endpoint, args.model)
    env = {"PATH": os.environ["PATH"], "HOME": str(path), "PI_CODING_AGENT_DIR": str(profile),
           "PI_CONFIG_DIR": str(path / ".omp"), "XDG_STATE_HOME": str(path / "state"),
           "LOCAL_OMP_FIXTURE_KEY": "local", "LANG": "C.UTF-8"}
    verdict = path / "engineering-verdict.json"
    if plugin:
        env["DL_VERDICT_FILE"] = str(verdict)
    (checkout / "solution.py").write_text(source)
    contract(checkout / ".performance/public/contract.json", training, expected)
    git(checkout, "init", "-qb", "main")
    git(checkout, "add", ".")
    git(checkout, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "paired experiment baseline")
    if plugin:
        subprocess.run(["omp", "plugin", "link", plugin], cwd=checkout, env=env, check=True, capture_output=True, timeout=15)
    command = ["omp", "--offline", "--no-judge", "--no-spotlight", "--no-lsp", "--no-session",
               "--max-time", str(args.seconds), "--mode", "json", "--tools", TOOLS, "-p", prompt]
    start = time.monotonic()
    with (path / "events.jsonl").open("w+") as stream, (path / "generation.stderr").open("w") as errors:
        proc = subprocess.Popen(command, cwd=checkout, env=env, stdout=stream, stderr=errors, start_new_session=True)
        try:
            exit_code = proc.wait(timeout=args.seconds + 5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            exit_code = "TIMEOUT"
        elapsed = time.monotonic() - start
        stream.seek(0)
        usage = token_usage(stream)
    candidate = checkout / "solution.py"
    sealed = candidate.read_bytes() if candidate.is_file() and not candidate.is_symlink() else None
    gate = json.loads(verdict.read_bytes()) if verdict.is_file() else {}
    return {"task": key, "model": args.model, "generation_exit": exit_code, "wall_seconds": elapsed,
            "engineering": gate.get("state", "NOT VERIFIED" if plugin else "NOT APPLICABLE"),
            "usage": usage, "candidate_sha256": hashlib.sha256(sealed).hexdigest() if sealed else None}, sealed


def evaluate(path, recipe, sealed):
    *_, holdout, holdout_expected = recipe
    if not sealed:
        return {"status": "NOT VERIFIED", "reason": "Candidate is missing"}
    oracle = path / "holdout/contract.json"
    contract(oracle, holdout, holdout_expected)
    candidate = path / "evaluated"
    candidate.mkdir()
    (candidate / "solution.py").write_bytes(sealed)
    try:
        result = subprocess.run([GATE, oracle, "--isolated", "--candidate-dir", candidate], cwd=path,
                                text=True, capture_output=True, timeout=120)
        evidence = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError) as error:
        evidence = {"status": "NOT VERIFIED", "reason": str(error)}
    save_json(path / "evaluation.json", evidence)
    return evidence


def token_usage(lines):
    totals = None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message", {})
        usage = message.get("usage")
        if event.get("type") != "message_end" or message.get("role") != "assistant" or not usage:
            continue
        if totals is None:
            totals = dict.fromkeys(("input", "output", "cacheRead", "cacheWrite"), 0)
        for key in totals:
            totals[key] += usage.get(key, 0)
    return totals


def bootstrap(rows, arms, seed):
    paired = {(row["task"], row["repeat"], row["arm"]): row for row in rows}
    tasks = sorted({row["task"] for row in rows})
    comparisons = {}
    rng = random.Random(seed)
    for arm in arms:
        if arm == "A" or "A" not in arms:
            continue
        pairs = {task: [(row, paired[task, row["repeat"], arm]) for row in rows
                        if row["arm"] == "A" and row["task"] == task] for task in tasks}
        correctness = [[float(contender["correct"]) - float(base["correct"]) for base, contender in group]
                       for group in pairs.values()]
        comparisons[arm + "-A"] = {
            "pass_rate_difference": interval(correctness, rng),
            "generation_wall_ratio": interval(ratios(pairs, lambda row: row["wall_seconds"]), rng),
            "cpu_ratio_on_joint_correct": interval(ratios(pairs, lambda row: row["metrics"].get("cpu_time_s"),
                                                          correct_only=True), rng),
            "rss_ratio_on_joint_correct": interval(ratios(pairs, lambda row: row["metrics"].get("peak_rss_kib"),
                                                          correct_only=True), rng),
        }
    return comparisons


def ratios(pairs, metric, correct_only=False):
    groups = []
    for group in pairs.values():
        samples = []
        for base, contender in group:
            if correct_only and not (base["correct"] and contender["correct"]):
                continue
            reference, candidate = metric(base), metric(contender)
            if reference and candidate is not None:
                samples.append(candidate / reference)
        if samples:
            groups.append(samples)
    return groups


def interval(groups, rng):
    if not groups:
        return {"pairs": 0}
    values = [statistics.mean(group) for group in groups]
    repeats = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return {"mean_task_effect": statistics.mean(values), "pairs": sum(map(len, groups)),
            "task_cluster_bootstrap_95": [repeats[49], repeats[1949]] if len(values) > 1 else None}


def tree_digest(root):
    """Hash the code used by the experiment, including edits beyond Git HEAD."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or set(relative.parts) & {"results", "__pycache__", "node_modules"}:
            continue
        digest.update(str(relative).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def arguments():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--endpoint", required=True)
    cli.add_argument("--model", required=True)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--repeats", type=int, default=5)
    cli.add_argument("--seconds", type=int, default=60)
    cli.add_argument("--seed", type=int, default=42)
    cli.add_argument("--arms", nargs="+", choices=["A", "D", "E"], default=["A", "D", "E"])
    cli.add_argument("--task", choices=[t[0] for t in tasks()])
    cli.add_argument("--scripted", action="store_true", help="label transport validation without a model")
    args = cli.parse_args()
    endpoint = urlsplit(args.endpoint)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "::1"} or endpoint.username or endpoint.query or endpoint.fragment:
        cli.error("use a loopback-only OpenAI-compatible endpoint without credentials")
    if args.repeats < 1 or args.seconds < 1 or len(set(args.arms)) != len(args.arms):
        cli.error("choose positive limits and unique arms")
    args.out = args.out.resolve()
    return args


def main():
    args = arguments()
    args.out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        if "D" in args.arms:
            archive = subprocess.check_output(["git", "archive", BASE, "plugins/deadlion"], cwd=ROOT)
            subprocess.run(["tar", "-x", "-C", temp], input=archive, check=True)
        plugins = {"A": None, "D": temp / "plugins/deadlion", "E": PLUGIN}
        provenance = {"omp": subprocess.check_output(["omp", "--version"], text=True).strip(), "4.5.0": BASE,
                      "4.6.0_head": git(ROOT, "rev-parse", "HEAD"),
                      "plugins": {name: tree_digest(plugins[name]) for name in args.arms if plugins[name]},
                      "dataset_sha256": hashlib.sha256(json.dumps(list(tasks())).encode()).hexdigest(),
                      "gate_sha256": hashlib.sha256(GATE.read_bytes()).hexdigest(),
                      **vars(args), "out": str(args.out)}
        save_json(args.out / "protocol.json", provenance)
        rows = []
        rng = random.Random(args.seed)
        for recipe in tasks():
            if args.task and recipe[0] != args.task:
                continue
            for repeat in range(args.repeats):
                for arm in rng.sample(args.arms, len(args.arms)):
                    path = args.out / f"{recipe[0]}-{repeat}-{arm}"
                    result, sealed = generate(args, plugins[arm], recipe, path)
                    rows.append(({**result, "repeat": repeat, "arm": arm}, path, recipe, sealed))
                    save_json(args.out / "runs.json", [entry[0] for entry in rows])
        evaluated = []
        for result, path, recipe, sealed in rows:
            evidence = evaluate(path, recipe, sealed)
            passed = evidence.get("status") == "VERIFIED"
            evaluated.append({**result, "correct": passed and result["generation_exit"] == 0,
                              "functional": passed, "evaluator": evidence.get("status"),
                              "metrics": evidence.get("resources", {}).get("metrics", {})})
            save_json(args.out / "runs.json", evaluated)
        save_json(args.out / "summary.json", {
            "transport": "scripted" if args.scripted else "local",
            "status": "NOT VERIFIED" if args.scripted or len(evaluated) < 15 else "INCONCLUSIVE",
            "comparisons": bootstrap(evaluated, args.arms, args.seed), "runs": len(evaluated),
        })


if __name__ == "__main__":
    main()
