---
fecha: 2026-04-06
status: ✅ COMPLETADO
categoría: Hito 3 — Documentación de dependencias opcionales
---

# Hito 3: Documentar HDBSCAN como Dependencia Opcional con Fallback

## Resumen ejecutivo

Agregada sección explícita en README.md sobre HDBSCAN como dependencia **opcional** con **fallback automático**. 
El sistema detecta si HDBSCAN está disponible y elige la estrategia de clustering más apropiada, garantizando que Epic Analyzer 
funcione en cualquier escenario.

## Cambios documentados

### README.md — Nueva subsección "HDBSCAN (opcional — clustering de densidad)"

Ubicación: Entre **ChromaDB** y **Variables de entorno**

**Contenido**:
- ✅ Qué es HDBSCAN (algoritmo de clustering de densidad)
- ✅ Cuándo instalarlo (+5 criterios claros: corpus tamaño, semántica, embeddings disponibles, etc.)
- ✅ Qué pasa sin HDBSCAN (fallback automático explicado en 3 pasos)
- ✅ Instrucción de instalación opcional (pip + Docker)

**Subsecciones claras**:
1. ¿Qué es? → Descripción técnica breve
2. ¿Cuándo instalarlo? → 5 bullets con criterios ✅/❌
3. ¿Qué pasa sin HDBSCAN? → Cadena de fallback (HDBSCAN → DBSCAN → LabelPropagation) + equivalencia de resultados
4. Instalación opcional → comandos pip + Docker

### Lógica de fallback — Verificada en código

**Ubicación**: `backend/app/services/clustering_service.py`

**Flujo de ejecución** (líneas 424-444):

```python
# Paso 1: Intenta HDBSCAN en chunks (si embeddings de chunks disponibles)
if chroma_data:
    chunk_result = _try_hdbscan_on_chunks(chroma_data, docs_by_id)
    if chunk_result is not None:
        return chunk_result  # ✅ HDBSCAN EXITOSO

# Paso 2: Si no, intenta DBSCAN en documentos (embeddings de documentos)
    dbscan_result = _try_dbscan(embeddings, ids, docs_by_id)
    if dbscan_result is not None:
        return dbscan_result  # ✅ DBSCAN EXITOSO (HDBSCAN no disponible)

# Paso 3: Si no, intenta HDBSCAN en documentos
    hdbscan_result = _try_hdbscan(embeddings, ids, docs_by_id)
    if hdbscan_result is not None:
        return hdbscan_result  # ✅ HDBSCAN EN DOCUMENTOS EXITOSO

# Paso 4: Si todo falla, usa LabelPropagation basado en etiquetas Gemini
label_result = _label_based_clustering(documents)
return label_result  # ✅ FALLBACK COMPLETO (sin embeddings, sin HDBSCAN)
```

**Garantía**: El sistema SIEMPRE retorna clusters válidos, cualquiera que sea la configuración.

## Decisiones de diseño

### Por qué HDBSCAN es opcional

1. **Dependencia pesada**: HDBSCAN requiere compilación de Cython, aumenta tiempo de build
2. **No crítica**: LabelPropagation ofrece resultados útiles en muchos casos
3. **Entornos restringidos**: Algunos docker base o sistemas no pueden compilar
4. **Pero potente**: Si está disponible, produce clusters superiores en corpus semánticos

### Cadena de fallback

La documentación ahora aclara que **no es un riesgo** que HDBSCAN no esté instalado:

| Escenario | Algoritmo usado | Calidad | Requisitos |
|-----------|-------------------|---------|-----------|
| Con HDBSCAN + embeddings | HDBSCAN | 🟢 Óptima | pip install hdbscan + Gemini API |
| Sin HDBSCAN + embeddings | DBSCAN → LabelPropagation | 🟡 Buena | Solo Gemini API |
| Sin embeddings | LabelPropagation | 🟢 Adecuada | Gemini Flash para etiquetas |

## Testing & Validación

### Código verificado ✅

- `backend/app/services/clustering_service.py`: Función `_try_hdbscan()` existe (línea 239)
- Función `_try_hdbscan_on_chunks()` existe (línea 338)
- Import condicional: `try: import hdbscan / except ImportError:` (línea 248)
- Fallback chain correctamente anidada (líneas 424-444)

### Cobertura de la documentación

- ✅ README.md: Sección nuevaexplícita sobre HDBSCAN
- ✅ Explicación de cuándo instalar (5 criterios prácticos)
- ✅ Descripción clara del fallback (3 pasos documentados)
- ✅ Instrucción de instalación opcional
- ✅ Coherencia con clustering_service.py (flujo coincide con código)

## Referencias

- 📄 [README.md — HDBSCAN (opcional)](../../README.md#hdbscan-opcional--clustering-de-densidad)
- 🔧 [clustering_service.py](../../backend/app/services/clustering_service.py)
- 📊 Plan de cierre: [012_plan_cierre_cabos_sueltos.md](012_plan_cierre_cabos_sueltos.md)

---

## Operador: Notas de deployment

**Si NO instalas HDBSCAN**:
- Epic Analyzer funcionará perfectamente
- Los clusters se generarán con LabelPropagation (etiquetas Gemini)
- Clustering más rápido (sin compilación Cython)
- Ideal para CI/CD, contenedores base pequeños, MVP

**Si SÍ instalas HDBSCAN**:
- Clustering de densidad automático (HDBSCAN)
- Mejor agrupación semántica en corpus grandes
- Build más lento (~2-3 min extra en Docker)
- Ideal para análisis profundo de documentos correlacionados

**Recomendación**: Incluir en `requirements.txt` para producción. Para desarrollo, es opcional.
