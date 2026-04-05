# TODO

## Prioridad alta: búsqueda y filtrado documental

- Definir e implementar ranking híbrido para búsqueda documental.
	- Evaluar BM25 como capa textual principal.
	- Combinar BM25 con señales vectoriales y metadatos cuando aplique.
- Añadir filtrado por `mime_type` antes de enviar contenido al LLM.
	- Evitar clasificar binarios, ejecutables o archivos no textuales.
	- Mantener la decisión de filtrado cerca del scanner o del extractor.
- Introducir listas configurables de extensiones permitidas y denegadas.
	- Soportar modo de ingesta basado en lista blanca.
	- Soportar modo alternativo de ingesta de "todo" con exclusiones explícitas.
	- Permitir lista negra para bloquear extensiones concretas aunque estén permitidas por defecto.

## Prioridad media: documentación de API y fuentes

- ~~Documentar ejemplos de request/response para `/api/search` y `/api/rag/query`.~~ ✅ **COMPLETADO** — Archivo [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) creado con ejemplos exhaustivos.
- ~~Añadir un ejemplo de uso del websocket de logs en `/api/jobs/{job_id}/logs/ws`.~~ ✅ **COMPLETADO** — Sección 3 en [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) con ejemplos en Python, JavaScript, Bash y flujo completo.
- ~~Documentar las integraciones remotas de origen: Google Drive y SharePoint.~~ ✅ **COMPLETADO** — Sección 4 en [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) con guías de configuración de credenciales, ejemplos de request/response, flujos Python y bash para ambos proveedores.
- Regenerar `frontend/package-lock.json` y consolidar el stack CSS para volver a `npm ci` en la imagen Docker.

## Prioridad baja: seguimiento y soporte

- Revisar si la configuración de filtrado debe exponerse también en frontend.
- Evaluar si las reglas de `mime_type` y extensiones deben quedar reflejadas en la guía de despliegue.
