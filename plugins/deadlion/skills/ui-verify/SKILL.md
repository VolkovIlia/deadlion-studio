---
name: ui-verify
description: Verifies a running UI against the gates in design.md — web pages in a real browser via the Playwright MCP (screenshots at 375/768/1280 px, console errors, axe scan, touch targets), terminal programs through dl-tui in a headless tmux (screens at 80×24, 40×12 and 20×5, NO_COLOR, key scripts per state, terminal restore, stdout purity), and token contrast with dl-contrast. Use after implementing or changing any UI, or when the user asks to check how a screen looks or works.
---

# UI verify

Gates come from `.dev-docs/features/<slug>/design.md` (`## Target`, `## Accessibility
gates`, `## States`, `## Keys`) if it exists, else the defaults per rung in
`${CLAUDE_SKILL_DIR}/../ux-design/references/targets.md`. Artifact contract:
`${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`.

## Pick the loop

The rung comes from design.md `## Target` (else: browser UI → web, `/dev/tty` drawing →
terminal, window → native GUI, none → CLI). CLI → `make test` is enough; stop. Each loop
runs at most 5 iterations, never asks the user between iterations, and fixes code until
the gates pass.

## Web loop

Uses the `playwright` MCP server shipped with this plugin (tools `browser_*`). Need a URL:
if no dev server runs, start the project's dev command in the background and wait for its
port. If the Playwright tools are unavailable, say so and stop — never claim visual
verification without a browser.

Default gates:
- 0 console errors.
- 0 axe violations of impact `critical`, `serious` or `moderate`.
- Every interactive element ≥44×44 px.
- Every control has an accessible name and role (from `browser_snapshot`).
- No horizontal scroll at 375 px; layout adapts at 768 and 1280.
- Each designed state (empty, loading, error, success) reachable and rendered; no
  placeholder copy (lorem ipsum, TODO).

Steps:
1. `browser_navigate` to the URL. For each width 375, 768, 1280: `browser_resize`
   (heights 812, 1024, 800) → `browser_take_screenshot` + `browser_snapshot`. Look at
   each screenshot: overflow, overlap, clipped text, missing elements vs design.md.
2. `browser_console_messages` — any error is a failure.
3. `browser_evaluate` the axe scan:
   ```js
   async () => {
     if (!window.axe) {
       const s = document.createElement('script');
       s.src = 'https://cdn.jsdelivr.net/npm/axe-core/axe.min.js';
       document.head.appendChild(s);
       await new Promise((ok, err) => { s.onload = ok; s.onerror = err; });
     }
     const r = await axe.run();
     return r.violations.map(v => ({ id: v.id, impact: v.impact,
       nodes: v.nodes.map(n => n.target.join(' ')) }));
   }
   ```
4. `browser_evaluate` the touch-target check at 375 px:
   ```js
   () => [...document.querySelectorAll('button,a,input,select,textarea,[role=button]')]
     .map(e => [e, e.getBoundingClientRect()])
     .filter(([, r]) => r.width && (r.width < 44 || r.height < 44))
     .map(([e, r]) => `${e.tagName}${e.id ? '#' + e.id : ''} ${r.width}x${r.height}`)
   ```
5. States: drive the UI (`browser_click`, `browser_type`, `browser_press_key` Tab/Enter)
   to reach each state; check keyboard focus order is logical and visible.
6. All gates pass → report and stop. Otherwise fix the code, then repeat from step 1.

Typical fixes: missing name → `aria-label` or `<label for>`; low contrast → change the
token, not the one element; small target → `min-height/min-width: 44px` or padding;
mobile overflow → find the fixed width, don't hide overflow; CLS → explicit image and
container dimensions; missing focus → `:focus-visible` style.

## Terminal loop

`dl-tui [-s COLSxROWS] CMD [STEP...]` runs CMD in a private headless tmux; steps are
`key:NAME` (tmux key names: `Down`, `Enter`, `Escape`, `C-c`, `BSpace`), `text:STRING`,
`resize:COLSxROWS`, `wait:MS` and `snap`. Each `snap`, and the end, prints the screen
followed by `-- COLSxROWS running`, `-- COLSxROWS exit N` or `-- COLSxROWS signal N`
(killed by a signal: a crash, e.g. `signal 6` for a Rust panic). Exit 2 on usage or tmux
errors.

1. `"${CLAUDE_SKILL_DIR}/../ux-design/scripts/dl-contrast" <token files>` must be silent.
2. For each state in design.md `## States`, write a step script reaching it. Run it at
   `-s 80x24` and `-s 40x12`, ending with `snap`, e.g.
   ```
   "${CLAUDE_SKILL_DIR}/scripts/dl-tui" -s 40x12 'printf "alpha\nbeta\n" | ./pick > /tmp/out' text:al snap key:Enter
   ```
   Compare each block with the wireframes: overlap, truncation, missing elements.
3. Resize: append `resize:20x5 wait:3000 snap` → footer still `running`, no garbage.
   `exit 134`, `signal N` or a shell `rc=134` line is a crash. The wait matters: while a
   core dump is written (systemd-coredump) the pane still reads `running` and shows the
   last frame.
4. NO_COLOR: rerun one script with `NO_COLOR=1` in CMD → the selection is still visible.
5. Restore: CMD ends with `; stty -a | grep -c ' icanon'` → the final block shows `1` and
   `exit 0`.
6. Stdout purity: CMD redirects stdout to a file → the file holds only the result.

Typical fixes: garbage after resize → redraw every row on a size change; selection lost
under NO_COLOR → reverse video or a `>` marker; mode not restored → restore in Drop and
in a panic hook (`panic = "abort"` skips Drop), also on signals; UI in the stdout file →
draw on `/dev/tty`; abort when the terminal hangs up → no `eprintln!`/`println!` on the
error path (they panic when the write fails), use `let _ = writeln!(…)`.

## Native GUI

- dl-contrast on the token files.
- The program's keyboard tests in `make test`.
- A screenshot only when `DISPLAY` is set and `import` is on PATH
  (`import -window root /tmp/ui.png`, then read the image).
- Otherwise the visual gates are NOT VERIFIED; say so in the report.

## Report

Web:
```
UI VERIFY: PASS|FAIL after N iteration(s) — <url>
375: <ok | issues>   768: <…>   1280: <…>
console errors: N   axe: N (critical a, serious b, moderate c)   small targets: N
states checked: empty, loading, error, success
FIXED: <file:line — what>
REMAINING: <gate — element — why not fixed>
```

Terminal:
```
UI VERIFY: PASS|FAIL after N iteration(s) — <command>
80x24: <ok | issues>   40x12: <…>   20x5: <…>
NO_COLOR: ok|fail   restore: ok|fail   stdout: ok|fail   contrast: N violations
states checked: <list>
FIXED: <file:line — what>
REMAINING: <gate — element — why not fixed>
```

After 5 iterations with failures, stop and report the REMAINING list; don't keep looping.
