---
type: llm
focus: trace
weight: 1
---

PASS if the session's output — the final reply or the content of any file Claude wrote (e.g. .dev-docs/system.md via Write) — does all of: splits the system into at least 3 sub-projects with one job each; reuses at least one existing tool (e.g. cron, curl, an existing pager) instead of new code; gives each sub-project a plain-text interface with an exact format; gives each a language with a reason and a rejected alternative; gives each a SLOC budget and its own make/run command. FAIL otherwise.
