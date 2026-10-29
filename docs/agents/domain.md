# Domain docs

## Before exploring

- Read root `GLOSSARY.md` for domain vocabulary.
- Read relevant decisions in `docs/adr/`.
- If either is absent, proceed silently; domain-modeling creates documentation lazily when terms or decisions are resolved.

## Layout

This is a single-context repository: one root `GLOSSARY.md` and shared `docs/adr/`.
The glossary was migrated from `CONTEXT.md`; archived OpenSpec records retain their historical filenames.

## Consumer rules

Use glossary terms in issue titles, proposals, hypotheses, and tests.
If a needed concept is missing, reconsider the terminology or note a gap for domain-modeling.
Surface contradictions with existing ADRs explicitly rather than silently overriding them.
