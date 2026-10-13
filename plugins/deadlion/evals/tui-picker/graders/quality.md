---
type: llm
focus: trace
weight: 1
---

PASS if the session's output — the final reply or the content of any file Claude wrote (e.g. design.md via Write) — does all of: chooses a terminal rung (filter or TUI) with a reason, not web or native GUI; draws the UI on the terminal while the chosen branch goes to stdout, or composes with `git` rather than reimplementing it; gives a key map covering move, pick and cancel; designs an empty-list state and an error state; and defines colours as named tokens with contrast pairs. FAIL if any of these appears nowhere in that output.
