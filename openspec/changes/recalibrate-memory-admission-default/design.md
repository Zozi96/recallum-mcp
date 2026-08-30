## Context

See `proposal.md`. Sibling change `improve-memory-context-precision` already shipped the vector SQL floor (default `None`), graded metrics, and the 2026-08-29/30 experiment record. FTS remains OR-any-lexeme (`_or_tsquery`); that contract stays. Calibration failed because `irr@5` is mostly undeclared fill, not because the floor was unimplemented.

Reuse `recallum-admin eval`, `scripts/eval_dataset.json`, and throwaway Postgres + Ollama. Do not add a second evaluator.

## Goals / Non-Goals

**Goals:**

- Make the existing guards informative: most top-5 grade-0 slots should be judged keys, not auto-0 leftovers.
- Expose explicit-zero vs unjudged split in the same report so a future matrix cannot confuse fill-to-limit with hard negatives.
- Pick a production Vmin only if the same guards pass on the denser dataset.

**Non-Goals:**

- Changing FTS or trigram predicates (including AND / min-lexeme-count).
- Redefining `irrelevant-rate@5`.
- LLM reranking, new vector stores, fusion weight default changes, MCP schema changes.
- Enabling a Vmin by intuition if guards fail again.

## Decisions

### 1. Densify judgments from a frozen baseline ranking, not from intuition

Run one baseline `recall` (Vmin unset, `k=10`) on the throwaway stack and add `relevance` entries for every served key plus the existing hard negatives. Grades 1–3 stay reserved for useful context; new entries that are off-theme are 0. Do not judge the entire 59-row corpus for every query.

Alternative discarded: treat undeclared as "not irr". That retcons the failed matrix and hides fill-to-limit, which is the failure mode the original change exists to stop.

### 2. Add rates; do not replace `irr@5`

`explicit-zero-rate@5` and `unjudged-rate@5` are extra lines on the graded report. Selection still uses shipped `irr@5` plus nDCG/ess/useful-tok and the four language tags. The new rates are diagnostics: if `irr@5` drops only because unjudged fill disappeared while explicit-zero stays flat, that is not a precision win on hard negatives, but it *is* a valid fill-to-limit win under the original guards.

Alternative discarded: switch the guard to explicit-zero-only. That would let Vmin pass while still filling the limit with unjudged neighbours.

### 3. Same stack, same selection rule, still no FTS AND

Matrix, model (`embeddinggemma:300m`), fusion defaults, and "lowest passing Vmin else stay `None`" stay as in `improve-memory-context-precision`. If none pass, document the second block; do not AND the tsquery. Rank-side FTS (`ts_rank_cd`) already exists; this change does not retune it.

### 4. Archive both changes together

`improve-memory-context-precision` remains unarchived until this change either enables a default or records that the denser dataset still cannot. Then archive both so main specs pick up graded eval, the floor, and the dense-judgment contract in one sync.

## Risks / Trade-offs

- [Densifying from one baseline run overfits that ranking] → Freeze the baseline dump in the experiment record; new keys must be thematic 0/1/2/3, not "whatever came back gets a 3".
- [Operators confuse the three irr-like rates] → Keep `irr@5` first; label the others as diagnostics in the report.
- [Guards fail again] → Default stays `None`; do not touch FTS. A later change would need ranking or a different model, not this one.
- [Two active changes both MODIFY Evaluación] → Apply this one after the sibling's code is on the branch; the delta here is the full post-sibling requirement text.

## Migration Plan

1. Land sibling code (floor + graded eval) with default `None`.
2. Extend evaluator report and unit tests for the two diagnostic rates.
3. Densify the dataset from a recorded baseline ranking; unit-test that unjudged top-k keys fail a check (or that the dataset fixture has none).
4. Re-run the Vmin matrix on throwaway Postgres; write the record.
5. Set the default only if guards pass; pin with the existing unit test pattern.
6. Archive both OpenSpec changes. Rollback of a production floor is still "unset the limit".

## Open Questions

None. The numeric Vmin remains the output of the experiment, as in the sibling change.
