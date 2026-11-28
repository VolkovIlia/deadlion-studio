# Deadlion Studio 4.6.0 for OMP

Deadlion links task completion to approved verification. Each receipt identifies the workspace, checks, and changed paths it covers. A task can complete with a scope of `read-only` when the workspace comparison finds no changes.

## Install

Clone the tag or extract the release archive. For the archive, check the SHA256 before extracting. Keep the package at its linked path. [Release downloads](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.0)

```sh
git clone --branch v4.6.0 --depth 1 https://github.com/VolkovIlia/deadlion-studio.git
omp plugin link "$PWD/deadlion-studio/plugins/deadlion"
cd /path/to/project
omp
```

Project installations can use the local marketplace and `omp plugin install --scope project deadlion@deadlion-studio`. Run `omp plugin uninstall deadlion-studio` to remove a user link. Restart OMP after switching plugin revisions. The original release evidence remains available. [4.5.0 guide](omp-engineering.md)

## Setup and policy

Run `/deadlion setup` to discover project manifests, languages, analyzers and a test entry point without running project code. The output includes an approval command tied to the discovered configuration. Approval enables the listed project-native checks, including language servers. The operator policy supplied through `DL_ENGINEERING_POLICY` takes precedence. Project trust is stored under `$XDG_STATE_HOME/deadlion/projects`, with `~/.local/state` as the default state home.

Standard mode checks changed code for structural limits and available Computer Science diagnostics. Python AST hints can run without Ruff. Native analysis, language servers and tests can execute project code. Ordinary OMP sessions share the user's permissions. Run strict candidate evaluation through the existing isolated contract or Evolution runner.

An operator policy for a Python project can explicitly state the verification scope.

```json
{
  "tests": ["python3", "-m", "pytest", "-q"],
  "testsScope": ["src", "tests"],
  "protectedPaths": ["tests/contracts"],
  "verificationInputs": ["pyproject.toml", "fixtures/oracle.json"],
  "performancePaths": ["src/hot_path.py"],
  "trustProject": true
}
```

| Field | How the gate uses it |
| --- | --- |
| `tests`, `testsScope` | Run approved argv and accept the declared project-relative coverage. Use `["."]` only if the verified integration scope covers the whole project. An existing command without `testsScope` runs and produces a receipt with no asserted coverage. |
| `checks` | Run the named operator checks. A functional check can declare `"type": "functional"` and `"scope": ["component"]`. |
| `protectedPaths` | Block changes to protected tracked or unignored project inputs during the task. |
| `verificationInputs` | Pin the content of listed files or directories across verification, including ignored inputs. List compile flags, oracle fixtures and external dependencies reachable within the workspace when they affect results. Use `DL_COMPILE_COMMANDS` for an external compilation database. |
| `performancePaths` | Raise the mode for actual changes to designated resource-sensitive paths. |
| `native`, `requiredAnalyzers`, `requireLsp` | Opt into native analysis or require a named analyzer or fresh semantic diagnostics. Required unavailable checks block a passing verdict. |

A performance contract records resource evidence and the oracle result for its declared candidate files and workload. The gate requires functional evidence for other changed paths. Shared schemas, headers and build manifests conservatively require coverage across discovered components. Controlled tests need reapproval when their existing inputs change alongside production code.

Use `/deadlion status` for the current task and remaining budget, `mode` for routing, `verify` for the gate and `report` for the persisted receipt. Use `stop` to end an unfinished task, `continue` or `resume` to reuse it, `retry` to rerun its checks and `new` to start from a fresh baseline. The RPC launcher accepts `--resume ID`, waits for settlement and checks the final receipt and fresh workspace fingerprint before exiting 0.

## Compatibility

The status applies to the capabilities exercised on Fedora 44. The compatibility adapter records known lifecycle contracts and checks the runtime session interface. Other versions can expose configuration and diagnostics even when mandatory enforcement remains unverified.

| OMP | Core | Lifecycle | LSP | Quality Gate and RPC | Subagents | Evolution |
| --- | --- | --- | --- | --- | --- | --- |
| 19.2.1 | VERIFIED | VERIFIED | PARTIALLY VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| 19.2.0 | VERIFIED | VERIFIED | PARTIALLY VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| Other | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |

Native diagnostics were exercised with clangd for C/C++ and the TypeScript language server. The Python fixture exercises targeted pylsp hover while retaining heuristic confidence for the original AST finding. Runtime Rust, Go, Java and Kotlin LSP evidence is pending. [Evidence and commands](omp-4.6-report.md)

## Multi-session refactoring

Extend the existing workflow `plan.md` and mark it `Status: approved`. An entry uses the workflow's task format. Add `Checks:` for comma-separated exact Quality Gate check names and `Constraints:` for stage-specific constraints. `Owners:` can assign nonoverlapping paths to OMP agent names.

```md
### T2: Extract storage
Files: storage, tests/storage
Project: —
Change: Preserve the storage interface while moving query preparation.
Test: Run the storage API integration suite.
Verify: python3 -m pytest tests/storage
Checks: functional tests
Depends: T1
Owners: implementer=storage, tester=tests/storage
- [ ] done
```

Use normalized relative paths without trailing slash in the actual `Files:` field. `Verify:` documents the command. Configure its approved invocation and functional coverage in the operator policy. An OMP model never gets shell execution merely because a command appears in the plan.

1. Run `/deadlion refactor start path/to/plan.md` once. The global snapshot includes original dirty state fingerprints, the tracked patch, a project inventory, structural measurements and an initial receipt.
2. Run `/deadlion refactor begin T1` and give the implementation prompt. Deadlion reserves the milestone and records a new milestone baseline. Successful gates write a checkpoint. A failed gate keeps dependent stages waiting.
3. Resume the OMP session shown by `/deadlion refactor status`. In RPC use `dl-omp --resume ID`. After an operator commit, `/deadlion refactor reconcile` accepts a new Git identity if the checked source bytes are the same and the updated index agrees. Unreconciled edits prevent progression.
4. Run `/deadlion refactor verify` after all milestones. This rechecks cumulative changes against the original baseline. `/deadlion refactor report` points to the comparison. A later source change invalidates the final status.

The structural ratchet allows a pre-existing over-limit metric to improve or remain at its milestone value. New and worsened violations fail. Runtime enforcement and write attribution apply to supported OMP hooks and final disk comparisons. Use OMP's isolated worktree support for independent larger work and review the integration in the parent. Checkpoint files preserve source identity and the existing Git working copy is left under operator control.

## CI and experimental evidence

The CI workflow pins OMP release binaries by SHA256. Live checks exercise the real harness with a loopback scripted provider, including RPC, lifecycle, LSP, Evolution, Autoresearch and refactoring. The isolation preflight fails the job when the base isolation layer is unavailable. Evolution and Autoresearch report `UNSUPPORTED` and skip the test step if hosted runners lack nested namespaces or a delegated CPU quota. Run those checks on a Fedora host with cgroup v2 and a user systemd manager. Branch rules determine which checks are required for merging. The pull-request performance workflow uses the evaluator from the trusted base revision. [GitHub Actions](https://github.com/VolkovIlia/deadlion-studio/actions/workflows/ci.yml)

For a real-model comparison, run the scripts from a Git checkout with access to the 4.5.0 baseline. Start an approved local inference server and use a new output directory.

```sh
python3 tests/omp_llm_experiments.py \
  --endpoint http://127.0.0.1:8080/v1 --model MODEL_ID \
  --repeats 5 --seconds 60 --out /tmp/deadlion-comparison
```

The A/D/E protocol sets equal tool and wall-clock limits, preserves failure rows and evaluates sealed solutions after generations finish. The bundled holdouts are suitable for plumbing checks. Use separately maintained holdouts for scientific claims. [Verification report](omp-4.6-report.md)
