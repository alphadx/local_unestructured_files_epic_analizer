# TODO

## Prioridad alta: búsqueda y filtrado documental

- Definir e implementar ranking híbrido para búsqueda documental.
	- Evaluar BM25 como capa textual principal.
	- Combinar BM25 con señales vectoriales y metadatos cuando aplique.
- ~~Añadir filtrado por `mime_type` antes de enviar contenido al LLM.~~ **✅ COMPLETADO** — Archivo [003_mime_type_filtering.md](DOCS/avances/003_mime_type_filtering.md) con detalles. Sistema configurable con modos `whitelist`/`blacklist`.
	- ~~Evitar clasificar binarios, ejecutables o archivos no textuales.~~
	- ~~Mantener la decisión de filtrado cerca del scanner o del extractor.~~
- ~~Introducir listas configurables de extensiones permitidas y denegadas.~~ **✅ COMPLETADO** — Variables en `.env`: `INGESTION_MODE`, `ALLOWED_EXTENSIONS`, `DENIED_EXTENSIONS`, `ALLOWED_MIME_TYPES`, `DENIED_MIME_TYPES`.
	- ~~Soportar modo de ingesta basado en lista blanca.~~
	- ~~Soportar modo alternativo de ingesta de "todo" con exclusiones explícitas.~~
	- ~~Permitir lista negra para bloquear extensiones concretas aunque estén permitidas por defecto.~~

## Prioridad media: documentación de API y fuentes

- ~~Documentar ejemplos de request/response para `/api/search` y `/api/rag/query`.~~ ✅ **COMPLETADO** — Archivo [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) creado con ejemplos exhaustivos.
- ~~Añadir un ejemplo de uso del websocket de logs en `/api/jobs/{job_id}/logs/ws`.~~ ✅ **COMPLETADO** — Sección 3 en [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) con ejemplos en Python, JavaScript, Bash y flujo completo.
- ~~Documentar las integraciones remotas de origen: Google Drive y SharePoint.~~ ✅ **COMPLETADO** — Sección 4 en [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) con guías de configuración de credenciales, ejemplos de request/response, flujos Python y bash para ambos proveedores.
- ~~Regenerar `frontend/package-lock.json` y consolidar el stack CSS para volver a `npm ci` en la imagen Docker.~~ ✅ **COMPLETADO** — Dockerfile actualizado para usar `npm ci`. Stack CSS configurado con `@tailwindcss/postcss` y `autoprefixer`.
- ~~**[NUEVA]** Exponer configuración de filtrado (mime_type, extensiones) en el frontend — selector de modo ingesta + listas configurables en formulario de jobs.~~ ✅ **COMPLETADO** — Archivo [006_filter_configuration_frontend.md](DOCS/avances/006_filter_configuration_frontend.md) con detalles. Componente React `FilterConfiguration` integrado en formulario; endpoint GET `/api/admin/filter-config`; soporte para overrides por job.
- ~~Crear endpoint `/api/admin/filter-stats` para auditoría de archivos rechazados durante scans recientes.~~ ✅ **COMPLETADO** — Archivo [004_filter_stats_endpoint.md](DOCS/avances/004_filter_stats_endpoint.md) con detalles. Endpoint expone estadísticas de filtrado con consulta por job_id.

## Prioridad baja: seguimiento y soporte

- ~~Revisar si la configuración de filtrado debe exponerse también en frontend.~~ ✅ **COMPLETADO** — Componente `FilterConfiguration` en frontend; endpoint `/api/admin/filter-config` expone configuración actual.
- [ ] Evaluar si las reglas de `mime_type` y extensiones deben quedar reflejadas en la guía de despliegue.
- [ ] **PostgreSQL**: Reemplazar el store en memoria por PostgreSQL (estado de jobs y documentos).
- [ ] **Celery + Redis**: Cola de tareas para procesamiento paralelo de corpus grandes.

---

## Investigaciones recomendadas

### 1. Filtrado de contenido para LLM (evitar binarios)
**Objetivo**: Detectar y saltar archivos binarios antes de enviarlos a Gemini.

**Tareas**:
- [ ] Ampliar el `mime_type_filter` en el scanner o `document_extraction_service` para detectar binarios (`application/octet-stream`, ejecutables, imágenes binarias, archivos comprimidos).
- [ ] Usar herramientas locales simples: `python-magic`, `filetype` o `mimetypes` estándar.
- [ ] Mantener lista configurable de tipos/extensiones ignoradas para LLM.
- [ ] Documentar el nuevo comportamiento en README y USAGE_EXAMPLES.md.

**Beneficios**:
- Reducir tiempo de procesamiento de Gemini.
- Evitar enviar contenido sin valor semántico.
- Mayor control sobre qué archivos pasan al pipeline de clasificación.

**Referencia**:
- Variables de env existentes: `DENIED_MIME_TYPES`, `ALLOWED_MIME_TYPES`
- Archivo de referencia: [003_mime_type_filtering.md](DOCS/avances/003_mime_type_filtering.md)

---

### 2. NER y base de datos de contactos
**Objetivo**: Extraer entidades nombradas (personas, organizaciones, RUTs, emails, teléfonos) del corpus.

**Tareas**:
- [ ] Agregar campo `named_entities` o `contact_records` en `DocumentMetadata` (schemas.py).
- [ ] Extender el prompt de Gemini en `gemini_service.py` para devolver NER adicionales además de campos contables (emisor, receptor, monto, moneda).
- [ ] Crear endpoint `/api/reports/{job_id}/contacts` para listar contactos detectados con frecuencia.
- [ ] Agregar vista/tabla en frontend para explorar entidades encontradas.
- [ ] Documentar en USAGE_EXAMPLES.md ejemplos de request/response para contactos.

**Beneficios**:
- Capa de datos de personas/empresas extraídas sin procesamiento manual.
- Reutilizable para búsquedas, auditorías y cruces posteriores.
- Preparar el sistema para funcionalidades de relación gráfica entre entidades.

---

### 3. Ranking moderno — alternativas a BM25
**Status**: ✅ **INVESTIGACIÓN COMPLETADA**  
**Documento**: [DOCS/avances/007_investigacion_ranking_moderno.md](DOCS/avances/007_investigacion_ranking_moderno.md)

**Hallazgos principales**:
- Técnicas: BM25 (léxica) + Embeddings (densa) + Learning to Rank (aprendida)
- Soluciones evaluadas: Elasticsearch, Weaviate, Milvus, Vespa, LanceDB
- **Recomendación arquitectónica**:
  - [ ] **Fase 1 (corto plazo)**: Implementar RRF (Reciprocal Rank Fusion) para hybrid search — combinar BM25 + dense retrieval
  - [ ] **Fase 2 (mediano plazo)**: Migrar a Elasticsearch híbrido si corpus > 1M docs
  - [ ] **Fase 3 (largo plazo)**: Learning to Rank con LambdaMART si datos de relevancia disponibles

**Próximos pasos de implementación**:
- [ ] Benchmark local: latencia BM25 vs embeddings vs RRF (corpus 1k-10k docs)
- [ ] PoC Elasticsearch (opcional, si presupuesto permite)
- [ ] Análisis de costos: almacenamiento + compute + operacional
- [ ] Decisión final basada en feedback de usuarios y benchmarks

---

### 4. NER (Named Entity Recognition) y extracción de contactos
**Status**: ✅ **INVESTIGACIÓN COMPLETADA**  
**Documento**: [DOCS/avances/008_investigacion_ner_contactos.md](DOCS/avances/008_investigacion_ner_contactos.md)

**Hallazgos principales**:
- Técnicas: CRF clásico → BiLSTM-CRF → BERT-based → LLM-based (Gemini, GPT)
- Soluciones evaluadas: spaCy, HuggingFace Transformers, Gemini, Azure API, OpenAI
- **Estrategia híbrida recomendada** (3 capas):
  - Layer 1: Regex para email, RUT, teléfono (precisión 100%, sin costo compute)
  - Layer 2: spaCy local para PER/ORG/LOC (10-50ms, CPU-friendly)
  - Layer 3: Gemini para contexto complejo, entidades ambiguas, custom types

**Implementación recomendada**:
- [ ] **Fase 1 (inmediato, 4-6h)**: Extender Gemini con tipos NER + schema DocumentMetadata + endpoint contacts
- [ ] **Fase 2 (mediano, 1-2 sprints)**: Integrar spaCy + base de datos de contactos si PostgreSQL se implementa
- [ ] **Fase 3 (futuro)**: Entity linking a externa knowledge graphs (CRM, DBpedia)

**Costo/Beneficio**:
- Fase 1: Negligible (tokens Gemini existentes), +30-50% recall de contactos
- Fase 2: ~$200/mes GPU (opcional para acelerar), -60% latencia
- Prioridad: Baja-media (puede combinarse con otras investigaciones)

---

## Hoja de ruta de fases

### ✅ Fase 1 — Núcleo e ingesta (COMPLETADO)
- Escaneo recursivo, clasificación con Gemini, embeddings, clustering, detección PII.

### ✅ Fase 2 — Análisis avanzado (COMPLETADO)
- Estadísticas de distribución, mapa de calor temporal, grafo de relaciones.

### ✅ Fase 3 — Documentación y experiencia (COMPLETADO)
- Ejemplos de uso exhaustivos (USAGE_EXAMPLES.md), integraciones remotas (Google Drive, SharePoint), filtrado configurable en frontend.

### Fase 4 — Persistencia y escala (_EN INVESTIGACIÓN_)
- [ ] Reemplazar store en memoria por PostgreSQL.
- [ ] Implementar cola async con Celery + Redis.

### Fase 5 — Inteligencia avanzada (_EN INVESTIGACIÓN_)
- [ ] NER generalizado y base de datos de contactos.
- [ ] Ranking híbrido moderno.
- [ ] Filtrado mejorado de binarios para LLM.

### ✅ Fase 6 — Seguridad y cumplimiento (COMPLETADO)
- API keys, auditoría inmutable, políticas de retención.
