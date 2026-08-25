## 1. Esquema

- [x] 1.1 Migración: columna `kind` nullable + check constraint del enumerado; verificar filas existentes con NULL
- [x] 1.2 Validar `kind=todo` exige `ttl_seconds`; verificar rechazo sin TTL y éxito con TTL

## 2. Filtros y superficie

- [x] 2.1 Filtro `kind` en `recall`, `list_memories` y `context`; verificar que NULL no coincide con un filtro concreto
- [x] 2.2 Args/respuestas MCP y self-service; verificar compatibilidad cuando se omite `kind`
- [x] 2.3 Actualizar la skill del plugin con el mapa categoría+kind; verificar test de plugin que ancla el texto clave

## 3. Verificación

- [x] 3.1 Suite unitaria de validación y retrieval en verde
