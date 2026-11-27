import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

TOOLS = (
    Path(__file__).resolve().parents[1] / "plugins/deadlion/skills/performance/scripts"
)
sys.path.insert(0, str(TOOLS))
from candidate_runner import execute  # noqa: E402
from correctness import verify  # noqa: E402
from growth_models import analyze, median_interval  # noqa: E402
from scaling import validate  # noqa: E402


def series(fn, points=range(1, 19)):
    return [dict(dimensions={"n": n}, cost=fn(n)) for n in points for _ in range(7)]


@pytest.mark.parametrize(
    "name,fn",
    [
        ("linear", lambda n: 900 + 7 * n),
        ("quadratic", lambda n: 900 + n * n),
        ("cubic", lambda n: 900 + n**3),
        ("exponential", lambda n: 900 + 2**n),
        ("factorial", lambda n: 900 + __import__("math").factorial(n)),
    ],
)
def test_unseen_sizes(name, fn):
    models = ["constant", "linear", "quadratic", "cubic", "exponential", "factorial"]
    result = analyze(series(fn), models, ["n"], "cost", 1e-8)
    assert result["admissible"] == [name]


def test_indistinguishable_and_sparse():
    models = ["constant", "linear", "quadratic"]
    assert (
        analyze(series(lambda n: 1e10 + n), models, ["n"], "cost", 0.01)["status"]
        == "INCONCLUSIVE"
    )
    assert (
        analyze(series(lambda n: n, range(1, 4)), models, ["n"], "cost", 0.01)["status"]
        == "INCONCLUSIVE"
    )
    assert median_interval([1, 2, 3], 0.95) is None


def test_multidimensional():
    rows = [
        dict(dimensions=dict(V=v, E=e), cost=10 + v + e)
        for v in [20, 50, 100, 200]
        for e in [1, 10, 100, 300]
        for _ in range(7)
    ]
    result = analyze(rows, ["V+E", "V*E", "V**2+E"], ["V", "E"], "cost", 1e-8)
    assert result["admissible"] == ["V+E"]


def test_resource_and_data_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("DL_TEST_PRIVATE", "canary")
    (tmp_path / "data").write_text("ok")
    (tmp_path / "private").write_text("private")
    cmd = [
        "python3",
        "-c",
        "import os,socket;from pathlib import Path as P; "
        "assert list(P.cwd().iterdir())==[P('/work/data')];assert not os.getenv('DL_TEST_PRIVATE');"
        "assert not P('/home').exists();assert socket.if_nameindex()==[(1,'lo')];print(P('data').read_text())",
    ]
    out, m = execute(tmp_path, ["data"], cmd, b"", 4, 96)
    assert out == b"ok\n" and m["wall_ns"] > 0
    with pytest.raises(ValueError):
        execute(tmp_path, ["data"], ["python3", "-c", "open('data','w')"], b"", 2, 96)
    start = time.monotonic()
    with pytest.raises(ValueError):
        execute(tmp_path, [], ["sleep", "2"], b"", 0.2, 96)
    assert time.monotonic() - start < 2


def test_caps(tmp_path):
    for cmd in (
        ["python3", "-c", "print('x'*10000)"],
        ["python3", "-c", "x=bytearray(180*1024**2)"],
    ):
        with pytest.raises(ValueError):
            execute(tmp_path, [], cmd, b"", 3, 80, output_bytes=4096)


def test_numeric_oracle(tmp_path):
    spec = dict(kind="numeric", atol=0.01)
    verify(spec, b"3", b"3.001", b"", tmp_path, 1)
    for output in (b"nan", b"inf", b"3.1", b"3 0"):
        with pytest.raises(ValueError):
            verify(spec, b"3", output, b"", tmp_path, 1)


def test_grid_limit_and_expression():
    source = TOOLS.parents[2] / "evals/scaling-membership/contract.json"
    s = json.loads(source.read_bytes())["scaling"]
    s["limits"]["max_points"] = 4
    with pytest.raises(ValueError, match="max_points"):
        validate(s)
    s["limits"]["max_points"] = 24
    s["models"] = ["f(n)"]
    with pytest.raises(ValueError, match="expression"):
        validate(s)


def test_fast_ast_cached_and_stdin(tmp_path):
    file = tmp_path / "sort.py"
    source = "for key in keys:\n    out.append(sorted(rows))\n"
    file.write_text(source)
    for flags in (
        ["--json", "--cache-dir", str(tmp_path / "cache"), str(file)],
        ["--stdin-name", str(file)],
    ):
        proc = subprocess.run(
            [TOOLS / "dl-analyze", *flags],
            input=source,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "dl-py-repeat-sort" in [
            d["rule"] for d in json.loads(proc.stdout)["diagnostics"]
        ]


def test_state_and_determinism(tmp_path):
    from correctness import checked_run

    verifier = tmp_path / "oracle.py"
    verifier.write_text(
        'import base64,json,sys\np=json.load(sys.stdin)\nsys.exit(base64.b64decode(p["state"]["answer"])!=b"ok")\n'
    )
    oracle = dict(
        kind="external",
        command=[sys.executable, str(verifier)],
        state_files=["answer"],
        deterministic=True,
    )
    cmd = ["python3", "-c", "open('answer','w').write('ok')"]
    assert (
        checked_run(
            tmp_path, [], cmd, b"", b"", oracle, tmp_path, time.monotonic() + 5, 96
        )["wall_ns"]
        > 0
    )
    cmd = [
        "python3",
        "-c",
        "import os;print(os.urandom(12));open('answer','w').write('ok')",
    ]
    with pytest.raises(ValueError, match="repeated execution"):
        checked_run(
            tmp_path, [], cmd, b"", b"", oracle, tmp_path, time.monotonic() + 5, 96
        )


def test_slope_change_and_quantile():
    from growth_models import quantile_interval

    r = analyze(
        series(lambda n: n if n < 20 else n**4 / 20**3, range(1, 50)),
        ["linear", "quadratic"],
        ["n"],
        "cost",
        0.1,
    )
    assert 15 < r["observations"][0]["split"] < 24
    assert quantile_interval([1] * 1000, 0.99, 0.95) == (1, 1)


def test_growth_requirement():
    from scale_report import summarize

    rows = [
        dict(
            implementation="x",
            distribution="fixed",
            dimensions=dict(n=n),
            wall_ns=n**2,
            peak_rss_kib=100,
        )
        for n in (8, 16)
        for _ in range(11)
    ]
    s = dict(
        implementations={"x": {}},
        dimensions={"n": [8, 16]},
        distributions=["fixed"],
        models=["linear"],
        model_tolerance=0.1,
        growth_limits=[
            {
                "implementation": "x",
                "metric": "wall_ns",
                "from": {"n": 8},
                "to": {"n": 16},
                "max_ratio": 2.1,
            }
        ],
    )
    report = dict(choice="x", rows=rows, checks=[], models=[])
    summarize(s, report)
    assert report["status"] == "CONTRADICTED" and report["checks"][0]["interval"] == [
        4,
        4,
    ]


def test_external_holdout_and_fresh_receipt(tmp_path):
    import socket

    sys.path.insert(0, str(TOOLS.parents[2] / "omp"))
    from contract_evaluator import evaluator

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "candidate").write_text("ok")
    template = json.loads(
        (TOOLS.parents[2] / "evals/indexed-membership/contract.json").read_bytes()
    )
    paths = []
    for name in ("training", "holdout"):
        base = tmp_path / name
        base.mkdir()
        (base / "input").write_text(name)
        (base / "expected").write_text("ok")
        template["benchmark"] = dict(
            baseline=["sh", "-c", "sleep .03; printf ok"],
            candidate=["cat", "candidate"],
            expected="expected",
        )
        template["budget"] = {"max_wall_ratio": 1}
        path = base / "contract.json"
        path.write_text(json.dumps(template))
        paths.append(str(path))
    limits = dict(
        contracts=paths,
        candidate_files=["candidate"],
        deadline=(time.time() + 60) * 1000,
    )

    def ask(operation):
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(tmp_path / "verifier.sock"))
            client.sendall(operation)
            return json.load(client.makefile())

    with evaluator(tmp_path, limits):
        assert ask(b"K")["status"] == "NOT VERIFIED"
        assert ask(b"B")["status"] == "VERIFIED"
        assert ask(b"K")["status"] == "VERIFIED"
        assert ask(b"K")["status"] == "NOT VERIFIED"
        assert ask(b"B")["status"] == "VERIFIED"
        (repo / "candidate").write_text("changed")
        assert ask(b"K")["status"] == "NOT VERIFIED"


def test_descendant_accounting(tmp_path):
    code = "a=bytearray(50*1024**2);sum(range(20000000))"
    _, metrics = execute(tmp_path, [], ["python3", "-c", code], b"", 4, 128)
    assert metrics["peak_rss_kib"] > 50 * 1024 and metrics["user_cpu_s"] > 0.02


def test_crossover_is_bracketed_only_by_resolved_points():
    from scale_report import comparisons

    rows = []
    for n in (2, 4, 8, 16, 32):
        for i in range(12):
            for impl, time_ns in (("table", 45), ("scan", 5 * n)):
                rows.append(
                    dict(
                        implementation=impl,
                        distribution="fixed",
                        dimensions={"n": n},
                        repetition=i,
                        wall_ns=time_ns,
                        peak_rss_kib=100,
                    )
                )
    r = dict(rows=rows, comparisons=[])
    comparisons(dict(implementations={"table": {}, "scan": {}}), r)
    assert [
        p["crossover_bracket"] for p in r["comparisons"] if "crossover_bracket" in p
    ] == [[(8,), (16,)]]
    assert all("frontier" in cohort for cohort in r["pareto"])


def test_all_required_files_staged_from_git(tmp_path, monkeypatch):
    import runpy

    script = TOOLS.parents[4] / "scripts/approved-performance"
    stage = runpy.run_path(str(script))["stage"]
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    contract = Path("contract.json")
    contract.write_text(
        json.dumps(
            dict(
                benchmark=dict(
                    candidate=["cat", "candidate"], candidate_files=["candidate"]
                )
            )
        )
    )
    Path("candidate").write_text("approved")
    Path("unrelated").write_text("private")
    subprocess.run(["git", "add", "."], check=True)
    commit = [
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
    ]
    subprocess.run([*commit, "fixture"], check=True)
    dest = tmp_path / "stage"
    dest.mkdir()
    stage(contract, "HEAD", dest)
    assert list(dest.iterdir()) == [dest / "candidate"]
    subprocess.run(
        ["git", "rm", "--cached", "contract.json"], check=True, capture_output=True
    )
    subprocess.run([*commit, "remove contract"], check=True)
    with pytest.raises(ValueError, match="contract removed"):
        stage(contract, "HEAD", dest)


def test_stop_gate_selects_changed_approved_input(tmp_path):
    src = TOOLS.parents[2] / "evals/indexed-membership/contract.json"
    base = tmp_path / ".performance/sample"
    base.mkdir(parents=True)
    record = json.loads(src.read_bytes())
    record["budget"] = {"peak_rss_kib": 64000}
    record["benchmark"] = dict(
        candidate_root="src",
        candidate_files=["impl"],
        candidate=["cat", "impl"],
        baseline=["cat"],
        expected="expected",
    )
    (base / "contract.json").write_text(json.dumps(record))
    (base / "input").write_text("correct")
    (base / "expected").write_text("correct")
    (tmp_path / "src").mkdir()
    impl = tmp_path / "src/impl"
    impl.write_text("correct")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=tmp_path,
        check=True,
    )

    def status():
        r = subprocess.run(
            [TOOLS / "dl-perf-gate", "--changed"], cwd=tmp_path, capture_output=True
        )
        return json.loads(r.stdout)["status"]

    (tmp_path / "styles.css").touch()
    assert status() == "NOT APPLICABLE"
    impl.write_text("incorrect")
    assert status() == "NOT VERIFIED"
    impl.unlink()
    assert status() == "NOT VERIFIED"


def test_adaptive_schedule_reduces_the_next_step():
    from scaling import scheduled
    costs=[]
    points=scheduled({"design":"adaptive","limits":{"max_points":12},"distributions":["one"]},
                     [[2,4,8,16]],costs,time.monotonic()+100)
    assert next(points)==(2,)
    costs.append(.1)
    assert next(points)==(4,)
    costs.append(.4)
    assert next(points)==(5,)
