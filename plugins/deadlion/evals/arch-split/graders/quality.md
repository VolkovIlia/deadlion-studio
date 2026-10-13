---
type: llm
focus: trace
weight: 1
---

PASS if the session's output — the final reply or the content of any file Claude wrote (e.g. arch.md via Write) — splits the service into components that each do one job (e.g. download, parse, dedupe, upload), defines explicit text interfaces between them (such as line-oriented or JSON lines on stdin/stdout, or files with a stated format), and gives one command to run each component on its own. FAIL if components share hidden state, interfaces are left implicit, or there is no per-component run command.
