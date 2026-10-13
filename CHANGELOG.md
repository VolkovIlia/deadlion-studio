# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and each plugin follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/VolkovIlia/deadlion-studio/compare/v4.2.0...HEAD
[4.2.0]: https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.2.0
