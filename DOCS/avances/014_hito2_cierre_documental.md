---
fecha: 2026-04-06
status: ✅ COMPLETADO
categoría: Feature — Documentación operativa
---

# Hito 2 — Cierre documental: Estrategia de ingesta

## Objetivo

Dejar la configuración de despliegue (filtrado de ingesta) completamente documentada, sin contradicciones entre README, USAGE_EXAMPLES y código actual.

## Cambios realizados

### 1. Nueva sección en README.md

**Título**: "Configuración de despliegue: Estrategia de ingesta"

**Contenido**:
- Explicación clara de whitelist vs blacklist
- Detecci\u00f3n temprana autom\u00e1tica de binarios
- 3 ejemplos pr\u00e1cticos por sector:
  - **Corporativo** (whitelist): solo PDF, Word, Excel
  - **Repositorio abierto** (blacklist): rechaza ejecutables y comprimidos 
  - **Investigaci\u00f3n forense** (whitelist estricto): solo documentos legales
- Tabla comparativa de 5 escenarios
- 3 formas de cambiar estrategia (sin reiniciar si es por frontend)
- Auditoría de filtrado via endpoint `/api/admin/filter-stats`

**Ubicaci\u00f3n**: Secci\u00f3n nueva entre "Variables de entorno" y "Referencia de API"

### 2. Nuevas secciones en USAGE_EXAMPLES.md

**Nuevo contenido**: "5. Configuraci\u00f3n de filtrado de ingesta"

**Incluye**:

#### Escenario A: Modo Whitelist
```json
curl -X POST /api/jobs -d '{
  "ingestion_mode": "whitelist",
  "allowed_extensions": [".pdf", ".docx", ".xlsx"],
  "allowed_mime_types": ["text/", "application/pdf"]
}'
```
**Resultado**: Procesa solo documentos de negocio

#### Escenario B: Modo Blacklist
```json
curl -X POST /api/jobs -d '{
  "ingestion_mode": "blacklist",
  "denied_extensions": [".exe", ".dll", ".so", ".zip", ".tar", ".gz"],
  "denied_mime_types": ["application/x-executable", "application/zip"]
}'
```
**Resultado**: Todo excepto ejecutables y comprimidos

#### Escenario C: Detecci\u00f3n temprana de binarios
- Explica qu\u00e9 se salta autom\u00e1ticamente
- Logging DEBUG: "Archivo binario detectado, saltando..."
- Ejemplo de auditor\u00eda completo con response de `/api/admin/filter-stats`

### 3. Referencias cruzadas coherentes

Verificado que NO haya contradicciones:
- **README**: Variables env + tabla de conf recomendadas + ejemplos
- **USAGE_EXAMPLES**: JSON requests completos + responses reales
- **DOCS/avances/003_mime_type_filtering.md**: Semántica técnica (ya existía, intacta)
- **DOCS/avances/013_hito1_endurecimiento_ingesta.md**: Implementación binarios (ya existía, referenciada)

### 4. Archivos modificados

```
✏️  README.md                            (+180 líneas: nueva sección de despliegue)
✏️  USAGE_EXAMPLES.md                    (+120 líneas: 3 escenarios de filtrado)
✏️  DOCS/avances/012_plan_cierre_cabos_sueltos.md  (referencia a Hito 2)
```

## Criterios de terminado

✅ Un operador nuevo puede configurar filtrado SIN tocar código  
✅ README, USAGE_EXAMPLES y docs de avance dicen lo mismo  
✅ Ejemplos prácticos de blacklist/whitelist en ambos documentos  
✅ Tabla de recomendaciones por sector en README  
✅ Auditoría explicada: cómo validar qué se rechazó  
✅ Tres formas de cambiar estrategia: env, API, frontend  

## Documentación final para operadores

### Flujo rápido: Corporativo (whitelist)

1. **Configurar en `.env`**:
   ```bash
   INGESTION_MODE=whitelist
   ALLOWED_EXTENSIONS=.txt,.pdf,.docx,.xlsx
   ```

2. **Lanzar escaneo desde frontend** (sin reinicio):
   - Ir a formulario de nuevo job
   - Seleccionar "Filter Configuration"
   - Elegir modo y extensiones
   - Lanzar scan

3. **Auditar rechazos**:
   ```bash
   curl http://localhost:8080/api/admin/filter-stats?job_id=<JOB_ID>
   ```

### Tabla decisoria

| Necesito... | Usar... | Configurar... |
|-----------|---------|---------------|
| Solo documentos legales | whitelist | `ALLOWED_EXTENSIONS=.pdf,.msg,.eml` |
| Repositorio abierto sin ejecutables | blacklist | `DENIED_EXTENSIONS=.exe,.zip,.so` |
| Solo documentos internos | whitelist | `ALLOWED_MIME_TYPES=text/,application/pdf` |
| GitHub/GitLab típico | blacklist | Defaults suficientes |
| Máxima seguridad | whitelist | Lista mínima de extensiones |

## Próximos pasos (Hito 3+)

- Hito 3: Documentar fallback de HDBSCAN
- Hito 4: E2E final con todos los tests pasando
