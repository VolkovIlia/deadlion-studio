---
name: suckless-code
description: "Suckless coding constraints: functions ≤50 lines, files ≤500, ≤2000 SLOC and ≤5 direct dependencies per program, table-driven dispatch, early returns, errors as values, language choice and idioms, shrinking existing code without behaviour change, and detection of tricks that game the limits. Includes the dl-size and dl-budget checkers. Use when writing, refactoring, simplifying, cleaning up or reviewing code, or choosing a language for a program."
---

# Suckless code

Limits exist to reduce cognitive load through decomposition, not to compress code.

## Hard limits
- Function: ≤50 lines (non-blank, non-comment, docstring excluded).
- File: ≤500 lines.
- Program: ≤2000 SLOC (dl-budget, override in `.budget`).
- Dependencies: ≤5 direct per program (dl-budget); prefer the stdlib over frameworks.
- Every program builds, tests and installs through its own POSIX Makefile.
- Config lives in source (a constants/table block at the top); ENV/CLI overrides only where needed.

## Language
Choice and per-language idioms: `${CLAUDE_SKILL_DIR}/references/languages.md`.
Program behaviour (flags, exit status, stderr, files, embedding, versions): `${CLAUDE_SKILL_DIR}/references/conventions.md`.

## Patterns
- **Table-driven dispatch**: map key → handler or value; no long if/elif/switch chains.
- **Early returns / guard clauses**: validate, acquire, operate, release, return. Keep nesting flat.
- **Errors as values**: return Result/error types; log to stderr; no exceptions for control flow.
- **Extract method** when a function nears the limit; name it by what it does.
- **Split modules** by concern when a file nears the limit.
- Implement against agreed contracts (`arch.md`, `contracts/`); never invent an API.

## Dependency budget
Every new dependency needs a one-line justification (what it replaces, why the stdlib or an
existing dependency is not enough) in the commit message or in `arch.md` Decisions.
No justification → do not add it.

## Deletion beats addition
Before writing code, look for code to delete: dead paths, duplicate helpers, unused options,
wrappers that only forward. A change that removes lines and keeps tests green is preferred
over one that adds them.

## Limit-gaming is a violation
Meeting the numbers by compression is worse than exceeding them. Forbidden: line cramming,
cryptic names, deleting WHY-comments, removing logical blank lines, multi-condition
comprehensions, nested ternaries. Detection rules and fixes:
`${CLAUDE_SKILL_DIR}/references/anti-cheat.md`.

## Checker: dl-size
```
${CLAUDE_SKILL_DIR}/scripts/dl-size [PATH...]     # default PATH is .
```
- Directories: `git ls-files` inside a repo, else a walk that skips `.git node_modules vendor dist build target __pycache__ .venv venv`.
- Checks source files only (`.py .js .ts .go .rs .c .java .sh …`, plus extensionless files starting with `#!`).
- Output: one violation per line, silent when clean:
  ```
  path:1: file has 612 lines (max 500)
  path:LINE: function NAME has 57 lines (max 50)
  ```
- Exit: `0` clean, `1` violations, `2` usage/IO error (stderr, prefixed `dl-size:`).
- Env: `DL_MAX_FILE` (default 500), `DL_MAX_FUNC` (default 50).
- Python functions (`.py` and `#!…python` scripts) are measured via `ast`. Other languages
  use `lizard` if it is on PATH (`pipx install lizard`); its warning lines pass through
  unchanged. Without lizard, CLI mode prints one stderr notice
  (`dl-size: lizard not on PATH; function length of N non-Python files not checked …`);
  the exit status still depends only on violations.
- The plugin's PostToolUse hook runs `dl-size --hook` after every Write/Edit and reports
  violations back. `DL_HOOKS=0` disables hook mode.

Run it on changed files before declaring code done; fix every line it prints by
decomposition, not compression.

## Checker: dl-budget
```
${CLAUDE_SKILL_DIR}/scripts/dl-budget [DIR...]   # default: each projects/*/, else .
```
- SLOC: non-blank lines of source files (same set as dl-size) that do not start with a
  comment marker; test code (`test/`, `tests/`, `test*`, `*_test.*`) is excluded.
  Approximate, like sloccount.
- Direct dependencies from the DIR root: `Cargo.toml` (`[dependencies]`,
  `[build-dependencies]`, `[target.*.dependencies]`), `pyproject.toml`
  (`project.dependencies`), `package.json` (`dependencies`), `go.mod` (`require`,
  not `// indirect`), `config.mk` (`-l<name>` on `LIBS` lines, except `-lc`).
- Output, silent when clean:
  ```
  DIR:1: project has 2412 SLOC (max 2000)
  DIR:1: project has 7 direct dependencies (max 5): a, b, c, d, e, f, g
  ```
- Exit: `0` clean, `1` violations, `2` usage/IO/parse error (stderr, prefixed `dl-budget:`).
- Env: `DL_MAX_SLOC` (default 2000), `DL_MAX_DEPS` (default 5).
- `DIR/.budget` overrides both per program, one per line, `#` comments allowed:
  ```
  sloc 1000
  deps 0
  ```

## Shrinking existing code
Behaviour does not change; every step is proven by the same tests passing before and after.
1. **Baseline.** Tests green, else stop and use `debug` first. Uncovered target → write
   characterization tests that pin current behaviour. Record line counts, dl-size and
   dl-budget output, test counts.
2. **Targets, ranked:** dead code (unused functions, flags, branches, config,
   dependencies) → duplication (near-identical blocks) → size/complexity violations.
3. **One refactoring per step:**

   | Smell | Refactoring |
   |---|---|
   | Unused code / dependency | Delete |
   | Duplicate blocks | Extract one shared function, replace all copies |
   | Function >50 lines | Extract method along its existing phases |
   | Nested conditionals | Early returns / guard clauses |
   | if/elif or switch on a value | Lookup table / dispatch dict |
   | Flag argument | Split into two functions |
   | Single-use abstraction | Inline it |
   | File >500 lines | Split by job, one module per job |
   | Program >2000 SLOC | Split by job into two programs (`decompose`) |

4. **Check the step:** tests, dl-size, and the diff for limit-gaming. Failing → reason from
   the log and repair; max 3 repair iterations, then revert the step and record why.
5. **Report:**
   ```
   Before: <lines> lines, <n> dl-size violations, tests <pass/total>
   After:  <lines> lines, <n> dl-size violations, tests <pass/total>
   Steps:  <refactoring> — <files>  (one line each)
   Reverted: <step — reason> (if any)
   ```
