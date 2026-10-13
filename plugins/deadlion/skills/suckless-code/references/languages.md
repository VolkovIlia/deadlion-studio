# Language choice and idioms

The single source for choosing a program's language. `decompose` and `scaffold`
link here. Record the result as
`Language: X — reason; rejected: Y — reason`.

## Decision procedure
Apply in order; the first match wins. Write down the reason.

1. **Extends an existing codebase** → that codebase's language.
2. **Runs in a browser** → TypeScript, no framework unless the design needs one
   (justify it in Decisions).
3. **≤150 lines composing existing tools, data is lines** → POSIX sh.
4. **All of the following** → C:
   - ≤1000 SLOC;
   - talks mainly to libc, POSIX, X11 or kernel interfaces;
   - parses no complex untrusted input;
   - must build with only `cc` on any Unix.
5. **Glue or data munging with no performance or deploy constraint, or it needs an
   ecosystem only Python has (scientific, ML)** → Python, stdlib first.
6. **Otherwise** → Rust. The default: memory safety for parsers, network input and
   long-running daemons.

Templates exist for C, Rust, Rust terminal UIs (`rust-tui`) and sh (`dl-new`,
scaffold skill). For any other language, apply the layout checklist below by hand.

## Idioms and limits

### C
- C99 + `-D_POSIX_C_SOURCE=200809L`; `-std=c99 -pedantic -Wall -Wextra`, zero warnings.
- `die()` for fatal errors (a trailing `:` in the format appends `strerror(errno)`),
  `ecalloc()` for allocation that cannot fail silently.
- Options via POSIX `getopt`.
- Function names at column 0, return type on the line above.
- `static` for everything file-local; no declarations after statements.
- File order: includes, macros, declarations, globals, `#include "config.h"`,
  definitions, `main`.
- Libraries: libc plus at most one protocol library (X11, libcurl, …), listed in
  `config.mk` `LIBS`.

### Rust
- Zero dependencies by default; each dependency needs a Decisions line.
- No `unwrap`/`expect` outside tests; errors bubble to `main` as `Result` and end
  in `die`.
- No async runtime unless concurrent network I/O is the job.
- Release profile as in the template: `opt-level = "s"`, `lto`, `panic = "abort"`,
  `strip`, `codegen-units = 1`.
- Manual argument parsing for small CLIs; no clap.
- Terminal UI (filter/TUI): std + `libc` only (termios, `TIOCGWINSZ`, `poll`); template
  `rust-tui`; ratatui/crossterm only with a Decisions line.

### sh
- POSIX only (no bash arrays, `[[`, `local`), `set -eu`.
- Quote every expansion; `--` before operands.
- `shellcheck` clean if it is installed.

### Python
- stdlib only by default; one file ≤500 lines.
- `argparse`; exit status per `conventions.md`.

### TypeScript
- No runtime dependencies unless justified in Decisions.
- `tsc --noEmit` clean.

## Layout checklist (any language)
- [ ] POSIX Makefile with `all test install uninstall clean`
- [ ] man page `NAME.1`
- [ ] `LICENSE` (MIT)
- [ ] plain-text `README`
- [ ] default config file copied to the real config on the first build
- [ ] `.budget` (`sloc N`, `deps N`)
- [ ] behaviour per `conventions.md`
- [ ] `dist` target producing `NAME-VERSION.tar.gz`
- [ ] release = tarball or tag
