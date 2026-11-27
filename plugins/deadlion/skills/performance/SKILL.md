---
name: performance
description: "Analyze algorithm choices, verify a runtime budget, or investigate an allocation, I/O or CPU bottleneck using workload-specific evidence."
---

# Performance

Use the current architecture, plan, review and verification artifacts.

| Mode | Trigger | Evidence |
|---|---|---|
| Standard | Default | Run scripts/dl-analyze on changed source files from the repository root. Record its scope. |
| Performance | Runtime requirement or observed resource bottleneck | Freeze input, output contract, release build, budget and baseline before editing. Profile the bottleneck and compare paired measurements. |
| Research | Algorithm choice depends on a model or numerical assumptions | State the input dimensions, distribution, invariant, lower bound if known, and independent oracle. Compare alternatives at representative sizes. |
| Evolution | Explicit bounded candidate search | Use an isolated worktree per candidate and an external evaluator. Record all trials and Pareto tradeoffs. Enforcement of experimental limits requires a verified runner. |

## Architecture and review

For a nontrivial algorithm record alternatives, preprocessing and update costs, auxiliary and output space, worst and expected cost and the assumptions for amortization. Separate mathematical bounds, checker results and observed scaling. Test both small and large inputs. Review invariants, ownership, cancellation, backpressure and numerical tolerance against a trusted reference.

For CPU hotspots inspect samples before selecting available counters. Evaluate SIMD, cache locality, false sharing and synchronization only where the profile motivates them. For rising memory measure lifetimes, allocation counts and peak RSS separately. Record the memory and invalidation cost of any cache.

## Execution

Run scripts/dl-analyze --changed from the target Git root using the executable inside this skill. For Python source returned in chat, pipe the draft to scripts/dl-analyze --stdin-name draft.py. Use --help for CLI flags.

For Performance and Research run scripts/dl-contract on the plan contract and scripts/dl-perf against the trusted baseline. Use scripts/dl-profile when a CPU, memory or PMU metric answers the question. Read references/commands.md for workload setup, profiling, evidence interpretation or OMP Evolution.

For profiling choices and limitations by symptom and language, read references/investigation.md.
