---
fecha: 2026-04-06
status: 🚀 HITO 1 COMPLETADO
categoría: Plan — Cierre de pendientes
---

# Plan de cierre de cabos sueltos

## Objetivo

Cerrar los pendientes pequeños pero relevantes que quedaron después de la fase de documentación y filtrado: endurecer la ingesta, completar la documentación operativa y dejar explícito el comportamiento de dependencias opcionales.

## Alcance

Este plan cubre solo los pendientes con impacto inmediato y bajo costo de implementación:

- skip temprano para archivos sin texto extraíble antes de clasificación/embedding
- documentación de reglas de `mime_type` y extensiones en la guía de despliegue
- documentación del fallback de `hdbscan`
- validación final con pruebas de regresión

## Hito 0 — Planificación

✅ **COMPLETADO** — Diagnosís del estado actual.

### Modo de ejecución

El trabajo avanza por hitos grandes. Antes de empezar cada hito, se solicita el avance disponible para decidir si seguimos, si ajustamos alcance o si cerramos el punto.

### Alcance confirmado

El cierre incluye exactamente estos pendientes operacionales:

1. **Skip temprano para archivos sin texto extraíble** (Hito 1)
   - Problema: algunos archivos no tienen contenido textual y se envían innecesariamente a Gemini
   - Solución: detectar antes de clasificación/embedding y registrar en auditoría
   - Riesgo: bajo (solo agregamos una etapa, no modificamos lógica existente)

2. **Documentación en guía de despliegue** (Hito 2)
   - Problema: las reglas de `mime_type` y extensiones no se hallan en secciones de despliegue
   - Solución: agregar sección explícita con ejemplos de configuración blacklist/whitelist
   - Riesgo: bajo (documentación, no código)

3. **Documentación explícita del fallback de HDBSCAN** (Hito 3)
   - Problema: el fallback está implementado pero no documentado formalmente en README
   - Solución: describir cómo funciona clustering cuando HDBSCAN no está disponible
   - Riesgo: nulo (ya está implementado y funcionando)

### NO entra en este cierre

- Ranking híbrido (BM25 + embeddings) → Fase 4 posterior
- NER y base de contactos → Fase 5 posterior
- PostgreSQL + Celery → Fase 4 posterior
- Integraciones Datashare → Post-2027

### Criterios de terminado

**Para el cierre completo**:
- Todas las tareas de Hito 1, 2, 3 tienen tests o documentación que lo valida
- El README y USAGE_EXAMPLES no contradicen el comportamiento real
- Un operador nuevo puede desplegar, configurar filtros y auditar sin inferir por código
- Las pruebas existentes siguen pasando (regresión)

### Batería mínima de pruebas (ya existen)

- ✅ `tests/test_scanner.py::TestMimeFiltering` — cobertura de filtrado en scanner
- ✅ `tests/test_admin_api.py::TestFilterStatsEndpoint` — 5 tests de auditoría y paginación
- ✅ `tests/test_api.py::test_start_scan_e2e_pipeline_applies_filters` — E2E aplicación de filtros de punta a punta
- ✅ `tests/test_clustering.py` — fallback de HDBSCAN ya validado localmente

**Comando para validar regresión**:
```bash
cd /workspaces/local_unestructured_files_epic_analizer
pytest tests/ -xvs -k "mime or filter or hdbscan or clustering" --tb=short
```

## Hito 1 — Endurecimiento del pipeline

✅ **COMPLETADO** — Ver detalle en [DOCS/avances/013_hito1_endurecimiento_ingesta.md](013_hito1_endurecimiento_ingesta.md)

**Qué se hizo**:
- Detección temprana de binarios (extensión + MIME type) en `extract_document_content()`
- Skip inmediato sin intentar `unstructured` ni lectura de texto
- Logging diferenciado: "binario detectado" vs "sin contenido textual"
- 3 nuevos tests unitarios validando skip de binarios (.exe, .png, .zip, etc.)
- Compatibilidad 100%: Paso 2 del pipeline sigue saltando archivos vacíos como antes

Objetivo: evitar trabajo inútil y reducir riesgo de enviar contenido sin valor al LLM.

- detectar archivos sin texto extraíble antes de clasificación/embedding
- extender la cobertura a binarios, ejecutables y archivos comprimidos
- conservar el comportamiento coherente entre scanner, extractor y auditoría

**Criterio de terminado**: los archivos no textuales quedan fuera del camino de Gemini y hay tests que lo prueban.

## Hito 2 — Cierre documental

Objetivo: dejar el comportamiento operativo claro para despliegue y soporte.

- reflejar reglas de ingesta en la guía de despliegue
- consolidar README y USAGE_EXAMPLES para que no contradigan la semántica real
- mantener una sola fuente de verdad para los modos `blacklist` y `whitelist`

**Criterio de terminado**: un operador nuevo puede configurar, desplegar y auditar el filtrado sin tener que inferir comportamiento por código.

## Hito 3 — Dependencias y fallback

Objetivo: hacer explícita la historia de `hdbscan` para evitar sorpresas en instalación.

- documentar que `hdbscan` es opcional
- explicar qué hace el sistema cuando no está instalado
- asegurar que la guía de instalación refleje el camino recomendado y el camino degradado

**Criterio de terminado**: la instalación no genera ambigüedad y el fallback queda descrito en términos verificables.

## Hito 4 — Validación final

Objetivo: cerrar el ciclo con evidencia.

- correr pruebas unitarias del filtro
- correr E2E del pipeline de ingesta
- verificar auditoría y endpoint de estadísticas
- revisar que la documentación final coincida con el comportamiento probado

**Criterio de terminado**: las pruebas pasan y no quedan referencias pendientes en el TODO para estos temas.

## Secuencia recomendada

1. Completar Hito 0.
2. Implementar Hito 1.
3. Cerrar Hito 2.
4. Documentar Hito 3.
5. Ejecutar Hito 4 y congelar el cierre.

## Punto de control operativo

- Antes de cada salto de hito, se solicita tu avance actual.
- Si el avance cambia el alcance, se replanifica el siguiente hito.
- Si no hay cambios, se continúa con la siguiente etapa sin reabrir lo ya cerrado.
