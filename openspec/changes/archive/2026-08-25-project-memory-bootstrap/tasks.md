## 1. Parsers

- [x] 1.1 Implementar escaneo allowlisteado (README*, AGENTS.md, CLAUDE.md, pyproject.toml, package.json, Dockerfile, docker-compose.yml, presencia de dirs); verificar fixtures sin I/O de red ni LLM
- [x] 1.2 Emitir candidatos atómicos en inglés con `source_ref` de archivo y tope de cantidad; verificar que un README largo no se vuelca entero

## 2. CLI

- [x] 2.1 Comando `recallum-admin bootstrap --email --project --path` dry-run por defecto; verificar exit 0 y cero escrituras
- [x] 2.2 Flag `--apply` vía `remember_batch`; verificar dedup en segunda pasada e aislamiento de usuario

## 3. Verificación

- [x] 3.1 Tests unitarios de parsers + un test de apply con fakes; ruff en archivos tocados
