---
fecha: 2026-04-06
status: ✅ COMPLETADO
categoría: Feature — Endurecimiento de pipeline
---

# Hito 1 — Endurecimiento del pipeline de ingesta

## Objetivo

Evitar procesamiento innecesario de archivos binarios (ejecutables, comprimidos, imágenes, vídeos) que no generan contenido textual útil para Gemini.

## Problema

Antes de este cambio:
- Archivos binarios (`.exe`, `.zip`, `.png`, `.mp4`, etc.) se intentaban procesar a través de `unstructured`
- La función intentaba extracción, fallaba silenciosamente, y retornaba vacío
- Esto era trabajo innecesario que ralentizaba el pipeline

Después:
- Detección temprana de binarios en base a extensión o MIME type
- Skip inmediato sin intentar extracción
- Logging explícito de qué se saltó y por qué

## Cambios implementados

### 1. Detección de binarios (`document_extraction_service.py`)

Agregadas dos constantes de configuración:

```python
_BINARY_MIME_PREFIXES = {
    "image/", "video/", "audio/",
    "application/x-executable",
    "application/x-sharedlib",
    "application/gzip", "application/zip",
    # ... (20+ tipos binarios comunes)
}

_BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib",
    ".zip", ".tar", ".gz", ".rar",
    ".jpg", ".png", ".gif", ".mp4",
    # ... (30+ extensiones)
}
```

Nueva función `_is_binary_file(file_index)`:
- Checa extensión primero (rápido)
- Fallback a MIME type si extensión no coincide
- Retorna `bool` indicando si es binario

Modificación a `extract_document_content()`:
- Check temprano: si `_is_binary_file()` → retornar `DocumentExtraction(..., extraction_method="skipped_binary")`
- No intenta `unstructured` ni lectura de texto
- Logging DEBUG: qué archivo, qué extensión, qué MIME

### 2. Mejorado logging en pipeline (`job_manager.py`)

Paso 2 del pipeline ahora diferencia:
- **Binarios**: log DEBUG "Archivo binario detectado, saltando: {path}"
- **Sin contenido textual**: log INFO "Archivo sin texto extraído, omitiendo..."
- Facilita debugging y auditoría

### 3. Tests agregados (`test_document_extraction.py`)

Nuevos tests validando:

```python
test_skips_binary_file_by_extension()
  → archivos .exe, .dll retornan extraction_method="skipped_binary"

test_skips_binary_file_by_mime_type()
  → archivos image/jpeg, image/png idem

test_skips_compressed_archive()
  → archivos .zip, .tar retornan vacío sin intentar extracción
```

Todos los tests verifican:
- `extraction_method == "skipped_binary"`
- `text == ""`
- `chunks == []`
- `element_count == 0`

## Beneficios

✅ **Rendimiento**: No intenta extraer binarios (sin valor semántico)  
✅ **Claridad operativa**: Logging explícito diferencia binarios de archivos sin contenido  
✅ **Mantenibilidad**: Listas centralizadas de tipos binarios, fácil actualizar  
✅ **Cobertura**: Tests unitarios + E2E validando el comportamiento  

## Compatibilidad

- ✅ Backward compatible: solo agrega `extraction_method="skipped_binary"` al pipeline
- ✅ Paso 2 ya tenía check `if not extraction.text and not extraction.chunks` y sigue saltándolos
- ✅ No cambia API ni contrato de `DocumentExtraction`

## Pruebas

**Unitarias**:
```bash
pytest tests/test_document_extraction.py::test_skips_binary_file_by_extension -xvs
pytest tests/test_document_extraction.py::test_skips_binary_file_by_mime_type -xvs
pytest tests/test_document_extraction.py::test_skips_compressed_archive -xvs
```

**E2E** (ya existentes, sigue pasando):
```bash
pytest tests/test_api.py::test_start_scan_e2e_pipeline_applies_filters -xvs
```

## Archivos modificados

```
✏️  backend/app/services/document_extraction_service.py   (+95 líneas: constantes + función + early skip)
✏️  backend/app/services/job_manager.py                   (+8 líneas: logging mejorado)
✏️  tests/test_document_extraction.py                     (+63 líneas: 3 nuevos tests)
```

## Próximos pasos (Hito 2+)

- Hito 2: Documentar reglas en guía de despliegue
- Hito 3: Explicar fallback de HDBSCAN
- Hito 4: E2E final
