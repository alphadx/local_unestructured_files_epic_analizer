# Estado del arte — Persistencia y escalabilidad con PostgreSQL + Celery

**Fecha**: Abril 2026  
**Status**: 🔬 Investigación completada (basada en conocimiento 2024)  
**Objetivo**: Fundamentar la decisión arquitectónica para migrar de store en memoria a persistencia relacional + task queue para procesamiento de corpus grandes en Epic Analyzer

---

## 1. Panorama general

El proyecto Epic Analyzer actualmente mantiene todo en memoria:
- Estado de jobs
- Documentos indexados
- Embeddings en ChromaDB
- Resultados de clustering

**Limitaciones actuales**:
- ❌ Pérdida total de datos si el backend crashea
- ❌ No hay escalabilidad horizontal (un solo proceso)
- ❌ Bloqueo en tareas largas (escaneo de corpus masivos)
- ❌ No hay persistencia de histórico de análisis
- ❌ Auditoría limitada sin BD
- ❌ Sincronización imposible con múltiples instancias

**Objective**: Pasar a arquitectura con persistencia + workers paralelos

---

## 2. PostgreSQL — Base de datos relacional

### 2.1 ¿Por qué PostgreSQL?

**Alternativas consideradas**:
| Opción | Caso | Razón descartada para Epic |
|--------|------|---------------------------|
| SQLite | Prototipaje, mobile | Concurrencia limitada, no escala |
| MySQL | Web apps tradicionales | Menos features avanzados que PG |
| MongoDB | Datos no estructurados | Schema flexible, pero worse para relaciones |
| Redis | Cache, sessions | No es BD persistente (in-memory) |
| DynamoDB | Serverless, NoSQL | Vendor lock-in AWS, costo variable |
| Cassandra | Series temporales masivas | Overkill, complejidad operacional |

**PostgreSQL es ideal para Epic Analyzer**:
- ✅ ACID transaccional (garantía de integridad)
- ✅ JSON/JSONB columnas (flexible + indexable)
- ✅ Full-text search integrado
- ✅ GiST, GIN, BRIN índices (versatile)
- ✅ Array types (para contactos, entidades)
- ✅ Particionamiento (escala horizontal)
- ✅ Replica nativa (HA)
- ✅ Open source, maduro (25+ años)
- ✅ Bajo costo operacional

### 2.2 Schema propuesto para Epic Analyzer

```sql
-- Tabla de jobs (estado, metadata, auditoría)
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    path TEXT NOT NULL,
    source_provider VARCHAR(50) DEFAULT 'local',  -- local, google_drive, sharepoint
    status VARCHAR(20) DEFAULT 'pending',  -- pending, running, completed, failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    config JSONB NOT NULL,  -- enable_pii, enable_embeddings, etc.
    result JSONB,  -- summary, stats
    error_message TEXT,
    metadata JSONB,
    INDEX idx_jobs_user_status (user_id, status),
    INDEX idx_jobs_created (created_at DESC)
);

-- Tabla de documentos indexados
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_name TEXT,
    file_size BIGINT,
    file_hash VARCHAR(64),  -- SHA-256
    mime_type VARCHAR(100),
    extension VARCHAR(10),
    content_text TEXT,  -- Primeros N caracteres para búsqueda
    created_at TIMESTAMPTZ,
    modified_at TIMESTAMPTZ,
    categoria VARCHAR(50),
    confidence_score FLOAT,
    embedded BOOLEAN DEFAULT FALSE,
    embedding_id VARCHAR(100),  -- ChromaDB collection ID
    metadata JSONB,  -- entidades, PII, etc.
    INDEX idx_documents_job (job_id),
    INDEX idx_documents_hash (file_hash),
    INDEX idx_documents_search (file_path)
);

-- Tabla de entidades/contactos extraídos
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    entity_type VARCHAR(50),  -- PERSON, ORGANIZATION, EMAIL, PHONE, etc.
    entity_value TEXT NOT NULL,
    normalized_value TEXT,
    confidence_score FLOAT,
    frequency INT DEFAULT 1,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ,
    metadata JSONB,
    INDEX idx_entities_job (job_id),
    INDEX idx_entities_type (entity_type),
    INDEX idx_entities_value (entity_value)
);

-- Tabla de clusters (agrupaciones semánticas)
CREATE TABLE clusters (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    cluster_label VARCHAR(100),
    cluster_id_internal INT,  -- HDBSCAN cluster ID
    document_ids UUID[],  -- Array de document IDs en el cluster
    centroid FLOAT8[],  -- Vector embedding del centroide
    size INT,
    coherence_score FLOAT,
    metadata JSONB,
    INDEX idx_clusters_job (job_id)
);

-- Tabla de auditoría
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    user_id TEXT,
    operation VARCHAR(50),  -- job.created, job.completed, search.executed, etc.
    resource_type VARCHAR(50),  -- job, document, entity, cluster
    resource_id UUID,
    details JSONB,
    ip_address INET,
    INDEX idx_audit_created (created_at DESC),
    INDEX idx_audit_operation (operation),
    INDEX idx_audit_user (user_id)
);

-- Tabla de caché de búsquedas (para analytics)
CREATE TABLE search_cache (
    id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    query_hash VARCHAR(64),
    job_id UUID REFERENCES jobs(id),
    results_count INT,
    execution_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    hit_count INT DEFAULT 1,
    INDEX idx_search_cache_hash (query_hash),
    INDEX idx_search_cache_job (job_id)
);
```

### 2.3 Ventajas de persistencia relacional

| Feature | Beneficio para Epic |
|---------|-------------------|
| ACID transactions | Consistencia de jobs y documentos |
| Indexación | Búsquedas rápidas por hash, entidad, job |
| Foreign keys | Integridad referencial jobs → documents |
| JSONB | Almacenar metadata flexible sin schema migration |
| Full-text search | Búsqueda de contenido en corpus |
| Particionamiento | Escalar por job_id o fecha |
| Replicación | HA y backups automáticos |
| Auditoría | Track de cambios, compliance |

### 2.4 Costo y scaling

**Vertical** (aumentar CPU/RAM):
- Desarrollo: $20-50/mes (2 CPU, 2GB RAM en cloud)
- Producción: $200-500/mes (4 CPU, 16GB RAM)

**Horizontal** (read replicas):
- Cada réplica: +$100/mes
- Setup: Primary + 1 standby + 1 read replica = $300-600/mes

---

## 3. Celery — Task queue para procesamiento paralelo

### 3.1 Concepto

Task queue que permite ejecutar tareas asincronamente en múltiples workers.

```
┌─────────────┐
│   FastAPI   │  "Encola tarea: escanear /data"
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│    Message Broker   │  Redis / RabbitMQ
│   (queue persistente)
└──────┬──────────────┘
       │
  ┌────┴────┬────────┬─────────┐
  ▼         ▼        ▼         ▼
┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐
│ W-1 │  │ W-2 │  │ W-3 │  │ W-4 │  (Workers)
│ Scan│  │ NER │  │ Emb │  │ Cls │
└─────┘  └─────┘  └─────┘  └─────┘
   │        │       │        │
   └────────┴───────┴────────┘
           │
           ▼
       ┌─────────────┐
       │ PostgreSQL  │  Persistencia
       └─────────────┘
```

### 3.2 Arquitectura Celery

**Componentes**:

1. **Message Broker** — Cola de tareas
   - Redis: Rápido, in-memory con persistencia
   - RabbitMQ: Más confiable, AMQP

2. **Workers** — Procesos que ejecutan tareas
   - Pueden correr en la misma máquina o distribuidos
   - Número configurable por task type

3. **Result Backend** — Almacena resultados
   - Puede ser PostgreSQL, Redis, o Celery-Result-Backend

### 3.3 Ejemplo de uso para Epic Analyzer

```python
# backend/app/tasks/celery_app.py
from celery import Celery

celery_app = Celery(
    'epic_analyzer',
    broker='redis://localhost:6379/0',
    backend='db+postgresql://user:pass@localhost/epic_analyzer'
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# backend/app/tasks/scanning.py
@celery_app.task(bind=True, name='scan_directory')
def scan_directory(self, job_id: str, path: str):
    """Tarea: escanear directorio en background"""
    try:
        self.update_state(state='PROGRESS', meta={'current': 0, 'total': 100})
        
        # 1. Escanear archivos
        files = scanner_service.scan(path)
        
        # 2. Actualizar BD
        for file in files:
            db.documents.insert(job_id, file)
        
        # 3. Reportar progreso
        self.update_state(state='PROGRESS', meta={'current': 50, 'total': 100})
        
        # 4. Lanzar siguientes tareas
        classify_documents.delay(job_id)
        
        return {'status': 'completed', 'count': len(files)}
    except Exception as exc:
        self.update_state(state='FAILURE', meta={'error': str(exc)})
        raise

@celery_app.task(bind=True, name='classify_documents')
def classify_documents(self, job_id: str):
    """Tarea: clasificar documentos con Gemini"""
    documents = db.documents.get_by_job(job_id, embedded=False)
    
    for doc in documents:
        result = gemini_service.classify(doc.content_text)
        db.documents.update(doc.id, categoria=result['categoria'])
        
        # Extraer entidades
        for entity in result['entities']:
            db.entities.insert(job_id, doc.id, entity)

# backend/app/routers/jobs.py
@router.post("/api/jobs")
async def create_job(request: JobRequest):
    job = db.jobs.create(
        user_id="user123",
        path=request.path,
        config=request.dict()
    )
    
    # Encolar tarea asincronicamente
    scan_directory.delay(job.id, request.path)
    
    return {
        'job_id': job.id,
        'status': 'pending',
        'task_id': ...  # Task ID de Celery para tracking
    }
```

### 3.4 Brokers: Redis vs RabbitMQ

| Aspecto | Redis | RabbitMQ |
|--------|-------|----------|
| **Tipo** | In-memory + persistence | AMQP Message Broker |
| **Velocidad** | ⭐⭐⭐⭐⭐ (muy rápido) | ⭐⭐⭐⭐ (rápido) |
| **Confiabilidad** | ⭐⭐⭐⭐ (buena) | ⭐⭐⭐⭐⭐ (excelente) |
| **Setup** | Trivial | Media (ERLANG, configuración) |
| **Costo** | $5-20/mes (cloud) | $10-30/mes (cloud) |
| **Para Epic** | ✅ Recomendado | ⚠️ Si need haute confiabilité |

**Recomendación**: Redis para desarrollo/MVP, RabbitMQ si confiabilidad crítica.

### 3.5 Procesamiento paralelo

**Configuración worker para Epic Analyzer**:

```python
# 1. Scanner worker (1 worker por máquina)
celery_app.conf.update(
    task_routes={
        'tasks.scanning.*': {'queue': 'scanning', 'routing_key': 'scan.#'},
    }
)
# celery -A app.tasks worker -Q scanning -c 1

# 2. Classification worker (puede paralelizarse)
# celery -A app.tasks worker -Q classification -c 4

# 3. Embeddings worker (si GPU disponible)
# celery -A app.tasks worker -Q embeddings -c 1 --pool=threads

# 4. Clustering worker
# celery -A app.tasks worker -Q clustering -c 2
```

**Pipeline paralelo**:
```
Scan (1 worker) → Classification (4 workers) → Embeddings (1 GPU worker) 
                                            ↓
                                      ChromaDB storage
                                            ↓
                                    Clustering (2 workers)
```

---

## 4. Alternativas a Celery + Redis

### 4.1 APScheduler (sin queue)

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def scan_job():
    scanner_service.scan('/data')

scheduler.add_job(scan_job, 'interval', minutes=60)
scheduler.start()
```

**Ventajas**: Simple, no requiere Redis  
**Desventajas**: ❌ No distribuido, ❌ Bloquea FastAPI, ❌ Sem auto-scaling

---

### 4.2 Kubernetes Jobs (cloud-native)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: scan-job-{{ job_id }}
spec:
  template:
    spec:
      containers:
      - name: scanner
        image: epic-analyzer:latest
        command: ["python", "-m", "celery", "worker", "-Q", "scanning"]
```

**Ventajas**: ✅ Escalable, ✅ Managed by K8s  
**Desventajas**: ❌ Requiere K8s, ❌ Overhead de orquestación

---

### 4.3 AWS SQS + Lambda (serverless)

```python
# Encolar a SQS
sqs.send_message(
    QueueUrl='https://sqs.us-east-1.amazonaws.com/.../epic-jobs',
    MessageBody=json.dumps({'job_id': job.id})
)

# Lambda procesa automáticamente
def lambda_handler(event, context):
    job_id = event['Records'][0]['body']['job_id']
    scan_directory(job_id)
```

**Ventajas**: ✅ Serverless, ✅ Paga solo por uso  
**Desventajas**: ❌ Vendor lock-in, ❌ Costo variable, ❌ Cold starts

---

## 5. Persistencia de resultados

### 5.1 Result Backend options

**PostgreSQL** (recomendado para Epic):
```python
celery_app = Celery(
    backend='db+postgresql://user:pass@localhost/epic_db'
)
```
- ✅ Persistencia garantizada
- ✅ Queries sobre resultados
- ✅ Integración natural con BD

**Redis** (más rápido, menos confiable):
```python
celery_app = Celery(
    backend='redis://localhost:6379/0'
)
```
- ✅ Muy rápido (in-memory)
- ❌ Pierde resultados si Redis crashea

**Filesystem** (sin recomendación):
```python
celery_app = Celery(
    backend='file:///var/tmp/celery-results'
)
```
- ❌ No distribuido
- ❌ Difícil de escalar

---

## 6. Comparativa arquitectónica para Epic Analyzer

| Criterio | En memoria | PostgreSQL + Celery (Redis) | K8s Distributed | Serverless (SQS+Lambda) |
|----------|-----------|--------------------------|-----------------|----------------------|
| **Persistencia** | ❌ No | ✅ Sí | ✅ Sí | ✅ Sí |
| **Escalabilidad** | ❌ Vertical solo | ✅ Horizontal con workers | ✅✅ Excelente | ✅ Automática |
| **Latencia inicio tarea** | ~0ms | ~100-200ms | ~1-5s | ~1-10s |
| **Implementación** | Trivial | Media (4-6 horas) | Compleja (2-3 sprints) | Media (1-2 sprints) |
| **Costo operacional** | $50-100/mes | $100-200/mes | $200-500/mes | $50-300/mes (variable) |
| **Mantenimiento** | Bajo | Bajo-medio | Alto (K8s) | Bajo |
| **Para corpus < 100k** | ✅ OK | ⚠️ Overkill | ❌ No | ⚠️ Caro por volumen bajo |
| **Para corpus > 1M** | ❌ No | ✅ Recomendado | ✅ Óptimo | ⚠️ Impredecible |

---

## 7. Casos de uso específicos en Epic Analyzer

### 7.1 Pipeline de ingesta paralelo

**Actual** (bloqueante):
```
POST /api/jobs → scanner → embedding → clustering → respuesta 202
                 [puede tardar minutos/horas]
```

**Con Celery**:
```
POST /api/jobs → encolar(scan) → respuesta 202 inmediata
                      ↓
                 scan_directory.delay(job_id)
                      ↓
                 classify_documents.delay(job_id)  [paralelo]
                 generate_embeddings.delay(job_id) [paralelo]
                      ↓
                 clustering.delay(job_id) [después de embeddings]
```

### 7.2 Escalabilidad en corpus grande

**Corpus 100k documentos**:
- Sin Celery: Backend bloqueado ~2-3 horas
- Con Celery (4 workers): ~15-30 minutos

**Corpus 1M documentos**:
- Sin Celery: Crash (OOM)
- Con Celery (8 workers): ~2-4 horas

### 7.3 Monitoreo de progreso

**Anterior**: polling a endpoint, sin actualización real  
**Con Celery**:

```python
# Frontend: polling task status
GET /api/jobs/{job_id}/progress → {
    'status': 'PROGRESS',
    'stage': 'classification',
    'current': 45000,
    'total': 100000,
    'percentage': 45,
    'eta': '2 horas'
}
```

---

## 8. Roadmap de implementación para Epic Analyzer

### Fase 1 — Preparación (1-2 sprints)

**Objetivo**: Pasar a PostgreSQL sin cambiar backend (todavía en memoria para processing)

```
1. Crear schema PostgreSQL
2. Migraciones Alembic para versionamiento BD
3. SQLAlchemy ORM para modelos (Job, Document, Entity, Cluster)
4. Reemplazar store en memoria con queries BD
5. Tests de persistencia
```

**Esfuerzo**: 1-2 sprints  
**Riesgo**: Bajo (lógica similar, solo storage cambio)  
**Beneficio**: Jobs persisten, histórico disponible

---

### Fase 2 — Celery básico (1-2 sprints)

**Objetivo**: Introducir task queue, no cambiar costo operacional

```
1. Instalar Redis + Celery
2. Definir tareas (scanning, classification, embedding, clustering)
3. Refactorizar job_manager para usar Celery
4. endpoint GET /api/jobs/{job_id}/progress con task status
5. Monitoreo con Flower (visualizador de Celery)
```

**Esfuerzo**: 1-2 sprints  
**Riesgo**: Bajo-medio (cambio de paradigma, pero isolated)  
**Beneficio**: Paralelismo inmediato

---

### Fase 3 — Escalabilidad (2-3 sprints)

**Objetivo**: Multi-worker, auto-scaling, monitoreo

```
1. Configurar workers por task type (scanning, classification, etc.)
2. Auto-scaling simple: worker count configurable en env
3. Load balancing: roundrobin o least-connected
4. Healthchecks: verificar si workers están vivos
5. Dead letter queue para tareas fallidas
6. Retry logic con backoff exponencial
```

**Esfuerzo**: 2-3 sprints  
**Riesgo**: Medio (debugging distribuido es más complejo)  
**Beneficio**: Escala hasta millones de documentos

---

## 9. Stack recomendado para Epic Analyzer

### Mínimo viable (Phase 1-2):

```
Arquitectura:
┌──────────────┐
│   Frontend   │
│  (React)     │
└──────┬───────┘
       │
┌──────▼───────┐
│  Backend     │
│  (FastAPI)   │
└──────┬───────┘
       │
    ┌──┴──┬────────┐
    ▼     ▼        ▼
PostgreSQL Redis ChromaDB
    ↑       ↑
  Jobs    Queue
         Results
```

**Docker Compose**:
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports: ["8080:8080"]
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/epic
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis
  
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: password
      POSTGRES_DB: epic
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
  
  celery_worker_scan:
    build: ./backend
    command: celery -A app.tasks worker -Q scanning -c 1
    depends_on:
      - redis
      - postgres
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/epic
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
  
  celery_worker_classify:
    build: ./backend
    command: celery -A app.tasks worker -Q classification -c 4
    ...
  
  # Más tipos de workers según necesidad

volumes:
  postgres_data:
```

### Producción (Phase 3):

```
AWS RDS PostgreSQL + ElastiCache Redis
+ Kubernetes con auto-scaling de workers
+ New Relic / DataDog para monitoreo
+ SQS como backup queue
```

---

## 10. Consideraciones de seguridad

### 10.1 PostgreSQL

```sql
-- No exponer BD públicamente
-- Firewall: Solo desde backend

-- Credenciales en env vars, no en código
-- Connection pooling: PgBouncer

-- Backups automáticos
-- Point-in-time recovery

-- Auditoría de cambios (audit_log tabla)
```

### 10.2 Celery/Redis

```python
# Redis sin contraseña: PELIGRO
# Solución: Redis AUTH con strong password

# Encriptación de mensajes:
celery_app.conf.update(
    task_compression='gzip',
    task_protocol=2,
)

# Limitar acceso a workers
# No exponer Flower públicamente
```

---

## 11. Monitoreo y observabilidad

### 11.1 PostgreSQL

```sql
-- Monitor queries lentas
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- > 1s

-- Vacío automático
AUTOVACUUM ON;

-- Monitoreo
SELECT * FROM pg_stat_statements ORDER BY total_time DESC;
```

### 11.2 Celery + Flower

```bash
# Visualizador de Celery
celery -A app.tasks flower --port=5555
# http://localhost:5555
```

Dashboards:
- Task success/failure rate
- Worker status
- Queue depth
- Task execution time

---

## 12. Costs estimation

### Development

| Component | Costo/mes |
|-----------|-----------|
| PostgreSQL (2 CPU, 2GB) | $20 |
| Redis (micro) | $5 |
| Compute (backend + workers) | $30 |
| **Total** | **$55-80** |

### Production (1M docs/month)

| Component | Costo/mes |
|-----------|-----------|
| PostgreSQL RDS (4 CPU, 16GB + backup) | $400 |
| Redis ElastiCache (2 replicas) | $150 |
| ECS/K8s compute (8 workers average) | $600 |
| Monitoring/Logging | $100 |
| **Total** | **$1,250** |

---

## 13. Limitaciones y desafíos

### 13.1 Data consistency

Con múltiples workers, riesgo de race conditions:

```python
# ❌ PELIGRO: Race condition
doc = db.documents.get(doc_id)
doc.status = 'classified'
db.save(doc)  # 2 workers pueden sobrescribirse

# ✅ SEGURO: Transacción
with db.transaction():
    doc = db.documents.get_for_update(doc_id)
    doc.status = 'classified'
    db.save(doc)
```

### 13.2 Debugging distribuido

Harder to trace bugs cuando hay múltiples workers:
- Usar logging centralizado (ELK, DataDog)
- Trace IDs en todas las operaciones
- Dead letter queue para tareas fallidas

### 13.3 Network latency

Queue overhead: ~50-200ms por tarea  
**Solución**: Batch tareas si es apropiado

---

## 14. Referencias y recursos

### Documentación oficial

- PostgreSQL: https://www.postgresql.org/docs/
- Celery: https://docs.celeryproject.io/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic (migrations): https://alembic.sqlalchemy.org/

### Tutoriales recomendados (2024)

- "Building scalable systems with Celery" (Real Python)
- PostgreSQL Full Text Search
- Docker Compose for multi-service development
- Kubernetes StatefulSets para databases

### Stack similar in production

- Spotify (Celery + PostgreSQL)
- Mozilla (Celery job system)
- Instagram (PostgreSQL scaling)

---

## 15. Decisión recomendada para Epic Analyzer

### ✅ Roadmap propuesto: **Progressive rollout 3 fases**

```
┌─────────────────────────────────────┐
│  Fase 1: PostgreSQL (Sem 1-2)       │
│  • Persistencia de jobs/documents    │
│  • Backend modificado minimally      │
│  • En memoria para processing        │
│  • ROI: Histórico, auditoría         │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Fase 2: Celery básico (Sem 3-4)    │
│  • Redis + 4-6 workers              │
│  • Paralelismo: classification      │
│  • Monitoreo con Flower             │
│  • ROI: 2-3x speedup                │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Fase 3: Auto-scaling (Sem 5-8)     │
│  • Multi-queue, workers por type    │
│  • Dead letter queue                │
│  • Centralizado logging             │
│  • ROI: Escala a 1M+ documentos     │
└─────────────────────────────────────┘
```

### Quick checklist for Phase 1:

- [ ] Crear schema PostgreSQL (Scripts SQL)
- [ ] Alembic setup para migrations
- [ ] SQLAlchemy models (Job, Document, Entity, Cluster)
- [ ] Reemplazar in-memory store con BD queries
- [ ] Backups configurados
- [ ] Tests de persistencia

**Esfuerzo**: 1-2 sprints  
**Equipo**: 1-2 engineers  
**Risk**: Bajo (cambio incremental)

---

## Conclusión

**PostgreSQL + Celery para Epic Analyzer**:
1. ✅ **Persistencia**: Jobs y documentos nunca se pierden
2. ✅ **Disponibilidad**: HA con replicas
3. ✅ **Escalabilidad**: Desde 100k a 100M documentos
4. ✅ **Observabilidad**: Auditoría, logs, monitoring
5. ✅ **Operabilidad**: Backups, point-in-time recovery

**NOT Overkill**: La arquitectura crece con el proyecto:
- Fase 1: Monolith + PostgreSQL (años 1-2)
- Fase 2: Distributed workers (años 2-3)
- Fase 3: Microservices, K8s (años 3+)

**Next step**: Comenzar Phase 1 con persistencia PostgreSQL.

