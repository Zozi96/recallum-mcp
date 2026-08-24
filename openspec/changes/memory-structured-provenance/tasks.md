## 1. Esquema

- [ ] 1.1 Migración Alembic: `source_type` (default `unknown`, check constraint) y `source_ref` nullable; verificar upgrade/downgrade en tests de migración o integración
- [ ] 1.2 Mapear columnas en `Memory` y `MemoryOut`; verificar serialización de filas antiguas (`unknown`, nulo)

## 2. Escritura y lectura

- [ ] 2.1 Aceptar `source_type`/`source_ref` en `remember`, `remember_batch` y update de atributos; verificar validación de enum y longitud
- [ ] 2.2 Exponer los campos en MCP y self-service; verificar tests de tools y que omitirlos sigue siendo válido

## 3. Límites

- [ ] 3.1 Confirmar que no existe tabla de conversaciones ni `derived_from`; grep de esquema y revisión del delta de spec
- [ ] 3.2 Suite unitaria/integración de ciclo de vida en verde
