## What and why

<!-- One or two sentences. Link the issue: Closes #123 -->

## Type

- [ ] Bug fix
- [ ] New skill, tool or template
- [ ] Change to an existing skill or tool
- [ ] Docs, tests or CI only

## Checks

- [ ] `pytest tests -q`
- [ ] `sh tests/test_export_skills.sh`
- [ ] `claude plugin validate` for every changed plugin
- [ ] `dl-size plugins scripts tests` prints nothing
- [ ] Eval case run for every skill whose wording changed (or: not needed)
- [ ] `CHANGELOG.md` updated under `Unreleased` (or: nothing a user would notice)
