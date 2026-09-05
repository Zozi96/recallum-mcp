## 1. Configuración del chequeador

- [x] 1.1 Añadir `mypy` a las dependencias de desarrollo y configurarlo en `pyproject.toml` con modo estricto en `recallum/` y permisivo en `tests/`. Verificación: `uv run mypy recallum` corre y reporta un estado conocido.
- [x] 1.2 Barrido inicial: corregir los errores de tipo reales encontrados o suprimirlos con `# type: ignore` puntual y justificado; registrar el conteo total en una nota del cambio. Verificación: `uv run mypy recallum` termina en verde o con baseline explícita contada. Baseline medida: 18 errores reales en 9 archivos tras relajar los módulos con falsos positivos de framework; 2 corregidos en código, 16 suprimidos por código y archivo en `pyproject.toml`.

## 2. Integración en CI

- [x] 2.1 Añadir paso de chequeo de tipos a `.github/workflows/ci.yml` como blocking, con cache. Verificación: el workflow falla si se introduce un error de tipo y pasa en verde.
- [x] 2.2 Documentar el comando local (`uv run mypy recallum`) en la guía de contribución o README. Verificación: el comando aparece documentado.

## 3. Validación

- [x] 3.1 Ejecutar la suite completa de calidad local (ruff + mypy + tests). Verificación: todo verde.
