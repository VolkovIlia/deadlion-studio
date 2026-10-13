# Raymond's 17 rules of Unix design, with checks

| # | Rule | Concrete check |
|---|---|---|
| 1 | Modularity: simple parts, clean interfaces | Each component's interface fits in 5 lines of arch.md |
| 2 | Clarity is better than cleverness | A newcomer can explain any function after one read; no tricks needing a comment to decode |
| 3 | Composition: design to connect with other programs | Reads stdin or a file, writes stdout; usable in a pipe |
| 4 | Separation: policy from mechanism, interface from engine | Changing a limit or rule edits config/data, not engine code |
| 5 | Simplicity: add complexity only where you must | Each abstraction has ≥2 current users; delete it otherwise |
| 6 | Parsimony: big programs only when nothing else works | Files ≤500 lines, functions ≤50 (`dl-size` clean) |
| 7 | Transparency: design for visibility | State is inspectable with `cat`/`jq`/`sqlite3`; no opaque blobs |
| 8 | Robustness is the child of transparency and simplicity | Each failure mode has a test and a specific error message |
| 9 | Representation: fold knowledge into data | Dispatch via tables/maps, not long if/else or switch chains |
| 10 | Least surprise | Flags, names and exit codes follow common conventions (`-h`, `--`, 0 = success) |
| 11 | Silence: say nothing when there's nothing to say | Successful run prints nothing (or only the requested output) |
| 12 | Repair: fail noisily and as soon as possible | Bad input → stderr message naming input + cause, non-zero exit, no partial output |
| 13 | Economy: programmer time over machine time | No hand optimisation without a measured bottleneck |
| 14 | Generation: write programs to write programs | Repetitive code/stubs generated from the contract or a table |
| 15 | Optimization: prototype before polishing | A working end-to-end path exists before any tuning |
| 16 | Diversity: distrust "one true way" | Decisions list at least one rejected alternative and why |
| 17 | Extensibility: design for the future | Text formats tolerate unknown fields; new behaviour = new table row or new stage |
