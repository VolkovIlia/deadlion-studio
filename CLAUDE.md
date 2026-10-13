# deadlion-studio

Claude Code plugin marketplace. No build step; everything is Markdown, JSON and
stdlib-only Python/POSIX sh, plus the C/Rust/sh program templates of `scaffold`.

## Layout
- `.claude-plugin/marketplace.json` — one entry per directory in `plugins/`.
- `plugins/deadlion/` — core: `skills/`, `agents/`, `hooks/hooks.json`, `.mcp.json`, `evals/`.
- `plugins/deadlion-triz/` — optional domain plugin (skills only).
- Tools live in the owning skill's `scripts/` (never a plugin `bin/`):
  `skills/suckless-code/scripts/{dl-size,dl-budget}`, `skills/commit/scripts/dl-guard`,
  `skills/ux-design/scripts/dl-contrast`, `skills/ui-verify/scripts/dl-tui`,
  `skills/scaffold/scripts/dl-new` (templates in `skills/scaffold/templates/<lang>/`;
  a template `gitignore` becomes `.gitignore`, `__NAME__` never as an identifier).
- `scripts/export-skills` — copies skills to `.agents/skills/` for Codex/Copilot.
- `tests/` — pytest suites plus `test_export_skills.sh`.
- `.github/` — CI, issue forms, PR template, CODEOWNERS, Dependabot. Root
  `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`.

## Skill authoring
- Frontmatter: only `name` (= directory name, `^[a-z0-9-]{1,64}$`) and
  `description` (third person, "what + Use when …", ≤1024 chars); add
  `argument-hint` / `disable-model-invocation` only when needed.
- Body ≤150 lines in core, ≤500 elsewhere; detail goes in `references/`.
- Reference bundled files as `${CLAUDE_SKILL_DIR}/…`; hooks use `"${CLAUDE_PLUGIN_ROOT}"/…`.
- Feature skills read/write the artifact contract in
  `plugins/deadlion/skills/workflow/references/artifacts.md`; link it, never copy it.
- Write only what Claude doesn't already know: numeric gates, procedures, output contracts.
- All prompts in English.
- Tools: output `path:line: message`, silent when clean, exit 0/1/2,
  limits in a top-of-file table with env overrides, functions ≤50 lines.

## Checks
```
pytest tests -q
sh tests/test_export_skills.sh
for p in plugins/*/; do claude plugin validate "$p" --strict; done
plugins/deadlion/skills/suckless-code/scripts/dl-size plugins scripts tests
```

## Commits
`type(scope): summary`, explicit paths only. No `Co-Authored-By`, no AI attribution.
User-visible changes get a line in `CHANGELOG.md` under `Unreleased`.
