## Purpose

Inicializar de forma barata e incremental el contexto de un repositorio a partir de archivos conocidos, sin pretender comprender el código con un LLM gigante.

## ADDED Requirements

### Requirement: Escaneo acotado de archivos conocidos
El sistema MUST ofrecer un comando administrativo que, dado un directorio de proyecto y un usuario, examine sólo una allowlist fija: `README`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `pyproject.toml`, `package.json`, `docker-compose.yml`, `Dockerfile`, y la presencia (no el contenido completo) de `src/`, `tests/`, `docs/`, `migrations/`. MUST NOT recorrer el árbol fuente ni incrustar el repositorio entero.

#### Scenario: Proyecto Python típico
- **WHEN** el directorio contiene `pyproject.toml` con `requires-python` y `AGENTS.md`
- **THEN** el informe de candidatos incluye el runtime y un hecho de que existen instrucciones de agente, sin volcar esos archivos completos

#### Scenario: Sin LLM
- **WHEN** Ollama no está disponible
- **THEN** el comando aún produce candidatos deterministas

### Requirement: Candidatos, no escritura silenciosa
El resultado por defecto MUST ser una lista de candidatos atómicos en inglés (categoría, contenido propuesto, `source_type=bootstrap`, `source_ref` = ruta del archivo). MUST NOT insertar memorias salvo un flag explícito de aplicación. Cada candidato MUST ser lo bastante corto para pasar las validaciones de `remember`.

#### Scenario: Dry-run por defecto
- **WHEN** el operador ejecuta bootstrap sin flag de aplicación
- **THEN** no se crea ninguna memoria

#### Scenario: Aplicación opt-in
- **WHEN** el operador aplica los candidatos
- **THEN** se persisten a través de la misma semántica de `remember` (dedup exacta, aviso de similares, aislamiento del usuario)

### Requirement: Incremental
Re-ejecutar bootstrap MUST ser seguro: los candidatos idénticos MUST deduplicarse si se aplican de nuevo, y MUST NOT borrar memorias existentes que no coincidan.

#### Scenario: Segunda pasada
- **WHEN** bootstrap se aplica dos veces con los mismos archivos
- **THEN** no se duplican las memorias de contenido idéntico en el mismo proyecto
