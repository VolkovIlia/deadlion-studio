# Performance command reference

## Static analysis and paired measurement

Run from the Git root. Explicit file arguments also work outside a repository.

    tools=plugins/deadlion/skills/performance/scripts
    "$tools/dl-analyze" --changed --json
    "$tools/dl-analyze" --all --deep
    "$tools/dl-perf" --baseline './old' --candidate './new' --input data --expected answer --build 'release, same compiler and flags' --tolerance 0.05

The Ruff adapter requires Ruff on PATH. Its PERF findings are hypotheses. Review each native rule with `ruff rule ID`. Unsupported explicit paths and failed tools exit 2. Static checks for C, C++, Rust, Go, Java, Kotlin, JavaScript and TypeScript use ast-grep 0.51.3 on PATH. See ast/tests for positive and negative fixtures. A scan without applicable inputs reports NOT APPLICABLE.

The paired runner requires Linux and Python 3.11+. It feeds the same stdin bytes to each trusted command, checks exact stdout against an independent oracle on every run, alternates order and reports wall time including process startup. Quote each command as one shell argument. The runner parses arguments without shell expansion. Use deterministic commands with bounded output and no shared mutable state. A single stdout fixture covers only that input. Run correctness tests for the full contract separately.

Set tolerance before measuring. The output contains raw nanoseconds and a two-sided sign-test interval of at least 95% nominal coverage for the median paired ratio under independent pairs. Thermal drift and autocorrelation can invalidate that assumption. Run on a controlled host. Exit 0 indicates the upper bound meets the budget, exit 1 a regression and exit 2 missing or inconclusive evidence. Retain JSON with revision IDs, release flags and host details.

## OMP

Export skills with `scripts/export-skills DEST deadlion`, where DEST is a project .agents/skills directory. From the repository checkout load the post-edit adapter with `omp -e ./plugins/deadlion/omp/performance.mjs`. Hooks provide feedback after edit/write. CI re-runs the scan from source.

OMP 19.2.1 provides native Autoresearch. Start from a trusted committed repository. A fresh external workspace holds its clone, history, dispatch slots and evaluation receipts.

    plugins/deadlion/omp/dl-evolve /tmp/experiment --goal 'Improve the approved workloads' --candidate-file indexed.py --contract /approved/train/contract.json --holdout-contract /approved/control/contract.json --iterations 4 --seconds 300

Repeat `--candidate-file` for editable regular files. Run `dl-evolve /tmp/experiment --resume` to continue within the original deadline. Use an explicit OMP provider profile with models.yml/config.yml and an environment API key. The controller receives a private profile and can contact the provider. The agent edits the declared files using candidate_shell. Candidate jobs receive an empty network namespace, clean environment, system runtime, private /tmp, and only the declared files. Native OMP continues to manage Git decisions. Training and holdout gates run outside OMP. With scaling evidence, the primary cost is the largest paired median time ratio of the selected implementation across measured points and comparators. A changed candidate needs a fresh measurement.

For an existing trusted data-only verifier, use `--check ./verify-candidate` with a checked-in autoresearch.sh and declared candidate files. The verifier receives the declared files read-only and reports VERIFIED plus its metric interval. A verifier which executes or imports candidate code in that same process cannot independently attest its result. Use the contract pair for executable candidates. The host needs Bubblewrap, user namespaces and a working user systemd manager with CPU, pids and memory controllers.

## Profiling

Use scripts/dl-profile resources -- COMMAND for Linux CPU time, peak RSS and context switches via GNU time. The pmu mode runs perf stat for the selected generic counters. It reports NOT VERIFIED when the host or its permission policy cannot supply the complete group. Use the profiler appropriate to the question, including allocators and GC for managed runtimes. PMU counts and peak RSS describe different resources. Repeat profiles on identical workloads.

Use --cache-dir DIR with dl-analyze for a private local cache of up to 256 clean Ruff snapshots. The key includes the source content, absolute path, runner and Ruff binary identity. Structural scans and CI run fresh.

For a single comparable cohort run `scripts/dl-perf frontier cohort.json`. Supply directions keyed by metric and candidates keyed by name, each with status and metrics. Only VERIFIED candidates enter the Pareto calculation. Keep the original observations, units, correctness tests and uncertainty with the cohort. Point estimates on the frontier can still be indistinguishable within measurement noise.

Use `dl-profile --max peak_rss_kib=65536 resources -- COMMAND` for an absolute memory ceiling. Exceeding a declared ceiling emits ERROR and exits 1. An unavailable requested metric emits NOT VERIFIED and exits 2.

Use --pause-after N to stop at a logged checkpoint. Resume retains the original absolute deadline, source revision, OMP history, saved changes and consumed attempt slots. The launcher exposes a private /dev without host GPU devices.

On success the independent verifier prints a JSON object with status VERIFIED and a two-element numeric interval for the reported primary metric. Deadlion rejects a keep outside those bounds, malformed evidence and a nonzero verifier exit. For a deterministic operation count the bounds may be equal.

The --patience option stops after consecutive logged discards (default 3). --tokens stops on observed foreground model usage. It checks completed messages and can exceed its threshold by the in-flight response. It does not cap provider-side or auxiliary calls. A strict total token budget still needs provider-side enforcement.

### Reproduce on Fedora

From a checkout, install only the adapters you intend to run. The tested Python adapter used `pipx install ruff==0.15.4`. A project-local ast-grep install can use `npm install --prefix /tmp/deadlion-tools @ast-grep/cli@0.51.3` and `export PATH="/tmp/deadlion-tools/node_modules/.bin:$PATH"`. Run `ruff --version` and `ast-grep --version` before the first scan. The unrelated Unix sg utility cannot substitute for ast-grep.

    bin="$PWD/plugins/deadlion/skills/performance/scripts"
    corpus="$PWD/plugins/deadlion/evals/indexed-membership"
    "$bin/dl-contract" "$corpus/contract.json"
    "$bin/dl-analyze" --changed --json
    "$bin/dl-perf" --baseline "python3 '$corpus/scan.py'" --candidate "python3 '$corpus/indexed.py'" --input "$corpus/input" --expected "$corpus/expected" --build "same CPython" --tolerance 0.05
    ast-grep test --skip-snapshot-tests -c plugins/deadlion/skills/performance/ast/sgconfig.yml

For the false-sharing fixture compile counters.c twice using the same C11 compiler, -O2 and -pthread. Use -DSTRIDE=8 on the second build. Pass two available logical CPUs on different physical cores to both commands. The recorded run uses cores with logical CPU IDs 0 and 2 and 64-byte lines. The oracle is the file expected and the input is /dev/null.

### Required CI contracts

Track an approved contract under `.performance/<feature>/contract.json`. Give it a benchmark object with baseline and candidate argument arrays and an expected-output file. Benchmark paths are relative to the contract by default. The optional `budget.max_wall_ratio` sets a ceiling on the candidate/baseline time ratio. Push CI evaluates the checked-out contracts and the built-in indexed-membership control.

For Python allocation counts put Memray on PATH and run `dl-profile allocations -- script.py [args...]`. The report includes allocation_count and allocated_bytes for the Memray allocator configuration. The optional profiler was exercised with Memray 1.21.0. PMU mode counts userspace events; the Fedora hybrid CPU run used perf 7.3.6 and its hybrid-merge option. Install optional tools separately from the core.

For a pull request, the base revision supplies the evaluator, approved contracts, baseline, workload and oracle. Only the approved candidate files come from the proposed revision. The `performance-evidence` artifact contains one JSON line per contract with both commit IDs. Missing required metrics yield `NOT VERIFIED`. For timing intervals that straddle the limit, remeasure the same revisions on a controlled runner. Set `"ci_inconclusive": "advisory"` in the approved contract to allow that outcome in PR CI. To repeat the comparison locally, run the base revision's `dl-perf-gate /path/to/base/contract.json --candidate-dir /path/to/changed/feature --isolated`.

For closed-loop command latency run `dl-perf load --input input --expected expected --workers 4 --requests 120 -- python3 indexed.py`. Each timed request starts a process and checks its response bytes. The output contains raw latency in nanoseconds, nearest-rank p50/p95/p99 and aggregate requests per second. For a persistent network service, use a service-specific driver and validate responses there.

Pass `--require-hard-token-cap` to dl-evolve when exceeding the provider token limit is unacceptable. The current transport exits before starting or resuming the experiment because it supports accounting only after a foreground message completes.


## Scaling experiments

Run from a checkout with Linux, Python 3.11+, Bubblewrap and a user systemd manager.

    tools=plugins/deadlion/skills/performance/scripts
    contract=plugins/deadlion/evals/scaling-membership/contract.json
    "$tools/dl-contract" "$contract"
    "$tools/dl-perf" scale "$contract" --output /tmp/scale.json --csv /tmp/samples.csv
    "$tools/dl-perf" scale "$contract" --replay /tmp/scale.json --extrap /tmp/scale.jsonl
    "$tools/dl-perf-gate" "$contract" --isolated

The contract's `scaling` object declares named axes as positive integer lists or `{min,max,growth}`. Choose `design` grid, axes or adaptive (one axis). The generator reads one JSON object with dimensions, distribution and seed from stdin. Return input and expected as UTF-8 strings or input_base64 and expected_base64 for binaries. Supply one argv and a relative file allowlist per implementation. Include required helper modules explicitly. Prebuild native binaries in a trusted build environment or build them using the isolated candidate shell. External dependencies must exist in the mounted system runtime.

An optional instrument argv returns JSON with output and integer counters. These runs are separate from timing. Reported counters have explicit provenance and are descriptive. The evaluator can compare a fixed reference, seeded differential or property-based workloads, exact bytes or finite whitespace-separated decimals. Configure `benchmark.oracle` for fixed workloads and `scaling.oracle` for generated workloads. Use `{"kind":"numeric","atol":1e-10,"rtol":1e-8}` or `{"kind":"external","command":["python3","verify.py"],"state_files":["answer"],"deterministic":true}`. The external verifier receives base64 input, actual, expected and named output files in a JSON packet. Exit 0 accepts, 1 rejects and other exits indicate verifier failure. Determinism adds a separate repeat of the same input.

Model formulas accept dimension names, positive powers, sums, products, log, sqrt and factorial. Default named families use the first axis. For multiple axes specify formulas such as `["V+E","V**2+E","V*E"]`. Model tolerance means relative prediction error on unseen coordinates. Expected models apply to the chosen implementation. Requirements compare the population median at each coordinate to a declared maximum. Growth limits compare medians across explicit coordinates. CI always measures fresh evidence. Replay trusts a local report for exploratory analysis only.

Fixed budgets use the exact unit-bearing field names emitted by dl-profile, latency_p50_ns, latency_p95_ns, latency_p99_ns, min_requests_per_second, cpu_time_s, allocations_per_operation or allocated_bytes_per_operation. Per-operation values require an independently declared positive benchmark.operations_per_input. relative_budget maps metrics to candidate/baseline ratio limits. Isolated execution supports elapsed time, CPU, RSS, PMU where permitted, and sequential request latency/throughput. Throughput in isolated mode includes service dispatch. Memray requires trusted Python programs. Missing required measurements exit 2. A p99 gate requires at least 1000 requests and uses an order-statistic interval.

Set DL_PERF_CONTRACT to an approved external contract and DL_PERF_CANDIDATE_DIR to the implementation directory when loading the OMP performance extension for a contracted task. Its session_stop handler evaluates the current candidate before completion. Without that variable, dl-perf-gate --changed selects approved contracts from .performance by changes to contract directories and declared candidate files. Set benchmark.candidate_root relative to the project root when sources live outside the contract directory. DL_PERF_BASE selects the approved revision, default HEAD. Changes outside contracted paths use the fast path. Review a trusted project using dl-analyze --changed --deep --native --json. The report identifies selected and unavailable project analyzers.

For PMU scaling add, for example, `"metrics":["instructions","cycles"]` inside scaling. Each instrumented run receives the same verified input as its independent time measurement. Use dl-analyze --infer-cost --json File.java for a fresh Java capture with Infer and javac on PATH.
