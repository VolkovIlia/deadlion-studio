# Performance command reference

## Static analysis and paired measurement

Run from the Git root. Explicit file arguments also work outside a repository.

    scripts/dl-analyze --changed --json
    scripts/dl-analyze --all --deep
    scripts/dl-perf --baseline './old' --candidate './new' --input data --expected answer --build 'release, same compiler and flags' --tolerance 0.05

The Ruff adapter requires Ruff on PATH. Its PERF findings are hypotheses. Review each native rule with `ruff rule ID`. Unsupported explicit paths and failed tools exit 2. Static checks for C, C++, Rust, Go, Java, Kotlin, JavaScript and TypeScript use ast-grep 0.51.3 on PATH. See ast/tests for positive and negative fixtures. A scan without applicable inputs reports NOT APPLICABLE.

The paired runner requires Linux and Python 3.11+. It feeds the same stdin bytes to each trusted command, checks exact stdout against an independent oracle on every run, alternates order and reports wall time including process startup. Quote each command as one shell argument. The runner parses arguments without shell expansion. Use deterministic commands with bounded output and no shared mutable state. A single stdout fixture covers only that input. Run correctness tests for the full contract separately.

Set tolerance before measuring. The output contains raw nanoseconds and a two-sided sign-test interval of at least 95% nominal coverage for the median paired ratio under independent pairs. Thermal drift and autocorrelation can invalidate that assumption. Run on a controlled host. Exit 0 indicates the upper bound meets the budget, exit 1 a regression and exit 2 missing or inconclusive evidence. Retain JSON with revision IDs, release flags and host details.

## OMP

Export skills with `scripts/export-skills DEST deadlion`, where DEST is a project .agents/skills directory. From the repository checkout load the post-edit adapter with `omp -e ./plugins/deadlion/omp/performance.mjs`. Hooks provide feedback after edit/write. CI re-runs the scan from source.

OMP 19.2.1 includes native autoresearch. The optional checkout command `plugins/deadlion/omp/dl-evolve /tmp/fresh-experiment --goal '...' --check ./verify-candidate --iterations 4 --seconds 300` starts from committed HEAD in a separate clone with the configured OMP model. Reopen with the same directory and `--resume`. A wall-clock deadline includes paused time. Attempt directories record dispatch even if a process dies. Inspect the clone and OMP history before importing a change. The launcher bind-mounts the source tree, common Git directory, limits file and extension read-only with Bubblewrap. A keep request runs the trusted executable from the source tree with the candidate as cwd. That executable must check semantics and independently enforce performance requirements using trusted workload and oracle paths. Use a sandbox and an external verifier for untrusted candidates. The launcher requires Bubblewrap and a user systemd scope and applies --memory-mib and --cpu-percent (defaults 2048 MiB and one CPU equivalent). For a strict total token ceiling establish a provider-side limit before starting. GPU execution is disabled in this launcher.

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

Track an approved contract under `.performance/<feature>/contract.json`. Give it a benchmark object with baseline and candidate argument arrays and an expected-output file. Paths resolve relative to the contract. CI runs dl-perf-gate on every such contract and on the built-in indexed-membership control. Every required budget must have a supported metric. Errors, noisy comparisons and incorrect output fail the step. The JSON line in the job log includes the tested revision, hashes and interval. The optional max_wall_ratio sets an absolute ceiling on candidate/baseline time. Review changes to contracts, workloads, oracles and the CI workflow alongside changes to measured code.

For Python allocation counts put Memray on PATH and run `dl-profile allocations -- script.py [args...]`. The report includes allocation_count and allocated_bytes for the Memray allocator configuration. The optional profiler was exercised with Memray 1.21.0. PMU mode counts userspace events; the Fedora hybrid CPU run used perf 7.3.6 and its hybrid-merge option. Install optional tools separately from the core.
