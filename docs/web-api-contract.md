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
