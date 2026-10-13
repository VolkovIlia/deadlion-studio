# Artifact contract

Plain-text Markdown files are the pipe between pipeline stages. Every core skill
that reads or writes feature artifacts follows this contract.

## Layout

```
.dev-docs/
  system.md               # decompose (repo-level, shared by all features)
  features/<slug>/        # <slug> is kebab-case, e.g. invoice-reminders
    product.md            # product-discovery
    design.md             # ux-design
    arch.md               # unix-design
    plan.md               # write-plan (checkboxes flipped by build)
    review.md             # review
  research/<topic>.md     # researcher agent
contracts/<name>.md       # decompose (repo root): one file per interface between projects
projects/<name>/          # decompose + scaffold (repo root): one program each
```

`ls .dev-docs/features/<slug>/` plus `.dev-docs/system.md` is the whole pipeline
state. There is no other state file, database or index.

## Header

Every artifact starts with exactly:

```
# <Title>
Status: draft|approved
```

- A skill writes `Status: draft`. Only the user approves; then set `Status: approved`.
- A downstream stage proceeds only when its inputs are `approved`.

## Rules

- A stage reads only the files of earlier stages (order: product → design → system → arch → plan → review). It never edits an upstream file; if an upstream file is wrong, say so and send the user back to that stage.
- Any stage can run alone or be skipped. A missing upstream file is not an error: use the user's request as input instead.
- Required `##` sections appear in the order listed, with these exact headings. Extra sections are allowed after them.
- No placeholders (`TBD`, `TODO`, `...`). Unknowns are written as `[D]` assumptions.

## Files and required sections

| File | Required `##` sections |
|---|---|
| `product.md` | `Problem`; `Users & Jobs`; `Evidence` (every claim tagged `[A]` external source, `[B]` experiment, `[C]` internal/SME, `[D]` assumption); `Riskiest assumption` (impact×uncertainty, test, success threshold fixed before the test, PROCEED/PIVOT); `Scope` (In / Cut); `Acceptance criteria` (Given/When/Then); `Success metric` |
| `design.md` | `Target` (rung, reason, rejected rung, how it runs alone and embeds); `Flows`; `Screens` (ASCII wireframes at the rung's sizes); `States` (empty/loading/error/success per screen); `Tokens` (4–6 named hex colours with `dl-contrast:` pairs, type or attribute scale, spacing scale or cell grid); `Keys` (every action → key; web: tab order and shortcuts); `Accessibility gates` (the rung's table from targets.md plus feature gates); `Copy` |
| `system.md` | `Projects` (table: name, one job, language, input, output, SLOC budget, deps budget, run command); `Contracts` (table: file, version, producer, consumers); `Composition` (mermaid graph, pattern named on each edge); `Build order`; `Decisions` (one `<name>: Language: X — reason; rejected: Y — reason` line per project, then contradictions, one paragraph each); `Jobs` (table: job, done by tool or project, command that runs it alone) |
| `arch.md` | `Components` (table: name, one job, input, output, run command); `Interfaces` (exact CLI/API/file formats); `Data flow` (mermaid); `Mechanism vs policy`; `Threats` (STRIDE table, ≤1 line per row); `Decisions` (one paragraph each) |
| `plan.md` | `Tasks`: each `### T<n>: <title>` with `Files:`, `Project:` (`<name>` or `—`), `Change:`, `Test:`, `Verify:` (exact command), `Depends:`, and a checkbox line `- [ ] done` that `build` flips to `- [x] done` |
| `review.md` | One finding per line: `BLOCKING\|IMPORTANT\|NIT path:line — finding — evidence` |

## Research notes

The researcher agent writes `.dev-docs/research/<topic>.md` (`<topic>` kebab-case)
with the same header. Every claim carries an evidence tag `[A]`–`[D]` and a link
or named source. Feature artifacts cite research files by path.
