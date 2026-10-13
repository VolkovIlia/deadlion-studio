# Contributing

Thanks for helping. Bug reports, fixes, new evals and sharper skill wording are all
welcome. This file is the short version; the full house rules for skills, tools and
layout are in [`CLAUDE.md`](CLAUDE.md).

## Before you start

- Bugs and feature ideas: open an issue first with the matching form, so we agree on
  the change before you write it.
- Questions: use [Discussions](https://github.com/VolkovIlia/deadlion-studio/discussions),
  not issues.
- Security problems: never in a public issue. See [`SECURITY.md`](SECURITY.md).

## Set up

You need Python 3.12+, a C compiler, `cargo`, `tmux` and `groff` for the template
and tool tests, and Node.js 22 for the `claude` CLI.

```sh
git clone https://github.com/VolkovIlia/deadlion-studio
cd deadlion-studio
pip install -r requirements-dev.txt     # pytest, lizard
npm i -g @anthropic-ai/claude-code      # for `claude plugin validate`
claude --plugin-dir ./plugins/deadlion  # try your changes locally
```

## Checks

Run all four before you push. CI runs the first three on every push and pull request.

```sh
pytest tests -q
sh tests/test_export_skills.sh
for p in plugins/*/; do claude plugin validate "$p" --strict; done
plugins/deadlion/skills/suckless-code/scripts/dl-size plugins scripts tests
```

If you change a skill's wording, also run its eval case. Evals call the model and cost
money, so run only the case you touched:

```sh
claude plugin eval plugins/deadlion --case <case> --no-publish
```

## What a change must follow

- **Skills:** frontmatter `name` equals the directory name; `description` says what the
  skill does and "Use when …"; core skill bodies stay at 150 lines or fewer, details go
  in `references/`.
- **Tools:** stdlib-only Python or POSIX sh, output `path:line: message`, silent when
  clean, exit 0/1/2, functions of 50 lines or fewer, limits in a table at the top of the
  file.
- **Tests:** a behaviour change comes with a test that fails before it and passes after.

## Commits and pull requests

- One logical change per commit, message `type(scope): summary`
  (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`, …). No AI attribution or
  `Co-Authored-By` trailers.
- Keep pull requests small and link the issue (`Closes #123`).
- Add a line to [`CHANGELOG.md`](CHANGELOG.md) under `Unreleased` for anything a user
  would notice.
- By contributing you agree that your work is licensed under Apache-2.0, like the rest of
  the project, and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
