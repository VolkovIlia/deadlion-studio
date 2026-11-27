# Coding-agent pilot

Model gpt-6.2-astra, Codex CLI 0.172.0, existing ChatGPT login. Each arm used two new read-only sessions. One solved membership queries; one solved the seven functions in prompt.md. The first prompt requested solve(xs, queries) to return integer multiplicities for up to 100000 integers per input, with duplicates and negative keys. The limits were 90 and 240 seconds respectively. Each prompt required Python standard library, no network services and no subagents. The benchmark evaluator and sample answers were outside agent workspaces.

A had an empty project. B received skills from 02aa71c. C and D received the development snapshot of updated skills at the start of the pilot, before later cache, contract and profiling work. B/C were asked to use applicable skills. D was additionally asked to measure at most two candidate algorithms before selecting one. D exercised experimental optimization in Codex; the OMP launcher is tested separately.

| Arm | Passing tasks | Input tokens | Cached input tokens | Output tokens | Tool commands |
|---|---:|---:|---:|---:|---:|
| A | 8/8 | 35268 | 27648 | 1556 | 0 |
| B | 8/8 | 214720 | 192896 | 4221 | 18 |
| C | 8/8 | 312147 | 282368 | 5809 | 25 |
| D | 8/8 | 325536 | 297600 | 7394 | 29 |

For each reviewed sample, run `python3 -I grade.py samples/A` from this directory, substituting the arm. measurements.json retains nine uninstrumented wall-clock observations per case and the Python traced peak from a separate execution. Timings include fixture construction and assertions. They are suitable for reproducing the pilot and identifying follow-up workloads. The grader covers sockets with fragmented reads, short file reads, an instrumented SQLite connection and bounded concurrent iteration.

There was one generation trial per arm, with seven tasks batched in the second session. Timing batches were collected sequentially on one shared host. Instruction text differed by treatment, and tool access was read-only. The results establish feasibility; they do not establish an agent-quality improvement. Provider totals include cached inputs on repeated turns. Allocation event counts, energy, longitudinal repair rates and exact end-to-end generation latency were not collected.

For the seven-function session, event-file creation to final write took approximately 35 s (A), 88 s (B), 121 s (C) and 144 s (D). These are local elapsed-time estimates at one-second resolution.
