---
name: testing
description: "Test strategy and execution: test-first, isolated unit tests, then integration, then regression; tests assert behaviour, boundaries and errors, never wiring or mock echoes; make test and test.sh for programs, fixture tests for contracts; memory-safe fixtures for large suites. Use when writing tests, choosing what to test, or when a test suite is slow, flaky or runs out of memory."
---

# Testing

Acceptance criteria come from `product.md` / `plan.md` when a feature is active (contract: `${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`).

## TDD law
No production code without a failing test first. Code written before its test is deleted
and rewritten after the test fails for the right reason.

## Gates (blocking, in order)
1. **Pre-flight**: project env and toolchain present (`cc`, `cargo`, venv…), dependencies consistent (`pip check`, lockfile in sync). Broken env → stop and report; do not test around it.
2. **Isolated (unit)**: 100% pass before running integration.
3. **Integration**: 100% pass; contracts match their schema files.
4. **Workflows**: every happy path covered end to end.
5. **Browser E2E**: zero console errors.
6. Never loosen a gate, skip a test or exclude code from coverage to go green.

## What a test must assert
- Behaviour: observable output/state, not that a function was called. A test that only re-asserts what a mock returned proves nothing.
- Every handler has an explicit state assertion; "does not crash" is not a test.
- Boundaries: empty, min, max, null/missing optional fields.
- Errors: invalid input, 401, 403, 429 — each yields a clear, specific message and status.
- Type coercion across boundaries (a string id from a token vs an int id in the DB) — the most common integration failure.
- Concurrency where it applies (≥5 simulated users), soft-delete visibility, persistence across reload.
- Synthetic test data; never real credentials.
- Every RNG is seeded with a fixed, named seed.

## Programs and contracts
- **Programs:** `make test` is every program's test entry; CLI behaviour is tested by
  `test.sh`: exact stdout for an input, exit code, `NAME:` stderr prefix.
- **Interactive terminal programs:** tmux-driven screen tests in `test.sh` (see the
  `rust-tui` template) and dl-tui snapshots for each designed state.
- **Contracts:** each consumer has a test that feeds its fixture copy of the contract
  example; each producer has a test that its output matches the example format.

## Order
1. Unit tests, no external dependencies.
2. Integration: API vs schema, DB type conversions, auth flows, contract fixtures.
3. Workflow/E2E: full CRUD lifecycle, then error paths, then edge cases. Collect console errors:
   ```javascript
   const errors = [];
   page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
   // after each step
   expect(errors).toHaveLength(0);
   ```
4. Risk-based regression — score and run highest first:
   - +20 critical path (auth, payment, data loss)
   - +15 cyclomatic complexity >10
   - +10 changed in the current diff
   - +5 defect history or external dependency

Gates >1 min run in background with output to `.logs/tests/<gate>.log`.

## Failure classification
Classify every failure into exactly one row. Calling a non-failure a failure is itself a defect.

| Category | Indicators | Action |
|---|---|---|
| True test failure | Assertion fails in a regime the gate is specified to hold; contract violation | Reproduce and fix via `debug` |
| Implementation bug | Code does not meet acceptance criteria | Fix with a repro test |
| Environment | Env missing, service down | Fix env; do not retry tests |
| Test bug | Flaky (<95% pass rate), non-deterministic | Pin seed, fix test, re-run once |
| Infra / timeout | Budget exceeded, network | Decompose; retry with backoff, max 2 |

Never widen a threshold to pass. After 2 retries of a transient failure, stop and report.

## Logs
Test logs go to `.logs/tests/{unit,integration,e2e}/` (`mkdir -p` first); never `.log` files in the project root.

## Large suites
Suite slow or OOM, many per-file engines/fixtures, or files >500 lines → follow `${CLAUDE_SKILL_DIR}/references/memory-efficient-testing.md`.

## Report
Per phase: command run, pass/fail counts, each failure with its category and repro command. Partial results are reported as partial.
