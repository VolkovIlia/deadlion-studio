---
name: ux-design
description: Designs the user interface of a program at the lowest rung that serves the job — CLI, filter (dmenu/fzf style), terminal UI, native GUI or web — with flows, states, a key map, design tokens kept in config.def and numeric gates per rung, so every UI works alone and embeds; avoids generic AI-looking UI. Includes the dl-contrast checker. Writes design.md. Use when building or changing any user interface, screen, TUI, GUI, component or visual style.
---

# UX design

Output: `.dev-docs/features/<slug>/design.md`, following the contract in
`${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`. Read `product.md` first if it
exists; design nothing that its Scope cuts.

## Gates

Gates per rung: `${CLAUDE_SKILL_DIR}/references/targets.md`; copy the chosen rung's table
into design.md `## Accessibility gates`. WCAG detail: `${CLAUDE_SKILL_DIR}/references/wcag.md`.

## Procedure

0. **Target.** Choose the rung via targets.md; record the Target line and the embedding
   modes from `${CLAUDE_SKILL_DIR}/../suckless-code/references/conventions.md`. Above the
   CLI rung, the UI is a front end over an engine that runs headless.
1. **Ground in the subject.** Name the product's domain, its users and the mood the
   domain earns (a ledger is calm and dense; a kids' game is loud). Derive palette, type
   and density from that, not from current SaaS fashion.
2. **Flows.** List each user job as a numbered path: entry → steps → exit. Cut steps that
   don't serve the job.
3. **Token plan before code.**
   - 4–6 named hex colours (background, surface, text, muted, accent, danger) with
     contrast ratios checked against their backgrounds; a type or attribute scale; a
     spacing scale on a 4 or 8 px grid, or the cell grid.
   - C/Rust programs keep tokens as constants in `config.def.h`/`config.def.rs` (dwm
     colour-scheme style); web keeps CSS custom properties in the master token file.
   - Every fg/bg pair gets a `dl-contrast: FG BG [MIN]` comment line next to the tokens.
   - Run `${CLAUDE_SKILL_DIR}/scripts/dl-contrast <file>` until it is silent.
4. **ASCII wireframes** for each screen. Terminal: 80×24, then 40×12. GUI: 1280×800,
   then 640×400. Web: 375 first. Mark the primary action.
5. **Keys.** A table mapping every action to a key (web: tab order and shortcuts).
6. **Review the plan** against the brief and `${CLAUDE_SKILL_DIR}/references/anti-patterns.md`.
   Any hit → change the plan, not the excuse.
7. **One bold choice.** Pick a single distinctive element (a typeface, an accent, a layout
   move) and keep everything else quiet. Write the choice and its reason in design.md.
8. **Every state.** For each screen design empty (first use and no results), loading
   (skeleton, never blank), error (what failed + how to recover) and success.
9. **Copy.** Real text, not lorem ipsum. Buttons are verbs; errors say what to do next.
10. Write design.md with `Status: draft`. In the reply, show what the user approves: the
    Target line, the Keys table, the States per screen and the token names with their
    contrast pairs and ratios; then ask the user to approve.

After implementation, run the `ui-verify` skill against the rung's gates.

## Tokens: master + overrides

- One master token file is the single source of base values (colour, type, spacing):
  `config.def.*` for C/Rust programs, the master CSS file for the web.
- An override file holds only the keys that differ for one page or feature (e.g. denser
  dashboard spacing), using the same key paths; the build merges master ← override.
- Global or permanent changes go in master, never in an override. Never copy master
  values into overrides.

## Checker: dl-contrast
```
${CLAUDE_SKILL_DIR}/scripts/dl-contrast [PATH...]   # default PATH is .
```
- Directive: a line that starts, after an optional comment leader (`//`, `/*`, `<!--`,
  `#`, `;`, `*`, `%`, `-`), with `dl-contrast:` then FG, BG and an optional MIN
  (default 4.5). The marker mid-line (prose, messages) is ignored. Only files holding
  the marker are parsed; the last definition of a token name wins.
- Token forms: `pub const FG: &str = "#rrggbb";`, `static const char fg[] = "#rrggbb";`,
  `--fg: #rgb;` (several per line), `FG='#rrggbb'`, `"fg": "#rrggbb"`. In design.md
  write tokens as `fg: #rrggbb` lines so they are checked too.
- Output, one line per directive, silent when clean:
  ```
  path:LINE: contrast FG/BG is 4.48:1 (min 4.5)
  path:LINE: unknown token NAME
  ```
- Exit: `0` clean, `1` violations, `2` usage/IO error (stderr, prefixed `dl-contrast:`).
- The plugin's PostToolUse hook runs `dl-contrast --hook` after every Write/Edit and
  reports violations back. `DL_HOOKS=0` disables hook mode.

## Challenge the request

When a requirement breaks a gate, don't silently comply. Name the gate and standard,
the impact, and propose an alternative (e.g. "32 px button fails 44 px target → 48 px,
or extend hit area with padding"). Record it in design.md under Accessibility gates.

Before each screen ask: does it serve the job; can an element be removed; can it be
chunked or progressively disclosed; how many decisions does the user make here.

## design.md sections

`## Target`, `## Flows`, `## Screens` (ASCII wireframes at the rung's sizes), `## States`
(empty/loading/error/success per screen), `## Tokens` (4–6 named hex colours with
`dl-contrast:` pairs, type or attribute scale, spacing scale or cell grid), `## Keys`,
`## Accessibility gates` (the rung's table from targets.md plus feature gates), `## Copy`.
