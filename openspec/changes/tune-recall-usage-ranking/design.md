## Context

Uso ya se registra al servir recall/context; `recall_usage_weight` default 0.0. Existe `evaluation.py` para ranking. Falta contrato de dataset + experimento antes de default > 0.

## Goals / Non-Goals

**Goals:**
- Dataset versionado + informe MRR/recall@k/misses.
- Voto de uso en fusión con default 0.0 y activación documentada.
- Capar el voto para no superar una señal primaria de recuperación.

**Non-Goals:**
- Cambiar ciclo de adherencia, telemetría con contenido, grafo, o higiene automática.
- Entrenar un ranker ML.

## Decisions

- **Mismo mecanismo que importancia**: competition-ranking / peso acotado ≤ 1.0, simétrico a `recall_importance_weight`, no un score absoluto de `recall_count`.
- **Default producción 0.0**: cualquier peso > 0 es configuración explícita tras comparar dataset.
- **Separación de evaluadores**: ranking ≠ workflow checkpoints (ya es la intención del código).

## Risks / Trade-offs

- [Rich-get-richer] → Default 0; peso pequeño; evaluar misses, no sólo MRR.
- [Dataset sintético poco realista] → Etiquetar tags (typo, exact, semantic) y expandir con fallos reales anonimizados sólo si el operador aporta fixtures sin PII.

## Migration Plan

1. Cerrar dataset + baseline peso 0.
2. Experimentar pesos candidatos; documentar elección.
3. Opcionalmente publicar default > 0 en un change posterior si el experimento lo justifica; este change NO exige cambiar el default.

## Open Questions

- ¿Este change deja el default en 0 para siempre y sólo documenta el knob, o incluye un default > 0 candidato? Default de diseño: **knob + experimento; default permanece 0** hasta un follow-up explícito.
