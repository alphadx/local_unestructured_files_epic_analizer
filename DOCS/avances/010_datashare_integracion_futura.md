# Estado del arte — Integración con Datashare (ICIJ)

**Fecha**: Abril 2026  
**Status**: 🔮 Investigación prospectiva (futuro, post-Phase 3)  
**Objetivo**: Evaluar sinergia y arquitectura para integración de Epic Analyzer con Datashare de ICIJ como herramienta complementaria de análisis forense y colaborativo

---

## 1. ¿Qué es Datashare?

### 1.1 Descripción general

**Datashare** es una plataforma open-source desarrollada por **ICIJ** (International Consortium of Investigative Journalists) para:
- Ingesta de documentos no estructurados (masiva, multi-formato)
- Análisis colaborativo en tiempo real
- Búsqueda full-text mejorada + visualizaciones
- Detección de patrones (named entities, conexiones)
- Investigación forense de corporaciones, gobiernos, documentos filtrados

**Ejemplos de uso**:
- Panama Papers (11.5M documentos)
- Paradise Papers (13.4M documentos)
- Investigaciones de corrupción

**Licencia**: AGPL-3.0 (open source)  
**Stack**: Elasticsearch + OCR + NLP + Web UI

### 1.2 Capacidades principales

| Feature | Descripción |
|---------|-------------|
| **OCR** | Extracción de texto de PDFs, imágenes (Tesseract) |
| **Full-text search** | Búsqueda avanzada con Elasticsearch |
| **Named Entity Recognition** | Extracción de nombres, organizaciones, emails |
| **Entity linking** | Vinculación a bases de conocimiento externas |
| **Graph analysis** | Visualización de redes de conexiones |
| **Collaboration** | Múltiples usuarios, anotaciones compartidas |
| **Tagging** | Etiquetado de documentos y análisis |
| **Filtering** | Búsqueda con metadatos complejos |
| **Multi-language** | +30 idiomas soportados |

---

## 2. Arquitectura de Datashare

### 2.1 Componentes principales

```
┌─────────────────────────────────────────────────────────┐
│                    DATASHARE API                        │
│                    (Backend HTTP)                       │
└────────────┬──────────────────────────────┬─────────────┘
             │                              │
      ┌──────▼──────┐             ┌─────────▼──────────┐
      │ Elasticsearch│             │  PostgreSQL DB     │
      │   Full-text  │             │   Metadata, users  │
      │   + reranking│             │   + annotations    │
      └──────┬────────┘             └─────────────────────┘
             │
      ┌──────▼──────┐
      │   Tika      │
      │ (OCR, texto)│
      └─────────────┘

┌─────────────────────────────────────────────────────────┐
│              Web UI (React/Vue)                          │
│    Search + Graph visualization + Collaboration        │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Flujo de ingesta

```
Input files (PDF, DOC, images)
         │
         ▼
   [Tika OCR] → Extract text
         │
         ▼
   [NLP Pipeline] → Named entities, language detection
         │
         ▼
   [Elasticsearch] → Index full-text + metadata
         │
         ▼
   [PostgreSQL] → Store metadata, user annotations
```

---

## 3. Comparativa: Epic Analyzer vs Datashare

| Aspecto | Epic Analyzer | Datashare |
|---------|---------------|-----------|
| **Scope** | Gobernanza interna, reorganización | Análisis forense, investigación |
| **Focus** | Clasificación + clustering | Búsqueda + graph analysis |
| **OCR** | ❌ No | ✅ Sí (Tesseract integrado) |
| **Entity linking** | ⚠️ Parcial (Gemini) | ✅ Avanzado (grafos) |
| **Colaboración** | ❌ No | ✅ Sí (multi-user) |
| **Graph DB** | ❌ No | ✅ Sí (Neo4j optional) |
| **Escalabilidad** | ChromaDB, clustering | Elasticsearch distribuido |
| **UI** | Dashboard básico | Avanzado (search, viz) |
| **Backend language** | Python (FastAPI) | Java (Kotlin) |
| **Licencia** | MIT (ejemplo) | AGPL-3.0 |

**Conclusión**: **Complementarios, NO competidores**
- Epic: Automatización, clasificación, reorganización
- Datashare: Investigación manual, búsqueda, análisis forense

---

## 4. Casos de uso combinados

### 4.1 Flujo Epic → Datashare

```
1. Epic procesa corpus (classifica, genera embeddings, clusters)
2. Exporta documentos + metadatos a Datashare
3. Datashare proporciona UI de búsqueda/investigación
4. Usuario encuentra patrones, genera reportes

Ejemplo:
┌─────────────────┐
│ Epic Analyzer   │ Scan: 100k documentos corporativos
│ • Classifier    │ • Extrae: emisores, receptores, montos
│ • Embeddings    │ • Agrupa por tema, detecta anomalías
│ • PII detection │ • Identifica posible fraude
└────────┬────────┘
         │ Export JSON + Elasticsearch snapshot
         │
         ▼
    ┌─────────────────────┐
    │ Datashare           │
    │ • Búsqueda completa │
    │ • Grafo de personas │
    │ • Anotaciones       │
    │ • Reporte forense   │
    └─────────────────────┘
```

### 4.2 Caso: Auditoría de proveedores

```
Escenario: Empresa audita 50k facturas de proveedores

Epic Analyzer:
1. Escanea todas las facturas
2. Clasifica por proveedor, período fiscal, monto
3. Detecta PII (emails, RUTs)
4. Agrupa por similitud semántica
5. Identifica anomalías (montos inusuales)

Datashare (análisis posterior):
1. Investigador busca "proveedor XYZ" en todos los documentos
2. Ve timeline de transacciones
3. Detecta conexiones entre personas (grafo)
4. Genera reporte de auditoría con anotaciones
5. Comparte hallazgos con team de compliance
```

### 4.3 Caso: Análisis de documentos clasificados

```
Escenario: Ministerio audita documentos classificados heterogéneos

Epic:
- OCR preparatorio (si Datashare OCR falló)
- Classificación preliminar (urgencia, tema)
- Detección de PII para enmascarar
- Clustering por relevancia

Datashare:
- Búsqueda multi-idioma
- Grafo de referencias cruzadas
- Interface para investigadores
- Descubrimiento de patrones
```

---

## 5. Opciones de integración

### 5.1 Opción A: Integración suave (recomendada)

**Arquitectura**:
```
Epic Analyzer → PostgreSQL + archivo JSON
                    ↓
            [Export script]
                    ↓
    Datashare importa via API
```

**Implementación**:
- Epic exporta documents + metadata a formato estándar (JSON/CSV)
- Datashare API ingesta vía bulk endpoint
- Documentos aparecen en Datashare automáticamente

**Ventajas**:
- ✅ Zero coupling entre sistemas
- ✅ Cada uno evoluciona independientemente
- ✅ Bajo overhead

**Desventajas**:
- ❌ No hay sincronización bidireccional
- ⚠️ Duplicación de datos

### 5.2 Opción B: Message bus (futuro)

```
Epic Analyzer → Kafka/RabbitMQ ← Datashare
      ↓
   [Event stream]
      ↓
  PostgreSQL
  Elasticsearch
  (ambos reciben events en tiempo real)
```

**Ventajas**:
- ✅ Sincronización bidireccional
- ✅ Escalable

**Desventajas**:
- ❌ Complejidad significativa
- ⚠️ Requiere consenso en schemas

### 5.3 Opción C: Single backend (máxima integración)

```
Shared Elasticsearch + PostgreSQL backend
    ↑                    ↑
 Epic API            Datashare API
```

**Ventajas**:
- ✅ Single source of truth
- ✅ Sin duplicación

**Desventajas**:
- ❌ Tight coupling
- ❌ Difícil de separar después
- ⚠️ Complejidad operacional

**Recomendación**: Opción A (suave) inicialment, Opción B después.

---

## 6. Data flow export/import

### 6.1 Formato de exportación recomendado

```json
{
  "documents": [
    {
      "id": "uuid-123",
      "file_name": "factura_2024_001.pdf",
      "file_path": "/auditoría/facturas/2024/",
      "file_size": 245000,
      "content_text": "La factura fue emitida por...",
      "mime_type": "application/pdf",
      "created_at": "2024-05-15T10:30:00Z",
      "metadata": {
        "categoria": "Factura_Proveedor",
        "emisor": "ACME Corp.",
        "receptor": "Mi Empresa",
        "monto": 50000,
        "moneda": "CLP",
        "pii_level": "yellow",
        "confidence": 0.92
      },
      "entities": [
        {"type": "PERSON", "value": "Juan Pérez", "confidence": 0.95},
        {"type": "EMAIL", "value": "juan@acme.cl", "confidence": 1.0},
        {"type": "PHONE", "value": "+56 2 2123 4567", "confidence": 0.87}
      ]
    }
  ],
  "clusters": [
    {
      "id": "cluster-1",
      "label": "Facturas de servicios IT",
      "document_ids": ["uuid-123", "uuid-124", ...],
      "coherence": 0.87
    }
  ]
}
```

### 6.2 Mapeo a Datashare indices

```
Epic document → Datashare document:
- file_name → fileName
- content_text → content
- metadata.emisor → namedEntitiesLabel (ORGANIZATION)
- entities → namedEntities
- clusters → tags

Result in Datashare:
- Full-text searchable
- NER pre-populated
- Tagged by cluster
```

---

## 7. Roadmap de integración

### Fase 1: Investigación (AHORA)
- ✅ Evaluar Datashare como complemento
- ✅ Identificar casos de uso
- ✅ Definir formato de export

### Fase 2: MVP Export (Post-Phase 3, ~Q3 2026)
- [ ] Implementar exporter JSON en Epic
- [ ] Test import en Datashare sandbox
- [ ] Documentar interfaz

### Fase 3: Integración UI (Q4 2026)
- [ ] Botón "Import to Datashare" en Epic UI
- [ ] Validación de formato
- [ ] Progress tracking

### Fase 4: Sincronización (2027)
- [ ] Message bus (Kafka/RabbitMQ)
- [ ] Bidirectional sync
- [ ] Conflict resolution

---

## 8. Requisitos técnicos para integración

### 8.1 Datashare setup

```bash
# Docker Compose Datashare
version: '3.8'
services:
  datashare:
    image: icij/datashare:latest
    ports:
      - "8080:8080"
    environment:
      - DIGEST_USERNAME=admin
      - DIGEST_PASSWORD=secret
      - DATASHARE_EXTENSIONS_HOME=/opt/datashare/extensions
    depends_on:
      - elasticsearch
      - postgresql
  
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:7.16.0
    environment:
      - discovery.type=single-node
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
  
  postgresql:
    image: postgres:13
    environment:
      POSTGRES_DB: datashare
      POSTGRES_PASSWORD: password
```

### 8.2 API endpoint para import

```bash
# Datashare API
POST /api/batch/importFiles
    ?project=epic_analyzer
    &fileType=JSON
    &language=es

body: [documento1.json, documento2.json, ...]

response:
{
  "success": true,
  "imported": 1000,
  "errors": 5,
  "indexing_status": "queued"
}
```

---

## 9. Limitaciones y consideraciones

### 9.1 AGPL-3.0 implicaciones

Datashare usa AGPL-3.0, que requiere:
- ✅ Si usas Datashare como library, publish source
- ✅ Si lo integras, derivatives también AGPL
- ⚠️ Considerar licencia de Epic (MIT vs AGPL)

**Solución**: Mantener sistemas separados (loose coupling)

### 9.2 Performance en corpus masivos

- Elasticsearch soporta billones de docs
- Pero búsqueda degradada si > 10M docs sin tuning
- **Epic + Datashare es ideal**: Epic pre-filtra/clasifica, Datashare busca en subconjunto

### 9.3 Duración de análisis

Epic (batch): Genedera resultados offline  
Datashare: Real-time, UI interactiva

**Combo**: Epic genera, Datashare explora

---

## 10. Stack alternativo: Kibana + ElasticSearch

Si complemento a Datashare es heavy:

```
Epic → Elasticsearch
     → Kibana (dashboard)
```

**Ventajas**:
- Elastic stack nativo
- Sin dependencias adicionales

**Desventajas**:
- Menos features que Datashare (graph, NER)
- Menos suitable para investigación forense

---

## 11. Casos de éxito (Datashare in production)

| Caso | Volumen | Resultado |
|------|---------|-----------|
| **Panama Papers** | 11.5M docs | 150+ investigaciones |
| **Paradise Papers** | 13.4M docs | 80+ países, 700+ journalistas |
| **Luanda Leaks** | 715k docs | Angola corruption exposed |
| **FinCEN Files** | 2М docs | Global money laundering |

**Todos usaron Datashare + complementos para análisis a escala**

---

## 12. Conclusión y recomendación

### Oportunidad

**Epic Analyzer + Datashare = Match perfecto**:
1. Epic: Automatización, clasificación, normalización
2. Datashare: Investigación, colaboración, búsqueda

### Roadmap sugerido

```
2026 Q1-Q3:
  ✅ Epic Phase 1-3 (ranking, NER, persistencia)
  
2026 Q4:
  [ ] Implementar export JSON
  [ ] Test con Datashare
  
2027 Q1:
  [ ] UI integration (import button)
  [ ] Documentación de flujo
  
2027 Q2+:
  [ ] Message bus (si escalabilidad needed)
  [ ] Grafo de análisis multiproject
```

### Beneficios al término

✅ **Epic**: Ingesta inteligente, clasificación, alertas  
✅ **Datashare**: Búsqueda, grafos, colaboración  
→ **Combinado**: Plataforma de análisis de unstructured data de clase mundial

### No es MVP prioritario

**Recomendación**: Post-Phase 3 (post-2026 Q3)
- Primero estabilizar Epic core
- Luego agregar Datashare cuando ambos sean robustos
- Evita complejidad temprana

---

## 13. Referencias

### Documentación oficial
- Datashare GitHub: https://github.com/ICIJ/datashare
- Datashare Docs: https://icij.gitbook.io/datashare/
- ICIJ: https://www.icij.org/

### Publicaciones relacionadas
- "The Panama Papers: Investment implications" (ICIJ, 2016)
- "Scaling investigation platforms" (ICIJ tech blog)

### Comunidad
- ICIJ Forum: https://forum.icij.org/
- GitHub Discussions: Active

---

## Conclusión

**Status**: 🔮 **Investigación prospectiva**

Datashare es una herramienta **complementaria estratégica** para Epic Analyzer, enfocada en análisis forense e investigación colaborativa a escala.

**Next step**: Incorporar a la propuesta de valor post-Phase 3, con énfasis en casos de uso forense + investigación.

**ETA de implementación**: 2027 Q1-Q2

