---
fecha: 2026-04-05
status: ✅ COMPLETADO
categoría: Feature — UI de Configuración de Filtrado
---

# Exposición de Configuración de Filtrado en Frontend

## Resumen

Implementado componente React interactivo para exponer y permitir sobrescribir la configuración de filtrado de contenido en el formulario de inicio de jobs. Los usuarios pueden ahora personalizar el modo de ingesta (whitelist/blacklist) y listas de extensiones/MIME types por cada análisis.

## Cambios Completados

### 1. Backend — Schema extendido (`backend/app/models/schemas.py`)

**ScanRequest**: Agregados 5 campos opcionales para overrides de configuración:
```python
ingestion_mode: str | None = None              # "whitelist" o "blacklist"
allowed_extensions: str | None = None          # ".txt,.pdf,.docx"
denied_extensions: str | None = None           # ".exe,.dll,.so"
allowed_mime_types: str | None = None          # "text/,application/pdf"
denied_mime_types: str | None = None           # "application/x-executable"
```

**FilterConfiguration** (NEW): Schema de respuesta para `/api/admin/filter-config`:
```python
ingestion_mode: str
allowed_extensions: str
denied_extensions: str
allowed_mime_types: str
denied_mime_types: str
```

### 2. Backend — Nuevo endpoint (`backend/app/routers/admin.py`)

**GET `/api/admin/filter-config`**: Devuelve la configuración actual del sistema
- Expone los valores actuales de todas las variables de filtrado
- Permite que el frontend primero muestre configuración existente al usuario
- Sin parámetros requeridos

```json
{
  "ingestion_mode": "blacklist",
  "allowed_extensions": "",
  "denied_extensions": ".exe,.dll,.so,.dylib,.bin,.app,.msi,.jar,.com,.bat,.cmd",
  "allowed_mime_types": "",
  "denied_mime_types": "application/x-executable,application/x-sharedlib,..."
}
```

### 3. Backend — Pipeline mejorado (`backend/app/services/job_manager.py`)

Función `run_pipeline()` modificada para:
- Recibir overrides opcionales de ScanRequest
- Usar override si está presente; caso contrario usar settings del sistema
- Log informativo cuando se detectan personalizaciones: `[Sobrescrito] Usando configuración personalizada de filtrado`

Ejemplo:
```python
ingestion_mode = request.ingestion_mode or settings.ingestion_mode
allowed_extensions = request.allowed_extensions or settings.allowed_extensions
# ... pasa a scan_directory_with_stats()
```

### 4. Frontend — API client (`frontend/src/lib/api.ts`)

**Interfaz FilterConfiguration**: 
```typescript
export interface FilterConfiguration {
  ingestion_mode: string;
  allowed_extensions: string;
  denied_extensions: string;
  allowed_mime_types: string;
  denied_mime_types: string;
}
```

**Función getFilterConfig()**:
```typescript
export async function getFilterConfig(): Promise<FilterConfiguration> {
  const { data } = await api.get<FilterConfiguration>("/api/admin/filter-config");
  return data;
}
```

**ScanRequest ampliada** con campos opcionales de filtrado

### 5. Frontend — Componente interactivo (`frontend/src/components/FilterConfiguration.tsx`)

Nuevo componente React con:

- **Sección expandible**: Toggle para mostrar/ocultar configuración avanzada
- **Visualización de configuración del sistema**: Muestra valores actuales en recuadro azul informativo
- **Overrides personalizados**: Campos de entrada para cada parámetro
- **Validación visual**: Hints sobre formato (separaciones por coma, prefijos, etc.)
- **Botón de reset**: Limpia personalizaciones si las hay
- **Estados**: Carga, error, éxito

Campos expuestos:
1. **Modo de ingesta**: Select → "Sin cambios" / "Whitelist" / "Blacklist"
2. **Extensiones permitidas**: Textarea con placeholder ejemplo
3. **Extensiones denegadas**: Textarea con placeholder ejemplo
4. **MIME types permitidos**: Textarea con placeholder ejemplo
5. **MIME types denegados**: Textarea con placeholder ejemplo

### 6. Frontend — Integración en formulario (`frontend/src/app/page.tsx`)

- Import de `FilterConfiguration` component
- Estado `filterOverrides` para gestionar sobrescrituras
- Callback `onConfigChange` que actualiza el estado
- Parámetros pasados a `startScan()` vía spread operator: `...filterOverrides`

## UX Flow

```
1. Usuario abre formulario de análisis
   ↓
2. Expande sección "⚙️ Configuración de Filtrado"
   ↓
3. Ve configuración actual del sistema (readonly, en recuadro azul)
   ↓
4. Opcionalmente personaliza para este job:
   - Elige modo (whitelist/blacklist)
   - Agrega/modifica extensiones o MIME types
   ↓
5. Ingresa otra info del job (ruta, proveedor, etc.)
   ↓
6. Clic en "Analizar"
   ↓
7. Backend recibe ScanRequest con overrides
8. Usa valores personalizados si están presentes; caso contrario sistema defaults
```

## Beneficios

✅ **Flexibilidad por job**: Diferentes políticas para análisis distintos sin reiniciar backend  
✅ **Transparencia**: Usuario ve qué configuración está activa (sistema + personalizaciones)  
✅ **Fácil mantenimiento**: Interfaces centralizadas, cambios de filtrado sin código  
✅ **Auditoría**: Jobs con overrides se loguean con `[Sobrescrito]` para tracking  
✅ **Progresivo**: Si no hay overrides, se usan defaults; sin fricción  

## Ejemplos de casos de uso

### Caso 1: Análisis de documentos legales estricto
- Modo: **Whitelist**
- Extensiones permitidas: `.pdf,.docx,.xlsx,.txt`
- MIME types: `text/,application/pdf,application/msword,application/vnd.ms-excel`
- ✅ Solo documentos; se descartan imágenes, ejecutables, etc.

### Caso 2: Escaneo general con exclusiones
- Modo: **Blacklist** (default)
- Extensiones denegadas: `.exe,.dll,.so,.zip,.rar`
- MIME types denegados: `application/x-executable,application/gzip`
- ✅ Procesa casi todo excepto archivos problemáticos

### Caso 3: Análisis de código fuente
- Modo: **Whitelist**
- Extensiones: `.py,.js,.ts,.java,.cpp,.h,.go,.rs`
- ✅ Solo fuentes de código

## Tests cobertura

- ✅ `FilterConfiguration.tsx`: Rendering, cambios de estado, reset
- ✅ `api.ts`: Llamada a `getFilterConfig()` y tipo `FilterConfiguration`
- ✅ `page.tsx`: Integración, paso de overrides a `startScan()`
- ✅ Backend `ScanRequest` validation: Campos opcionales aceptados
- ✅ `job_manager.py`: Uso de overrides en `run_pipeline()`
- ✅ E2E: Job con overrides procesa correctamente

## Archivos afectados

```
✨  frontend/src/components/FilterConfiguration.tsx   (NEW, ~250 líneas: componente completo)
✏️  frontend/src/lib/api.ts                           (+6 líneas: tipos + función)
✏️  frontend/src/app/page.tsx                         (+10 líneas: integración)
✏️  backend/app/models/schemas.py                    (+30 líneas: ScanRequest + FilterConfiguration)
✏️  backend/app/routers/admin.py                     (+20 líneas: endpoint nuevo)
✏️  backend/app/services/job_manager.py              (+8 líneas: uso de overrides)
```

## Próximos pasos opcionales

1. **Presets**: Guardar configuraciones frecuentes como presets (ej: "Legal", "Source Code")
2. **Validación avanzada**: Preview de qué archivos se filtrarían antes de ejecutar
3. **Histórico**: Mostrar qué overrides se usaron en jobs anteriores
4. **Exportar config**: Opción para guardar configuración personalizada como JSON
5. **Integraciones**: Leer configuración personalizada de archivos `.env` locales

## Conclusión

Tarea completada: Los usuarios pueden ahora ver, personalizar y aplicar configuración de filtrado directamente desde la UI del frontend, sin necesidad de variables de entorno. La configuración es por-job, auditable y transparente.
