## Frontend del analizador

Este frontend es el dashboard de [Analizador de Archivos No Estructurados](../README.md). Consume la API FastAPI del backend y expone las vistas de análisis, grupos, auditoría, búsqueda y RAG.

## Desarrollo local

```bash
npm install
npm run dev
```

Abre [http://localhost:3000](http://localhost:3000) para ver la interfaz.

## Variables útiles

- `NEXT_PUBLIC_API_URL`: URL base del backend. Útil si el backend no está en `http://localhost:8080`.

## Pestañas del dashboard

- `dashboard`: configuración del escaneo y seguimiento del job.
- `clusters`: mapa visual de clusters semánticos.
- `groups`: análisis por grupos de directorio.
- `audit`: registro de auditoría.
- `exploration`: exploración del corpus.
- `search`: búsqueda híbrida con filtros.
- `rag`: consulta asistida sobre el corpus indexado.
