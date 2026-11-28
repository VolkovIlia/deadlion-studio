# Deadlion Studio 4.6.1 for OMP

Audit base `fcacc3e98acadc29d4550bf31b44da8f27f488a0` (`v4.6.0`). Verification environment Fedora 44, Linux 7.2.11, Node 22.22.2, and real OMP with a loopback scripted transport. Model quality and paid providers were outside this release. [Audit revision](https://github.com/VolkovIlia/deadlion-studio/tree/fcacc3e98acadc29d4550bf31b44da8f27f488a0)

## Install and migrate

On Fedora, install Git, Python and util-linux `flock`. Install Lizard for structural measurements of supported non-Python sources. Link the package and restart OMP.

```sh
git clone --branch v4.6.1 --depth 1 https://github.com/VolkovIlia/deadlion-studio.git
omp plugin link "$PWD/deadlion-studio/plugins/deadlion"
```

For an archive installation, download `deadlion-studio-4.6.1.tar.gz` and its `.sha256` file into the same directory. Run `sha256sum -c deadlion-studio-4.6.1.tar.gz.sha256` before extraction. Link `deadlion-studio-4.6.1/plugins/deadlion` with OMP. Keep the linked directory at the same path. [Release downloads and checksums](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.1)

1. Run `/deadlion setup` again after upgrading. The previous automatic approval format must be reviewed. With an external `DL_ENGINEERING_POLICY`, review any existing `testsScope: ["."]` against the actual integration tests. Start a new engineering task after changing approval.
2. Before upgrading an in-progress 4.6.0 campaign, stop its OMP sessions and retain the checkout, project evidence and plan. Legacy stage receipts predate scoped execution and symbol metrics. Use `/deadlion refactor cancel` if the old campaign has a reservation, then `/deadlion refactor cancel campaign` and `/deadlion refactor archive`. The archived global baseline and receipts retain their original meaning. Start the new campaign on the reviewed checkout. Old campaigns cannot be resumed as 4.6.1 campaigns with the original milestone receipts.
3. Replace meaningful legacy `Constraints:` entries with `Advisory:` guidance or a `Required:` check name backed by operator policy. Review existing `Checks:` against their actual executable commands. Leave `Verify:` as human-readable guidance.

## Scoped functional verification

`/deadlion setup` shows a numbered candidate suite, its working directory and the reason for its suggested scope. The approval hash by itself enables project-native tooling. A JSON map explicitly records the components for which the operator accepts the suite as functional evidence.

```text
/deadlion setup
/deadlion setup approve <hash> {"1":["frontend"],"2":["backend"]}
```

Discovered suites require positive runner evidence. The supported summaries include TAP, pytest, Cargo, Maven and Go test JSON. Skips, cancellations, filtered runs and zero completed tests can leave a suite unverified. For a runner whose output is unavailable or unsupported, approve an independently reviewed exit-code oracle through the operator policy and name its inputs. A receipt distinguishes invoked argv, observed runner counts and the operator's declared scope. Functional coverage of an individual behavior still depends on what the suite asserts.

```json
{
  "checks": [
    {
      "name": "backend integration",
      "argv": ["python3", "-m", "pytest", "-q", "tests/integration"],
      "cwd": "backend",
      "type": "functional",
      "scope": ["backend", "schemas"],
      "requireTestCount": true
    }
  ],
  "verificationInputs": ["backend/tests/integration", "fixtures"]
}
```

Shared schemas, public headers, migrations and build manifests conservatively require the affected component scopes. Added and removed components use the union of old and current manifests. Moves are reviewed from both paths. Protect custom fixtures, ignored outputs, compiler settings and external build inputs explicitly with the existing policy and `DL_COMPILE_COMMANDS`. The strict gate checks the working tree, affected staged paths and approved input identities. These checks operate within the trusted developer account. Strict candidates still use the existing isolated evaluator.

## Refactoring lifecycle and constraints

A campaign is `ACTIVE`, `PAUSED`, `COMPLETED`, `CANCELLED` or `ARCHIVED`. A milestone is `WAITING`, `READY`, `ACTIVE`, `VERIFIED`, `FAILED`, `PAUSED` or `CANCELLED`. A failed or cancelled milestone never satisfies a dependency. A verification of an unchanged stage has no checkpoint to accept.

- Use `/deadlion refactor start plan.md` and `/deadlion refactor begin T1`. Give the next implementation prompt to the selected OMP session.
- Use `/deadlion stop` to interrupt an active run. Use `/deadlion refactor pause` and `resume` for the campaign. Open the owning OMP session and use `/deadlion refactor recover` after an interrupted stage. Recovery checks the owner identity, original checkpoint, task, session and current changes. Review its record under `recovery/` before giving the next prompt. The task's original time and analysis budgets still apply.
- Use `/deadlion refactor cancel` to abandon a reserved stage. Any edits remain on disk and the checkpoint stays at the last verified state. Restore the tested contents through an operator-owned change or retain the edits for independent verification in a new task. Reopening the stage requires the checkpoint. `reconcile` accepts Git identity changes when tested bytes are unchanged and the index agrees.
- Edit an unfinished plan entry, run `/deadlion refactor revise`, then approve the printed hash with `/deadlion refactor revise <hash> <reason>`. Approval records the previous plan and the new revision. Keep verified stages immutable and express new requirements as follow-up milestones.
- Run `/deadlion refactor verify` for cumulative verification using the original baseline and the approved time and analysis limits. An interrupted final check can be rerun. `report` rechecks the final receipt, plan, sources and approved inputs. `archive` after completion or after `cancel campaign` preserves receipts and plan revisions under `refactoring/history/<worktree>/<campaign-id>`. Use `history` to find the archived paths.

```md
### T1: Simplify the storage workload
Files: storage
Depends: —
Change: Preserve storage behavior and bound the measured memory.
Test: Storage integration suite.
Verify: python3 -m pytest -q tests/storage
Required: plan: storage integration, structural ratchet, trusted profile
Advisory: Prefer existing interfaces
```

`plan: storage integration` must resolve to a typed, operator-approved check with executable argv. Functional constraints require successful coverage of the relevant paths. `trusted profile` needs a configured `profile.max` and actual measurements for those metrics. Use `approved contracts` or `performance contract` when the named gate is applicable and its receipt confirms execution. Use `protected verification inputs` to bind the declared protected paths and input fingerprints. A name, a shell no-op or advisory prose alone yields no required evidence. Final verification repeats required constraints and cumulative structural checks. Project contracts compare against the approved Git revision. The report retains separate initial and final observations from the actual checkout. A dirty original checkout and its Git revision can represent different baselines. Use a pinned workload and limit for each desired cumulative regression check.

Structural measurements use Python AST qualified names and signatures or Lizard names and source spans. A unique, unchanged normalized body can preserve the baseline of a moved or renamed symbol within the same language. Copying a legacy function cannot transfer its exemption. Ambiguous matches and unavailable measurements are inconclusive. The fallback fingerprint is structural evidence and does not establish semantic equivalence. An unchanged over-limit legacy function may improve gradually while correctness and resource constraints remain required.

## Defects and evidence

| ID | Origin at audit revision | Reproduction and fix | Evidence and result |
| --- | --- | --- | --- |
| S-01 | `capabilities.py:130`, `gate.mjs:236` | Initial OMP reproduction gave VERIFIED for a broken backend with only a frontend-shaped `make test` approval. Discovery now proposes scope. The actual suite must be approved and complete. | `omp_stability_smoke.py` exercised two components, a shared schema, a skipped suite and approved success on both OMP versions. **VERIFIED** |
| S-02 | `gate.mjs:52` | Stage a file, change the worktree, and run a check of the unstaged bytes. Inspect both index and dirty tracked paths, including changes present at task startup. | `omp_stability_smoke.py` produced BLOCKED on both OMP versions. The same fixture rejected mutation of a pinned ignored oracle. **VERIFIED** |
| S-03 | `refactor.mjs:116,129,152,242` | Previous state reused a worktree slot indefinitely. Terminate real OMP with SIGKILL during its lease, recover in the owning session and recheck. Archive frees the campaign slot. | `omp_refactoring_smoke.py` exercises cancellation after a refused write, approved revision, SIGKILL recovery, native parallel integration across disjoint API and storage paths, final verification, stale receipts, archive and a new campaign. **VERIFIED** for the exercised transitions. |
| S-04 | `refactor.mjs:28,179,213` | Prose alone could appear in an approved plan. Enforce typed gates and preserve the original campaign baseline. Final limits come from the original operator policy. | Live fixture executes functional checks, structural ratchet and an actual peak RSS budget, including a final rerun. It rejects a no-op named as a memory check and a measured budget violation. **VERIFIED** for those constraints. Arbitrary performance delta constraints need an approved comparative contract. |
| S-05 | `structural.py:25–34`, `refactor.mjs:84` | Positional keys lost identity after reordering. Dependency lists were passed to numeric comparison. Use qualified keys, unique one-to-one relocation and actual dependency counts. | Node regression measures Python AST data and checks insert, reorder, rename, relocation, copy, nested/async functions, growth, improvement and source relocation out of measurement and reordered C++ overloads. An isolated Python invocation also verifies the unavailable-Lizard outcome. **VERIFIED** for those cases. Cross-language semantic identity remains **NOT VERIFIED**. |
| S-06 | `performance.mjs:244,422` | Each ordinary LSP diagnostics tool call did two whole snapshots. Keep the interactive result advisory and obtain authoritative diagnostics in the final gate. | Two helper invocations removed from the call path. Native diagnostics and Python hover regressions exercised. See measurement below. **VERIFIED** for snapshot elimination. |
| S-07 | `diagnostics.mjs:96` | Cold rust-analyzer returned `OK` on an erroneous fixture. Treat such responses as inconclusive. Distinguish partial reports with unavailable servers. | Real Rust workspace and an observed E0308 error. See the matrix for remaining operations. **VERIFIED** for the reproduced case. |
| S-08 | `semgrep.mjs:33–35` | A scanned path or empty file list could pass without an applicable rule. Require per-target matching evidence and a nonempty request. | Structured-result regressions cover empty rule applicability and an empty request. Semgrep 1.148.0 emitted the Kotlin fixture finding and rejected an unrelated Python-only ruleset. Detekt 1.23.8 reported the Kotlin primitive-wrapper fixture. **VERIFIED** for those rules. [Semgrep CLI output schema](https://github.com/semgrep/semgrep-interfaces/blob/main/semgrep_output_v1.jsonschema) |

The implementation paths are under [plugins/deadlion/omp](../plugins/deadlion/omp). The automated cases are in [stability smoke](../tests/omp_stability_smoke.py), [refactoring smoke](../tests/omp_refactoring_smoke.py), [LSP matrix](../tests/omp_lsp_matrix.py) and [readiness tests](../tests/test_readiness_omp.mjs).

## Native LSP coverage

| Language | Server and test environment | Startup | Diagnostics | Semantic query | Performance analysis |
| --- | --- | --- | --- | --- | --- |
| C, C++ | clangd 22.1.8 | STARTED | VERIFIED | NOT VERIFIED | clang-tidy availability depends on the project |
| Python | pylsp | STARTED | NOT VERIFIED in this matrix | VERIFIED for targeted list hover | Python AST hints available |
| TypeScript | typescript-language-server | STARTED | VERIFIED | NOT VERIFIED | Heuristics depend on available rules |
| Go | gopls 0.24.0, Go 1.27.1 | STARTED | VERIFIED for type mismatch | VERIFIED for hover type and definition | Staticcheck availability depends on the project |
| Rust | rust-analyzer 1.100.1 | STARTED | VERIFIED for a warmed Cargo workspace E0308 case. Cold empty reports remain INCONCLUSIVE. | NOT VERIFIED | Clippy exercised separately |
| Java | Eclipse JDT LS from the Red Hat Java 1.59.2026112708 package | STARTED | VERIFIED for an Eclipse workspace type mismatch | NOT VERIFIED | Infer Cost and PMD remain NOT VERIFIED for this fixture |
| Kotlin | JetBrains standalone 271.2085.0 and community 1.3.13 | INSTALLED | NOT VERIFIED | NOT VERIFIED | Semgrep and Detekt each confirmed for one local rule |

The additional Go, Rust and Java diagnostics were observed on OMP 19.2.1. The matrix describes the tested operations. Definitions, references, implementations, document symbols, call hierarchy and the requested Kotlin collection/coroutine and other language-specific performance cases remain open. The community Kotlin server failed to initialize on the host JDK 25 and timed out through OMP with Temurin 21. Type-resolved Detekt rules such as ArrayPrimitive require an approved project classpath. The built-in Detekt invocation was confirmed for a syntax-based performance rule. The JetBrains standalone startup required accepting its EULA. [OMP built-in server configuration](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/packages/coding-agent/src/lsp/defaults.json) · [Eclipse JDT LS](https://github.com/eclipse-jdtls/eclipse.jdt.ls) · [JetBrains Kotlin Language Server](https://github.com/Kotlin/kotlin-lsp)

## Tests, overhead and CI

Local tests ran with established tool binaries and scripted OMP. The Python suite passed 174 tests with Rust, Clippy and Detekt installed. The Node suite passed 18 tests with Lizard and Semgrep installed. The live engineering suite passed with OMP 19.2.1 and OMP 19.2.0. Scoped coverage and staged-state regressions passed on both. The Fedora user systemd manager exposed `cpu.max` as `100000 100000`. Live Evolution and Autoresearch passing runs exercised the existing isolated evaluator. Local `dl-size` and `git diff --check` passed. GitNexus classified the tracked diff as critical because it reaches verification, task initialization and milestone checkpoint flows.

GitHub CI runs the stability scenario against both pinned OMP versions. The release notes link to the hosted checks for the tagged revision and list any skipped scenarios. The hosted workflow for 4.6.0 skipped the nested Evolution and Autoresearch scenarios after its CPU quota preflight. [4.6.1 release results](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.1) · [4.6.0 hosted run](https://github.com/VolkovIlia/deadlion-studio/actions/runs/46130344753)

```sh
python3 -m pytest tests -q -rs
node --test tests/test_*_omp.mjs
python3 tests/omp_engineering_smoke.py
python3 tests/omp_stability_smoke.py
python3 tests/omp_refactoring_smoke.py
python3 tests/omp_lsp_matrix.py
python3 tests/omp_engineering_evolution.py
python3 tests/omp_autoresearch_smoke.py --contracts
```

For local isolation use Fedora with Bubblewrap, cgroup v2, user systemd and delegated CPU quotas. The workflow runs an actual nested namespace and quota preflight. If those capabilities are unavailable, record `UNSUPPORTED`. The PR performance workflow checks out the trusted base with read-only contents permission and runs the approved evaluator separately. `CODEOWNERS` covers the tree. At audit time the GitHub API reported `main` unprotected and no repository rulesets. The repository owner can require the Live OMP engineering, stability and refactoring checks for both pinned versions and the Approved performance evidence job.

Snapshot overhead was measured with seven warm repetitions on Git fixtures of 512-byte Python files. Run the existing `python3 -I plugins/deadlion/omp/workspace.py` from a fixture directory once or twice per timed sample. The two-call median was **106.42 ms** at 1,000 files and **451.44 ms** at 10,000. The one-call control was **54.07 ms** and **231.99 ms** respectively. The interactive diagnostics path removes both calls. The strict final gate still fingerprints the tree and reruns required diagnostics. These are helper costs measured separately from language-server latency. End-to-end speedup and large-repository peak memory remain **INCONCLUSIVE**.

## Remaining limits

- Refactoring evidence is grounded in a two-component scope fixture and a small three-module campaign with two native subagents. Larger production-style cases remain unverified. Competing worktrees, conflict resolution and rollback of a real parallel refactoring are still operator-managed and **NOT VERIFIED**. The OMP hooks reject write-scope violations and symlink traversal. The final gate reviews the integrated checkout.
- Profiler-unavailable behavior remains outside the live campaign coverage. Passing and failing peak RSS ceilings were both observed. A successful cumulative final gate establishes the requirements configured for the tested workloads.
- Test coverage depends on accurate operator scope and fixture protection. Unknown ignored inputs and same-user tampering remain outside the guarantee. There was no OS isolation change.
- Ratchet keeps existing function metrics within their baseline. More complex moves involving both renamed and edited bodies, overload permutations across languages and formal decomposition need manual review or additional evidence.
