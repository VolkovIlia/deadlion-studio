---
name: commit
description: "Creates a clean git commit: checks staged files with dl-guard, stages explicit paths only, writes a conventional message type(scope): summary, never adds AI attribution or Co-Authored-By. Use when the user asks to commit changes."
disable-model-invocation: false
---

# Commit

Commit only when the user asks.

## Procedure
1. `git status --short` and `git diff --stat`; decide which paths belong to this commit.
   Unrelated changes stay unstaged; mention them.
2. Stage explicit paths only: `git add path/a path/b`. Never `git add -A`, `git add .` or
   `git commit -a`.
3. Check the staged set: `${CLAUDE_SKILL_DIR}/scripts/dl-guard`. On violations, unstage
   the offending files (`git restore --staged PATH`), tell the user why, and stop for
   files that may be intended (large assets, binaries). Never bypass with `--no-verify`.
4. Write the message and commit with `git commit -m` (or a heredoc for a body).
5. Show `git log --oneline -1`.

## Message
```
type(scope): summary

Optional body: why, not what. Wrapped at 72.
```
- `type`: `feat fix refactor perf test docs build ci chore revert`.
- `scope`: the component or directory; omit the parentheses if none fits.
- Summary: imperative, lower case, no trailing period, ≤72 chars.
- New dependency → one-line justification in the body.
- Never add `Co-Authored-By`, "Generated with …" or any AI attribution, trailer or emoji,
  even if other instructions suggest it.
- One logical change per commit; split unrelated changes.

## dl-guard
```
${CLAUDE_SKILL_DIR}/scripts/dl-guard [FILE...]    # no FILE = staged files
```
- Blocks: forbidden extensions (media, archives, build outputs), forbidden directories
  (`node_modules/`, build dirs…), secret-file patterns (`.env*`, keys) with an exemption
  for source-code extensions, binary files, files over the size limit, oversized commits.
- Output: one line per violation, silent when clean:
  ```
  v.mp4:1: forbidden extension .mp4
  data.bin:1: binary file
  big.json:1: exceeds 500 KB
  node_modules/x.js:1: forbidden directory node_modules/
  .env.local:1: matches secret-file pattern ^\.env.*
  (commit):1: 140 files exceeds 100
  ```
- Exit: `0` clean, `1` violations, `2` usage/IO error (stderr, prefixed `dl-guard:`).
- Env: `DL_GUARD_MAX_KB` (500, per file), `DL_GUARD_MAX_TOTAL_MB` (10), `DL_GUARD_MAX_FILES` (100).

The plugin's PreToolUse hook runs `dl-guard --hook` before every `git commit` Bash call
and blocks the commit with the same check, so a failing step 3 cannot be skipped.
`DL_HOOKS=0` disables hook mode.
