# UI targets and gates per rung

Embedding modes and program behaviour:
`${CLAUDE_SKILL_DIR}/../suckless-code/references/conventions.md`.

## Ladder

Pick the lowest rung that serves the job. Record in design.md `## Target`:
`Target: <rung> — reason; rejected: <next rung up> — reason`, plus how the program runs
alone and how it embeds. An existing codebase keeps its rung unless the job changed.

| Rung | When | Runs alone and embeds | Stack | Verify | Template |
|---|---|---|---|---|---|
| 1. CLI | input known up front, one result | pipes | per `languages.md` | `test.sh` | `c`, `rust`, `sh` |
| 2. Filter | the user picks among items another program produces | any pipeline, terminal or launcher; UI on /dev/tty, choice on stdout | Rust std + libc | dl-tui | `rust-tui` |
| 3. TUI | browsing or editing over time, several views | any terminal or tmux pane; the engine is a separate CLI/back end (decompose patterns 5 and 8) | Rust std + libc | dl-tui | `rust-tui` as the start |
| 4. Native GUI | pixels: images, canvas, pointer-heavy work, users without a terminal | X11 `-w WINID`; Wayland has no embedding (say so) | C + Xlib/Xft when X11-only and ≤1000 SLOC (dwm/dmenu lineage); otherwise Rust + `winit` + `softbuffer`, each dependency a Decisions line | dl-contrast, keyboard tests, screenshot only on X11 (`import -window root`), otherwise NOT VERIFIED | none |
| 5. Web | remote or multi-user access, or mobile | every view has its own URL | TypeScript, no framework unless justified | ui-verify with Playwright | none |

Above the CLI rung the UI is a front end: the work happens in an engine that also runs
headless (a CLI, library or back end with a contract).

## Terminal gates (filter, TUI)

| Gate | Threshold |
|---|---|
| Sizes | correct at 80×24; usable at 40×12; no crash or garbage at 20×5 |
| Resize | redrawn within 100 ms |
| Keys | every action by keyboard; filter: arrows + Ctrl-n/Ctrl-p, Enter, Esc/Ctrl-c; TUI: arrows + hjkl, Enter, q, `?` help |
| Help | filter: key help always in the status line; TUI: on `?` |
| Colour | every fg/bg token pair ≥4.5:1 (dl-contrast); state never shown by colour alone (marker, reverse video or text) |
| NO_COLOR | non-empty NO_COLOR → no colour sequences, still fully usable |
| Output | UI on /dev/tty; only the result on stdout; errors `NAME: cause` on stderr |
| Restore | terminal mode and screen restored on every exit path |
| Text | truncated, never wrapped; columns aligned on the cell grid |
| States | empty input, no match, error and success each designed and reachable |

## Native GUI gates

| Gate | Threshold |
|---|---|
| Contrast | text ≥4.5:1, UI boundaries ≥3:1 (dl-contrast) |
| Keys | full keyboard operation, visible focus |
| Sizes | correct at 1280×800, usable at 640×400, no clipping at 320×200 |
| Scale | fonts and spacing from config tokens; honour `Xft.dpi` or the Wayland scale factor |
| Feedback | <100 ms to a visible response |
| Embed | `-w WINID` on X11 |

## Web gates

| Gate | Threshold |
|---|---|
| Primary actions visible at once | ≤7 (more → progressive disclosure or split screen) |
| Items per group | 5–7, then chunk |
| Touch targets | ≥44×44 px; ≥8 px between adjacent targets (WCAG 2.5.8 floor is 24×24) |
| Text contrast | ≥4.5:1; large text (≥18px or 14px bold) and UI components/focus ring ≥3:1 |
| Body text | ≥16 px, line height ≥1.5 |
| Focus | visible, ≥2 px outline, never removed |
| LCP / INP / CLS | <2.5 s / <200 ms / <0.1 |
| Feedback to an action | <200 ms (show pressed/loading state) |
| Breakpoints | design 375 first, then 768, 1280; no horizontal scroll at 320 |

Also: every action works without dragging and by keyboard alone; labels are never
placeholder-only; `prefers-reduced-motion` disables non-essential motion; help sits in the
same place on every screen. Full criteria: `${CLAUDE_SKILL_DIR}/references/wcag.md`.

## Professional finish (all rungs)

- One typeface: terminal → the user's font; GUI → one font from config; web → at most two.
- Alignment on a grid: the cell grid, or a 4/8 px grid.
- One key map shared by all programs of a system.
- Buttons and keys named by verbs.
- Errors say what to do next.
