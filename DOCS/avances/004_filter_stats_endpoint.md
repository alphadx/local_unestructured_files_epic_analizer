---
fecha: 2026-04-05
status: ✅ COMPLETADO
categoría: Feature — Auditoría y Monitoreo
---

# Endpoint de Auditoría para Estadísticas de Filtrado

## Resumen

Implementado endpoint `/api/admin/filter-stats` para consultar estadísticas de archivos rechazados durante scans recientes. Permite auditoría y monitoreo de la aplicación de reglas de filtrado (MIME type y extensiones).

## Cambios Completados

### 1. Nueva función en scanner.py

Se agregó `scan_directory_with_stats()` que retorna:
- `(file_indices, stats_dict)` donde `stats_dict` contiene:
  - `skipped_by_filter`: lista de archivos rechazados con razón
  - `filters_applied`: booleano indicando si hay filtros activos

**Ventajas:**
- Mantiene compatibilidad con la función original `scan_directory()`
- Captura información de filtrado sin cambiar la API existente

### 2. Integración en pipeline (job_manager.py)

El paso 1/5 ahora:
- Usa `scan_directory_with_stats()` en lugar de `scan_directory()`
- Registra eventos de filtrado en el audit_log cuando se rechacen archivos
- Registra detalles: job_id, cantidad de rechazados, primeros 10 archivos con razones
- Emite log informativo al usuario mediante el websocket de logs

### 3. Nuevo router administrativo (routers/admin.py)

**Endpoint: `GET /api/admin/filter-stats`**

Parámetros de consulta:
- `job_id` (opcional): Filtrar por job específico
- `limit` (default=100, max=1000): Cantidad de registros a retornar
- `offset` (default=0): Paginación

**Respuesta:**
```json
{
  "total_scans_with_filters": 5,
  "total_files_filtered": 247,
  "scans": [
    {
      "job_id": "uuid-123",
      "timestamp": "2026-04-05T14:30:22Z",
      "skipped_count": 45,
      "skipped_files": [
        {"path": "/path/to/file.exe", "reason": "extension in blacklist: .exe"},
        {"path": "/path/to/lib.so", "reason": "extension in blacklist: .so"}
      ],
      "entry_id": "audit-entry-uuid"
    }
  ]
}
```

### 4. Registro en auditoría

Nuevo tipo de operación: `scan.files_filtered`
- Registra automáticamente cuando se aplica filtrado
- Incluye detalles de rechazo para cada archivo
- Permite auditoría y debugging de reglas incorrectas

### 5. Integración en aplicación (main.py)

- Importado nuevo router `admin`
- Incluido en la aplicación FastAPI mediante `app.include_router()`

## Tests

Archivo: `tests/test_admin_api.py`

Casos de prueba:
- ✅ Endpoint retorna estadísticas vacías cuando no hay filtrado
- ✅ Endpoint calcula correctamente totales
- ✅ Filtrado por job_id funciona correctamente
- ✅ Paginación con limit y offset funciona
- ✅ Acumulación de totales es correcta

## Ejemplo de uso

### Consultar estadísticas agregadas:
```bash
curl http://localhost:8000/api/admin/filter-stats
```

### Consultar estadísticas de un job específico:
```bash
curl "http://localhost:8000/api/admin/filter-stats?job_id=abc123-def456"
```

### Paginación:
```bash
curl "http://localhost:8000/api/admin/filter-stats?limit=50&offset=100"
```

## Implementación técnica

### Arquitectura

```
scan_directory_with_stats()
         ↓
  job_manager.run_pipeline()
         ↓
  audit_log.record("scan.files_filtered")
         ↓
  /api/admin/filter-stats
         ↓
  get_all(operation="scan.files_filtered")
```

### Conversión a auditoría

Los datos de filtrado se registran como:
```python
audit_log.record(
    "scan.files_filtered",
    actor="system",
    resource_id=job_id,
    resource_type="job",
    outcome="success",
    skipped_count=len(skipped),
    skipped_files=skipped[:10],  # Primeros 10 por brevedad
    filters_applied=True,
)
```

## Beneficios

✅ **Auditoría completa**: Cada scan con filtrado queda registrado permanentemente  
✅ **Debugging facilitado**: Identificar qué archivos se rechazan y por qué  
✅ **Monitoreo**: Seguimiento de cuántos archivos se filtran en el tiempo  
✅ **Cumplimiento normativo**: Trazabilidad de decisiones de ingesta  
✅ **Gestión de reglas**: Validar efectividad de política whitelist/blacklist  

## Próximos pasos

1. **Frontend dashboard**: Mostrar gráficos de filtrado en UI admin
2. **Alertas**: Configurar alertas si filtrado >threshold
3. **Exportación**: CSV/Excel de estadísticas de filtrado
4. **Historial ampliado**: Guardar TODOS los rechazados (actualmente almacena primeros 10)
5. **Reglas dinámicas**: Permitir cambiar reglas sin reiniciar

## Archivos afectados

```
✨  backend/app/routers/admin.py              (NEW, 87 líneas: endpoint admin)
✏️  backend/app/services/scanner.py           (+125 líneas: nueva función)
✏️  backend/app/services/job_manager.py       (+20 líneas: integración)
✏️  backend/app/main.py                       (+2 líneas: registro router)
✨  tests/test_admin_api.py                   (NEW, 151 líneas: tests)
```

## Compatibilidad

- ✅ Backward compatible con `scan_directory()` existente
- ✅ No requiere cambios en frontend
- ✅ Funciona con audit_log en memoria existente
- ✅ Compatible con Docker Compose actual
