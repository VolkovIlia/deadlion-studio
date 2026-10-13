---
name: decompose
description: "Plans how to build an app, tool or system that does more than one job (e.g. fetch + store + browse, daemon + CLI, server + UI) by splitting it into small sub-projects in projects/<name>/, each with one job, a plain-text interface, its own language, SLOC and dependency budget and its own Makefile, composed by Unix patterns (pipes, files/FIFOs, exec chains, plumbing/porcelain, privilege separation). Writes .dev-docs/system.md and contracts/. Use when the user asks to plan, build, structure, split or organise a system with several jobs, processes or runtimes, or one estimated over 2000 lines, or when a codebase does more than one job."
argument-hint: "<system or idea>"
---

# Decompose

A system is a set of small programs, each one job, each readable in one sitting,
each built, tested and released alone, talking through plain text. This skill
draws that map; `unix-design` designs inside one program.

Output: `.dev-docs/system.md`, `contracts/<name>.md`, `projects/<name>/`, following
`${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`.

## Procedure

0. **Read.** `.dev-docs/system.md` if it exists; `product.md` and `design.md` of the
   active feature; the repo tree. For existing code, run
   `${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-budget` and
   `${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-size` and read their output.
1. **Jobs.** List every verb the system performs, one job per line. "and" means split.
2. **Prior art first.** For each job, name an existing tool that already does it
   (coreutils, `curl`, `jq`, `sqlite3`, `entr`, `cron`, `dmenu`, `fzf`, `socat`, …).
   Such a job becomes glue (a few lines of sh in an existing sub-project, or a
   Makefile rule), not a new sub-project. Unknown space → dispatch the
   `deadlion:researcher` agent. Every job, glue included, gets a row in `## Jobs`
   with the exact command that runs it alone (`curl -fsS "$URL" > raw.xml`).
3. **Boundary test.** A job becomes its own sub-project if any holds:
   - its process lifetime differs (daemon vs one-shot);
   - its privilege or trust differs (untrusted network input vs local state);
   - it is useful alone from a shell;
   - a different language fits it better;
   - merged with a neighbour it would exceed the neighbour's SLOC budget;
   - it has an independent release cadence;
   - it is a user interface above the CLI rung (a front end over the engine's contract;
     rung via `${CLAUDE_SKILL_DIR}/../ux-design/references/targets.md`).

   Otherwise it stays a module inside a sub-project, designed later by `unix-design`.
4. **Composition.** For each edge between sub-projects, pick one pattern from
   `${CLAUDE_SKILL_DIR}/references/patterns.md`. A network protocol only when the
   boundary is a network.
5. **Language.** For each sub-project, sh glue included, follow the decision
   procedure in `${CLAUDE_SKILL_DIR}/../suckless-code/references/languages.md`.
   Record one line per project, no exceptions:
   `<name>: Language: X — reason; rejected: Y — reason`.
6. **Budgets.**
   - SLOC: ≤2000 default, ≤1000 for a filter/CLI, ≤200 for sh glue.
   - Direct dependencies: default 0 for C/sh, ≤3 for Rust/Python, hard cap 5.
   - Shared code only as a tiny `projects/lib<name>/` (sbase libutil pattern), when
     ≥2 sub-projects need the same ≤300 SLOC. Never a framework.
7. **Contracts.** One file per edge: `contracts/<data-name>.md`, shaped as below.
   - Breaking change: `Version:` +1, and the plan updates the producer and every
     consumer.
   - Each consumer's tests carry their own copy of the example as a fixture
     (`tests/<name>-v<N>.*` or inline in `test.sh`), so a contract change breaks
     only the projects whose plan tasks update them.
8. **Contradictions.** Phrase each trade-off as "need X and not-X". Separate it in
   time, space or condition before compromising; record the result in Decisions. If
   the `deadlion-triz` plugin is installed, offer
   `/deadlion-triz:triz-inventive-solver` for unresolved ones.
9. **Write `.dev-docs/system.md`** with `Status: draft`. Show the Projects table and
   ask for approval.
10. **After approval:**
    - For each project: `${CLAUDE_SKILL_DIR}/../scaffold/scripts/dl-new <lang> <name>`
      (scaffold skill), then write its `.budget` with the agreed numbers.
    - Write the root `Makefile`, verbatim except the list:
      ```make
      .POSIX:
      PROJECTS = <names in build order>
      all test clean install uninstall:
      	@for p in $(PROJECTS); do $(MAKE) -C projects/$$p $@ || exit 1; done
      .PHONY: all test clean install uninstall
      ```
    - Run `make test` and `dl-budget` at the root. Both must exit 0.
11. **Exactly one sub-project results** → no `projects/` dir and no `system.md`.
    Scaffold into the repo root (`dl-new <lang> <name> .`) and continue with
    `unix-design`.

## Rules
- Never two sub-projects with the same job.
- No cross-project calls except through a contract.
- No shared mutable state, including a shared DB file, except through a contract
  that names its single writer.
- Every sub-project builds, tests and installs alone with
  `make -C projects/<name> <target>`.
- Every program follows `${CLAUDE_SKILL_DIR}/../suckless-code/references/conventions.md`.
- A chat-only answer still gives the full Projects table (name, job, language,
  input, output, budgets, run command), the Jobs table and one `Language:` line per
  project.

## system.md
~~~markdown
# <System> map
Status: draft

## Projects
| Name | One job | Language | Input | Output | SLOC budget | Deps budget | Run |
|---|---|---|---|---|---|---|---|
| fetch | download feeds listed in a file | Rust | feeds.txt | items JSONL on stdout | 1000 | 2 | `make -C projects/fetch test` |

## Contracts
| File | Version | Producer | Consumers |
|---|---|---|---|
| contracts/items.md | 1 | fetch | store |

## Composition
```mermaid
flowchart LR
  cron -->|exec chain| fetch -->|pipe: items JSONL| store
```

## Build order
fetch, store

## Decisions
fetch: Language: Rust — parses untrusted network input; rejected: C — complex untrusted parsing.
store: Language: POSIX sh — a few sqlite3 calls; rejected: Rust — 10× the code for the same job.
<then one paragraph each: reused tools, contradictions and how they were separated>

## Jobs
| Job | Done by | Run alone |
|---|---|---|
| schedule | cron | `*/30 * * * * fetch < ~/.config/rss/feeds \| store add` |
| download | curl (glue in fetch) | `curl -fsS "$URL" > raw.xml` |
~~~

## contracts/<name>.md
~~~markdown
# items
Version: 1
Producer: fetch
Consumers: store

## Format
<exact grammar: fields, separators, encoding, ordering>

## Example
```
<≥3 lines of real data>
```

## Errors
<exit codes and stderr format of the producer>
~~~
