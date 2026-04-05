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
10. [Análisis por grupos de directorio (próxima tarea)](#análisis-por-grupos-de-directorio-próxima-tarea)
11. [Hoja de ruta](#hoja-de-ruta)

---

## Descripción general

El sistema toma una ruta de directorio (local o montada) y ejecuta un pipeline de cinco pasos:

| Paso | Servicio | Descripción |
|------|----------|-------------|
| 1 | `scanner` | Indexado recursivo: nombre, extensión, tamaño, SHA-256, MIME type, detección de duplicados |
| 2 | `gemini_service` | Clasificación semántica con **Gemini Flash**: categoría, entidades, relaciones, palabras clave |
| 3 | `embeddings_service` | Vectorización con **text-embedding-004** → almacenamiento en ChromaDB |
| 4 | `clustering_service` | Agrupación por similitud con **HDBSCAN** (o fallback a etiqueta Gemini) |
| 5 | `job_manager` | Reporte de salud de datos: duplicados, PII, inconsistencias, plan de reorganización |

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

External:  Google Gemini API (Flash + text-embedding-004)
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
│   │   │   ├── embeddings_service.py # Embeddings con text-embedding-004
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

### Actualización reciente
- Implementación de navegación por familias de clusters en el dashboard.
- Mapa de burbujas de clusters con selección de familia y cluster individual.
- Backend mejorado de clustering con `AgglomerativeClustering` para subagrupaciones más estables.
- Extensión de la API de reportes con exploración de corpus y metadatos de grupo.
- Corrección de build frontend para producción y tipado de D3/TypeScript.

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
- Genera embeddings de 768 dimensiones con `text-embedding-004`
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
git clone https://github.com/alphadx/local_unestructured_files_epic_analizer.git
cd local_unestructured_files_epic_analizer

# 2. Crear el archivo de variables de entorno
cp .env.example .env
# Editar .env: añadir GEMINI_API_KEY y ajustar SCAN_PATH
# Si usas un vector store cloud, configura CHROMA_HOST, CHROMA_PORT,
# VECTOR_STORE_SSL y VECTOR_STORE_HEADERS para apuntar al servicio remoto.

# 3. Levantar los tres servicios
docker compose up --build

# 4. Abrir el dashboard
open http://localhost:3000
```

Una vez levantado:

| Servicio | URL |
|----------|-----|
| Dashboard | http://localhost:3000 |
| Backend API | http://localhost:8080 |
| Swagger UI | http://localhost:8080/docs |
| ChromaDB | http://localhost:8001 |

### Docker images
- `local_unestructured_files_epic_analizer-backend`: backend FastAPI
- `local_unestructured_files_epic_analizer-frontend`: frontend Next.js

Puedes verificar las imágenes locales con `docker images | grep local_unestructured_files_epic_analizer`

### Uso en Codespaces / GitHub.dev

El campo **"API Endpoint"** del dashboard permite configurar la URL del backend en tiempo de ejecución.  
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
| `GEMINI_EMBEDDING_MODEL` | `models/text-embedding-004` | Modelo de embeddings |
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

**Body de `POST /api/jobs`:**
```json
{
  "path": "/ruta/absoluta/a/analizar",
  "enable_pii_detection": true,
  "enable_embeddings": true,
  "enable_clustering": true
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
| `GET` | `/api/reports/{job_id}/statistics` | Estadísticas de distribución (extensiones, categorías, PII) |
| `GET` | `/api/reports/{job_id}/exploration` | Exploración de corpus: carpetas, temas, ruido y concentración |

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
    "enable_clustering": true
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

## Análisis por grupos de directorio (próxima tarea)

La siguiente iteración incorporará análisis de contexto de carpeta para que un archivo no se evalúe sólo por su contenido individual, sino también por el patrón del directorio donde vive.

### 1) Prerrequisito: indexación completa del árbol

Para tratar carpetas como grupos, primero debemos tener el inventario indexado:
- Nodos de archivo con: ruta, hash, categoría, entidades, embedding y señales de riesgo (PII, ruido, duplicados)
- Nodos de directorio con: ruta normalizada, profundidad y relación padre/hijo
- Relación archivo → directorio y agregados por carpeta (conteos, diversidad, distribución temporal)

Sin esta capa de indexación no es posible construir una representación consistente de grupo.

### 2) ¿Cómo tratar un grupo?

Un **grupo** será una unidad derivada de estructura de árbol, con dos modos:
- **Modo estricto**: un grupo = un directorio (sin subdirectorios)
- **Modo extendido**: un grupo = un directorio + subárbol (incluye descendientes)

Cada grupo tendrá un `group_profile` con features agregadas:
- Distribución de categorías documentales (ej.: facturas, contratos, licitaciones)
- Distribución de extensiones y MIME
- Huella semántica: centroide de embeddings y dispersión interna
- Señales operativas: ratio de duplicados, ratio de PII, archivos sin clasificar
- Señales temporales: concentración por período fiscal/fecha de emisión

### 3) ¿Cómo analizar un grupo?

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

### 4) ¿Cómo decidir que un grupo se parece a otro?

Usaremos una similitud híbrida entre perfiles de grupo:

$$
S(G_i, G_j) = w_1\,\cos(c_i, c_j) + w_2\,J(C_i, C_j) + w_3\,(1 - \Delta_{pii}) + w_4\,(1 - \Delta_{dup})
$$

Donde:
- $\cos(c_i, c_j)$: similitud coseno entre centroides semánticos
- $J(C_i, C_j)$: similitud tipo Jaccard/overlap sobre categorías y entidades dominantes
- $\Delta_{pii}$ y $\Delta_{dup}$: diferencia normalizada de tasas de PII y duplicados
- $w_k$: pesos calibrables según objetivo (compliance, operación, orden documental)

Con esta métrica podremos:
- Detectar carpetas equivalentes (misma función documental en distintas áreas)
- Detectar carpetas atípicas (outliers estructurales)
- Sugerir consolidación o normalización de estructura

### 5) Plan del siguiente turno (implementación)

1. Extender modelos (`schemas`) con entidades de grupo: `GroupProfile`, `GroupSimilarity`, `GroupAnalysisResult`.
2. Crear servicio `grouping_service` para construir grupos en modo estricto/extendido desde archivos indexados.
3. Implementar extracción de features agregadas y centroides por grupo.
4. Implementar motor de similitud híbrida y ranking top-k de grupos similares.
5. Exponer endpoints iniciales:
  - `GET /api/reports/{job_id}/groups`
  - `GET /api/reports/{job_id}/groups/similarity`
6. Añadir tests unitarios para construcción de grupos, features y métrica de similitud.
7. Integrar vista frontend mínima (tabla de grupos + "se parece a").

> Criterio de aceptación propuesto: dado un corpus con carpetas temáticas conocidas, el sistema debe recuperar como similares al menos los grupos equivalentes esperados en el top-3.

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

### Fase 2 — Análisis avanzado
- [ ] **Estadísticas de distribución**: breakdown por extensión, categoría y nivel de riesgo PII
- [ ] **Mapa de calor temporal**: distribución de archivos por fecha de emisión/modificación
- [ ] **Grafo de relaciones**: visualización de conexiones factura ↔ OT ↔ licitación

### Fase 3 — Persistencia y escala
- [ ] Reemplazar el store en memoria por **PostgreSQL** (estado de jobs y documentos)
- [ ] Cola de tareas con **Celery + Redis** para procesar corpus grandes en paralelo
- [x] Exportación a CSV / JSON del inventario completo de documentos

### Fase 4 — Inteligencia aumentada
- [ ] **Búsqueda semántica**: consultas en lenguaje natural sobre el corpus (`/api/search`)
- [x] **Comparación entre scans**: detectar archivos nuevos/modificados/eliminados
- [ ] **Resumen ejecutivo**: generación de reporte PDF con Gemini
- [ ] Soporte para **SharePoint** y **Google Drive** como fuente de datos

### Fase 5 — Seguridad y cumplimiento
- [ ] Autenticación con API keys o OAuth2
- [ ] Registro de auditoría inmutable (quién ejecutó qué reorganización)
- [ ] Políticas de retención configurables

---

## Licencia

MIT © alphadx
