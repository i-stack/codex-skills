<!-- last-verified: 2026-07 -->
# plan-grill Agent Invocation Guide

> This is an English mirror of the authoritative Chinese `AGENT-BRIEF.md`.
> In case of discrepancies, the Chinese source takes precedence.

## One-line Description

For every non-trivial build/modify/solution request, first perform requirements clarity gate; only automatically grill question-by-question when blocking decisions exist that cannot be found and would substantially alter outcomes. Do not execute before confirmation; produce PLAN.md for cross-model-review relay.

## When to Invoke

- **Conditional auto**: Non-trivial requests still have blocking decisions that cannot be found from code/context
- **User forced trigger**: User says `【盘问】` / "grill me" / "lock plan" / "grill my solution"
- **Relay from problem-analysis**: After problem-analysis completes, problem is clear, need to lock implementation solution

## Key Behaviors

1. Read `SKILL.md` + full text of `references/plan_grill.md`.
2. First execute requirements clarity gate (PG-000); history recall is handled by the global `historical-recall` skill, so this skill no longer recalls inline (PG-006 only declares the delegation).
3. One question at a time (PG-001), each question with recommended answer + reasoning (PG-002).
4. For questions answerable by checking code, check directly, don't ask user (PG-003).
5. When PG-003 involves cross-file/cross-module dependency analysis and platform engineer is loaded, pause grilling, delegate quick architecture analysis and write `architecture-analysis.md` path back to PLAN.md (PG-005).
6. After the decision tree is resolved and the user confirms, invoke `scripts/write_plan.py` to write the complete plan to `.plan-reviews/<plan-slug>/PLAN.md` under the current workspace root (PG-004). Claim it is locked only when the script exits zero.
7. Do not execute plan before confirmation.

## When Not to Invoke

- Trivial changes (typos, formatting, single-point syntax)
- Fact queries, explanations, translations, reviews, or diagnosis-only-without-fix
- Pure execution tasks where acceptance criteria and implementation path are both clear
- User explicitly says "just do it" / "don't grill"
- problem-analysis not completed (problem itself not reviewed)
