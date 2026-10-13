# Security policy

## Supported versions

Only the latest release of each plugin gets security fixes.

| Plugin | Supported |
|---|---|
| `deadlion` 4.2.x | yes |
| `deadlion-triz` 4.0.x | yes |
| anything older | no |

## Report a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through
[GitHub private vulnerability reporting](https://github.com/VolkovIlia/deadlion-studio/security/advisories/new),
or email ilia.volkov@outlook.com with `deadlion security` in the subject.

Include the plugin and version, what an attacker can do, and the steps to reproduce.

## What to expect

- A first reply within 7 days.
- A fix or a decision within 30 days for confirmed issues.
- Credit in the release notes, unless you prefer to stay anonymous.

## Scope

The plugins run code on your machine, so these are in scope:

- the hooks in `plugins/deadlion/hooks/hooks.json`, which run after every Write/Edit
  and before `git commit`;
- the tools in `plugins/*/skills/*/scripts/` (`dl-size`, `dl-budget`, `dl-guard`,
  `dl-contrast`, `dl-tui`, `dl-new`);
- skill or agent text that makes Claude run commands you did not ask for.

Bugs in Claude Code itself go to Anthropic, not here.
