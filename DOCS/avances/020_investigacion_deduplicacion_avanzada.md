# 020 — Investigación: Deduplicación Avanzada (Fase 5B)

**Estado**: 🔬 Implementado  
**Fecha**: 2026-04-07  
**Fase**: 5B — Deduplicación avanzada (complementa Fase 5 de Inteligencia Avanzada)

---

## Resumen ejecutivo

Epic Analyzer ya implementa detección de duplicados exactos mediante SHA-256. Esta fase
añade soporte para herramientas externas especializadas en detección de similitud visual y
deduplicación masiva, integrándolas como **workers opcionales** que no rompen el
comportamiento existente cuando no están instalados.

Las herramientas integradas son:

| Herramienta | Caso de uso | Capa |
|-------------|-------------|------|
| **Czkawka** | Imágenes/vídeos similares (no idénticos); caché de escaneo incremental | Capa 1 — Scanner |
| **dupeGuru** (modo Picture) | Pre-filtro visual antes de llamadas a Gemini (ahorro de tokens) | Capa 2 — Pre-Gemini |
| **rmlint** | Generación de scripts de shell auditables para limpieza física | Capa 3 — Reorganización |
| **jdupes** | Deduplicación masiva en background como worker Celery independiente | Capa 3 — Reorganización |

---

## Arquitectura híbrida

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Epic Analyzer (alphadx)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    CAPA DE INGESTA (Mejorada)                       │ │
│  │  ┌─────────────┐    ┌─────────────────────────────────────────────┐ │ │
│  │  │   Scanner   │───►│  DedupService (backend: native/czkawka/    │ │ │
│  │  │   (SHA-256) │    │  dupeguru — configurable via DEDUP_BACKEND) │ │ │
│  │  └─────────────┘    └──────────────────┬──────────────────────────┘ │ │
│  │                                        │                            │ │
│  │  ┌─────────────────────────────────────▼──────────────────────────┐ │ │
│  │  │  Filtro visual pre-Gemini (skip_visual_dedup=False por defecto) │ │ │
│  │  │  → Imágenes visualmente idénticas: se marca is_duplicate=True  │ │ │
│  │  │  → Solo archivos únicos visualmente llegan a Gemini            │ │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  │                              │                                      │ │
│  │                              ▼                                      │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │              Gemini Flash (solo archivos únicos)              │   │ │
│  │  │  • Clasificación semántica  • Extracción de entidades         │   │ │
│  │  │  • Detección de PII         • Análisis de relaciones          │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │              CAPA DE CLUSTERING Y ANÁLISIS (Actual)                 │ │
│  │  • Embeddings  • HDBSCAN  • Perfiles de grupo  • Similitud         │ │
│  │  • exact_duplicate_ratio y visual_duplicate_ratio en health_score  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │           CAPA DE EJECUCIÓN (Reorganización)                        │ │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │ │
│  │  │   rmlint    │    │   jdupes    │    │  Mover/Eliminar/Link   │  │ │
│  │  │ (generate-  │    │ (Celery     │    │  (reorganize execute)   │  │ │
│  │  │  script)    │    │  worker)    │    │                         │  │ │
│  │  └─────────────┘    └─────────────┘    └─────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Diseño de `DedupService`

### Backends soportados

**`native`** (predeterminado — sin dependencias externas):
- Usa el SHA-256 ya calculado por el scanner
- Sin cambio de comportamiento respecto a versiones anteriores

**`czkawka`** (opcional):
- Requiere `czkawka` instalado en el sistema (`czkawka_cli`)
- Ejecución como subproceso con output JSON
- Soporta: imágenes similares, vídeos similares, caché de escaneo incremental
- Parámetro de configuración: `DEDUP_SIMILARITY_THRESHOLD` (0.95 por defecto)

**`dupeguru`** (opcional, modo Picture):
- Requiere `dupeguru` instalado y accesible desde CLI
- Usado exclusivamente como pre-filtro visual antes de llamadas a Gemini
- Configurable con `DEDUP_SIMILARITY_THRESHOLD`

### Configuración en `.env`

```env
# Backend de deduplicación: native | czkawka | dupeguru
DEDUP_BACKEND=native

# Umbral de similitud para backends fuzzy (0.0–1.0; default 0.95)
DEDUP_SIMILARITY_THRESHOLD=0.95
```

### Interfaz pública

```python
class DedupService:
    def find_duplicates(self, file_indices: list[FileIndex]) -> list[FileIndex]:
        """Retorna la lista con is_duplicate actualizado según el backend activo."""
        ...
    
    def find_visual_duplicates(self, image_file_indices: list[FileIndex]) -> list[FileIndex]:
        """Filtra duplicados visuales. Solo aplica a imágenes (MIME image/*)."""
        ...
```

Ambos métodos **siempre retornan el mismo schema `FileIndex`** — la integración es
transparente para el resto del pipeline.

---

## Endpoint: `POST /api/reorganize/{job_id}/generate-script`

Alternativa no-destructiva al endpoint `/execute`. Genera un script de shell auditable
(estilo `rmlint`) que el operador puede revisar antes de ejecutar en el servidor.

**Comportamiento**:
1. Recupera el `reorganisation_plan` del job
2. Genera un script `.sh` con comandos `mv` comentados y verificados
3. Si `rmlint` está instalado en el sistema, lo usa; si no, genera el script nativo
4. Devuelve el script como `text/plain` descargable

**Respuesta de ejemplo**:
```bash
#!/bin/bash
# Epic Analyzer — Script de reorganización generado automáticamente
# Job: 550e8400-e29b-41d4-a716-446655440000
# Generado: 2026-04-07T02:00:00
# AVISO: Revisa este script antes de ejecutarlo. Los movimientos son IRREVERSIBLES.

set -euo pipefail

# Acción 1/3
mkdir -p "/Empresa/Organizado/Facturas"
mv "/datos/facturas/f2023.pdf" "/Empresa/Organizado/Facturas/a1b2c3d4"

# Acción 2/3
mkdir -p "/Empresa/Organizado/Contratos"
mv "/datos/varios/contrato_abc.docx" "/Empresa/Organizado/Contratos/e5f6g7h8"
```

---

## Worker Celery: `run_dedup_worker`

Tarea Celery independiente para deduplicación masiva en background, desacoplada del
pipeline principal de análisis semántico.

**Cuándo usar**:
- Corpus masivos donde la deduplicación debe ejecutarse sin bloquear la clasificación
- Pre-procesamiento nocturno de repositorios de fotos o vídeos corporativos
- Migraciones de SharePoint/Google Drive con volumen masivo

**Invocación**:
```python
from app.workers.tasks import run_dedup_worker
result = run_dedup_worker.delay(job_id="...", backend="jdupes")
```

**Resultado**:
```json
{
  "job_id": "...",
  "backend": "jdupes",
  "duplicates_found": 42,
  "groups": [{"sha256": "...", "files": ["path1", "path2"]}],
  "status": "completed"
}
```

---

## Impacto en métricas de Group Analysis

Los nuevos campos del `DataHealthReport` alimentan el health score de grupos:

| Campo nuevo | Descripción |
|-------------|-------------|
| `tokens_saved_by_visual_dedup` | Archivos imagen filtrados antes de Gemini |

Los `GroupFeatures` ya incluyen `duplicate_share` (ratio de duplicados exactos SHA-256).
Con `DEDUP_BACKEND=czkawka`, este valor también incorpora duplicados similares no exactos.

---

## Casos de uso habilitados

### Caso 1: Repositorio de fotos corporativas
1. `DEDUP_BACKEND=czkawka`
2. Czkawka detecta similitudes visuales (misma foto, diferente resolución)
3. Epic clasifica solo las únicas con Gemini (ahorro de tokens)
4. Reorganización inteligente con sugerencias semánticas

### Caso 2: Migración SharePoint/Google Drive
1. Ejecutar `run_dedup_worker` como pre-procesamiento con `backend=jdupes`
2. Epic Analyzer valida semánticamente (sin falsos positivos)
3. Migración limpia con script generado por `generate-script`

### Caso 3: Auditoría forense (Fase 6 Datashare)
1. `rmlint`/`jdupes` como pre-procesamiento masivo
2. Epic Analyzer para clasificación semántica del corpus depurado
3. Exportación a Datashare (ICIJ) del corpus único y clasificado

---

## Compatibilidad y retrocompatibilidad

- **Todos los backends externos son opcionales**: `DEDUP_BACKEND=native` es el default
- **Sin breaking changes**: el schema `FileIndex` y `DuplicateGroup` no se modifica
- **Docker**: `ARG ENABLE_DEDUP_TOOLS=false` en Dockerfile para instalación opcional
- **Tests**: los backends externos se mockean; los 174 tests existentes no se tocan
- **Degradación graceful**: si una herramienta CLI no está instalada, `DedupService`
  registra un warning y cae al backend `native` automáticamente

---

## Instalación de herramientas opcionales

Ver sección "Herramientas de Deduplicación Opcionales" en `OPERATOR_GUIDE.md`.

```bash
# Ubuntu/Debian
apt-get install rmlint jdupes

# Czkawka (desde GitHub releases)
wget https://github.com/qarmin/czkawka/releases/latest/download/linux_czkawka_cli
chmod +x linux_czkawka_cli && mv linux_czkawka_cli /usr/local/bin/czkawka_cli

# dupeGuru (AppImage)
# Ver: https://github.com/arsenetar/dupeguru/releases
```
