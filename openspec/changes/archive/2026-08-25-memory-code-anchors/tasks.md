## 1. Esquema

- [x] 1.1 Migración `memory_anchors` (kind, identifier, unique por memoria, FK cascade, índice btree); verificar cap de anclas en límites
- [x] 1.2 Aceptar anclas en `remember` / `remember_batch`; verificar NFC+strip y rechazo de kind desconocido

## 2. Retrieval

- [x] 2.1 Pre-filtro `symbol`/`file` en `search_candidates` antes de RRF; verificar vacío cuando no hay ancla y FTS sin filtro sigue encontrando el identificador en el contenido
- [x] 2.2 Args MCP; verificar tests de identificadores (`PaymentService.capture`, ruta de archivo)

## 3. Verificación

- [x] 3.1 Suite unitaria/integración relevante en verde
