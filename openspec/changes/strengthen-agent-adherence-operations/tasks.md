## 1. Runbook y matriz

- [ ] 1.1 Redactar runbook operativo del benchmark (comando, env, interpretación omitido/incompleto, qué versionar)
- [ ] 1.2 Definir matriz mínima de clientes/políticas/escenarios en docs o manifiesto versionado

## 2. Escenarios y harness

- [ ] 2.1 Revisar cobertura de escenarios sintéticos (pivote + captura) y añadir sólo los huecos necesarios
- [ ] 2.2 Asegurar que el harness reporta huecos de cliente sin fabricar éxito

## 3. Alineación bootstrap

- [ ] 3.1 Verificar equivalencia de nombres de herramienta y fail-open entre `SessionStart` por cliente y el benchmark
- [ ] 3.2 Ajustar skill/hooks/docs de plugin sólo si hay desajuste contractual

## 4. Verificación

- [ ] 4.1 Dry-run del harness sin agente (omisión limpia)
- [ ] 4.2 Al menos una corrida observada real en un cliente disponible, con informe por cliente/política
