# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and each plugin follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [4.5.0] - 2026-11-28

### Native OMP integration

- Install the package once and use OMP 19.2.1 normally. The package provides the engineering skills and agents, the `/deadlion` command and one model-facing verifier.
- Pin the baseline and correction budget for the task. The main session checks changes from edits, shell commands, external writers and parallel subagents, including after a commit or restart.
- Use OMP's own LSP for diagnostics and targeted hover. Send compact findings to the agent and retain the complete evidence on disk.
- Enforce approved functional checks, algorithm contracts, resource limits and plan steps. Missing mandatory evidence blocks completion. The RPC launcher checks the final receipt and returns a machine-readable verdict.
- Run Scaling Analyzer and native Autoresearch through the task policy. Evolution verifies the frozen training and holdout workloads and records the accepted revision for operator promotion.
- On Fedora 44, a short scripted prompt on a 10,000-file fixture took a median of 410 ms with extensions disabled and 1,270 ms with Deadlion enabled. Real-model quality improvement remains unverified. [Measurements, integration tests and limitations](docs/omp-engineering.md)

### Core changes since the last public release

The following features first landed on `main` at core version 4.4.0 and are included in this release. [4.4.0 baseline](https://github.com/VolkovIlia/deadlion-studio/commit/21d817529b25c55d3ecdcec9b80c1ca80024ea20)

- Measure scaling on fixed-seed multidimensional workloads using `dl-perf scale`. Compare held-out predictions, paired ratios and observed time/memory tradeoffs.
- Enforce independent numerical, property and state oracles, extended resource budgets and approved contracts in OMP and CI.
- Isolate Evolution candidates with explicit files and separate training and holdout verification. Report fast Python AST hints after edits and select project-native tools for review.
- Replay saved measurements and export individual samples to CSV or Extra-P JSON Lines. The verification report covers the membership and sorting experiments, local OMP runs, and limits of the coding-agent pilot. [Measurements and reproduction commands](docs/scaling-verification.md)

## [4.3.0] - 2026-11-28

- The core plugin runs executable time and resource contracts, structural performance diagnostics and isolated OMP experiments.
- Pull requests exercise current and previously approved workload contracts. The CLI records raw timings, executable hashes, profiler evidence and inconclusive results.
- The repository includes audited upstream revisions, paired fixtures, a labelled warning corpus and a controlled coding-agent evaluation.

## [4.2.0] - 2026-10-13

First public release. Earlier versions were developed privately.

### Added

- `deadlion` 4.2.0, the core plugin:
  - pipeline skills `workflow`, `product-discovery`, `ux-design`, `decompose`,
    `unix-design`, `write-plan`, `build`, `ui-verify`, `review`, `verify`, `commit` and
    `release`;
  - engineering skills `suckless-code`, `testing`, `debug` and `scaffold`;
  - subagents `researcher`, `implementer` and `reviewer`;
  - tools `dl-size`, `dl-budget`, `dl-guard`, `dl-new`, `dl-contrast` and `dl-tui`;
  - hooks: `dl-size` and `dl-contrast` after every Write/Edit, `dl-guard` before
    `git commit`;
  - program templates for C, Rust, Rust terminal UIs (`rust-tui`) and POSIX sh, each
    with `make dist`;
  - a UI target ladder (CLI, filter, TUI, native GUI, web) with gates per rung;
  - skill-trigger evals.
- `deadlion-triz` 4.0.0, an optional plugin with `triz-inventive-solver`.
- `scripts/export-skills` to use the skills from Codex and GitHub Copilot.

[Unreleased]: https://github.com/VolkovIlia/deadlion-studio/compare/v4.5.0...HEAD
[4.5.0]: https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.5.0
[4.3.0]: https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.3.0
[4.2.0]: https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.2.0
