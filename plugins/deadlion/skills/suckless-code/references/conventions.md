# Program conventions

The single contract every program follows: flags, exit status, output, files,
interactive behaviour, embedding and releases. Other skills link here.

## Invocation
- `NAME [-v] [options] [file...]`.
- `-` as a file operand means stdin; `--` ends options.
- `-v` prints `NAME-VERSION` on stdout and exits 0.
- An unknown option prints `usage: NAME …` on stderr.

## Exit status
| Kind | 0 | 1 | 2 |
|---|---|---|---|
| Programs (suckless/sbase style) | success | any error, usage included | — |
| Checkers and predicates (dl-* tools, grep-like) | clean / no | found / yes | usage or IO error |

## Output
- Silent on success; results on stdout.
- Diagnostics on stderr as `NAME: cause` or `NAME: FILE: cause`.
- No colour when stdout is not a tty or `NO_COLOR` is non-empty.

## Configuration and files
- Compile-time configuration: `config.def.*` is copied to `config.*` on the first build;
  users edit `config.*`.
- Runtime configuration: `${XDG_CONFIG_HOME:-$HOME/.config}/NAME/`.
- Data: `${XDG_DATA_HOME:-$HOME/.local/share}/NAME/`.
- State: `${XDG_STATE_HOME:-$HOME/.local/state}/NAME/`.
- Environment variables `NAME_*` only for overrides.

## Interactive programs
- The UI is drawn on `/dev/tty`, never on stdout, so the program sits in a pipe.
- `TERM=dumb` → `NAME: TERM=dumb: cannot draw`, exit 1.
- Terminal mode and screen are restored on every exit path.
- In raw mode Ctrl-C is a key that cancels (exit 1).

## Embedding modes
design.md `## Target` names the modes a program supports.

1. **Filter**: stdin → stdout.
2. **Terminal**: draws in whatever terminal or pane it gets and follows size changes.
3. **X11**: `-w WINID` reparents into the given window (XEmbed, as st, surf and dmenu
   do). Wayland has no general embedding; say so.
4. **Front end over an engine contract** (decompose patterns 5 and 8): the UI is a
   separate program; the engine runs headless.

## Versioning and release
- One version source per program:

  | Language | Source |
  |---|---|
  | C | `config.mk` `VERSION` |
  | Rust | `Cargo.toml` `[package] version` |
  | sh | `VERSION=` at the top of the script |

- `make dist` → `NAME-VERSION.tar.gz`.
- Tag `NAME-VERSION`.
- Checksum file `NAME-VERSION.tar.gz.sha256`.
