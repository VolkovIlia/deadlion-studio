---
name: scaffold
description: "Creates a new suckless-style program or sub-project skeleton with the dl-new tool: POSIX Makefile (all/test/install/uninstall/clean/dist), config.def copied to config on build, man page, LICENSE, README, a .budget file and a passing test.sh, for C, Rust, a Rust terminal UI (dmenu-style picker) or POSIX sh. Use when starting a new program, library or sub-project, or after decompose approves a project map."
argument-hint: "<c|rust|rust-tui|sh> <name>"
---

# Scaffold

A new program starts from a skeleton that already builds, tests, installs and
passes its budget. The skeleton is a working `cat`: replace its behaviour, keep
its layout.

## Tool: dl-new
```
${CLAUDE_SKILL_DIR}/scripts/dl-new LANG NAME [DEST]
```
- `LANG`: `c`, `rust`, `rust-tui` or `sh` (one directory per template under `templates/`).
  `rust-tui` is a dmenu-style picker (std + `libc`, `deps 1`; `make test` needs tmux):
  the start for the filter and TUI rungs.
- `NAME`: `^[a-z][a-z0-9-]{0,31}$`. It names the binary, the man page and the package.
- `DEST`: default `projects/NAME`. An existing empty directory, including `.`, is fine.
- Silent on success, exit 0. Errors go to stderr with exit 2 and nothing written:
  ```
  dl-new: usage: dl-new LANG NAME [DEST]
  dl-new: unknown language go (have: c rust rust-tui sh)
  dl-new: bad name Foo (want ^[a-z][a-z0-9-]{0,31}$)
  dl-new: projects/foo/Makefile: exists
  ```
- `__NAME__`, `__YEAR__` and `__AUTHOR__` (from `git config user.name`) are
  replaced in file names and contents.

## Choose the language
Choose LANG with `${CLAUDE_SKILL_DIR}/../suckless-code/references/languages.md`.
For other languages, apply the layout checklist from that file by hand.

## What every skeleton holds
| File | Purpose |
|---|---|
| `Makefile` | `.POSIX:`; targets `all test install uninstall clean`; honours `DESTDIR`, `PREFIX`, `MANPREFIX` |
| `dist` | `make dist` → `NAME-VERSION.tar.gz`; the release skill uses it |
| `config.def.h` / `src/config.def.rs` | defaults, copied to `config.h` / `src/config.rs` on the first build (sh: variables at the top of the script) |
| `NAME.1` | man page: NAME, SYNOPSIS, DESCRIPTION, OPTIONS, EXIT STATUS; `VERSION` filled in on install |
| `LICENSE` | MIT/X |
| `README` | one line, Requirements, Installation, Running, Configuration |
| `test.sh` | POSIX sh behaviour test of the binary in `$BIN`; silent on success, `FAIL: <what>` on failure |
| `.budget` | `sloc N` / `deps N` for dl-budget |

Every program follows `${CLAUDE_SKILL_DIR}/../suckless-code/references/conventions.md`
(flags, exit status, stderr, files, versions). C adds `config.mk` (version, paths,
flags) and `util.c` with `die()`/`ecalloc()`. Rust has an empty `[dependencies]` table
and a size-tuned release profile; `rust-tui` adds `src/term.rs` (raw mode on
`/dev/tty`, all `unsafe`) and a pure, unit-tested `src/ui.rs`.

## Procedure
1. Generate: `${CLAUDE_SKILL_DIR}/scripts/dl-new <lang> <name>`. No shell available →
   write the same files by hand from `${CLAUDE_SKILL_DIR}/templates/<lang>/` with the
   same substitutions (`gitignore` → `.gitignore`), and report step 2 as not run.
2. Prove the skeleton:
   ```
   make -C <DEST> test
   ${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-budget <DEST>
   ```
   Both must exit 0. A failure here is a toolchain problem; fix it before writing code.
3. Set `.budget` to the numbers agreed in `.dev-docs/system.md` (decompose), if any.
4. Replace the cat behaviour with the real job, test-first: change `test.sh` (and
   unit tests) to the new behaviour, watch it fail, then change the code. Update the
   man page SYNOPSIS/DESCRIPTION/OPTIONS and the README in the same change.
5. Re-run step 2 after every change that grows the program.

## Monorepo root
With more than one program under `projects/`, the repo root gets this Makefile;
only the `PROJECTS` list changes (build order):
```make
.POSIX:
PROJECTS = <names in build order>
all test clean install uninstall:
	@for p in $(PROJECTS); do $(MAKE) -C projects/$$p $@ || exit 1; done
.PHONY: all test clean install uninstall
```
Every program must still build, test and install alone with
`make -C projects/<name> <target>`.
