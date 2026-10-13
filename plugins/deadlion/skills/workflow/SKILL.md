---
name: workflow
description: "Runs the deadlion pipeline (product → design → decompose → architecture → plan → build → review → verify) through plain-text artifacts in .dev-docs/. Use when the user starts a new product, system, feature or multi-step change, or asks what to do next."
argument-hint: "<idea or feature>"
---

# Feature workflow

Stages are independent skills connected by files. The contract (layout, header,
required sections) is `${CLAUDE_SKILL_DIR}/references/artifacts.md`; read it before
writing any artifact.

## Stages

| # | Stage | Skill | Writes |
|---|---|---|---|
| 1 | Product | `/deadlion:product-discovery` | `product.md` |
| 2 | Design (UI only) | `/deadlion:ux-design` | `design.md` |
| 3 | Decompose (multi-project only) | `/deadlion:decompose` | `.dev-docs/system.md` |
| 4 | Architecture | `/deadlion:unix-design` | `arch.md` |
| 5 | Plan | `/deadlion:write-plan` | `plan.md` |
| 6 | Build | `/deadlion:build <slug>` | code, flips `plan.md` checkboxes |
| 7 | UI check (UI only) | `/deadlion:ui-verify` | — (fixes until design.md gates pass) |
| 8 | Review | `/deadlion:review` | `review.md` |
| 9 | Verify | `/deadlion:verify` | — (VERIFIED / NOT VERIFIED report) |
| 10 | Release (on request) | `/deadlion:release <dir> <version>` | tarball, .sha256, tag |

Commits happen only on user request via `/deadlion:commit`.

## Procedure

1. Pick `<slug>`: kebab-case from the argument (`notes app` → `notes-app`). If a matching dir already exists in `.dev-docs/features/`, reuse it.
2. Read state: `ls .dev-docs/features/<slug>/ 2>/dev/null` and the first two lines of each file, plus the first two lines of `.dev-docs/system.md`. These are the only state; never keep state elsewhere.
3. Choose the stages with the scale rules below. Tell the user the chosen route in one line.
4. Next stage = first chosen stage whose file is missing (or, for build, `plan.md` still has `- [ ] done`).
5. Gate: before running a stage, check that every input file has `Status: approved`. If one is `draft`, show it (or summarize it, with the path) and ask the user to approve or change it. On approval, edit the line to `Status: approved`. Never self-approve.
6. Run the stage's skill. It writes its file with `Status: draft`.
7. Stop after each artifact-producing stage for approval; continue straight through build → ui-verify → review → verify.

## Scale rules

Apply in order; combine all that match.

- Change touches ≤1 file and no UI → `write-plan` inline (no file needed), then `build`, then `verify`. Skip everything else.
- Value or users are unclear → start at `product-discovery`.
- Value and users are clear → skip `product-discovery`; the request is the input.
- Any UI → include `ux-design`; after build, run `ui-verify`.
- `system.md` missing and any of: ≥3 distinct jobs, >1 process or runtime (daemon + CLI, server + UI), estimated >2000 SLOC, existing code fails `dl-budget` → include `decompose`.
- `system.md` exists and the change adds a sub-project or changes a contract → include `decompose` (it sets system.md back to draft).
- A new component, service or interface → include `unix-design`.
- Everything larger than one file → `write-plan`, `build`, `review`, `verify`.

## Answering "what next?"

Report the listing as a checklist: each stage, its file, and `missing | draft | approved`
(for plan: `k/n tasks done`). Name the single next action and the command to run it.

## Rules

- Skipping a stage is fine; inventing its output is not. Downstream stages fall back to the user's request.
- Upstream file wrong? Go back to that stage and set it to `draft`; do not patch it from a downstream stage.
- Release runs only when the user asks.
- Reply to the user in their language; artifacts are written in the user's language too unless the repo's docs use another.
