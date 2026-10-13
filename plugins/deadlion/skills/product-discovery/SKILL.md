---
name: product-discovery
description: "Product discovery: frames the problem, users and jobs-to-be-done, tags every claim with an evidence level, finds the riskiest assumption and cuts scope to the smallest valuable release. Writes product.md. Use when a feature or product idea has unclear value, users, scope or success criteria, or when the user asks for requirements, an MVP or a PRD."
argument-hint: "<idea>"
---

# Product discovery

Output: `.dev-docs/features/<slug>/product.md` per
`${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`. Runs in the main session
because it needs the user.

## Evidence levels

Tag every factual claim; an untagged claim is a defect.

- `[A]` external source: market data, research, competitor docs (link or name it)
- `[B]` experiment: prototype, pilot, interview result
- `[C]` internal: analytics, SME, the user's own knowledge
- `[D]` assumption: needs validation

Never invent facts. Missing evidence does not block progress: tag it `[D]` and move on.

## Step 0: read before asking

Before the first question, read what already exists and do not ask what it answers:
`CLAUDE.md`, `README*`, `ls .dev-docs/` (features, research), any existing
`.dev-docs/features/*/product.md`, and a top-level scan of the source tree.
Summarize in ≤5 lines: what the product is, what exists, what is already decided.
Then ask contextual questions ("README says X; does this feature extend Y or add a new direction?").

## Asking

- Use AskUserQuestion, ≤4 questions per call, 2–4 options each, an "other" path always open.
- Ask only what changes the artifact. Prefer options with concrete numbers over open text.
- Question templates by block (Business, Users, Value, Delivery): `${CLAUDE_SKILL_DIR}/references/question-bank.md`. Adapt them to the idea; skip blocks already answered by Step 0.
- Do web research yourself for `[A]` claims (competitors, alternatives, market) or dispatch the `researcher` agent for larger questions.

## Procedure

1. **Problem.** Restate the goal, constraints (time, budget, compliance) and the target outcome in ≤5 lines. Start an assumption log.
2. **Users & jobs.** Answer the five discovery questions: who (segment), which job-to-be-done, current alternatives, their shortcomings, why this is better. Format jobs as "When <situation>, I want <motivation>, so I can <outcome>."
3. **Opportunities.** Outcome → opportunities → candidate solutions, ranked by impact. Contradiction scan: if a candidate needs X and not-X (simple and powerful, free and profitable), state it and try to separate it in time, space or condition before accepting a compromise.
4. **Hypothesis.** "For <segment> there is a need for <X> because <Y>; this will lead to <metric change>." Tag it.
5. **Clarity scan.** Check the 10 categories below. Score each ambiguity Impact (1–5) × Uncertainty (1–5); ask about the top ≤4 by score in one AskUserQuestion call. Repeat until the gate passes.
6. **Riskiest assumption.** See below.
7. **Scope by subtraction.** See below.
8. **Acceptance criteria.** Given/When/Then for each in-scope capability, including at least one error or edge case per capability.
9. **Success metric.** One metric, baseline, target, time window. Name the North Star if the product has one.
10. **Write `product.md`** with `Status: draft`, show the path and a ≤10-line summary, and ask for approval.

### Clarity scan categories

| # | Category | Check |
|---|---|---|
| 1 | Functional scope | Bounded? No open-ended "and more"? |
| 2 | Domain & data | Entities and relations named? |
| 3 | Interaction flow | Journeys complete, no missing states? |
| 4 | Non-functional | Performance/reliability/security quantified, not "fast"? |
| 5 | Integrations | External systems and versions listed? |
| 6 | Edge cases | Failure behaviour defined? |
| 7 | Constraints | Limits explicit, exclusions justified? |
| 8 | Terminology | One name per concept? |
| 9 | Completion | Every requirement has a measurable "done"? |
| 10 | Unknowns | No TBD; every `[D]` has a mitigation? |

Gate before writing: all 10 scanned; no ambiguity with Impact ≥4 and Uncertainty ≥4;
≤3 unmitigated `[D]` assumptions; terminology consistent.

## Riskiest assumption

1. List assumptions the hypothesis depends on. Score each Impact (1–3: if wrong, does the idea fail?) × Uncertainty (1–3: how little evidence?). Pick the highest; ties → the cheapest to test.
2. Choose the cheapest test that can falsify it within 24–72 h: interviews (5–10), review mining (100+ reviews), survey (50+), competitor analysis, fake-door or prototype.
3. **Fix the success threshold before the test**, as a number ("≥60% of 7 interviewees describe the pain unprompted"). Never adjust it after seeing results.
4. Decision rule: threshold met → PROCEED (upgrade the tag to `[B]` or `[A]`); not met → PIVOT.
5. On PIVOT, write: the result vs. the threshold, why it failed (findings with counts), 2–3 alternative hypotheses (different segment, integrate instead of replace, adjacent pain), and the questions to ask the user. Do not proceed to scope.
6. If the test has not run yet, record it as planned with `Decision: pending` and say that build work is a bet on a `[D]`.

## Scope by subtraction

Start from everything mentioned, then remove. For each candidate capability ask:
is the hypothesis still testable without it? If yes, cut it.

- Rank survivors by RICE = Reach × Impact (0.25/0.5/1/2/3) × Confidence (0–100%) / Effort (person-weeks); show the numbers.
- `In`: the smallest set that delivers the job end-to-end and measures the success metric.
- `Cut`: every removed item with a one-line reason ("not needed to test H", "Won't: v2", "manual workaround: CSV export").
- Prefer manual, existing-tool or no-code substitutes for anything not core to the job.
- The cut list is at least as long as the in list for a first release; if not, say why.

## product.md sections

Exactly, in order: `## Problem`, `## Users & Jobs`, `## Evidence`,
`## Riskiest assumption` (impact×uncertainty, test, threshold, PROCEED/PIVOT/pending),
`## Scope` (`### In`, `### Cut`), `## Acceptance criteria`, `## Success metric`.
Optional after them: `## Non-functional` (performance, reliability, security, privacy,
accessibility, localization — only with numbers), `## Risks` (likelihood L/M/H ×
impact L/M/H, mitigation, linked assumption), `## Open questions`.

Reply in the user's language.
