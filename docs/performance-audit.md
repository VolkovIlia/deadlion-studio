# Performance engineering audit

Current baseline `02aa71ce`, legacy HEAD `0ea59db7` (GitHub API and SSH agreed). Source inspection and executable integration have different evidence requirements. The license column is GitHub's repository classifier. Review the selected component's license before redistribution. No upstream code is vendored.

| Capability | Legacy | Current baseline | External solution | Decision |
|---|---|---|---|---|
| Implementation evidence | agentic-engineer, 2688 lines | build, testing, verify | independent reference implementation | Keep the current workflow and add an algorithm contract |
| Review | reviewer-suckless, 1611 lines | review, dl-size, dl-budget | native performance lints | Report structural and computational costs separately |
| Profiling | performance-testing-specialist, 1104 lines of instructions | testing reference | perf, heaptrack, Memray, Scalene | Select by workload and runtime |
| Proof | formal-verifier, 811 lines | testing and verify | differential and property tests | Record assumptions, invariants and counterexamples |
| Setup | engineer-setup, 33 lines | exported skills | native toolchain | Discover tools per task |
| Test memory | memory-efficient-testing, 193 lines | testing/references/memory-efficient-testing.md | memory profiler | Retain reference and measure peak memory on demand |
| Process guidance | ANTI_PATTERNS and PRINCIPLES | workflow, review, verify | none needed | Preserve isolated validation without importing orchestration rules |
| Baseline | save_performance_baseline.py, pytest-benchmark importer | no equivalent executable | Hyperfine | Keep raw samples. The historical quartile extrapolation cannot recover tail percentiles |
| Function size | validate-function-sizes.py, Python AST | dl-size, AST and lizard | lizard | Reuse current check |
| Architecture | validate-architecture-constraints.py checks package size and capability coverage | decompose, unix-design, dl-budget | native metrics | Keep design constraints distinct from measured runtime |

| Source | Pinned file | License classifier | Inspected path |
|---|---|---|---|
| VolkovIlia/deadlion-studio-legacy | [0ea59db7f](https://github.com/VolkovIlia/deadlion-studio-legacy/blob/0ea59db7fc26947d56980a6afa537c763814dbf6/scripts/save_performance_baseline.py) | Apache-2.0 | `scripts/save_performance_baseline.py` |
| K-Dense-AI/scientific-agents | [98c7fae46](https://github.com/K-Dense-AI/scientific-agents/blob/98c7fae46648724e1a43a1f2b207b0c82fcc462e/scientific-agents/computer-scientist/skills/computer-scientist/SKILL.md) | MIT | `scientific-agents/computer-scientist/skills/computer-scientist/SKILL.md` |
| pproenca/dot-skills | [cf93c57ca](https://github.com/pproenca/dot-skills/blob/cf93c57cac89d6fc3e4194686000411567f5caf3/skills/.experimental/algorithmic-complexity-review/SKILL.md) | MIT | `skills/.experimental/algorithmic-complexity-review/SKILL.md` |
| intel/intel-performance-skills | [3e33aecab](https://github.com/intel/intel-performance-skills/blob/3e33aecabb956ec48526b3f842f4f70ae96d98ff/skills/linux-perf/SKILL.md) | NOASSERTION | `skills/linux-perf/SKILL.md` |
| intel/skills | [a24b1d17a](https://github.com/intel/skills/blob/a24b1d17aa1ad173265cb5e0bcc8dd0d6183bd61/skills/linux-perf/SKILL.md) | Apache-2.0 | `skills/linux-perf/SKILL.md` |
| ast-grep/ast-grep | [b18c31947](https://github.com/ast-grep/ast-grep/blob/b18c3194722accf3be35127158baf1ee5f2ac22e/crates/cli/src/scan.rs) | MIT | `crates/cli/src/scan.rs` |
| semgrep/semgrep | [c4dbe9ee2](https://github.com/semgrep/semgrep/blob/c4dbe9ee2fc6d0022ba02ef6b97c5954ed9549e3/src/matching/Matching_generic.ml) | LGPL-2.1 | `src/matching/Matching_generic.ml` |
| facebook/infer | [ec62d9aa7](https://github.com/facebook/infer/blob/ec62d9aa765b6e769c199376488b7dec3306c321/infer/src/base/costKind.ml) | MIT | `infer/src/base/costKind.ml` |
| sebastianbreguel/agent-complexity-optimizer | [dd0b8bf9e](https://github.com/sebastianbreguel/agent-complexity-optimizer/blob/dd0b8bf9ed2b26c6385b9101b86c21146b43aa6f/skills/complexity-optimizer/scripts/analyze_complexity.py) | MIT | `skills/complexity-optimizer/scripts/analyze_complexity.py` |
| davebcn87/pi-autoresearch | [04b8a50da](https://github.com/davebcn87/pi-autoresearch/blob/04b8a50dac7efe80ffc91648bd00ed9b022e24c2/extensions/pi-autoresearch/index.ts) | MIT | `extensions/pi-autoresearch/index.ts` |
| skydiscover-ai/skydiscover | [0d932b690](https://github.com/skydiscover-ai/skydiscover/blob/0d932b690670a7e544388ad362e9876c8bd256a0/skydiscover/optimize/search/adaevolve/database.py) | Apache-2.0 | `skydiscover/optimize/search/adaevolve/database.py` |
| algorithmicsuperintelligence/openevolve | [2239f8710](https://github.com/algorithmicsuperintelligence/openevolve/blob/2239f871087d2f6f17a84c0d682ee7087d0fac33/openevolve/database.py) | Apache-2.0 | `openevolve/database.py` |
| KDE/heaptrack | [ef86ce54b](https://github.com/KDE/heaptrack/blob/ef86ce54b4c3767b695e7d3adbc6365631d868b3/src/analyze/print/heaptrack_print.cpp) | unclassified | `src/analyze/print/heaptrack_print.cpp` |
| sharkdp/hyperfine | [c51615249](https://github.com/sharkdp/hyperfine/blob/c5161524980522320c7d3425e714cc0965a869a5/src/benchmark/benchmark_result.rs) | Apache-2.0 | `src/benchmark/benchmark_result.rs` |
| bloomberg/memray | [c87362489](https://github.com/bloomberg/memray/blob/c873624894c1505a18691ce51602f385812c5617/src/memray/commands/run.py) | Apache-2.0 | `src/memray/commands/run.py` |
| plasma-umass/scalene | [df36d924c](https://github.com/plasma-umass/scalene/blob/df36d924c9284b9589cc21dd2bb0134d9d110f9d/scalene/scalene_profiler.py) | Apache-2.0 | `scalene/scalene_profiler.py` |
| rust-lang/rust-clippy | [6a58c2590](https://github.com/rust-lang/rust-clippy/blob/6a58c25905802686cd48e5b02d28df4b8689acd5/clippy_lints/src/redundant_clone.rs) | Apache-2.0 | `clippy_lints/src/redundant_clone.rs` |
| llvm/llvm-project | [11501b663](https://github.com/llvm/llvm-project/blob/11501b6633a2cb2e63a9839a1ba5c278d4229eb6/clang-tools-extra/clang-tidy/performance/AvoidEndlCheck.cpp) | NOASSERTION | `clang-tools-extra/clang-tidy/performance/AvoidEndlCheck.cpp` |
| astral-sh/ruff | [c05df9647](https://github.com/astral-sh/ruff/blob/c05df9647fbd20e2832120fae9b957a11b668e85/crates/ruff_linter/src/rules/perflint/rules/incorrect_dict_iterator.rs) | MIT | `crates/ruff_linter/src/rules/perflint/rules/incorrect_dict_iterator.rs` |
| jc1122/perf-benchmark-skill | [457340024](https://github.com/jc1122/perf-benchmark-skill/blob/457340024cb604658942f57674aefcc70cc733ad/SKILL.md) | MIT | `SKILL.md` |

Both Intel repositories contain the Linux perf skill. Begin with workload, elapsed time and hotspot samples. Select events from the machine's available PMU list. A missing counter or permission is missing evidence. Clippy's redundant-clone analysis uses compiler information. An AST match alone cannot establish ownership or lifetime. Infer Cost, Pulse and Buffer Overrun require separate language and checker validation. Unknown cost is possible, including through unmodeled calls.

The experimental dot-skills review and the K-Dense profile provide reasoning guidance. The complexity optimizer additionally ships a scanner. Nested traversals can be optimal for dense output. Confirm cardinality and output bounds before raising severity. SkyDiscover and OpenEvolve remain optional research engines pending bounded execution tests. Pi Autoresearch exposes an extension implementation with Pi-specific imports. Interface compatibility requires a live OMP test.

OMP 19.2.1 registered both the exported performance skill and the built-in autoresearch command in a fresh RPC session. The native implementation stores experiments and supports a per-segment iteration cap. Its default permits unlimited iterations. Discard and clear operations may reset the current checkout. Deadlion therefore starts OMP in an independent clone and adds an external deadline and a persistent total attempt counter. [Versioned OMP contract](https://github.com/can1357/oh-my-pi/blob/v19.2.1/docs/autoresearch.md)

On the audited Fedora installation, loading the pinned upstream Pi Autoresearch entrypoint directly in OMP failed before registration. Its package declares Pi peer dependencies. No extra Pi runtime was installed. The built-in implementation was available in the same binary. The two Intel repositories expose overlapping Linux perf skills. The dedicated project's COPYRIGHT.md gives the MIT grant despite its unclassified metadata. LLVM components carry the LLVM exceptions. Inspect individual KDE SPDX headers, and both MIT and Apache options where shipped (including Hyperfine and Clippy).

The structural adapter uses ast-grep 0.51.3. Its x86_64 GNU/Linux release ZIP verified against SHA-256 `22803eb0c5bf83164fb7fd76d4721d355ecf0c8466ef47342c1ec7d80897ca47`. Native rules run as warnings and include paired test fixtures. Semgrep remains optional for future dataflow checks. The external complexity optimizer includes a Python AST scanner and text heuristics in separate modules. No rules from it were vendored. The focused initial corpus assesses Deadlion rules, not the precision of that upstream scanner.

Running the pinned agent-complexity-optimizer against two Python functions flagged both the redundant membership scan and a generator that must yield every Cartesian-product pair. Both received the same high severity and score of 10. Relative to a label of avoidable computation this gives one true positive and one false positive on this two-function probe. Deadlion does not adopt that severity as a blocking gate.

Infer 1.3.0 documents Java and limited C/C++/Objective-C support for Cost. Buffer Overrun, Pulse and RacerD each list Java and C/C++/Objective-C. Pulse additionally lists experimental Rust. These are upstream claims, with local execution unverified. Kotlin capture needs a separate test. [Cost](https://fbinfer.com/docs/checker-cost/) · [Buffer Overrun](https://fbinfer.com/docs/checker-bufferoverrun/) · [Pulse](https://fbinfer.com/docs/checker-pulse/) · [RacerD](https://fbinfer.com/docs/checker-racerd/)

Direct loading of upstream pi-autoresearch 1.9.0 failed in the isolated OMP session. In a clean disposable Git repository, a real RPC prompt toggled the native /autoresearch command on, created an autoresearch branch and toggled it off without invoking a model. A dirty-repository probe refused activation. The installed profile also has a user-specific Deadlion adapter; the repository ships an independent opt-in performance event adapter and does not modify user configuration.

## Local acceptance evidence

| Evidence | Observed result | Boundary |
|---|---|---|
| Native OMP 19.2.1 lifecycle | Two separate RPC sessions against a local scripted transport. Keep, pause, resume, failed independent check, discard, persisted attempts and original branch checked by tests/omp_autoresearch_smoke.py | Harness integration test; agent quality measured separately |
| Structural fixtures | Fifteen ast-grep rules. Each found its positive fixture and omitted its negative fixtures | Curated in-distribution examples; warning-level precision does not imply field precision |
| Shell edit / commit | A real pre-commit installation in a temporary Git repository blocked invalid Python with exit 1 and accepted the corrected file | Local hooks can be skipped. CI recomputes from the checkout |
| Latency of analysis | See performance-overhead.json for eleven raw runs per case and median | Python process startup included, on one Fedora machine |
| Source checkout | Added CLI, AST corpus, references and smoke tests. Workflow, architecture, planning, build, review, verify, agents, hooks, pre-commit and CI call or route to those checks | Hosted CI execution and branch-protection settings are outside this local run |
| Performance and tradeoffs | indexed-membership records forward/reverse pairs and small inputs. false-sharing compares two independently updated atomic counters on distinct physical cores | Wall time includes startup; PMU attribution requires hardware counters |
| Agent comparison | Eight functional cases passed in each of A/B/C/D. See evals/agent-performance for generated code, token counts and independent measurements | One pilot per arm; seven functions batched. No demonstrated general improvement |

The verifier distinguishes heuristic feedback, resource-budget failure, missing evidence and an inconclusive ratio interval. An exact text-output oracle handles deterministic byte streams. Workloads with numerical tolerances, externally visible side effects or concurrency semantics need a separate trusted verifier. The generic runner does not estimate asymptotic bounds from finite samples. Automated allocator counts, JVM tooling, GPU profiling, a hard provider-level token limit and broad field estimates of precision/recall remain open. The OMP launcher isolates the source checkout, but a separate OS identity/container is still appropriate for adversarial generated code.

## Corpus coverage

| Requested scenarios | Executable evidence |
|---|---|
| 1, 14. Index lookup and small inputs | indexed-membership contains both sizes and the reverse regression run |
| 2–5. Copying, allocation in loops, repeated sorting, concatenation | ast/tests includes copy, clone, malloc, sort, Java concat and growing JS array fixtures |
| 6. N+1 | Python SQL loop hint; the independent SQLite grader counts statements |
| 7, 8. Synchronization and false sharing | Lock around awaited reads with an outside-lock alternative; compiled adjacent/padded atomic-counter pair |
| 9. Unbounded retention | Pytest compares retaining allocations versus one reused buffer with an absolute RSS ceiling; concurrent grader rejects unbounded prefetch |
| 10. Serialization | Python and TypeScript serialization fixtures |
| 11–13. Structural complexity and valid control flow | INFO for nested Python conditions, no required rewrite for a predictable branch, no diagnostic on a dense-output nested loop |
| 15, 16. Incorrect semantics and numerical drift | Wrong output rejection, exact-byte oracle and cancellation-sensitive floating-point reference |
| 17. Variability | Paired-ratio classification on a fixed high-dispersion series |
| 18. Missing or faulty tools | Missing executable, invalid tool output and invalid input syntax tests |
| 19, 20. Interruption and bypass | Cross-process OMP pause/resume with a consumed budget and independent keep check; changed-file scan after shell write and pre-commit exercise |

The Java rule detects repeated concat calls. Its arithmetic-addition negative fixture prevents a numeric accumulator from matching that rule. Static suggestions still require workload evidence. The default skill is short; command details and diagnostic interpretation are loaded separately. After the agent pilot, a stdin adapter was added because agents repeatedly read adapter implementation code to handle read-only tasks. The effect on token use needs a new controlled run.
