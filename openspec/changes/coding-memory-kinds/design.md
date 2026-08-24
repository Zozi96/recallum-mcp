## Context

Category is a closed four-value check constraint. Tencent levels (L0–L3) would duplicate profile vs row and violate the no-conversation rule. See proposal.md.

## Goals / Non-Goals

**Goals:**
- Second orthogonal dimension for coding retrieval strategies.
- Force TTL on `todo` so Recallum does not become a backlog.

**Non-Goals:**
- New categories.
- RAW/CORE levels.
- Auto-classification via LLM.

## Decisions

- **Column `kind` nullable text + check constraint**, not a second table. NULL means unclassified — required so old rows and casual captures stay valid.
- **Do not widen `category`**: agents already mis-file; adding failure/solution there would break every filter and the profile static rule (preference/constraint). Kind is the coding facet; category stays the lifecycle facet.
- **Strategy interaction**: `recall-token-budget` may prefer `kind=failure` then `solution` for debugging when the column exists; this change only supplies the field and filter.
- **TODO**: reuse `expires_at`. No `todo` status machine.

## Risks / Trade-offs

- [Agents ignore kind] → Skill documents the map; retrieval still works on category+text.
- [Kind/category mismatch, e.g. preference+failure] → Allowed; similar-advisory is category-blind already. Do not add a matrix of forbidden pairs (over-engineering).
- [TODO pile-up] → TTL required; expired rows are not served.

## Migration Plan

1. Alembic nullable column + check.
2. Schemas and validation.
3. Plugin skill: map architecture/conventions/failures onto kind without abandoning category.

## Open Questions

Ninguna.
