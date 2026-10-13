---
name: release
description: "Releases one program the suckless way: bumps its single version source, runs make test, dl-budget, dl-size and a groff man-page lint, commits the bump, tags NAME-VERSION and builds the make dist tarball with a sha256 file. Use when the user asks to release, tag, version or package a program."
argument-hint: "<program dir> <version>"
---

# Release

One program per run. The version, tag, tarball and checksum rules are in
`${CLAUDE_SKILL_DIR}/../suckless-code/references/conventions.md` (`## Versioning and
release`). Releasing is an explicit user request; it covers the bump commit and the tag.
Never push.

## Procedure

0. **Arguments.** DIR (default `.`) and VERSION. VERSION must match
   `^\d+\.\d+(\.\d+)?$` and be greater than the current version (compare the numbers
   field by field, a missing field counts as 0). VERSION missing → ask, offering the next
   patch and the next minor version.
1. **Identify.**
   - NAME = basename of the single `*.1` file in DIR (`ls DIR/*.1`); zero or several →
     stop and report.
   - `git status --porcelain -- DIR` must print nothing; else stop and list the files.
   - `git tag -l NAME-VERSION` must print nothing; else stop: the version is taken.
2. **Bump** the one version source, nothing else:

   | Language | Source | Edit |
   |---|---|---|
   | C | `DIR/config.mk` | `VERSION = VERSION` |
   | Rust | `DIR/Cargo.toml` | `[package]` `version = "VERSION"` |
   | sh | `DIR/NAME` | `VERSION=VERSION` near the top |
   | other | the file the Makefile reads `VERSION` from | — |

   No version source found → stop and point to `conventions.md`.
3. **Checks.** Run each; any failure → `git checkout -- <version file>`, report the
   output and stop.
   - `make -C DIR test` — output allowed; exit 0 required.
   - `${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-budget DIR` — exit 0, no output.
   - `${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-size DIR` — exit 0, no stdout.
   - `groff -man -ww -z DIR/NAME.1` — must print nothing. groff exits 0 even on
     warnings, so judge by the empty output.
4. **Commit** with the `commit` skill: the version file, plus `DIR/Cargo.lock` if it
   changed; message `chore(NAME): release VERSION`.
5. **Tag:** `git tag -a NAME-VERSION -m "NAME VERSION"`.
6. **Dist.**
   - `make -C DIR dist` → `DIR/NAME-VERSION.tar.gz`.
   - `(cd DIR && sha256sum NAME-VERSION.tar.gz > NAME-VERSION.tar.gz.sha256)`
     (`shasum -a 256` where `sha256sum` is missing).
   - `tar -tzf DIR/NAME-VERSION.tar.gz` lists only `NAME-VERSION/` entries, including
     `NAME.1`, `LICENSE`, `README` and `Makefile`. Anything else → report it; the tag
     stays, fix the `dist` target and rebuild the tarball.
7. **Report.**
   ```
   RELEASE: NAME-VERSION
   tag:      NAME-VERSION (<commit hash>)
   tarball:  DIR/NAME-VERSION.tar.gz
   sha256:   <line from the .sha256 file>
   push:     git push && git push origin NAME-VERSION
   ```

## Rules

- The tarball and `.sha256` are build outputs; they stay untracked (the templates'
  `.gitignore` covers `NAME-*.tar.gz*`).
- Never edit `CHANGELOG`-style files, version strings in code or the man page by hand:
  `make install` substitutes VERSION from the one source.
- Never move or delete an existing tag; a bad release gets the next version.
