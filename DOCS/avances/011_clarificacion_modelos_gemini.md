---
fecha: 2026-04-05
status: ✅ COMPLETADO
categoría: Documentation — Clarificación de modelos Gemini
---

# Clarificación de `GEMINI_FLASH_MODEL` y `GEMINI_EMBEDDING_MODEL`

## Resumen

Se documentó la diferencia entre ambos parámetros de configuración para evitar confusiones al ajustar el pipeline.

## Aclaración funcional

### `GEMINI_FLASH_MODEL`

Modelo usado en la etapa de clasificación y análisis semántico del documento. Se aplica cuando el backend necesita interpretar contenido y producir metadata estructurada, resúmenes, categorías o señales de negocio.

### `GEMINI_EMBEDDING_MODEL`

Modelo usado para convertir texto en vectores numéricos. Es la base de la búsqueda semántica, la comparación por similitud y el clustering a partir de embeddings.

## Regla práctica

- Si el objetivo es entender el contenido, clasificarlo o resumirlo, se usa `GEMINI_FLASH_MODEL`.
- Si el objetivo es representar el texto como vector para comparar documentos, se usa `GEMINI_EMBEDDING_MODEL`.

## Impacto

La documentación ahora deja explícito que ambos valores no son intercambiables y que cumplen roles distintos dentro del pipeline.
