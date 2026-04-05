---
fecha: 2026-04-05
status: ✅ COMPLETADO
categoría: Feature — Filtrado de Contenido
---

# Filtrado Inteligente por MIME Type y Extensiones

## Resumen

Implementado sistema configurable de filtrado de archivos en la etapa de escaneo para evitar procesar ejecutables, binarios y contenido no textual que no puede ser clasificado por Gemini.

## Cambios Completados

### 1. Configuración centralizada (`backend/app/config.py`)

Se agregaron 6 nuevas variables de entorno:

- **`INGESTION_MODE`**: Alterna entre dos estrategias:
  - `blacklist` (por defecto): Permite todo excepto lo explícitamente denegado
  - `whitelist`: Solo procesa lo explícitamente permitido

- **`ALLOWED_EXTENSIONS`**: Lista de extensiones permitidas en modo `whitelist` (ej: `.txt,.pdf,.docx`)

- **`DENIED_EXTENSIONS`**: Lista de extensiones denegadas en modo `blacklist`
  - Por defecto: `.exe,.dll,.so,.dylib,.bin,.app,.msi,.jar,.com,.bat,.cmd`

- **`ALLOWED_MIME_TYPES`**: Prefijos de MIME types permitidos (ej: `text/,image/,application/pdf`)

- **`DENIED_MIME_TYPES`**: Prefijos de MIME types denegados
  - Por defecto: `application/x-executable,application/x-sharedlib,application/x-dvi,application/x-java-applet`

> En modo `whitelist`, el sistema requiere al menos `ALLOWED_EXTENSIONS` o `ALLOWED_MIME_TYPES` para procesar archivos. Si no se configura ninguna regla de allow explícita, el filtro rechaza todo por defecto.

### 2. Módulo de utilidad (`backend/app/services/mime_filter.py`)

Nuevo módulo con funciones:

- **`_parse_list()`**: Parsea configuraciones CSV en sets normalizados
- **`should_process_file()`**: Valida un archivo contra reglas de filtrado
  - Retorna: `(should_process: bool, reason: str)`
- **`filter_file_index_list()`**: Filtra listas completas de `FileIndex`
  - Retorna: `(filtered_list, skipped_info)` con razones de exclusión

### 3. Integración en escáner (`backend/app/services/scanner.py`)

- Actualizada firma de `scan_directory()` para aceptar parámetros de configuración
- Filtrado aplicado al final de la ejecución (post-deduplicación)
- Se registra en logs: `skipped_by_filter` para auditoría

### 4. Integración en pipeline (`backend/app/services/job_manager.py`)

- Paso 1/5 del pipeline ahora pasa configuraciones a `scan_directory()`
- Usa `functools.partial()` para suministrar parámetros

## Beneficios

✅ **Evita procesamiento inútil**: Ejecutables, librerías compartidas y binarios se descartan en la etapa de escaneo  
✅ **Configurable**: Empresas pueden definir su propia política de ingesta (whitelist/blacklist)  
✅ **Casos de uso**:
  - **Whitelist**: Entornos regulados; solo procesar tipos conocidos y validados
  - **Blacklist**: Entornos abiertos; rechazo flexible de contenido peligroso

## Ejemplos de uso

### Modo Blacklist (por defecto)
```bash
# Solo deniega ejecutables, se procesan archivos normales
docker-compose up
```

### Modo Whitelist
```bash
# Solo acepta documentos y PDFs
docker-compose -f docker-compose.yml up -d backend
INGESTION_MODE=whitelist \
ALLOWED_EXTENSIONS=.txt,.pdf,.docx,.xlsx \
ALLOWED_MIME_TYPES=text/,image/,application/pdf,application/msword,application/vnd. \
uvicorn app.main:app --reload
```

## Próximos pasos

1. **Frontend**: Exponer configuración de filtrado en la UI de inicio de jobs
2. **Documentación de despliegue**: Agregar sección recomendando reglas por sector
3. **Auditoría**: Endpoint `/api/admin/filter-stats` para ver qué se está rechazando
4. **Benchmarks**: Comparar tiempo de escaneo antes/después del filtrado

## Release Notes

- Corrección de la lógica de ingestión: `whitelist` ahora exige al menos una regla de allow explícita y rechaza todo si no existen reglas de aprobación.
- Se reforzó el comportamiento de `blacklist` para bloquear extensiones denegadas en el pipeline completo.
- Cobertura E2E añadida en `tests/test_api.py` para validar que los filtros de ingestión se aplican desde el endpoint `/api/jobs` hasta el reporte final.
- Actualización de documentación en `README.md` y este documento para reflejar la semántica estricta de `whitelist`.

## Tests esperados

- `test_mime_filter.py`: Cobertura de `_parse_list()`, `should_process_file()`, `filter_file_index_list()`
- `test_scanner.py`: Verificar que `detected_extensions` y `skipped_by_filter` se registren correctamente
- Integración: Confirmar que ejecutables no llegan a `gemini_service`
- `tests/test_api.py`: E2E pipeline completo para validar que los filtros de `whitelist`/`blacklist` se aplican desde el endpoint hasta el reporte final

## Archivos afectados

```
✏️  backend/app/config.py                    (+14 líneas: configuración)
✏️  backend/app/services/scanner.py          (+20 líneas: integración)
✨  backend/app/services/mime_filter.py      (NEW, 110 líneas: módulo completo)
✏️  backend/app/services/job_manager.py      (+7 líneas: llamada con parámetros)
✏️  README.md                                (+6 líneas: documentación de variables)
```
