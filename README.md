# Deadlion Studio

[![CI](https://github.com/VolkovIlia/deadlion-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/VolkovIlia/deadlion-studio/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/VolkovIlia/deadlion-studio)](https://github.com/VolkovIlia/deadlion-studio/releases)
[![License: Apache-2.0](https://img.shields.io/github/license/VolkovIlia/deadlion-studio)](LICENSE)

Deadlion Studio provides an engineering workflow for OMP, Claude Code and Codex.
The core plugin takes a project from design to release. Its performance tools
compare implementations against a fixed workload, correctness oracle and resource budget.

**Deadlion Studio 4.6.6** reuses qualifying scoped test evidence from independent OMP runs and returns unresolved checks to the agent. [Release downloads](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.6) · [OMP recovery and migration](docs/omp-recovery.md)

`dl-perf scale` measures how runtime, memory and operation counts change across input sizes and distributions. It reports which growth models fit the measured range and where the evidence cannot distinguish between them.

## Engineering workflow

1. **Suckless + Unix engineering** — a system is split into small programs under
   `projects/<name>/`. Each has one job, its own language, Makefile, man page and
   budget (≤2000 SLOC, ≤5 direct dependencies). Programs talk through pipes, files,
   exec chains and plumbing/porcelain. Functions ≤50 lines, files ≤500, enforced by
   a hook.
2. **UI/UX design** — the lowest UI rung that serves the job: CLI, filter, TUI,
   native GUI or web. Flows, states, a key map and design tokens in `config.def`,
   with numeric gates per rung; every UI works alone and embeds. Verified in a
   headless tmux (`dl-tui`) or a real browser through the Playwright MCP.
3. **Product discovery** — problem, users and jobs, evidence-tagged claims, the
   riskiest assumption tested against a threshold fixed in advance, scope cut by
   subtraction.
4. **Algorithm and performance engineering** — choose a data structure for the expected input,
   state the invariant, then check correctness, time and memory against a baseline.

## Install

### OMP

Install from the official Marketplace in a fresh OMP profile.

```sh
omp plugin marketplace add VolkovIlia/deadlion-studio &&
omp plugin install --scope user deadlion@deadlion-studio
omp plugin list
```

Look for `deadlion@deadlion-studio (4.6.6) (user)` under Marketplace Plugins. For an existing Marketplace install, run the following from the target project and restart OMP when the upgrade finishes.

```sh
omp plugin marketplace update deadlion-studio &&
omp plugin upgrade deadlion@deadlion-studio
```

If the catalog still offers an older version, check its source with `omp plugin marketplace list`. Updating a registered marketplace refreshes its existing source. The following commands replace a stale or local `deadlion-studio` registration with the official source.

```sh
omp plugin marketplace remove deadlion-studio &&
omp plugin marketplace add VolkovIlia/deadlion-studio &&
omp plugin discover deadlion-studio
```

Run `omp plugin upgrade deadlion@deadlion-studio` again if Deadlion is already installed from Marketplace.

If you previously used `omp plugin link`, OMP lists `deadlion-studio` under npm Plugins. Before switching that installation to Marketplace, confirm `omp plugin discover deadlion-studio` offers the expected release. Then replace the link with the Marketplace installation.

```sh
omp plugin uninstall deadlion-studio &&
omp plugin install --scope user deadlion@deadlion-studio &&
omp plugin list
```

Start OMP in your project and give the agent the goal. It plans, verifies, and repairs within the session's tool permissions and resource budgets. `/deadlion doctor` inspects available tools. For CI, `dl-omp --seconds N` bounds the run and returns exit code 0 after validating the receipt and current workspace. [Autonomous verification](docs/omp-recovery.md#autonomous-verification)

### Claude Code

```
/plugin marketplace add VolkovIlia/deadlion-studio
/plugin install deadlion@deadlion-studio
```

Optional plugin, installed the same way (`/plugin install <name>@deadlion-studio`):

| Plugin | Skills |
|---|---|
| `deadlion-triz` | `triz-inventive-solver` |

## Quick start

In OMP, enter the task as an ordinary prompt. Use `/deadlion status` to inspect its engineering mode and `/deadlion report` to locate the verification evidence.

In Claude Code, describe what you want to build and let the `workflow` skill pick the stages.

```
/deadlion:workflow a tool that lets me pick a git branch from a list and switch to it
```

Each stage writes a plain-text artifact to `.dev-docs/features/<slug>/` and waits
for your approval before the next one. Any skill also works alone, for example
`/deadlion:ux-design`, `/deadlion:review` or `/deadlion:release projects/pick 0.2`.

## Core skills

In Claude Code each core skill is available as `/deadlion:<skill>`.

| Skill | Does |
|---|---|
| `workflow` | Runs the pipeline below; `ls .dev-docs/features/<slug>/` plus `.dev-docs/system.md` is its only state |
| `product-discovery` | Problem, users, evidence levels, riskiest assumption, scope → `product.md` |
| `ux-design` | Target rung, flows, screens, states, keys, tokens with `dl-contrast` pairs, gates per rung → `design.md` |
| `ui-verify` | Terminal: `dl-tui` screens at 80×24/40×12/20×5, NO_COLOR, restore, stdout purity. Web: screenshots at 375/768/1280 px, console errors, axe scan; loops until gates pass |
| `decompose` | Splits a system into sub-projects with one job, language, budget and contract each → `system.md`, `contracts/` |
| `scaffold` | Creates a C, Rust, Rust terminal UI (`rust-tui`) or sh program skeleton with `dl-new`: Makefile with `dist`, config.def, man page, LICENSE, test.sh |
| `unix-design` | Single-job modules inside one program, text interfaces, mechanism vs policy → `arch.md` |
| `write-plan` | Small ordered tasks, each with files, project, a test first and a verify command → `plan.md` |
| `build` | Runs `plan.md` task by task through the `implementer` and `reviewer` subagents |
| `suckless-code` | Size limits, per-program budgets, language choice, shrinking code, limit-gaming detection, `dl-size`, `dl-budget` |
| `performance` | Compares algorithms, profiles resource use and verifies performance contracts in Standard, Performance, Research and Evolution modes |
| `testing` | Test-first; unit → integration → regression; behaviour, not wiring; memory-safe suites |
| `debug` | Reproduce, failing test, L1/L2/L3 classification, root cause, minimal fix |
| `review` | Reviews a diff via the `reviewer` subagent, keeps only confirmed findings |
| `verify` | Runs the proving command fresh; reports VERIFIED and NOT VERIFIED separately |
| `commit` | Checks staged files with `dl-guard`, writes `type(scope): summary` |
| `release` | Bumps the one version source, runs the checks, tags `NAME-VERSION`, builds the `make dist` tarball and `.sha256` |

Subagents: `researcher` (web + code research, evidence-tagged), `implementer`
(one plan task, test-first), `reviewer` (read-only, one finding per line).

## Workflow

Stages run top to bottom. The `workflow` skill picks the ones the change needs
and asks you to approve each artifact before the next; any stage also runs alone.

| # | Stage | Skill | Runs when | Writes |
|---|---|---|---|---|
| 1 | Product | `product-discovery` | value or users are unclear | `product.md` |
| 2 | Design | `ux-design` | the change has a UI | `design.md` |
| 3 | Decompose | `decompose` | the system is more than one program | `.dev-docs/system.md` |
| 4 | Architecture | `unix-design` | a new component or interface | `arch.md` |
| 5 | Plan | `write-plan` | the change is larger than one file | `plan.md` |
| 6 | Build | `build` | always | code, ticks `plan.md` tasks |
| 7 | UI check | `ui-verify` | the change has a UI | fixes until the design gates pass |
| 8 | Review | `review` | the change is larger than one file | `review.md` |
| 9 | Verify | `verify` | always | VERIFIED / NOT VERIFIED report |
| 10 | Release | `release` | only when you ask | tag, tarball, `.sha256` |

## Artifact contract

Stages talk through plain-text files in `.dev-docs/features/<slug>/`, plus the
repo-level `.dev-docs/system.md`. Each file starts with `# <Title>` and
`Status: draft|approved`. Full contract:
[`artifacts.md`](plugins/deadlion/skills/workflow/references/artifacts.md).

| File | Written by | Holds |
|---|---|---|
| `product.md` | `product-discovery` | Problem, users, evidence, riskiest assumption, scope, acceptance criteria, metric |
| `design.md` | `ux-design` | Target rung, flows, wireframes, states, tokens, keys, accessibility gates, copy |
| `system.md` | `decompose` | Projects (job, language, I/O, budgets, run command), contracts, composition, build order, decisions |
| `arch.md` | `unix-design` | Components, interfaces, data flow, mechanism vs policy, threats, decisions |
| `plan.md` | `write-plan` | `### T<n>` tasks with Files/Project/Change/Test/Verify/Depends and a done checkbox |
| `review.md` | `review` | `BLOCKING\|IMPORTANT\|NIT path:line — finding — evidence` |

## Performance engineering

The membership example compares scanning a list with building an index for repeated lookups. It varies list length and query count independently. To inspect the recorded experiment with Python 3.11+ on Linux, run these commands from the repository root. Replay recomputes model fits and comparisons from saved samples. The CSV contains individual measurements for plotting.

```sh
tools=plugins/deadlion/skills/performance/scripts
example=plugins/deadlion/evals/scaling-membership
"$tools/dl-perf" scale "$example/contract.json" --replay "$example/measurements.json" --csv /tmp/membership.csv
```

For a fresh correctness and resource check, run `"$tools/dl-perf-gate" "$example/contract.json" --isolated`. Live isolated measurements require Linux, Bubblewrap, a user systemd manager and cgroup v2 CPU, memory and process controllers. The gate emits JSON. Exit 0 means the contract passed, exit 1 indicates a regression or evaluation error, and exit 2 covers inconclusive or unverified results and invalid invocations. [Contract and OMP command reference](plugins/deadlion/skills/performance/references/commands.md)

On pull requests, CI loads the evaluator, oracles and approved contracts from the base commit. It runs the candidate files named by those contracts and records both commit IDs in the `performance-evidence` artifact. A missing required metric yields `NOT VERIFIED`. An `INCONCLUSIVE` result calls for a repeat on the project's performance runner. The approved contract can mark that outcome advisory. [PR workflow](.github/workflows/performance.yml) · [Evaluator](scripts/approved-performance)

## Tools

The following project tools are written in Python 3. The checkers print `path:line: message`, one per
line, nothing when clean; `dl-new` is silent on success. Exit `0` clean, `1`
violations, `2` usage or IO error. `dl-tui` prints screens and exits `0` when its
script ran.

| Tool | Does | Env overrides |
|---|---|---|
| `skills/suckless-code/scripts/dl-size [PATH...]` | file >500 lines, Python function >50 lines (others via `lizard`; a notice when it is missing); extensionless `#!` scripts included | `DL_MAX_FILE`, `DL_MAX_FUNC` |
| `skills/suckless-code/scripts/dl-budget [DIR...]` | program >2000 SLOC or >5 direct dependencies (Cargo.toml, pyproject.toml, package.json, go.mod, config.mk); per-program `.budget` | `DL_MAX_SLOC`, `DL_MAX_DEPS` |
| `skills/scaffold/scripts/dl-new LANG NAME [DEST]` | creates a C, Rust, Rust terminal UI or sh program skeleton in `projects/NAME`; silent on success | — |
| `skills/ux-design/scripts/dl-contrast [PATH...]` | colour token pairs marked by `dl-contrast:` directives below their WCAG contrast minimum (default 4.5:1) | — |
| `skills/ui-verify/scripts/dl-tui [-s COLSxROWS] CMD [STEP...]` | runs a terminal program in a headless tmux, sends keys, text and resizes, prints the screens | `DL_TUI_SETTLE_MS` (2000) |
| `skills/commit/scripts/dl-guard [FILE...]` | staged files: forbidden extensions/dirs, secret-file names, binaries, size | `DL_GUARD_MAX_KB` (500), `DL_GUARD_MAX_TOTAL_MB` (10), `DL_GUARD_MAX_FILES` (100) |

Claude Code runs `dl-size`, `dl-contrast` and `dl-analyze` after edits. Before a
commit, `dl-guard` checks staged files. CI runs its own checks on the checkout.

## Codex and Copilot

Skills follow the open Agent Skills format. Export them as plain directories:

```
scripts/export-skills .agents/skills            # every plugin
scripts/export-skills .agents/skills deadlion   # core only
```

Codex and Copilot both read `.agents/skills/`.

## Contributing

Bug reports, fixes and new evals are welcome. Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md); the full house rules for skills and tools are
in [`CLAUDE.md`](CLAUDE.md). Questions go to [`SUPPORT.md`](SUPPORT.md), security
problems to [`SECURITY.md`](SECURITY.md). Changes are listed in
[`CHANGELOG.md`](CHANGELOG.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
