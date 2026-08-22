## 1. Guías y prompts

- [x] 1.1 Actualizar prompt `stale-review` con desenlace explícito por ítem
- [x] 1.2 Actualizar prompt `capture-scan` para reconciliar `similar` (merge vs update/forget)
- [x] 1.3 Actualizar skill y recordatorio `SessionStart` con el mismo criterio de higiene

## 2. Self-service

- [x] 2.1 Inventariar endpoints existentes para list/stale/related/reconfirm/update/forget/merge
- [x] 2.2 Añadir o completar lectura de cola stale y vecinos sin embeddings
- [x] 2.3 Reutilizar `MemoryService` para mutaciones de desenlace expuestas por HTTP

## 3. Pruebas

- [x] 3.1 Pruebas contractuales de prompts/skill (texto clave merge-vs-update y desenlace stale)
- [x] 3.2 Pruebas HTTP self-service de stale/related y aislamiento

## 4. Verificación

- [x] 4.1 Suite unitaria/plugin relevante en verde
- [x] 4.2 Confirmar que el servidor sigue sin auto-merge ante similares
