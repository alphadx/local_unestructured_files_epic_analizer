# Guía de Operador — Epic Analyzer

**Audiencia**: Operadores de sistemas, administradores de base de datos, especialistas en seguridad de datos.

**Objetivo**: Guiar la configuración, deployment y operación continua de Epic Analyzer sin reinicios innecesarios.

---

## Tabla de contenidos

1. [Configuración de ingesta sin reinicio](#configuración-de-ingesta-sin-reinicio)
2. [Auditoría de filtro y skip binario](#auditoría-de-filtro-y-skip-binario)
3. [Debugging: casos comunes](#debugging-casos-comunes)
4. [Checklist de deployment](#checklist-de-deployment)
5. [Monitoreo y alertas](#monitoreo-y-alertas)
6. [FAQ Operacional](#faq-operacional)
7. [Herramientas de Deduplicación Opcionales (Fase 5B)](#herramientas-de-deduplicación-opcionales-fase-5b)

---

## Configuración de ingesta sin reinicio

### Escenarios de configuración por departamento

Epic Analyzer soporta **tres estrategias de ingesta** sin reiniciar el backend:

#### 1. Modo Whitelist (Corporativo / Auditoría interna)

**Cuándo usar**: Entornos regulados donde necesitas controlar explícitamente qué tipos de documentos entran al sistema.

**Característica**: Solo procesa archivos en la lista `allowed_extensions` / `allowed_mime_types`.

**Ejemplo cURL**:
```bash
curl -X POST "http://localhost:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/nas/departamento-legal",
    "enable_pii_detection": true,
    "enable_embeddings": true,
    "enable_clustering": true,
    "group_mode": "extended",
    "ingestion_mode": "whitelist",
    "allowed_extensions": ".pdf,.docx,.doc,.txt,.eml,.msg",
    "allowed_mime_types": "text/,application/pdf,application/msword,message/"
  }'
```

**Respuesta**: Job 202 (Accepted)
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "path": "/nas/departamento-legal"
}
```

**Auditoría**: Consulta archivos denegados:
```bash
curl "http://localhost:8000/api/admin/filter-stats?job_id=550e8400-e29b-41d4-a716-446655440000"
```

---

#### 2. Modo Blacklist (Repositorio público / GitHub clones)

**Cuándo usar**: Cuando aceptas casi cualquier contenido pero necesitas excluir explícitamente binarios y ejecutables.

**Característica**: Procesa TODO excepto lo en `denied_extensions` / `denied_mime_types`.

**Ejemplo cURL**:
```bash
curl -X POST "http://localhost:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/mnt/github-mirror/python-project",
    "enable_pii_detection": false,
    "enable_embeddings": true,
    "enable_clustering": true,
    "group_mode": "strict",
    "ingestion_mode": "blacklist",
    "denied_extensions": ".exe,.dll,.so,.pyc,.pyo,.class,.jar",
    "denied_mime_types": "application/x-executable,application/x-sharedlib,application/x-java-applet"
  }'
```

**Resultado**: Se procesan .py, .md, .json, .yml, .txt, etc. Se saltan binarios compilados.

---

#### 3. Detección automática de binarios (Investigación forense)

**Cuándo usar**: Cuando deseas máxima flexibilidad pero necesitas evitar procesar archivos no-texto automáticamente.

**Característica**: Las extensiones y MIME type **se detectan automáticamente** sin necesidad de listar nada.

**Binarios detectados automáticamente**:
- Extensiones: `.exe`, `.dll`, `.so`, `.dylib`, `.jpg`, `.png`, `.mp4`, `.zip`, `.tar`, `.gz`, `.7z`, `.bin`, `.com`, `.bat`, `.cmd`, etc.
- MIME types: `image/*`, `video/*`, `audio/*`, `application/x-executable`, `application/zip`, `application/gzip`, etc.

**Ejemplo cURL**:
```bash
curl -X POST "http://localhost:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/mnt/evidence-storage",
    "enable_pii_detection": true,
    "enable_embeddings": true,
    "enable_clustering": true,
    "group_mode": "extended",
    "ingestion_mode": "blacklist"
  }'
```

**Comportamiento**: El sistema automáticamente saltará:
- Todos los binarios (cualquier extensión/MIME en la lista automática)
- Extensiones en `DENIED_EXTENSIONS` (vars env)
- MIME types en `DENIED_MIME_TYPES` (vars env)

**Auditoría**:
```bash
# Ver qué archivos se saltaron por binary auto-detection
curl "http://localhost:8000/api/admin/filter-stats?job_id=<JOB_ID>&limit=50"
```

Respuesta (extracto):
```json
{
  "scans": [
    {
      "job_id": "<JOB_ID>",
      "skipped_count": 245,
      "skipped_files": [
        {
          "path": "/mnt/evidence-storage/image001.jpg",
          "reason": "extraction_method=skipped_binary (MIME: image/jpeg)",
          "extraction_method": "skipped_binary"
        },
        {
          "path": "/mnt/evidence-storage/archive.zip",
          "reason": "extraction_method=skipped_binary (extension: .zip)",
          "extraction_method": "skipped_binary"
        },
        {
          "path": "/mnt/evidence-storage/app.exe",
          "reason": "extraction_method=skipped_binary (extension: .exe)",
          "extraction_method": "skipped_binary"
        }
      ]
    }
  ]
}
```

---

### Cambiar configuración en tiempo de ejecución

**Sin reiniciar el backend**, tienes **3 opciones**:

#### Opción A: Variables de entorno (reinicio del contenedor)

```bash
# .env
INGESTION_MODE=whitelist
ALLOWED_EXTENSIONS=.pdf,.docx,.txt
SCAN_CONCURRENCY=8

# Reiniciar backend
docker-compose restart backend
```

**Costo**: ~10-30 segundos de downtime

**Beneficio**: Aplica a TODOS los jobs nuevos

---

#### Opción B: Per-job en la API (**RECOMENDADO**)

```bash
curl -X POST "http://localhost:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/scan-especial",
    "ingestion_mode": "whitelist",
    "allowed_extensions": ".md,.txt,.py",
    "enable_pii_detection": true,
    "enable_embeddings": true,
    "group_mode": "strict"
  }'
```

**Costo**: 0 downtime

**Beneficio**: Aplica solo a este job; otros jobs usan config por defecto

**Limitación**: La próxima vez que inicies un job, debes especificar de nuevo (no se guarda globalmente)

---

#### Opción C: Frontend UI (si está disponible)

En el formulario de creación de jobs:
1. Selecciona **"Modo de ingesta"** → Whitelist / Blacklist
2. En **"Extensiones permitidas"** / **"Extensiones denegadas"** → agrega tus reglas
3. Click **"Iniciar scan"**

**Costo**: 0 downtime

**Beneficio**: UI amigable para operadores no-técnicos

**Nota**: Requiere que `frontend` esté ejecutándose en http://localhost:3000

---

## Auditoría de filtro y skip binario

### Endpoint: `/api/admin/filter-stats`

**Propósito**: Auditar qué archivos fueron saltados, por qué, y en qué jobs.

**GET /api/admin/filter-stats** — Resumen global

```bash
curl "http://localhost:8000/api/admin/filter-stats" | jq
```

Respuesta:
```json
{
  "total_scans_with_filters": 5,
  "total_files_filtered": 1847,
  "scans": [
    {
      "job_id": "uuid-1",
      "skipped_count": 245,
      "skipped_files": [
        {
          "path": "/data/image.jpg",
          "reason": "extraction_method=skipped_binary (MIME: image/jpeg)",
          "extraction_method": "skipped_binary"
        },
        {
          "path": "/data/script.bat",
          "reason": "extraction_method=skipped_binary (extension: .bat)",
          "extraction_method": "skipped_binary"
        }
      ]
    }
  ]
}
```

---

**GET /api/admin/filter-stats?job_id={JOB_ID}** — Un job específico

```bash
curl "http://localhost:8000/api/admin/filter-stats?job_id=550e8400-e29b-41d4-a716-446655440000"
```

---

**GET /api/admin/filter-stats?limit=100&offset=50** — Paginación

```bash
# Página 1
curl "http://localhost:8000/api/admin/filter-stats?limit=100&offset=0"

# Página 2
curl "http://localhost:8000/api/admin/filter-stats?limit=100&offset=100"
```

---

### Interpretación de razones de skip

| Razón | Significado | Acción |
|-------|------------|--------|
| `extraction_method=skipped_binary (MIME: image/*)` | Archivo binario detectado por MIME type | ✅ Normal, esperado |
| `extraction_method=skipped_binary (extension: .exe)` | Archivo binario detectado por extensión | ✅ Normal, esperado |
| `extension in blacklist: .exe` | Extensión lista en `DENIED_EXTENSIONS` | ✅ Normal, esperado |
| `"No text extracted from file"` | El archivo se intentó procesar pero no tiene contenido extraíble | ⚠️ Investigar si es un falso positivo |

---

### Verificar que configuración se aplicó correctamente

**Escenario**: Cambiaste a `whitelist` e `allowed_extensions=.pdf,.docx`. ¿Cómo verificar?

```bash
# 1. Crear job con nueva configuración
JOB_ID=$(curl -X POST ... | jq -r '.job_id')

# 2. Esperar a que termine
sleep 5

# 3. Revisar filter-stats
curl "http://localhost:8000/api/admin/filter-stats?job_id=$JOB_ID" | jq

# 4. Verificar: ¿se saltaron archivos no-.pdf/.docx?
# Respuesta esperada: sí, debería haber skip_count > 0
# Si skip_count == 0 y solo hay pdf/docx: ✅ Configuración correcta
```

---

## Debugging: casos comunes

### Problema: "El sistema procesa archivos que no debería"

**Checklist**:

1. ¿Verificaste que `ingestion_mode` es `whitelist` (no `blacklist`)?
   ```bash
   curl http://localhost:8000/api/admin/filter-stats?job_id=<ID> | jq '.scans[0]'
   ```

2. ¿Están los binarios en la lista de denied?
   ```bash
   # Ver vars env actuales (si está disponible el endpoint /api/admin/config)
   curl http://localhost:8000/api/admin/filter-config | jq
   ```

3. ¿Se aplicó per-job correctamente?
   ```bash
   # Revisar el job request que enviaste
   # ¿Incluyó denied_extensions / allowed_extensions?
   ```

**Solución**:
- Reiniciar backend si cambíaste vars env: `docker-compose restart backend`
- Crear nuevo job con params explícitos: `curl -X POST /api/jobs { "ingestion_mode": "whitelist", ... }`

---

### Problema: "Binarios se están procesando y crashean el pipeline"

**Checklist**:

1. ¿Tienes `hdbscan` instalado? (optional pero mejora stabilidad)
   ```bash
   docker-compose exec backend pip list | grep hdbscan
   ```

2. ¿El error está en clustering o en extracción?
   ```bash
   # Ver logs del job
   curl http://localhost:8000/api/jobs/<JOB_ID>/logs | tail -20
   ```

**Solución**:
- Agregar a `DENIED_EXTENSIONS`: `.exe,.dll,.so,.bin,.app`
- O cambiar a `whitelist` con solo extensiones text-safe: `.pdf,.txt,.doc,.docx,.md`
- Si el error persiste, contacta a dev team con logs

---

### Problema: "Filter-stats devuelve JSON vacío o error 500"

**Checklist**:

1. ¿El endpoint está disponible?
   ```bash
   curl http://localhost:8000/health
   # Debe devolver {"status": "ok"}
   ```

2. ¿Hay jobs ejecutándose o completados?
   ```bash
   curl http://localhost:8000/api/jobs | jq 'length'
   # Debe ser > 0
   ```

3. ¿La base de datos de auditoría está accesible?
   ```bash
   # Ver logs
   docker-compose logs backend | tail -50 | grep -i audit
   ```

**Solución**:
- Reiniciar backend: `docker-compose restart backend`
- Revisar que ChromaDB/DB está running: `docker-compose ps`

---

## Checklist de deployment

### Pre-deployment

- [ ] Variables env correctas en `.env`
  - [ ] `GEMINI_API_KEY` configurada
  - [ ] `SCAN_PATH` apunta a volumen válido
  - [ ] `INGESTION_MODE` es `whitelist` o `blacklist` (no typo)
  - [ ] `ALLOWED_EXTENSIONS` / `DENIED_EXTENSIONS` listados sin espacios

- [ ] Directorios de input válidos y accesibles
  - [ ] `SCAN_PATH` existe y tiene permisos de lectura
  - [ ] Suficiente espacio en disco (~10x tamaño corpus estimado)

- [ ] Backend y Frontend compilados
  - [ ] `docker-compose build` sin errores
  - [ ] `pip install -r requirements.txt` exitoso (backend)
  - [ ] `npm ci && npm run build` exitoso (frontend)

### Post-deployment

- [ ] Health check
  ```bash
  curl http://localhost:8000/health
  # Debe devolver 200 {"status": "ok"}
  ```

- [ ] Crear job de prueba
  ```bash
  curl -X POST http://localhost:8000/api/jobs \
    -H "Content-Type: application/json" \
    -d '{"path": "/tmp/test", "group_mode": "strict", ...}'
  ```

- [ ] Monitorear logs
  ```bash
  docker-compose logs -f backend | grep -E "ERROR|WARNING"
  ```

- [ ] Auditoría inicial
  ```bash
  curl http://localhost:8000/api/admin/filter-stats
  ```

---

## Monitoreo y alertas

### Métricas clave

**1. Tasa de skip binario**
```bash
# Calcular % de archivos saltados por binary detection
curl http://localhost:8000/api/admin/filter-stats | jq \
  '[.scans[] | select(.skipped_files[].extraction_method == "skipped_binary")] | length'
```

**Alerta**: Si > 80% de archivos se saltan, revisar configuración `ALLOWED_EXTENSIONS`

---

**2. Job completion rate**
```bash
# Ver jobs que fallaron
curl http://localhost:8000/api/jobs | jq '.[] | select(.status == "failed")'
```

**Alerta**: Si > 10% fail, revisar logs

---

**3. ChromaDB connection**
```bash
# Verificar que ChromaDB responde
curl http://chromadb:8000/api/v1 2>/dev/null && echo "OK" || echo "FAIL"
```

---

### Alertas recomendadas (antes de setup)

| Métrica | Umbral | Acción |
|---------|--------|--------|
| Memory backend | > 80% | Reducir `SCAN_CONCURRENCY` |
| Disk space | < 5% | Limpiar `/tmp/` y archivos temp |
| Job timeout | > 5 min | Aumentar `MAX_FILE_SIZE_MB` o dividir corpus |
| /health failures | > 3 en 5 min | Reiniciar backend |

---

## FAQ Operacional

### P: ¿Puedo cambiar `ingestion_mode` sin resetear base de datos?

**R**: Sí. Cada job puede tener su propia configuración. Jobs históricos NO se reabierten.

```bash
# Job 1 — whitelist
curl -X POST /api/jobs { "ingestion_mode": "whitelist", ... }

# Job 2 — blacklist (sin afectar Job 1)
curl -X POST /api/jobs { "ingestion_mode": "blacklist", ... }
```

---

### P: ¿Se cuentan los "binarios skippeados" en `total_files` de las estadísticas?

**R**: NO. `total_files` = archivos procesados exitosamente. Los binarios NO se cuentan.

Consultar `/api/admin/filter-stats` para ver skipped count.

---

### P: ¿Hay costo de performance por detección automática de binarios?

**R**: Mínimo:
- Extension check: O(1) — muy rápido
- MIME type check: O(n) donde n=tamaño de lista MIME (~20) — 1-2ms

**Recomendación**: Siempre usar en blacklist mode (beneficio seguridad >> costo perf).

---

### P: ¿Cómo habilitar debug logs de filtrado?

**R**: 
```bash
# En .env
LOG_LEVEL=DEBUG

# Reiniciar
docker-compose restart backend

# Ver logs
docker-compose logs backend | grep "skipped_binary"
```

---

### P: ¿Qué pasa si dejo `ALLOWED_EXTENSIONS` vacío en modo whitelist?

**R**: El sistema NO procesará ningún archivo (comportamiento seguro). 

Especifica al menos una extensión: `ALLOWED_EXTENSIONS=.txt,.pdf`

---

### P: ¿Es seguro cambiar configuración por-job frecuentemente?

**R**: Sí. No hay límite de jobs. Pero considera:
- Si cambias config cada job → difícil de auditar
- **Mejor práctica**: usar vars env para defaults, per-job solo para casos especiales

---

## Soporte y escalado

**Preguntas**:
- Jira: `epic-analyzer` tag
- Slack: `#epic-ops`
- Docs: `DOCS/avances/` folder

**Escalado horizontal** (WIP):
- Por ahora solo 1 backend container
- Roadmap: RabbitMQ + multi-backend (Q3 2026)

**Backup/Restore**:
- ChromaDB snapshots: `docker-compose exec chromadb tar czf /backup/snapshot.tar.gz /data`
- Audit logs: Stored locally in `/var/lib/epic-audit.db` (backup daily)


---

## Herramientas de Deduplicación Opcionales (Fase 5B)

Epic Analyzer incluye soporte opcional para herramientas externas de deduplicación
avanzada. El sistema **no las requiere** — funciona perfectamente con el backend
`native` (SHA-256) sin ninguna instalación adicional.

### Variables de entorno relevantes

```env
# Backend de deduplicación: native | czkawka | dupeguru
DEDUP_BACKEND=native

# Umbral de similitud para backends fuzzy (0.0–1.0; default 0.95)
DEDUP_SIMILARITY_THRESHOLD=0.95
```

Agrega estas variables a tu `.env` o `docker-compose.yml` en el servicio `backend`.

### Herramientas soportadas

#### rmlint + jdupes — Deduplicación exacta masiva

**Cuándo usar**: Corpus muy grandes donde la deduplicación debe ser un pre-paso
independiente del análisis semántico.

**Instalación (Ubuntu/Debian)**:
```bash
apt-get install rmlint jdupes
```

**Con Docker** (construir imagen con herramientas incluidas):
```bash
docker build --build-arg ENABLE_DEDUP_TOOLS=true -t epic-analyzer-dedup ./backend
```

**Invocar el worker de deduplicación**:
```python
# Desde Python (p. ej. script de administración)
from app.workers.tasks import run_dedup_worker

# jdupes — rápido, duplicados exactos
result = run_dedup_worker.delay(job_id="<uuid>", backend="jdupes")

# rmlint — con verificación de checksums y scripts de limpieza
result = run_dedup_worker.delay(job_id="<uuid>", backend="rmlint")
```

**Generar script de reorganización auditable (rmlint)**:
```bash
curl -X POST "http://localhost:8000/api/reorganize/<job_id>/generate-script" \
  -o reorg_<job_id>.sh
# Revisar el script y luego ejecutar:
bash reorg_<job_id>.sh
```

#### Czkawka — Imágenes y vídeos similares

**Cuándo usar**: Repositorios de fotos donde hay múltiples versiones de la misma
imagen (diferente resolución, compresión, metadatos). Evita enviar imágenes
visualmente idénticas a Gemini (ahorro de tokens API).

**Instalación**:
```bash
# Descargar binario desde GitHub Releases
wget https://github.com/qarmin/czkawka/releases/latest/download/linux_czkawka_cli
chmod +x linux_czkawka_cli
mv linux_czkawka_cli /usr/local/bin/czkawka_cli
```

**Habilitar en `.env`**:
```env
DEDUP_BACKEND=czkawka
DEDUP_SIMILARITY_THRESHOLD=0.95
```

**Con skip_visual_dedup por job** (si necesitas que un job específico omita el filtro):
```bash
curl -X POST "http://localhost:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/fotos/eventos",
    "skip_visual_dedup": true
  }'
```

#### dupeGuru (modo Picture) — Pre-filtro visual

**Cuándo usar**: Alternativa a Czkawka para detección visual de imágenes similares.

**Instalación**:
```bash
# AppImage desde GitHub Releases
wget https://github.com/arsenetar/dupeguru/releases/latest/download/dupeguru_Linux.AppImage
chmod +x dupeguru_Linux.AppImage
# Opcional: crear symlink
ln -s $(pwd)/dupeguru_Linux.AppImage /usr/local/bin/dupeguru
```

**Habilitar en `.env`**:
```env
DEDUP_BACKEND=dupeguru
DEDUP_SIMILARITY_THRESHOLD=0.90
```

### Métricas expuestas

El campo `tokens_saved_by_visual_dedup` en `GET /api/reports/<job_id>` indica
cuántas llamadas a Gemini se evitaron gracias al pre-filtro visual.

```bash
curl "http://localhost:8000/api/reports/<job_id>" | jq '.tokens_saved_by_visual_dedup'
# → 47
```

### Degradación graceful

Si la herramienta configurada no está instalada, Epic Analyzer lo detecta
automáticamente y continúa con el backend `native`. El log mostrará:

```
WARNING  DedupService: 'czkawka' backend requested but 'czkawka_cli' not found on PATH.
         Falling back to 'native'. Install czkawka_cli to enable advanced deduplication.
```

No se requiere reinicio ni cambio de configuración. La degradación es transparente.
