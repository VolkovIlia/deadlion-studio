# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and each plugin follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Core plugin 4.4.0

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

[Unreleased]: https://github.com/VolkovIlia/deadlion-studio/compare/v4.3.0...HEAD
[4.3.0]: https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.3.0
[4.2.0]: https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.2.0
