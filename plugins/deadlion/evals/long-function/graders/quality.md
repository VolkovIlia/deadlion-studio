---
type: llm
weight: 1
---

PASS if the resulting Python code has no function longer than 50 lines and handles invalid input with early returns, guard clauses, or errors returned/raised as values rather than deeply nested conditionals. FAIL if any function exceeds 50 lines or validation is buried in nested if/else blocks.
