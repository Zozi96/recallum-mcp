# Contrato de la API web

`recallum-ui` consume [`openapi/web-v1.json`](../openapi/web-v1.json) como
entrada versionada de su generador de cliente. El artefacto contiene únicamente
la aplicación montada en `/api/v1`: no incluye los probes operativos ni MCP.

Después de modificar una ruta o un modelo web:

```bash
uv run python scripts/export_web_openapi.py
uv run python scripts/export_web_openapi.py --check
```

El repositorio de la UI copia este fichero y regenera su cliente. Tanto el
backend como la UI versionan la copia para que sus builds no dependan de un
servidor en ejecución.

## Migración UI: paginación administrativa

`GET /admin/users` y `GET /admin/aggregates` aceptan `limit` (default **100**,
máximo **200**) y `offset` (default **0**). El cuerpo sigue siendo la página
(lista de usuarios o `memories` en agregados); el total de filas coincidentes va
en la cabecera `X-Total-Count`.

Contrato para `recallum-ui` en el mismo release:

1. Dejar de asumir que `/admin/users` o `/admin/aggregates` devuelven el censo
   completo.
2. Leer `X-Total-Count` para el total y paginar con `limit`/`offset`.
3. Rechazos con `limit > 200` responden `422`; no clampear en cliente.
4. Desplegar backend y UI juntos: un cliente antiguo sin paginar verá como
   máximo la primera página (100 filas) y un total distinto del length del JSON.

**Aceptación UI (task 10.3):** PENDING — el owner de `recallum-ui` debe confirmar
paginación (`limit`/`offset` + `X-Total-Count`) antes del release. Sin esa
evidencia el gate de release permanece bloqueado.

## Deprecación: `GET /me/memories/search`

Publicado para este change (ruta de compatibilidad **no** eliminada):

| Campo | Valor |
|---|---|
| Reemplazo | `POST /me/memories/search` (query en JSON) |
| Sunset (HTTP-date) | `Tue, 01 Dec 2026 00:00:00 GMT` |
| Config | `RECALLUM__WEB__GET_SEARCH_SUNSET` / `WebSettings.get_search_sunset` |
| OpenAPI | `deprecated: true` + cabeceras `Deprecation` / `Sunset` en `openapi/web-v1.json` |

Respuestas del GET emiten `Deprecation: true` y `Sunset` con la fecha anterior.
La UI y clientes deben migrar a POST antes del sunset; el GET permanece hasta
esa fecha.
