## 1. Runbook y matriz

- [x] 1.1 Redactar runbook operativo del benchmark (comando, env, interpretación omitido/incompleto, qué versionar)
- [x] 1.2 Definir matriz mínima de clientes/políticas/escenarios en docs o manifiesto versionado

## 2. Escenarios y harness

- [x] 2.1 Revisar cobertura de escenarios sintéticos (pivote + captura) y añadir sólo los huecos necesarios
- [x] 2.2 Asegurar que el harness reporta huecos de cliente sin fabricar éxito

## 3. Alineación bootstrap

- [x] 3.1 Verificar equivalencia de nombres de herramienta y fail-open entre `SessionStart` por cliente y el benchmark
- [x] 3.2 Ajustar skill/hooks/docs de plugin sólo si hay desajuste contractual

## 4. Verificación

- [x] 4.1 Dry-run del harness sin agente (omisión limpia)
- [x] 4.2 Al menos una corrida observada real en un cliente disponible, con informe por cliente/política
