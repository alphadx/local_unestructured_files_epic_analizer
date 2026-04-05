# 🧠 Analizador de Archivos No Estructurados

> **Motor de Ingesta Inteligente para Gobernanza de Datos**  
> Escanea directorios locales, clasifica documentos con Gemini Flash, genera embeddings semánticos, detecta PII y construye clusters de contenido — todo sin modificar un solo archivo del usuario.

[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen)](#testing)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org)

---

## Tabla de contenidos

1. [Descripción general](#descripción-general)
2. [Arquitectura](#arquitectura)
3. [Funcionalidades](#funcionalidades)
4. [Requisitos previos](#requisitos-previos)
5. [Inicio rápido (Docker)](#inicio-rápido-docker)
6. [Desarrollo local](#desarrollo-local)
7. [Variables de entorno](#variables-de-entorno)
8. [Referencia de API](#referencia-de-api)
9. [Testing](#testing)
10. [Análisis por grupos de directorio](#análisis-por-grupos-de-directorio)
11. [Hoja de ruta](#hoja-de-ruta)

---

## Descripción general

El sistema toma una ruta de directorio (local o montada) y ejecuta un pipeline de cinco pasos:

| Paso | Servicio | Descripción |
|------|----------|-------------|
| 1 | `scanner` | Indexado recursivo: nombre, extensión, tamaño, SHA-256, MIME type, detección de duplicados |
| 2 | `gemini_service` | Clasificación semántica con **Gemini Flash**: categoría, entidades, relaciones, palabras clave |
| 3 | `embeddings_service` | Vectorización con **models/text-multilingual-embedding-002** → almacenamiento en ChromaDB |
| 4 | `clustering_service` | Agrupación por similitud con **HDBSCAN** (o fallback a etiqueta Gemini) |
| 5 | `job_manager` | Reporte de salud de datos y análisis de directorios: perfiles de carpeta, similitud de grupos, alertas y recomendaciones |

El usuario puede revisar el reporte en el dashboard Next.js y — sólo si lo aprueba — ejecutar la reorganización de archivos con un click.

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose                                   │
│                                                                           │
│  ┌─────────────────┐    HTTP     ┌──────────────────────────────────────┐ │
│  │   Frontend      │◄──────────►│         Backend (FastAPI)            │ │
│  │   Next.js :3000 │            │                :8080                 │ │
│  └─────────────────┘            │                                      │ │
│                                 │  /api/jobs       → job_manager       │ │
│                                 │  /api/reports    → reports           │ │
│                                 │  /api/reorganize → reorganize        │ │
│                                 │                                      │ │
│                                 │  Pipeline:                           │ │
│                                 │   scanner ──► gemini_service         │ │
│                                 │       │            │                 │ │
│                                 │       ▼            ▼                 │ │
│                                 │  embeddings ──► vector_store         │ │
│                                 │       │            │                 │ │
│                                 │       └────────────►clustering       │ │
│                                 └──────────────────────────────────────┘ │
│                                           │                               │
│                                           ▼                               │
│                                 ┌──────────────────┐                      │
│                                 │  ChromaDB :8001  │                      │
│                                 │  (vector store)  │                      │
│                                 └──────────────────┘                      │
└──────────────────────────────────────────────────────────────────────────┘

External:  Google Gemini API (Flash + embeddings)
```

### Estructura del repositorio

```
├── backend/
│   ├── app/
│   │   ├── config.py               # Settings via pydantic-settings + .env
│   │   ├── main.py                 # FastAPI app + CORS
│   │   ├── models/
│   │   │   └── schemas.py          # Todos los modelos Pydantic
│   │   ├── routers/
│   │   │   ├── jobs.py             # POST/GET /api/jobs
│   │   │   ├── reports.py          # GET /api/reports/{id}
│   │   │   └── reorganize.py       # POST /api/reorganize/{id}/execute
│   │   ├── services/
│   │   │   ├── scanner.py          # Indexado local de archivos
│   │   │   ├── gemini_service.py   # Clasificación con Gemini Flash
│   │   │   ├── embeddings_service.py # Embeddings con Gemini
│   │   │   ├── clustering_service.py # HDBSCAN + fallback por etiqueta
│   │   │   └── job_manager.py      # Pipeline async + store en memoria
│   │   └── db/
│   │       └── vector_store.py     # Adaptador ChromaDB (opcional)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/page.tsx            # Dashboard principal
│   │   ├── components/
│   │   │   ├── ClusterMap.tsx      # Mapa de burbujas D3.js
│   │   │   ├── HealthReport.tsx    # Tarjetas de estadísticas
│   │   │   └── JobStatusCard.tsx   # Progreso + logs en tiempo real
│   │   └── lib/api.ts              # Cliente HTTP (axios)
│   └── Dockerfile
├── tests/
│   ├── test_api.py                 # Tests de integración FastAPI
│   ├── test_clustering.py          # Tests del servicio de clustering
│   └── test_scanner.py             # Tests del escáner local
├── docker-compose.yml
├── .env.example
└── pytest.ini
```

---

## Funcionalidades

### Estado actual
- Navegación por familias de clusters y selección de cluster individual en el dashboard.
- Vista de análisis por grupos de directorio con perfiles, alertas, recomendaciones y similitud entre grupos.
- API de reportes con estadísticas, exploración de corpus, exportación, comparación de scans y análisis de grupos.
- Dashboard con pestañas para `dashboard`, `clusters`, `groups`, `audit`, `exploration`, `search` y `rag`.
- Build frontend corregido para producción y tipado consistente en D3/TypeScript.

### Indexado de archivos (sin IA)
- Escaneo recursivo completo, sin límite de profundidad
- Omite automáticamente archivos de ruido: `.tmp`, `.exe`, `.dll`, `~$*`, `.DS_Store`, etc.
- Omite directorios ocultos (`.git`, `.venv`, etc.)
- Calcula **SHA-256** para detección exacta de duplicados
- Detecta **MIME type** real vía `python-magic` (si está instalado)
- Captura timestamps de creación y modificación

### Clasificación semántica (Gemini Flash)
Cada archivo único es enviado a Gemini y se extrae:

| Campo | Descripción |
|-------|-------------|
| `categoria` | `Factura_Proveedor`, `Orden_Trabajo`, `Licitacion`, `Nota_Credito`, `Contrato`, `Informe`, `Imagen`, `Desconocido` |
| `entidades` | Emisor, receptor, monto total, moneda |
| `relaciones` | ID de licitación vinculada, ID de OT de referencia |
| `analisis_semantico` | Resumen, cluster sugerido, confianza, palabras clave |
| `pii_info` | Presencia de PII, nivel de riesgo (`verde`/`amarillo`/`rojo`), detalles |
| `fecha_emision` | Fecha del documento (YYYY-MM-DD) |
| `periodo_fiscal` | Período fiscal (YYYY-MM) |

- Soporta PDFs, imágenes (JPEG, PNG, WebP, HEIC) y texto plano
- Archivos > `MAX_FILE_SIZE_MB` se procesan truncados (los primeros N bytes)
- Si no hay API key, el servicio devuelve metadata stub para no interrumpir el pipeline

### Vectorización y búsqueda semántica
- Genera embeddings con `models/gemini-embedding-001` (u otro modelo compatible de Gemini si se configura)
- Persiste documentos y chunks en **ChromaDB** con métrica coseno
- Permite búsqueda de documentos similares (`query_similar`)
- Soporta un ChromaDB remoto o cloud mediante `CHROMA_HOST`, `CHROMA_PORT`, `VECTOR_STORE_SSL` y `VECTOR_STORE_HEADERS`
- Degradación graciosa si ChromaDB no está disponible

### Clustering
- **HDBSCAN** cuando hay embeddings disponibles (parámetros adaptativos según tamaño del corpus)
- **Fallback por etiqueta** usando `cluster_sugerido` de Gemini si HDBSCAN no está instalado
- Detección de inconsistencias: facturas sin OT vinculada, licitaciones sin ID de proyecto

### Reporte de salud de datos
- Total de archivos, duplicados (con grupos por hash)
- Contador de archivos con PII
- Archivos sin categorizar
- Errores de consistencia agrupados por cluster
- **Plan de reorganización**: rutas sugeridas basadas en clusters

### Dashboard frontend
- Formulario de configuración de escaneo con toggles para PII, embeddings y clustering
- Polling automático del estado del job (cada 2 segundos)
- Mapa de burbujas D3.js de los clusters semánticos
- Vista de auditoría por cluster con inconsistencias
- Panel de estadísticas, exploración de corpus, búsqueda híbrida y asistente RAG
- Vista de análisis por grupos de directorio con scores de salud, alertas y recomendaciones
- Tablas y gráficos para explorar resultados desde las pestañas del dashboard
- Botón de ejecución de reorganización (con confirmación implícita)
- Visor de logs en tiempo real del pipeline

---

## Requisitos previos

| Herramienta | Versión mínima | Uso |
|-------------|----------------|-----|
| Docker + Compose | v2.x | Despliegue completo |
| Python | 3.12 | Desarrollo backend |
| Node.js | 18 | Desarrollo frontend |
| Gemini API key | — | Clasificación y embeddings |

> **Nota:** Sin API key de Gemini el sistema funciona en modo degradado: indexa archivos, detecta duplicados y genera el reporte, pero sin clasificación semántica ni embeddings.

---

## Inicio rápido (Docker)

```bash
# 1. Clonar el repositorio
 Con esta métrica el sistema puede:
cd local_unestructured_files_epic_analizer

# 2. Crear el archivo de variables de entorno
Ingresa la URL pública del puerto 8080 (visible en la pestaña *Ports*) antes de iniciar el análisis.

---

## Desarrollo local

### Backend

```bash
cd backend

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.venv\Scripts\activate          # Windows

# Instalar dependencias
pip install -r requirements.txt

# (Opcional) HDBSCAN para clustering avanzado
pip install hdbscan

# Iniciar servidor de desarrollo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

### ChromaDB (sólo si se necesitan embeddings localmente)

```bash
docker run -p 8001:8000 chromadb/chroma:0.5.0
```

---

## Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `GEMINI_API_KEY` | `""` | API key de Google AI Studio ([obtener aquí](https://aistudio.google.com/apikey)) |
| `GEMINI_FLASH_MODEL` | `gemini-2.5-flash` | Modelo de clasificación |
| `GEMINI_EMBEDDING_MODEL` | `models/text-multilingual-embedding-002` | Modelo de embeddings |
| `CHROMA_HOST` | `chromadb` | Host de ChromaDB |
| `CHROMA_PORT` | `8000` | Puerto de ChromaDB |
| `CHROMA_COLLECTION` | `documents` | Nombre de la colección |
| `VECTOR_STORE_PROVIDER` | `chroma` | Proveedor del vector store (`chroma` por ahora) |
| `VECTOR_STORE_SSL` | `false` | Habilita TLS al conectarse al vector store remoto |
| `VECTOR_STORE_HEADERS` | `{}` | Headers adicionales para autenticación remota; acepta JSON o pares `key=value` y puede dejarse vacío |
| `VECTOR_STORE_ALLOW_RESET` | `true` | Permite reiniciar la colección desde el backend |
| `MAX_FILE_SIZE_MB` | `10` | Tamaño máximo por archivo antes de truncar |
| `SCAN_CONCURRENCY` | `4` | Hilos para el escáner |
| `LOG_LEVEL` | `INFO` | Nivel de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CORS_ORIGINS` | `http://localhost:3000` | Orígenes CORS permitidos (lista JSON o `false` para `*`) |
| `SCAN_PATH` | `/tmp/fiasco_test` | Ruta del host a montar en el contenedor backend |
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | `{}` | Credenciales JSON de cuenta de servicio de Google Drive para escanear carpetas remotas |
| `GOOGLE_DRIVE_FOLDER_ID` | `""` | ID de carpeta raíz en Google Drive para el scan remoto |
| `SHAREPOINT_TENANT_ID` | `""` | Tenant ID de Azure AD para acceso a SharePoint |
| `SHAREPOINT_CLIENT_ID` | `""` | Client ID de aplicación registrada en Azure AD |
| `SHAREPOINT_CLIENT_SECRET` | `""` | Client secret de la aplicación de Azure AD |
| `SHAREPOINT_SITE_ID` | `""` | Site ID de SharePoint que contiene el drive |
| `SHAREPOINT_DRIVE_ID` | `""` | Drive ID de SharePoint para el scan remoto |
| `API_KEY` | `""` | Clave de autenticación de la API (si se configura, todos los endpoints requieren header `X-Api-Key`) |
| `MAX_JOBS_RETAINED` | `0` | Máximo de jobs completados en memoria (`0` = sin límite) |
| `JOB_MAX_AGE_HOURS` | `0` | Eliminar jobs más antiguos de N horas (`0` = sin límite) |

---

## Referencia de API

La documentación interactiva completa está disponible en `http://localhost:8080/docs` (Swagger UI).

### Jobs

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/jobs` | Iniciar nuevo análisis (202 Accepted) |
| `GET` | `/api/jobs` | Listar todos los jobs |
| `GET` | `/api/jobs/{job_id}` | Estado de un job |
| `GET` | `/api/jobs/{job_id}/logs` | Log en tiempo real del pipeline |
| `POST` | `/api/jobs/prune` | Purgar jobs antiguos según política de retención |

**Body de `POST /api/jobs`:**
```json
{
  "path": "/ruta/absoluta/a/analizar",
  "source_provider": "local",
  "source_options": {},
  "enable_pii_detection": true,
  "enable_embeddings": true,
  "enable_clustering": true,
  "group_mode": "strict"
}
```

Ejemplo para Google Drive:
```json
{
  "path": "<GOOGLE_DRIVE_FOLDER_ID>",
  "source_provider": "google_drive",
  "source_options": {
    "folder_id": "<GOOGLE_DRIVE_FOLDER_ID>"
  },
  "enable_pii_detection": true,
  "enable_embeddings": true,
  "enable_clustering": true,
  "group_mode": "extended"
}
```

> Nota: si envías `service_account_json` en `source_options`, debe ser JSON válido.

Ejemplo para SharePoint:
```json
{
  "path": "<path/within/site>",
  "source_provider": "sharepoint",
  "source_options": {
    "site_id": "<SHAREPOINT_SITE_ID>",
    "drive_id": "<SHAREPOINT_DRIVE_ID>"
  },
  "enable_pii_detection": true,
  "enable_embeddings": true,
  "enable_clustering": true,
  "group_mode": "extended"
}
```

### Reports

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/reports/{job_id}` | Reporte completo de salud de datos |
| `GET` | `/api/reports/{job_id}/documents` | Lista de documentos clasificados |
| `GET` | `/api/reports/{job_id}/chunks` | Fragmentos semánticos extraídos |
| `GET` | `/api/reports/{job_id}/export/json` | Exportar inventario completo en JSON |
| `GET` | `/api/reports/{job_id}/export/csv` | Exportar inventario completo en CSV |
| `GET` | `/api/reports/{base_job_id}/compare/{target_job_id}` | Comparar scans: nuevos/modificados/eliminados |
| `GET` | `/api/reports/{job_id}/executive-summary/pdf` | Generar y descargar resumen ejecutivo en PDF |
| `GET` | `/api/reports/{job_id}/statistics` | Estadísticas de distribución (extensiones, categorías, PII) |
| `GET` | `/api/reports/{job_id}/exploration` | Exploración de corpus: carpetas, temas, ruido y concentración |
| `GET` | `/api/reports/{job_id}/groups` | Análisis de grupos de directorio |
| `GET` | `/api/reports/{job_id}/groups/{group_id}/similarity` | Grupos similares a un grupo concreto |

### RAG

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/rag/query` | Recuperación semántica y respuesta asistida por LLM |

### Search

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/search` | Búsqueda híbrida con filtros por categoría, extensión y directorio |

### Reorganize

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/reorganize/{job_id}/execute` | Ejecutar el plan de reorganización (mueve archivos) |

> ⚠️ **Seguridad:** el escaneo es siempre de **sólo lectura**. La reorganización sólo ejecuta cuando el usuario invoca explícitamente el endpoint o hace clic en el botón del dashboard.

### Auditoría

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/audit` | Listar entradas del registro de auditoría (newest first) |

**Parámetros opcionales de `/api/audit`:**
- `operation` — filtrar por nombre de operación (`job.created`, `job.completed`, `job.failed`, `reorganization.executed`, `search.executed`, `job.pruned`)
- `resource_type` — filtrar por tipo de recurso (`job`, `search`)
- `limit` / `offset` — paginación (máx. 1000)

---

## Ejemplo rápido de uso

### Crear un nuevo job
```bash
curl -X POST http://localhost:8080/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/scan",
    "enable_pii_detection": true,
    "enable_embeddings": true,
    "enable_clustering": true,
    "group_mode": "strict"
  }'
```

### Consultar el reporte final
```bash
curl http://localhost:8080/api/reports/<job_id>
```

### Buscar clusters y exploración de corpus
```bash
curl http://localhost:8080/api/reports/<job_id>/exploration
```

---

## Testing

```bash
# Desde la raíz del repositorio
pip install pytest pytest-asyncio httpx fastapi pydantic pydantic-settings numpy

python -m pytest tests/ -v
```

Resultado esperado:

```
31 passed in ~1.5s
```

Los tests cubren:
- `test_api.py`: health check, endpoints de jobs y reports (sin APIs externas)
- `test_clustering.py`: agrupación por etiqueta, HDBSCAN fallback, detección de inconsistencias
- `test_scanner.py`: noise filter, SHA-256, detección de duplicados, escaneo recursivo, casos límite

---

## Análisis por grupos de directorio

Esta capacidad ya está implementada y expuesta tanto en el backend como en el dashboard. El análisis toma la estructura de carpetas como señal adicional para priorizar reorganización, detección de ruido y comparación entre grupos.

### 1) Indexación del árbol

Para tratar carpetas como grupos, el inventario debe estar indexado con:
- Nodos de archivo con: ruta, hash, categoría, entidades, embedding y señales de riesgo (PII, ruido, duplicados)
- Nodos de directorio con: ruta normalizada, profundidad y relación padre/hijo
- Relación archivo → directorio y agregados por carpeta (conteos, diversidad, distribución temporal)

Sin esta capa no se puede construir una representación consistente de grupo.

### 2) Modos de agrupación

Un **grupo** es una unidad derivada de la estructura de árbol, con dos modos:
- **Modo estricto**: un grupo = un directorio (sin subdirectorios)
- **Modo extendido**: un grupo = un directorio + subárbol (incluye descendientes)

El modo de agrupación se controla con `group_mode` en el payload de `POST /api/jobs`.

Cada grupo tendrá un `group_profile` con features agregadas:
- Distribución de categorías documentales (ej.: facturas, contratos, licitaciones)
- Distribución de extensiones y MIME
- Huella semántica: centroide de embeddings y dispersión interna
- Señales operativas: ratio de duplicados, ratio de PII, archivos sin clasificar
- Señales temporales: concentración por período fiscal/fecha de emisión

### 3) Análisis de grupo

El análisis combinará estadística + semántica:
- **Coherencia interna**: qué tan homogéneo es el grupo respecto a su tema dominante
- **Anomalías internas**: archivos que se alejan del centroide semántico del grupo
- **Calidad documental**: faltantes de metadatos clave, inconsistencias de relaciones, riesgo PII
- **Patrón de composición**: si el grupo se parece a una "carpeta operativa típica" o a una carpeta mixta/ruidosa

Salida esperada por grupo:
- `summary`: propósito inferido de la carpeta
- `health_score`: puntaje compuesto (0-100)
- `alerts`: inconsistencias o riesgo
- `representative_docs`: ejemplos más centrales del grupo

### 4) Similitud entre grupos

Usaremos una similitud híbrida entre perfiles de grupo:

$$
S(G_i, G_j) = w_1\,\cos(c_i, c_j) + w_2\,J(C_i, C_j) + w_3\,(1 - \Delta_{pii}) + w_4\,(1 - \Delta_{dup})
$$

Donde:
- $\cos(c_i, c_j)$: similitud coseno entre centroides semánticos
- $J(C_i, C_j)$: similitud tipo Jaccard/overlap sobre categorías y entidades dominantes
- $\Delta_{pii}$ y $\Delta_{dup}$: diferencia normalizada de tasas de PII y duplicados
- $w_k$: pesos calibrables según objetivo (compliance, operación, orden documental)

### 5) Interfaz disponible

El dashboard expone esta información en la pestaña **Groups**, donde se ven perfiles, alertas, recomendaciones y enlaces para cargar similitudes por grupo.

Con esta métrica el sistema puede:
- Detectar carpetas equivalentes (misma función documental en distintas áreas)
- Detectar carpetas atípicas (outliers estructurales)
- Sugerir consolidación o normalización de estructura

### Tareas futuras recomendadas
- Investigar una vista de árbol interactiva para el resumen de resultados:
  - dropdown/dropup del esqueleto del árbol de carpetas.
  - click en el nombre del archivo para desplegar detalles del archivo.
  - navegación dentro de carpetas para ver análisis de subcarpetas y sus perfiles.
- Añadir soporte de exportación/importación de resultados en formato JSON:
  - exportar metadatos, perfiles de grupo, reportes y resultados de análisis.
  - diseñar un formato que permita recargar un inventario desde otra fuente sin depender de las embeddings de búsqueda.
- Implementar un diccionario de checksums (sha256) por archivo:
  - usar el hash del archivo para saltar procesamiento redundante.
  - aprovechar cálculos previos de clasificación, PII y metadata cuando el checksum ya existe.
- Investigar asincronía y paralelización para las llamadas HTTP / API:
  - evaluar qué partes del pipeline pueden hacerse `async`/concurrentes.
  - revisar `POST /api/jobs`, comunicación con Gemini/ChromaDB y carga de análisis en paralelo.
  - considerar suites de tareas en paralelo como `asyncio`, `concurrent.futures`, `ray`, `prefect` o `dagster`.

> Criterio de aceptación propuesto: estos items quedan como investigación y definición de requisitos para futuras iteraciones.

---

## Hoja de ruta

### Investigación recomendada — ranking moderno
- Analizar alternativas open source a BM25 para este tipo de corpus híbrido de chunks y vectores.
- Investigar sistemas como:
  - `elasticsearch` / `OpenSearch` con BM25 + hybrid vector search
  - `pgvector` + SQL + texto completo
  - `Weaviate`, `Milvus`, `Vespa` para búsquedas semánticas híbridas
  - `LanceDB` o `Chroma` con ranking por proximidad de embeddings y metadata filters
- Objetivo: definir una etapa futura de ranking híbrido que combine:
  1. Relevancia textual (BM25 / exact match)
  2. Semántica vectorial (coseno / distancia euclidiana)
  3. Señales de confianza del modelo y calidad de metadatos
- Esta investigación debe incluir ejemplos concretos de repositorios open source y benchmarks ligeros.

### Investigación recomendada — NER y contactos
- El backend actual ya extrae campos estructurados para documentos contables:
  - `emisor`, `receptor`, `monto_total`, `moneda`
- No hay un reconocimiento de entidades nombradas generalizado ni una base de datos de contactos aún.
- Tarea propuesta:
  - añadir `named_entities` o `contact_records` en `DocumentMetadata`
  - extender el prompt de Gemini para devolver NER adicionales (personas, organizaciones, RUTs, emails, teléfonos, direcciones)
  - exponer un endpoint o export con los contactos detectados
  - construir un dashboard/tabla de entidades encontradas y su frecuencia
- Esto permitirá crear una capa de datos de personas/empresas extraídas del corpus que puede usarse para búsquedas, auditorías y cruces posteriores.

### Investigación recomendada — filtrado de contenido para LLM
- Evitar enviar binarios al LLM es clave: no tiene valor para clasificación/texto y es una pérdida de tiempo.
- Implementar una etapa local de decisión antes de llamar al LLM:
  - detectar el tipo de archivo con `mime_type` / extensión
  - usar herramientas locales simples como `python-magic`/libmagic, `filetype`, o el módulo estándar `mimetypes`
  - mantener una lista configurable de tipos/ extensiones ignoradas (`application/octet-stream`, ejecutables, imágenes binarias, archivos comprimidos, etc.)
- Objetivo: sólo pasar al LLM contenido textual o metadatos útiles; los binarios deben ser saltados o procesados con otro flujo especializado.
- Tarea propuesta:
  - añadir un filtro de binarios en el scanner o en el servicio de extracción de documentos
  - exponer una lista de tipos permitidos/denegados en la configuración
  - documentar el comportamiento para que el sistema no intente clasificar archivos binarios con Gemini

### Fase 2 — Análisis avanzado
- [x] **Estadísticas de distribución**: breakdown por extensión, categoría y nivel de riesgo PII
- [x] **Mapa de calor temporal**: distribución de archivos por fecha de emisión/modificación
- [x] **Grafo de relaciones**: visualización de conexiones factura ↔ OT ↔ licitación (D3 force-directed graph interactivo)

### Fase 3 — Persistencia y escala
- [ ] Reemplazar el store en memoria por **PostgreSQL** (estado de jobs y documentos)
- [ ] Cola de tareas con **Celery + Redis** para procesar corpus grandes en paralelo
- [x] Exportación a CSV / JSON del inventario completo de documentos

### Fase 4 — Inteligencia aumentada
- [x] **Búsqueda semántica**: consultas en lenguaje natural sobre el corpus (`/api/search`)
- [x] **Comparación entre scans**: detectar archivos nuevos/modificados/eliminados
- [x] **Resumen ejecutivo**: generación de reporte PDF con Gemini
- [x] Soporte para **SharePoint** y **Google Drive** como fuente de datos

### Fase 5 — Seguridad y cumplimiento
- [x] Autenticación con API keys (`API_KEY` env var + header `X-Api-Key`)
- [x] Registro de auditoría inmutable (endpoint `/api/audit`, vista en frontend)
- [x] Políticas de retención configurables (`MAX_JOBS_RETAINED`, `JOB_MAX_AGE_HOURS`)

---

## Licencia

MIT © alphadx
