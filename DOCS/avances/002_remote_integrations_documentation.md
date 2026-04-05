# Documentación de Integraciones Remotas: Google Drive y SharePoint

**Fecha:** 05 de abril de 2026  
**Tarea Completada:** Documentar las integraciones remotas de origen (Google Drive y SharePoint)

## Resumen

Se ha completado la documentación exhaustiva de las integraciones remotas en el archivo [USAGE_EXAMPLES.md](../../USAGE_EXAMPLES.md), Sección 4. Se incluyen:

### Google Drive

- **Configuración de Credenciales**: Guía paso a paso para:
  - Crear cuenta de servicio en Google Cloud Console
  - Habilitar Google Drive API
  - Generar clave JSON
  - Compartir carpetas en Google Drive
  - Configurar variables de entorno

- **Request/Response Examples**:
  - POST `/api/jobs` con `source_provider: "google_drive"`
  - Parámetros: `folder_id`, `service_account_json` (inline o via env)
  - Response con `job_id`, `status`, `progress`

- **Code Examples**:
  - Python con `requests` library
  - Bash curl commands
  - WebSocket monitoring integration

- **Notas Técnicas**:
  - Exportación de tipos de archivo Google (Docs → TXT, Sheets → CSV, Presentations → PDF)
  - Requisitos de permisos
  - Preservación de jerarquía de carpetas
  - Detección de duplicados por SHA256
  - Rate limiting de Google Drive API

### SharePoint

- **Configuración de Credenciales (Azure AD)**: Guía paso a paso para:
  - Registrar aplicación en Azure Portal
  - Configurar credenciales (Tenant ID, Client ID, Client Secret)
  - Otorgar permisos Microsoft Graph (Files.Read.All, Sites.Read.All, Drives.Read.All)
  - Obtener Site ID y Drive ID
  - Configurar variables de entorno

- **Request/Response Examples**:
  - POST `/api/jobs` con `source_provider: "sharepoint"`
  - Parámetros: `site_id`, `drive_id`, `path` (ruta dentro del drive)
  - Response con job metadata

- **Code Examples**:
  - Python con `requests` library
  - WebSocket monitoring para SharePoint jobs
  - Bash curl commands

- **Notas Técnicas**:
  - Autenticación via Microsoft Graph API
  - Soporte multi-tenant
  - Descarga de versión actual (sin historiales)
  - Rate limiting de Microsoft Graph

### Tabla Comparativa

Se añadió tabla resumen distinguiendo características entre:
- Local (sistema de archivos)
- Google Drive (API + carpetas compartidas)
- SharePoint (Azure AD + librerías de documentos)

### Ejemplo Multi-Source

Se proporciona script Bash completo que:
- Inicia escaneo local
- Inicia escaneo Google Drive
- Inicia escaneo SharePoint
- Monitorea los tres jobs en paralelo
- Reporta finalización

## Archivos Modificados

- **USAGE_EXAMPLES.md**:
  - Nueva Sección 4: "Integraciones Remotas: Google Drive y SharePoint"
  - Actualizada numeración de secciones posteriores (5 → 6, 6 → 7, etc.)
  - Nuevas subsecciones en "Manejo de Errores" para Google Drive y SharePoint

- **TODO.md**:
  - Marcada tarea "Documentar las integraciones remotas de origen" como ✅ COMPLETADO
  - Referencia añadida a Sección 4 del USAGE_EXAMPLES.md

## Validaciones Realizadas

✅ Configuración de credenciales validada contra `backend/app/services/source_service.py`  
✅ Modelos de request/response validados contra `backend/app/models/schemas.py`  
✅ Endpoints verificados en `backend/app/routers/jobs.py`  
✅ Flujos de Python y Bash probados contra fuente de integración  
✅ Documentación de errores alignada con validaciones de Pydantic  

## Próximos Pasos

1. Revisar si la configuración de filtrado debe exponerse también en frontend
2. Evaluar si las reglas de `mime_type` y extensiones deben quedar reflejadas en la guía de despliegue
3. Regenerar `frontend/package-lock.json` y consolidar stack CSS

## Notas Técnicas Clave

### Google Drive

```python
# Credenciales como JSON
service_account_info = {
    "type": "service_account",
    "project_id": "...",
    "private_key": "...",
    "client_email": "..."
}
```

### SharePoint

```python
# OAuth2 via Azure AD
token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
```

Ambos flujos requieren configuración previa en sus respectivas plataformas (Google Cloud, Azure AD).
