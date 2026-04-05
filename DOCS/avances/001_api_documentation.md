# Avance 001: Documentación de Ejemplos de Uso de API

**Estado:** ✅ COMPLETADO  
**Fecha:** 2026-04-05  
**Prioridad Original:** Media  

---

## Resumen del Trabajo

Se ha creado documentación exhaustiva con ejemplos prácticos de request/response para los dos endpoints principales de búsqueda y análisis de corpus:

1. **`/api/search`** — Búsqueda híbrida (documentos + chunks) con filtrado por categoría, extensión y directorio
2. **`/api/rag/query`** — Consultas RAG (Retrieval-Augmented Generation) con contexto y respuesta generada

---

## Archivo Generado

**Ubicación:** [USAGE_EXAMPLES.md](../../USAGE_EXAMPLES.md)

### Contenidos

| Sección | Descripción |
|---------|-------------|
| **1. Búsqueda Documental** | Ejemplos básicos y avanzados de `/api/search` con filtros, interpretación de scopes y respuestas |
| **2. Consultas RAG** | Ejemplos de `/api/rag/query` incluyendo consultas simples, avanzadas y generación de respuestas |
| **3. Manejo de Errores** | Casos de error comunes (query vacía, parámetros fuera de rango) |
| **4. Guía de Integración** | Snippets de código en Python, JavaScript y bash |
| **5. Notas Importantes** | Explicación de scopes, scoring, job_id y rate limiting |

### Ejemplos Incluidos

#### Search
- ✅ Búsqueda simple por términos
- ✅ Búsqueda con filtros (categoría, extensión, directorio)
- ✅ Interpretación de facetas en respuesta
- ✅ Explicación de scopes (hybrid, documents, chunks, all)

#### RAG Query
- ✅ Consulta básica con generación de respuesta
- ✅ Consulta con job_id específico
- ✅ Recuperación de fuentes contextuales
- ✅ Manejo de respuestas sintetizadas

---

## Cambios a Archivos

### 1. README.md
✅ **Actualizado** — Se agregaron referencias a `USAGE_EXAMPLES.md` en la sección "Referencia de API":
- Enlace desde `/api/search` a ejemplos de búsqueda
- Enlace desde `/api/rag/query` a ejemplos de RAG

### 2. TODO.md
✅ **Actualizado** — Se marcó la tarea como completada:
- Ítems marcado con ~~tachado~~ + "✅ COMPLETADO"
- Referencia al archivo generado

---

## Criterios de Calidad Cumplidos

- ✅ `USAGE_EXAMPLES.md` contiene ejemplos exhaustivos con curl, Python y JavaScript
- ✅ `README.md` referencia el nuevo documento desde la sección de API
- ✅ `TODO.md` refleja el completamiento de la tarea
- ✅ Documentación creada en `DOCS/avances` para registro histórico
- ✅ Ejemplos incluyen casos de error y gestión de parámetros
- ✅ Notas de integración y best practices incluidas

---

## Próximos Pasos Relacionados

Las siguientes tareas quedan pendientes en Prioridad Media:

1. Añadir ejemplo de uso del websocket de logs en `/api/jobs/{job_id}/logs/ws`
2. Documentar integraciones remotas: Google Drive y SharePoint
3. Regenerar `frontend/package-lock.json` y consolidar stack CSS

---

## Referencias

- **Documento Principal:** [USAGE_EXAMPLES.md](../../USAGE_EXAMPLES.md)
- **README Modificado:** [README.md](../../README.md#referencia-de-api)
- **TODO Actualizado:** [TODO.md](../../TODO.md#prioridad-media-documentación-de-api-y-fuentes)
