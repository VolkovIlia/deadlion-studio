---
type: llm
focus: trace
weight: 1
---

PASS if the session's output — the final reply or the content of any file Claude wrote (e.g. design.md via Write) — does all of: names its target rung (CLI, filter, TUI, native GUI or web) with a reason; covers user flows and screen states including at least an empty state and an error state; gives a colour token plan of 4–6 named tokens; and lists explicit gates of that rung (web: 44px minimum touch targets and colour contrast; terminal: 80×24 and 40×12 sizes, a key map and contrast; native GUI: contrast, keyboard operation and window sizes). FAIL if any of these appears nowhere in that output.
