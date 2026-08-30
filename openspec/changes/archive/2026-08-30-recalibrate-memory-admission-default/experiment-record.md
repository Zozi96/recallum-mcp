# Baseline ranking freeze — densify `relevance`

**Date:** 2026-08-30
**Freeze file:** `openspec/changes/recalibrate-memory-admission-default/baseline-topk.json`
**Do not regenerate** from `/tmp` or a new throwaway run. This record describes the on-disk freeze only.

## Stack

- PostgreSQL 17 + pgvector (`pgvector/pg17`), throwaway (not production)
- Embeddings: Ollama `embeddinggemma:300m`
- `recall_vector_min_similarity` (**Vmin**) **unset** (`None`)
- `k=10` (production recall default)
- Fusion defaults (importance 0.5, trigram 0.5, usage 0.0, freshness 0.0)

Source string in the freeze: `2026-08-30 throwaway pgvector/pg17 + Ollama embeddinggemma:300m, Vmin unset, k=10, fusion defaults`.

## Per-query returned keys (k=10)

Compact list from `baseline-topk.json` `returned` (order is rank):

| tag | query | returned |
| --- | --- | --- |
| semantic | which package manager should I use | pnpm, pnpm-ci, yarn-legacy, en-review-hotfix, db, deploy, tests, es-docs, fix-branch-retired, deploy-volume |
| semantic | where do production releases happen | en-retention-metrics, en-staging-prod-snap, en-oncall-weekend, tz, en-staging, deploy, tests, es-docs-runbooks, deploy-volume, auth-rotate |
| semantic | how are credentials protected | auth, auth-rotate, sessionprovider, tz, auth-v1-plaintext, tests, en-retention, deploy, en-review, feat-jira |
| semantic | what produces the embedding vectors | ollama, ollama-dims, openai-embed-retired, db, deploy, mysql-analytics, pnpm, deploy-volume, en-staging-prod-snap, en-staging |
| semantic | time zone handling rules | tz-warehouse-local, en-review-history, tz, auth-rotate, tz-ui, en-review, session-idle, sessionprovider, en-staging-window, es-soporte-tz |
| exact | pgvector | db, mysql-analytics, ollama-dims, es-docs-tu, deploy-volume, pnpm, ollama, tz, deploy, auth-rotate |
| exact | ruff line length | lint, ruff-ci, auth-rotate, en-retention, en-review, yarn-legacy, pnpm, db, en-review-drafts, en-retention-metrics |
| exact | feat branch naming | branch, feat-jira, fix-branch-retired, en-review, pnpm, db, deploy, tests, ruff-ci, yarn-legacy |
| typo | postgersql database | db, tz, deploy-volume, auth-rotate, mysql-analytics, pnpm, en-staging, en-retention, tz-warehouse-local, tests |
| typo | pnmp packages | pnpm, yarn-legacy, deploy, pnpm-ci, tests, db, deploy-volume, mysql-analytics, en-review, pnpm-history |
| identifier | SessionProvider | session-global-neg, sessionprovider, session-idle, pnpm, tz, auth-rotate, deploy, tests, deploy-volume, pnpm-ci |
| identifier | for_user transaction | sessionprovider, session-idle, session-global-neg, tz-ui, tz, auth-rotate, tests, feat-jira, en-review, auth |
| es-es | respaldos nocturnos de la base | es-backup, es-backup-history, es-backup-logs, es-soporte-status, es-facturas, es-backup-window, es-docs, es-docs-tu, es-soporte-chat, es-soporte |
| es-es | en qué idioma va la documentación | es-docs, es-docs-history, es-docs-tu, es-docs-runbooks, es-soporte-tz, en-retention, db, tz, es-soporte-status, en-staging |
| es-es | cuándo se emiten las facturas | es-facturas, es-facturas-neto, es-facturas-proforma, es-backup, es-soporte, es-backup-logs, es-soporte-tz, es-soporte-chat, es-docs, es-backup-window |
| es-es | hasta qué hora atienden los clientes | es-soporte, es-soporte-status, es-soporte-tz, es-backup, es-backup-logs, es-docs-runbooks, es-facturas-proforma, tz, en-oncall, auth-rotate |
| es-en | nightly database backup schedule | en-staging, en-staging-prod-snap, db, es-backup, auth-rotate, tz, en-retention, es-backup-logs, deploy-volume, en-oncall |
| es-en | what language is the user documentation written in | tz-ui, sessionprovider, session-global-neg, es-docs, session-idle, db, es-docs-runbooks, tz, es-docs-tu, mysql-analytics |
| es-en | when are invoices issued | es-facturas, tz, auth-rotate, es-facturas-neto, en-retention, es-facturas-proforma, en-oncall, en-staging-prod-snap, en-retention-export, tz-warehouse-local |
| es-en | when does customer support close | es-soporte, tz, es-soporte-chat, en-oncall, auth-rotate, en-staging-window, es-soporte-status, es-docs, en-review, es-soporte-tz |
| en-en | when does the staging data get wiped | en-staging, en-staging-prod-snap, en-staging-window, en-staging-history, tz, auth-rotate, en-retention, es-backup, deploy, deploy-volume |
| en-en | who is on call this week | en-oncall-weekend, en-oncall, en-oncall-handoff, sessionprovider, en-oncall-history, en-staging, en-staging-window, auth-rotate, openai-embed-retired, tz |
| en-en | how many approvals does a merge need | en-review, en-review-drafts, en-review-hotfix, en-review-history, auth-rotate, tests, pnpm, ruff-ci, mysql-analytics, feat-jira |
| en-en | how long are audit logs kept | en-retention, en-retention-export, en-retention-metrics, en-retention-legal, es-backup-logs, auth-rotate, tz, auth, db, en-staging-prod-snap |
| en-es | cuándo se borran los datos del entorno de pruebas | es-backup, es-docs, es-docs-tu, es-docs-history, es-backup-logs, es-facturas, es-backup-history, es-soporte-tz, es-soporte-chat, en-staging |
| en-es | quién está de guardia esta semana | es-facturas, es-soporte-status, es-backup-history, en-oncall, auth-rotate, en-staging-window, es-backup, en-oncall-weekend, es-backup-logs, db |
| en-es | cuántas aprobaciones hacen falta para integrar un cambio | en-review, auth-rotate, en-review-drafts, es-backup-history, ruff-ci, en-retention, en-review-history, en-retention-export, tests, en-review-hotfix |
| en-es | cuánto tiempo se conservan los registros de auditoría | es-backup, es-backup-logs, es-facturas, es-facturas-neto, es-docs, es-soporte-status, es-docs-history, es-backup-history, es-soporte-tz, es-soporte |

Densification (task 2.2) adds each missing `returned` key to that query's `relevance` as grade **0** (off-theme fill). Existing 1/2/3 grades are unchanged. Keys not served and not already judged are not added.

## Recalibration matrix (2026-08-30)

Same throwaway recipe, densified `scripts/eval_dataset.json`, user
`eval-recalibrate@example.com`. Baseline `unj@5` is **0.00** (freeze coverage).
`exp0@5` equals `irr@5` at Vmin unset because every served top-5 key is now
declared.

Guards unchanged from the sibling change: lowest Vmin that does not reduce
`nDCG@5` or `essential-recall@3` globally or on `es-es`/`es-en`/`en-en`/`en-es`,
reduces `irr@5`, and does not reduce useful-token density.

| Vmin | nDCG@5 | ess@3 | irr@5 | exp0@5 | unj@5 | useful-tok | es-es nDCG/ess | es-en nDCG/ess | en-en nDCG/ess | en-es nDCG/ess | guards |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| off | 0.74 | 0.79 | 0.64 | 0.64 | 0.00 | 0.20 | 0.88 / 1.00 | 0.61 / 0.50 | 0.90 / 1.00 | 0.31 / 0.25 | baseline |
| 0.25 | 0.76 | 0.82 | 0.64 | 0.64 | 0.00 | 0.21 | 0.91 / 1.00 | 0.61 / 0.50 | 0.90 / 1.00 | 0.35 / 0.50 | fail: irr@5 unchanged |
| 0.35 | 0.80 | 0.89 | 0.59 | 0.57 | 0.01 | 0.28 | 0.91 / 1.00 | 0.66 / 0.75 | **0.89** / 1.00 | 0.68 / 0.75 | fail: en-en nDCG 0.90→0.89 |
| 0.45 | 0.80 | 0.93 | 0.47 | 0.45 | 0.02 | 0.45 | 0.88 / 1.00 | 0.77 / 1.00 | **0.89** / 1.00 | 0.64 / 0.75 | fail: en-en nDCG 0.90→0.89 |
| 0.55 | 0.75 | 0.89 | 0.46 | 0.43 | 0.03 | 0.45 | **0.83** / 1.00 | 0.80 / 1.00 | 0.97 / 1.00 | 0.57 / 0.75 | fail: es-es nDCG 0.88→0.83 |
| 0.65 | **0.56** | **0.68** | 0.51 | 0.47 | 0.04 | 0.39 | 0.91 / 1.00 | **0.37** / 0.50 | 0.89 / 1.00 | **0.19** / 0.25 | fail: overall + mixed-language |
| 0.75 | **0.50** | **0.57** | 0.52 | 0.49 | 0.04 | 0.37 | **0.73** / **0.75** | **0.19** / 0.25 | 0.89 / 1.00 | **0.00** / **0.00** | fail: collapse |

**Second block:** no candidate passes. Production default stays `None`. FTS/trigram
untouched. `unj@5` > 0 at Vmin ≥ 0.35 is ranking drift vs the freeze (new keys
enter the top-5), not a dataset hole at baseline.
