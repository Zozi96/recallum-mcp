## 1. Guías y prompts

- [ ] 1.1 Actualizar prompt `stale-review` con desenlace explícito por ítem
- [ ] 1.2 Actualizar prompt `capture-scan` para reconciliar `similar` (merge vs update/forget)
- [ ] 1.3 Actualizar skill y recordatorio `SessionStart` con el mismo criterio de higiene

## 2. Self-service

- [ ] 2.1 Inventariar endpoints existentes para list/stale/related/reconfirm/update/forget/merge
- [ ] 2.2 Añadir o completar lectura de cola stale y vecinos sin embeddings
- [ ] 2.3 Reutilizar `MemoryService` para mutaciones de desenlace expuestas por HTTP

## 3. Pruebas

- [ ] 3.1 Pruebas contractuales de prompts/skill (texto clave merge-vs-update y desenlace stale)
- [ ] 3.2 Pruebas HTTP self-service de stale/related y aislamiento

## 4. Verificación

- [ ] 4.1 Suite unitaria/plugin relevante en verde
- [ ] 4.2 Confirmar que el servidor sigue sin auto-merge ante similares
