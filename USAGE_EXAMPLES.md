# Ejemplos de Uso de API

Esta guía proporciona ejemplos prácticos de request/response para los endpoints principales de la API.

---

## 1. Búsqueda Documental (`/api/search`)

### Descripción
Busca documentos en el corpus indexado, soportando filtrado por categoría, extensión, directorio y alcance de búsqueda (documentos, chunks, o híbrido).

### POST `/api/search`

#### Request Básico (Búsqueda Simple)
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "factura proveedores",
    "top_k": 10
  }'
```

**Payload JSON:**
```json
{
  "query": "factura proveedores",
  "job_id": null,
  "category": [],
  "extension": [],
  "directory": [],
  "scope": "hybrid",
  "top_k": 10
}
```

#### Response (Búsqueda Simple)
```json
{
  "query": "factura proveedores",
  "job_id": null,
  "total_results": 3,
  "results": [
    {
      "source_id": "chunk_001_1",
      "kind": "chunk",
      "title": "Factura Proveedor ABC",
      "path": "/documents/invoices/factura_2024_001.pdf",
      "document_id": "doc_001",
      "category": "Factura_Proveedor",
      "cluster_sugerido": "Compras Q1 2024",
      "snippet": "...factura de servicios profesionales emitida por proveedores autorizados...",
      "score": 0.92,
      "distance": 0.15
    },
    {
      "source_id": "doc_002",
      "kind": "document",
      "title": "Resumen de Facturas",
      "path": "/documents/reports/facturas_summary.docx",
      "document_id": "doc_002",
      "category": "Informe",
      "cluster_sugerido": null,
      "snippet": "...total de facturas de proveedores registradas en el período...",
      "score": 0.85,
      "distance": 0.28
    },
    {
      "source_id": "chunk_003_2",
      "kind": "chunk",
      "title": "Contrato Proveedor",
      "path": "/documents/contracts/contrato_proveedor_xyz.pdf",
      "document_id": "doc_003",
      "category": "Contrato",
      "cluster_sugerido": "Proveedores Críticos",
      "snippet": "...las condiciones de facturación y términos de pago con proveedores...",
      "score": 0.78,
      "distance": 0.42
    }
  ],
  "categories": [
    {
      "label": "Factura_Proveedor",
      "count": 2,
      "share": 0.67
    },
    {
      "label": "Contrato",
      "count": 1,
      "share": 0.33
    }
  ],
  "extensions": [
    {
      "label": ".pdf",
      "count": 2,
      "share": 0.67
    },
    {
      "label": ".docx",
      "count": 1,
      "share": 0.33
    }
  ],
  "directories": [
    {
      "label": "/documents/invoices",
      "count": 1,
      "share": 0.33
    },
    {
      "label": "/documents/contracts",
      "count": 1,
      "share": 0.33
    },
    {
      "label": "/documents/reports",
      "count": 1,
      "share": 0.33
    }
  ],
  "suggestions": [
    "Considera filtrar por categoría 'Factura_Proveedor' para resultados más específicos",
    "Se encontraron 2 documentos en el cluster 'Compras Q1 2024'"
  ]
}
```

#### Request con Filtros Avanzados
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "inversión capital",
    "job_id": "job_12345",
    "category": ["Contrato", "Informe"],
    "extension": [".pdf", ".docx"],
    "directory": ["/documents/strategies", "/documents/capital"],
    "scope": "documents",
    "top_k": 20
  }'
```

**Parámetros de Filtrado:**
- **query**: String opcional con los términos a buscar
- **job_id**: ID del job específico; si es null, busca en todo el corpus
- **category**: Array de categorías (ej: "Factura_Proveedor", "Contrato", "Informe", "Orden_Trabajo", "Licitacion", "Nota_Credito", "Imagen", "Desconocido")
- **extension**: Array de extensiones (ej: ".pdf", ".docx", ".xlsx")
- **directory**: Array de rutas de directorio para filtrar
- **scope**: Alcance de búsqueda:
  - `"all"`: Busca en documentos y chunks (sin deduplicación)
  - `"documents"`: Solo documentos lógicos completos
  - `"chunks"`: Solo fragmentos semánticos
  - `"hybrid"` (default): Busca inteligente combinando documentos y chunks
- **top_k**: Número de resultados (1-50, default: 10)

#### Response con Filtros
```json
{
  "query": "inversión capital",
  "job_id": "job_12345",
  "total_results": 5,
  "results": [
    {
      "source_id": "doc_045",
      "kind": "document",
      "title": "Plan de Inversión 2024",
      "path": "/documents/strategies/investment_plan_2024.pdf",
      "document_id": "doc_045",
      "category": "Informe",
      "cluster_sugerido": "Estrategia Financiera",
      "snippet": "...plan de capital para inversiones proyectadas en infraestructura...",
      "score": 0.94,
      "distance": 0.10
    }
  ],
  "categories": [
    {
      "label": "Informe",
      "count": 4,
      "share": 0.8
    },
    {
      "label": "Contrato",
      "count": 1,
      "share": 0.2
    }
  ],
  "extensions": [
    {
      "label": ".pdf",
      "count": 3,
      "share": 0.6
    },
    {
      "label": ".docx",
      "count": 2,
      "share": 0.4
    }
  ],
  "directories": [
    {
      "label": "/documents/strategies",
      "count": 3,
      "share": 0.6
    },
    {
      "label": "/documents/capital",
      "count": 2,
      "share": 0.4
    }
  ],
  "suggestions": []
}
```

---

## 2. Consultas RAG (Generación Aumentada por Recuperación) (`/api/rag/query`)

### Descripción
Realiza consultas mediante RAG (Retrieval-Augmented Generation): recupera documentos relevantes del corpus y genera una respuesta sintetizada basada en el contexto encontrado.

### POST `/api/rag/query`

#### Request Básico
```bash
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Cuáles son los términos de pago principales con proveedores?",
    "include_answer": true,
    "top_k": 5
  }'
```

**Payload JSON:**
```json
{
  "query": "¿Cuáles son los términos de pago principales con proveedores?",
  "job_id": null,
  "top_k": 5,
  "include_answer": true
}
```

#### Response Básica
```json
{
  "query": "¿Cuáles son los términos de pago principales con proveedores?",
  "answer": "Según los documentos analizados, los términos de pago principales con proveedores son: 1) Pago a 30 días desde la emisión de factura para proveedores estándar, 2) Descuento por pronto pago del 2% si se realiza pago a 10 días, 3) Para proveedores estratégicos se negocia plazo a 60 días, y 4) Se requiere depósito inicial del 20% para órdenes superiores a $50,000.",
  "context": "Los términos de pago con los proveedores autorizados están especificados en los contratos de abastecimiento. El departamento de compras mantiene acuerdos estándar de 30 días net, con opciones de descuento por pronto pago. Los proveedores críticos tienen términos negociados individualmente que pueden llegar hasta 60 días.",
  "sources": [
    {
      "source_id": "doc_012",
      "kind": "document",
      "document_id": "doc_012",
      "path": "/documents/contracts/supplier_agreement_standard.pdf",
      "title": "Acuerdo Estándar de Proveedores",
      "category": "Contrato",
      "cluster_sugerido": "Gestión de Proveedores",
      "chunk_index": null,
      "page_number": 2,
      "snippet": "Los términos de pago estándar son de treinta (30) días calendario desde la fecha de emisión de la factura. Se otorga descuento del dos por ciento (2%) si el pago se realiza dentro de diez (10) días de la facturación.",
      "distance": 0.18,
      "score": 0.91
    },
    {
      "source_id": "chunk_045_3",
      "kind": "chunk",
      "document_id": "doc_045",
      "path": "/documents/policies/payment_policy.docx",
      "title": "Política de Pagos",
      "category": "Informe",
      "cluster_sugerido": null,
      "chunk_index": 3,
      "page_number": null,
      "snippet": "Para proveedores estratégicos de categoría A, se negocian términos de pago hasta sesenta (60) días con documentación de crédito. Se requiere depósito inicial del veinte por ciento (20%) para órdenes mayores a cincuenta mil dólares.",
      "distance": 0.22,
      "score": 0.87
    },
    {
      "source_id": "doc_089",
      "kind": "document",
      "document_id": "doc_089",
      "path": "/documents/contracts/supplier_agreement_critical.pdf",
      "title": "Acuerdo - Proveedores Críticos",
      "category": "Contrato",
      "cluster_sugerido": "Proveedores Críticos",
      "chunk_index": null,
      "page_number": 1,
      "snippet": "Los proveedores catalogados como críticos participan en negociaciones de términos personalizados de acuerdo a su desempeño histórico y volumen de compras.",
      "distance": 0.31,
      "score": 0.81
    }
  ]
}
```

#### Request Avanzado (con Job Específico)
```bash
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Qué riesgos de cumplimiento se han identificado en auditorías recientes?",
    "job_id": "job_scan_2024_q1",
    "top_k": 8,
    "include_answer": true
  }'
```

**Parámetros:**
- **query**: String requerido con la pregunta (mín. 1 carácter)
- **job_id**: ID opcional del job; si es null, busca en todo el corpus
- **top_k**: Número máximo de fuentes a recuperar (1-20, default: 5)
- **include_answer**: Boolean (default: true) para generar una respuesta sintetizada

#### Response Avanzada
```json
{
  "query": "¿Qué riesgos de cumplimiento se han identificado en auditorías recientes?",
  "answer": "Se identificaron tres áreas críticas de riesgo en la auditoría Q1 2024: (1) Deficiencias en el seguimiento de documentación de proveedores no certificados, (2) Inconsistencias en la clasificación de gastos entre categorías contractuales, y (3) Exposición a información sensible sin protocolos de acceso adecuados. Se recomenda implementar verificación de proveedores en tiempo real y revisar políticas de datos sensibles.",
  "context": "Auditoría interna Q1 2024. Hallazgos principales: gestión de proveedores, clasificación de documentos, y protección de datos personales. Se estableció plan de acción para resolución en 90 días.",
  "sources": [
    {
      "source_id": "doc_156",
      "kind": "document",
      "document_id": "doc_156",
      "path": "/documents/audits/internal_audit_q1_2024.pdf",
      "title": "Auditoría Interna Q1 2024",
      "category": "Informe",
      "cluster_sugerido": "Cumplimiento Regulatorio",
      "chunk_index": null,
      "page_number": 5,
      "snippet": "Se identificaron deficiencias críticas en el seguimiento de certificaciones de proveedores no designados oficialmente como críticos.",
      "distance": 0.08,
      "score": 0.96
    },
    {
      "source_id": "chunk_156_2",
      "kind": "chunk",
      "document_id": "doc_156",
      "path": "/documents/audits/internal_audit_q1_2024.pdf",
      "title": "Auditoría Interna Q1 2024",
      "category": "Informe",
      "cluster_sugerido": "Cumplimiento Regulatorio",
      "chunk_index": 2,
      "page_number": 8,
      "snippet": "Hallazgo: Documentos con información personal identificable (PII) no están sujetos a protocolos de acceso restringido en el 35% de los casos revisados.",
      "distance": 0.12,
      "score": 0.93
    },
    {
      "source_id": "doc_167",
      "kind": "document",
      "document_id": "doc_167",
      "path": "/documents/policies/data_protection_policy.docx",
      "title": "Política de Protección de Datos",
      "category": "Informe",
      "cluster_sugerido": null,
      "chunk_index": null,
      "page_number": 3,
      "snippet": "Todo documento que contenga información personal identificable debe ser clasificado como nivel de acceso restringido.",
      "distance": 0.19,
      "score": 0.88
    }
  ]
}
```

---

## 3. Monitoreo de Logs en Tiempo Real (WebSocket) (`/api/jobs/{job_id}/logs/ws`)

### Descripción
Se conecta a través de WebSocket para recibir logs de un job en tiempo real. El servidor envía todos los logs históricos primero, y luego cualquier nuevo log mientras el job está en ejecución.

### Conexión WebSocket

#### Python (usando `websockets`)
```python
import asyncio
import websockets

async def monitor_job_logs(job_id: str):
    """Conecta al WebSocket de logs y muestra los logs en tiempo real."""
    uri = f"ws://localhost:8000/api/jobs/{job_id}/logs/ws"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Conectado a logs del job: {job_id}")
            
            # Recibir todos los logs (históricos y nuevos)
            while True:
                log_entry = await websocket.recv()
                print(f"[LOG] {log_entry}")
                
    except websockets.exceptions.ConnectionClosed:
        print("Conexión cerrada por el servidor")
    except Exception as e:
        print(f"Error: {e}")

# Uso:
# Primero, crear un job
import requests
response = requests.post("http://localhost:8000/api/jobs", json={"path": "/ruta/a/documentos"})
job_id = response.json()["job_id"]

# Luego, monitorear los logs
asyncio.run(monitor_job_logs(job_id))
```

#### JavaScript/Node.js (usando `ws`)
```javascript
const WebSocket = require('ws');

function monitorJobLogs(jobId) {
  const uri = `ws://localhost:8000/api/jobs/${jobId}/logs/ws`;
  const ws = new WebSocket(uri);

  ws.on('open', () => {
    console.log(`Conectado a logs del job: ${jobId}`);
  });

  ws.on('message', (data) => {
    console.log(`[LOG] ${data}`);
  });

  ws.on('close', () => {
    console.log('Conexión cerrada');
  });

  ws.on('error', (error) => {
    console.error('Error:', error);
  });
}

// Uso:
// const jobId = 'job_12345';
// monitorJobLogs(jobId);
```

#### Bash (usando `wscat`)
```bash
#!/bin/bash

JOB_ID="job_12345"

# Asegúrate de tener wscat instalado: npm install -g wscat
# O usar: apt-get install wscat

wscat -c "ws://localhost:8000/api/jobs/${JOB_ID}/logs/ws"

# La conexión mostrará logs en tiempo real:
# > [2024-01-15 10:30:45] Scanner iniciado para /documentos
# > [2024-01-15 10:30:46] Procesando archivo: doc_001.pdf
# > [2024-01-15 10:30:52] Extracción completada: 5 chunks
# ...
```

### Flujo de Conexión WebSocket

1. **Validación**: El servidor verifica que el `job_id` exista
2. **Rechazo**: Si el job no existe, cierra la conexión con código `1008` (POLICY_VIOLATION)
3. **Aceptación**: Si existe, acepta la conexión y envía todos los logs históricos
4. **Streaming**: Después de los históricos, envía nuevos logs en tiempo real mientras el job corre
5. **Cierre**: La conexión se cierra cuando:
   - El cliente se desconecta
   - El job finaliza (completado o fallido)
   - Se alcanza timeout del servidor

### Ejemplo Completo: Job Scanning con Monitoreo

#### 1. Crear un Job (HTTP)
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/documentos/financiero",
    "allowed_extensions": [".pdf", ".docx"],
    "excluded_directories": [".git", "node_modules"]
  }'
```

**Response:**
```json
{
  "job_id": "job_scan_2024_fin",
  "status": "running",
  "created_at": "2024-04-05T10:30:00Z",
  "progress": {
    "files_scanned": 0,
    "files_found": 0,
    "documents_indexed": 0
  }
}
```

#### 2. Monitorear Logs (WebSocket)
```javascript
// Después de crear el job, conectar inmediatamente
const jobId = "job_scan_2024_fin";
const ws = new WebSocket(`ws://localhost:8000/api/jobs/${jobId}/logs/ws`);

ws.onmessage = (event) => {
  // Parsear timestamp si está incluido
  const logLine = event.data; // ej: "[2024-04-05 10:30:05] Scanner iniciado"
  
  // Actualizar UI en tiempo real
  document.getElementById('logs').innerHTML += `<div>${logLine}</div>`;
  
  // Auto-scroll a los últimos logs
  document.getElementById('logs').scrollTop = document.getElementById('logs').scrollHeight;
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

#### 3. Obtener Logs Completos (HTTP fallback)
```bash
# Obtener todos los logs del job (alternativa HTTP)
curl -X GET http://localhost:8000/api/jobs/job_scan_2024_fin/logs

# Response:
[
  "[2024-04-05 10:30:05] Scanner iniciado para /documentos/financiero",
  "[2024-04-05 10:30:06] Encontrados 152 archivos",
  "[2024-04-05 10:30:07] Procesando doc_001.pdf...",
  "[2024-04-05 10:30:12] Extracción completada: 8 chunks",
  "[2024-04-05 10:30:13] Indexando chunks en vector store...",
  "[2024-04-05 10:30:20] Job completado exitosamente"
]
```

### Códigos de Desconexión WebSocket

| Código | Significado |
|--------|------------|
| `1000` | Cierre normal (esperado) |
| `1008` | Violación de política (job no encontrado) |
| `1011` | Error interno del servidor |
| `1001` | Punto final desconectado |

---

## 4. Integraciones Remotas: Google Drive y SharePoint

### Descripción General

El sistema soporta escaneo de documentos desde dos proveedores remotos principales:
- **Google Drive**: Para acceder a carpetas compartidas en Google Drive
- **SharePoint**: Para acceder a librerías de documentos en Microsoft SharePoint

Ambos proveedores requieren autenticación específica y se configuran mediante `source_options` en la solicitud de escaneo.

### Google Drive

#### Configuración de Credenciales

**Paso 1: Crear una Cuenta de Servicio en Google Cloud**

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear un nuevo proyecto o seleccionar uno existente
3. Habilitar la Google Drive API:
   - Buscar "Google Drive API" en la barra de búsqueda
   - Hacer clic en "Habilitar"
4. Crear una cuenta de servicio:
   - Ir a "Credenciales" → "Crear credenciales" → "Cuenta de servicio"
   - Nombre: ej. "epic-analyzer-drive"
   - Crear y continuar
5. Crear una clave JSON:
   - En la sección "Claves", hacer clic en "Agregar clave" → "Nueva clave"
   - Seleccionar formato JSON
   - Descargar el archivo JSON (contiene `client_email`, `private_key`, etc.)

**Paso 2: Compartir Carpeta Google Drive**

1. En Google Drive, crear una carpeta o seleccionar una existente
2. Obtener el `folder_id` desde la URL: `https://drive.google.com/drive/folders/{folder_id}`
3. Compartir la carpeta con el correo de la cuenta de servicio (`client_email` del JSON descargado)
4. Conceder al menos permisos de "Viewer" (lectura)

**Paso 3: Configurar Variables de Entorno**

```bash
# Opción A: Usar variables de entorno
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON='{"type": "service_account", "project_id": "...", "private_key_id": "...", ...}'
export GOOGLE_DRIVE_FOLDER_ID="1abc2def3ghi4jkl5mno6pqr7stu8vwx"

# Opción B: En archivo .env (docker-compose)
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
GOOGLE_DRIVE_FOLDER_ID=1abc2def3ghi4jkl5mno6pqr7stu8vwx
```

#### Request: Iniciar Escaneo desde Google Drive

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "1abc2def3ghi4jkl5mno6pqr7stu8vwx",
    "source_provider": "google_drive",
    "source_options": {
      "folder_id": "1abc2def3ghi4jkl5mno6pqr7stu8vwx",
      "service_account_json": "{\"type\": \"service_account\", \"project_id\": \"my-project\", ...}"
    },
    "enable_pii_detection": true,
    "enable_embeddings": true,
    "enable_clustering": true,
    "group_mode": "strict"
  }'
```

**Parámetros:**
- **path**: Puede ser el `folder_id` o una ruta dentro de la carpeta raíz
- **source_provider**: Debe ser `"google_drive"`
- **source_options.folder_id**: ID de la carpeta raíz en Google Drive (requerido o en `path`)
- **source_options.service_account_json**: Credenciales JSON como string (si no está en env)

**Response:**
```json
{
  "job_id": "job_gd_2024_fin_docs",
  "status": "running",
  "created_at": "2024-04-05T10:45:00Z",
  "progress": {
    "files_scanned": 0,
    "files_found": 0,
    "documents_indexed": 0
  }
}
```

#### Uso Alternativo: Variables de Entorno Solamente

```bash
# Si GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON está en env, solo necesitas folder_id
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "1abc2def3ghi4jkl5mno6pqr7stu8vwx",
    "source_provider": "google_drive"
  }'
```

#### Python: Escaneo Google Drive

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Credenciales (normalmente desde env, aquí inline para ejemplo)
service_account_json = json.dumps({
    "type": "service_account",
    "project_id": "my-project",
    "private_key_id": "key-id-here",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "my-sa@my-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/..."
})

# Crear job de escaneo
response = requests.post(
    f"{BASE_URL}/api/jobs",
    json={
        "path": "1abc2def3ghi4jkl5mno6pqr7stu8vwx",
        "source_provider": "google_drive",
        "source_options": {
            "folder_id": "1abc2def3ghi4jkl5mno6pqr7stu8vwx",
            "service_account_json": service_account_json
        }
    }
)

job_data = response.json()
job_id = job_data["job_id"]
print(f"Job iniciado: {job_id}")
print(f"Estado: {job_data['status']}")

# Monitorear progreso
import time
while True:
    job = requests.get(f"{BASE_URL}/api/jobs/{job_id}").json()
    print(f"Progreso: {job['progress']}")
    if job['status'] in ['completed', 'failed']:
        print(f"Job finalizado: {job['status']}")
        break
    time.sleep(5)
```

#### Notas sobre Google Drive

- **Tipos de archivo**: Google Docs, Sheets y Presentations se exportan a formatos estándar (TXT, CSV, PDF)
- **Permisos**: La cuenta de servicio debe tener acceso de lectura a la carpeta y sus sub-carpetas
- **Jerarquía**: Se preserva la estructura de carpetas del Google Drive
- **Duplicados**: Se detectan y marcan automáticamente basándose en SHA256
- **Rate Limiting**: Google Drive API tiene límites de velocidad; los escaneos grandes pueden tomar tiempo

---

### SharePoint

#### Configuración de Credenciales (Azure AD)

**Paso 1: Registrar Aplicación en Azure AD**

1. Ir a [Azure Portal](https://portal.azure.com/)
2. Navegar a "Azure Active Directory" → "Registros de aplicaciones"
3. Hacer clic en "Nuevo registro":
   - Nombre: ej. "epic-analyzer-sharepoint"
   - Tipos de cuenta soportados: "Cuentas en este directorio organizativo solamente"
   - URI de redireccionamiento: Dejar en blanco (app de demonio)
4. Copiar:
   - **Tenant ID** (Directory ID)
   - **Client ID** (Application ID)
5. Crear una contraseña de cliente:
   - Ir a "Certificados y secretos" → "Nuevo secreto de cliente"
   - Descripción: "epic-analyzer-secret"
   - Expiración: Elegir duración (recomendado 2 años)
   - Copiar el valor (este es el **Client Secret**)

**Paso 2: Otorgar Permisos a Microsoft Graph**

1. En el registro, ir a "Permisos de API"
2. Hacer clic en "Agregar un permiso"
3. Seleccionar "Microsoft Graph" → "Permisos de aplicación"
4. Buscar y seleccionar:
   - `Files.Read.All`
   - `Sites.Read.All`
   - `Drives.Read.All`
5. Hacer clic en "Agregar permisos"
6. **Consentimiento de administrador**: Hacer clic en "Conceder consentimiento de administrador para [Tu Organización]"

**Paso 3: Obtener IDs de SharePoint**

1. **Site ID**: 
   - Navegar a tu sitio SharePoint
   - URL: `https://yourtenant.sharepoint.com/sites/your-site`
   - Usar herramienta como [PnP Site Identifier](https://pnp.github.io/powershell/cmdlets/Get-PnPSite.html) o Microsoft Graph Explorer
   - O via PowerShell (requiere módulos PnP):
     ```powershell
     Connect-PnPOnline -Url "https://yourtenant.sharepoint.com/sites/your-site" -Interactive
     Get-PnPSite
     ```

2. **Drive ID**:
   - Dentro del sitio SharePoint, ir a la librería de documentos (Documents, etc.)
   - Obtener drive ID desde Microsoft Graph Explorer o PowerShell

**Paso 4: Configurar Variables de Entorno**

```bash
# variables de entorno
export SHAREPOINT_TENANT_ID="12345678-1234-1234-1234-123456789012"
export SHAREPOINT_CLIENT_ID="87654321-4321-4321-4321-210987654321"
export SHAREPOINT_CLIENT_SECRET="your-secret-value-here"
export SHAREPOINT_SITE_ID="site1234567890.sharepoint.com,site-id-123,hub-id-456"
export SHAREPOINT_DRIVE_ID="b!abc123...xyz"

# O en docker-compose (con escapes)
SHAREPOINT_TENANT_ID=12345678-1234-1234-1234-123456789012
SHAREPOINT_CLIENT_ID=87654321-4321-4321-4321-210987654321
SHAREPOINT_CLIENT_SECRET=your-secret-value-here
SHAREPOINT_SITE_ID=site1234567890.sharepoint.com,site-id-123,hub-id-456
SHAREPOINT_DRIVE_ID=b!abc123...xyz
```

#### Request: Iniciar Escaneo desde SharePoint

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/Reports",
    "source_provider": "sharepoint",
    "source_options": {
      "site_id": "site1234567890.sharepoint.com,site-id-123,hub-id-456",
      "drive_id": "b!abc123...xyz"
    },
    "enable_pii_detection": true,
    "enable_embeddings": true,
    "enable_clustering": true,
    "group_mode": "strict"
  }'
```

**Parámetros:**
- **path**: Ruta dentro del drive (ej. "/Reports", "/Shared Documents"). Raíz si está vacío
- **source_provider**: Debe ser `"sharepoint"`
- **source_options.site_id**: ID del sitio SharePoint (requerido o en env)
- **source_options.drive_id**: ID del drive dentro del sitio (requerido o en env)

**Response:**
```json
{
  "job_id": "job_sp_2024_reports",
  "status": "running",
  "created_at": "2024-04-05T11:00:00Z",
  "progress": {
    "files_scanned": 0,
    "files_found": 0,
    "documents_indexed": 0
  }
}
```

#### Uso Alternativo: Variables de Entorno Solamente

```bash
# Si todas las credenciales están en env, minimizar el payload
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/Reports",
    "source_provider": "sharepoint"
  }'
```

#### Python: Escaneo SharePoint

```python
import requests

BASE_URL = "http://localhost:8000"

# Crear job de escaneo
response = requests.post(
    f"{BASE_URL}/api/jobs",
    json={
        "path": "/Shared Documents",
        "source_provider": "sharepoint",
        "source_options": {
            "site_id": "site1234567890.sharepoint.com,site-id-123,hub-id-456",
            "drive_id": "b!abc123...xyz"
        }
    }
)

job_data = response.json()
job_id = job_data["job_id"]
print(f"Job iniciado: {job_id}")
print(f"Estado: {job_data['status']}")

# Monitorear con logs WebSocket
import asyncio
import websockets
import json

async def monitor_sp_scan(job_id: str):
    uri = f"ws://localhost:8000/api/jobs/{job_id}/logs/ws"
    async with websockets.connect(uri) as ws:
        async for log in ws:
            print(f"[LOG] {log}")

asyncio.run(monitor_sp_scan(job_id))
```

#### Notas sobre SharePoint

- **Autenticación**: Requiere credenciales de Azure AD (aplicación de servicio)
- **Permisos**: La aplicación debe tener permisos `Files.Read.All`, `Sites.Read.All`, `Drives.Read.All`
- **Multi-tenant**: Soporta múltiples sitios configurando diferentes `site_id` en source_options
- **Rate Limiting**: Microsoft Graph tiene límites; escaneos grandes pueden requerir reintentos
- **Versionado**: Descarga la versión actual del documento; no se incluyen historiales

---

## 5. Configuración de Filtrado de Ingesta

### Descripción

Epic Analyzer ofrece dos estrategias configurables para decidir qué archivos procesar durante el escaneo:

- **Modo `blacklist`** (por defecto): Procesa TODO excepto lo explícitamente excluido
- **Modo `whitelist`**: Procesa SOLO lo explícitamente permitido

Además, detecta y salta automáticamente binarios (ejecutables, imágenes, vídeos, comprimidos) sin intentar extracción.

### Escenario A: Modo Whitelist (Solo Documentos Corporativos)

**Caso de uso**: Auditoría de corpus corporativo. Solo interesa procesar documentos de negocio.

**Request**:
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/corporate",
    "source_provider": "local",
    "ingestion_mode": "whitelist",
    "allowed_extensions": [".pdf", ".docx", ".xlsx", ".csv"],
    "allowed_mime_types": ["text/", "application/pdf", "application/msword", "application/vnd"],
    "enable_embeddings": true,
    "enable_clustering": true,
    "enable_pii_detection": true
  }'
```

**Resultado**:
- ✅ Procesa: PDF, Word, Excel, CSV, TXT, JSON, XML
- ❌ Rechaza: Imágenes, vídeos, ejecutables, comprimidos
- 📊 Auditoría: Ver `/api/admin/filter-stats?job_id=<JOB_ID>`

**Response**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted"
}
```

### Escenario B: Modo Blacklist (Repositorio Abierto)

**Caso de uso**: Análisis de GitHub/GitLab. Puede haber de todo, pero queremos evitar ejecutables y comprimidos.

**Request**:
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/github-repos",
    "source_provider": "local",
    "ingestion_mode": "blacklist",
    "denied_extensions": [".exe", ".dll", ".so", ".dylib", ".zip", ".tar", ".gz", ".rar", ".7z"],
    "denied_mime_types": ["application/x-executable", "application/x-sharedlib", "application/zip", "application/gzip"],
    "enable_embeddings": true,
    "enable_clustering": false
  }'
```

**Resultado**:
- ✅ Procesa: `.py`, `.js`, `.ts`, `.md`, `.json`, `.yaml`, `.xml`, `.txt`, etc.
- ❌ Rechaza: Ejecutables, comprimidos
- 📊 Auditoría: Ver `/api/admin/filter-stats`

**Response**:
```json
{
  "job_id": "660f9511-f40c-52e5-b827-557766551111",
  "status": "accepted"
}
```

### Escenario C: Deteción Temprana Automática de Binarios

**Características**:
- Opera independientemente del modo (blacklist o whitelist)
- Detecta por extensión: `.jpg`, `.png`, `.gif`, `.mp4`, `.mp3`, etc.
- Detecta por MIME type: `image/*`, `video/*`, `audio/*`, `application/octet-stream`, etc.
- **Beneficio**: No intenta extraer contenido (ahorra tiempo, evita errores)

**Ejemplo: Request Sin Configuración Explícita**:
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/mixed",
    "source_provider": "local",
    "enable_embeddings": true
  }'
```

En este caso, los binarios se detectan automáticamente y se saltan.

### Auditar Archivos Filtrados

**Consultar rechazos después del escaneo**:
```bash
curl -X GET "http://localhost:8000/api/admin/filter-stats?job_id=550e8400-e29b-41d4-a716-446655440000&limit=10"
```

**Response**:
```json
{
  "total_scans_with_filters": 1,
  "total_files_filtered": 5,
  "scans": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-04-06T10:30:00Z",
      "skipped_count": 5,
      "skipped_files": [
        {
          "path": "/data/github-repos/image.png",
          "reason": "MIME type image/png detected as binary, skipped early"
        },
        {
          "path": "/data/github-repos/video.mp4",
          "reason": "MIME type video/mp4 detected as binary, skipped early"
        },
        {
          "path": "/data/github-repos/program.exe",
          "reason": "extension in blacklist: .exe"
        },
        {
          "path": "/data/github-repos/archive.zip",
          "reason": "MIME type application/zip detected as binary, skipped early"
        },
        {
          "path": "/data/github-repos/lib.so",
          "reason": "extension in blacklist: .so"
        }
      ],
      "entry_id": "audit-2026-04-06-10-30"
    }
  ]
}
```

### Cambiar Configuración Sin Reiniciar

**Opción 1: Variables de entorno (requiere reinicio)**:
```bash
docker-compose down
INGESTION_MODE=whitelist ALLOWED_EXTENSIONS=".pdf,.docx" docker-compose up -d backend
```

**Opción 2: Por job sin reinicio (✅ Recomendado)**:
```bash
# Cada request puede especificar su propia configuración
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/scan1",
    "ingestion_mode": "whitelist",
    "allowed_extensions": [".pdf"]
  }'

# Y luego otro job con configuración diferente
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/scan2",
    "ingestion_mode": "blacklist",
    "denied_extensions": [".exe", ".zip"]
  }'
```

**Opción 3: Frontend UI (✅ Más fácil para usuarios finales)**:
1. Abrir formulario de nuevo job en UI
2. Ir a sección "Filter Configuration"
3. Seleccionar modo (whitelist/blacklist)
4. Configurar extensiones permitidas/rechazadas
5. Lanzar escaneo

---

### Comparación: Local vs Google Drive vs SharePoint

| Característica | Local | Google Drive | SharePoint |
|---|---|---|---|
| **Autenticación** | Sistema de archivos | Cuenta de servicio (JSON) | Azure AD (credenciales) |
| **Configuración** | Path local | folder_id + credenciales | site_id + drive_id + credenciales |
| **Descarga** | Lectura directa | Via Google Drive API | Via Microsoft Graph |
| **Estructura** | Directorios locales | Jerarquía de carpetas GD | Jerarquía de SharePoint |
| **Velocidad** | Más rápido | Limitado por API | Limitado por API |
| **Escalabilidad** | Limitado al volumen local | Escalable | Escalable |

---

### Ejemplo Completo: Multi-Source (Local + Google Drive + SharePoint)

```bash
#!/bin/bash

BASE_URL="http://localhost:8000"

# 1. Escanear carpeta local
echo "=== Iniciando escaneo local ==="
local_job=$(curl -s -X POST "$BASE_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/data/documents",
    "source_provider": "local"
  }' | jq -r '.job_id')

echo "Job local: $local_job"

# 2. Escanear Google Drive
echo "=== Iniciando escaneo Google Drive ==="
gd_job=$(curl -s -X POST "$BASE_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "1abc2def3ghi4jkl5mno6pqr7stu8vwx",
    "source_provider": "google_drive"
  }' | jq -r '.job_id')

echo "Job Google Drive: $gd_job"

# 3. Escanear SharePoint
echo "=== Iniciando escaneo SharePoint ==="
sp_job=$(curl -s -X POST "$BASE_URL/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/Reports",
    "source_provider": "sharepoint"
  }' | jq -r '.job_id')

echo "Job SharePoint: $sp_job"

# 4. Monitorear todos los jobs
for job_id in $local_job $gd_job $sp_job; do
  while true; do
    job_status=$(curl -s -X GET "$BASE_URL/api/jobs/$job_id" | jq '.status')
    if [[ "$job_status" == '"completed"' || "$job_status" == '"failed"' ]]; then
      echo "Job $job_id finalizado: $job_status"
      break
    fi
    sleep 5
  done
done

echo "=== Todos los jobs completados ==="
```

---

## 6. Manejo de Errores

### Error: Query Vacía
```bash
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "   "}'
```

**Response:**
```json
{
  "detail": "Query cannot be empty"
}
```
**HTTP Status:** 400 Bad Request

### Error: top_k Fuera de Rango
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "top_k": 100}'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "top_k"],
      "msg": "Input should be less than or equal to 50",
      "ctx": {"le": 50}
    }
  ]
}
```
**HTTP Status:** 422 Unprocessable Entity

### Error: Google Drive - Credenciales Inválidas
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "folder_id",
    "source_provider": "google_drive",
    "source_options": {
      "service_account_json": "invalid json"
    }
  }'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "source_options"],
      "msg": "Google Drive service_account_json must be valid JSON.",
      "ctx": {"error": "..."}
    }
  ]
}
```
**HTTP Status:** 422 Unprocessable Entity

### Error: SharePoint - Credenciales Faltantes
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/Reports",
    "source_provider": "sharepoint",
    "source_options": {}
  }'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "SharePoint scan requires site_id and drive_id in source_options or environment settings.",
      "ctx": {}
    }
  ]
}
```
**HTTP Status:** 422 Unprocessable Entity

---

## 7. Guía de Integración

### Python (usando `requests`)
```python
import requests

BASE_URL = "http://localhost:8000"

# Búsqueda
search_response = requests.post(
    f"{BASE_URL}/api/search",
    json={
        "query": "factura proveedores",
        "top_k": 10
    }
)
results = search_response.json()
print(f"Total resultados: {results['total_results']}")

# RAG Query
rag_response = requests.post(
    f"{BASE_URL}/api/rag/query",
    json={
        "query": "¿Cuáles son los términos de pago?",
        "top_k": 5
    }
)
answer_data = rag_response.json()
print(f"Respuesta: {answer_data['answer']}")
print(f"Fuentes utilizadas: {len(answer_data['sources'])}")
```

### JavaScript/Node.js (usando `fetch`)
```javascript
const BASE_URL = "http://localhost:8000";

// Búsqueda
const searchResponse = await fetch(`${BASE_URL}/api/search`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: "factura proveedores",
    top_k: 10
  })
});
const searchData = await searchResponse.json();
console.log(`Total resultados: ${searchData.total_results}`);

// RAG Query
const ragResponse = await fetch(`${BASE_URL}/api/rag/query`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: "¿Cuáles son los términos de pago?",
    top_k: 5
  })
});
const ragData = await ragResponse.json();
console.log(`Respuesta: ${ragData.answer}`);
console.log(`Fuentes: ${ragData.sources.length}`);
```

### cURL (bash)
```bash
#!/bin/bash

BASE_URL="http://localhost:8000"

# Búsqueda
echo "=== Búsqueda ==="
curl -X POST "$BASE_URL/api/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "factura",
    "top_k": 5
  }' | jq .

# RAG Query
echo -e "\n=== RAG Query ==="
curl -X POST "$BASE_URL/api/rag/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Cuáles son los términos de pago?",
    "top_k": 5
  }' | jq .
```

---

## 8. Notas Importantes

### Scopes de Búsqueda
- **hybrid** (default): Combina documentos completos con fragmentos semánticos, eliminando duplicados automáticamente
- **documents**: Retorna solo documentos lógicos completos (más lento pero más contexto)
- **chunks**: Retorna solo fragmentos individuales (más rápido, resultados más específicos)
- **all**: Retorna ambos sin deduplicación (útil para análisis comparativos)

### Scoring y Distancia
- **score**: Puntuación de relevancia (0.0-1.0), calculada mediante combinación de:
  - BM25 para similitud textual
  - Similitud vectorial del embedding
  - Señales de metadatos (categoría, directorio, etc.)
- **distance**: Distancia euclidiana en el espacio vectorial (0.0 = máxima similitud)

### Job ID
- Cuando `job_id` es **null**, la búsqueda abarca todo el corpus indexado
- Cuando se especifica un `job_id` válido, se filtra a documentos pertenecientes a ese job de escaneo específico
- Útil para análisis comparativos entre diferentes ejecuciones de escaneo

### Rate Limiting
- Por defecto: 100 requests por minuto por IP
- Para mayores volúmenes, contactar a administradores

---

## 9. Extracción de Entidades Nombradas — NER (`/api/reports/{job_id}/contacts`)

El endpoint `/api/reports/{job_id}/contacts` devuelve todas las entidades nombradas extraídas del corpus de un job, agregadas por tipo y valor. La extracción usa un pipeline híbrido de dos capas:

| Capa | Técnica | Tipos extraídos | Costo |
|------|---------|-----------------|-------|
| **Layer 1** | Regex (CPU-only) | EMAIL, RUT, PHONE | Cero |
| **Layer 2** | Gemini (LLM) | PERSON, ORGANIZATION, LOCATION, DATE, MONEY | Tokens Gemini |

### 9.1 Request básico — todos los contactos

```bash
JOB_ID="abc-123"
curl "http://localhost:8000/api/reports/$JOB_ID/contacts" | jq .
```

**Response**:
```json
{
  "job_id": "abc-123",
  "total_documents_analyzed": 42,
  "total_entities_found": 187,
  "contacts": [
    {
      "entity_type": "EMAIL",
      "value": "contacto@acmecorp.cl",
      "frequency": 12,
      "document_ids": ["sha256abc1", "sha256abc2"],
      "source_paths": ["/docs/facturas/f001.pdf", "/docs/contratos/c005.pdf"]
    },
    {
      "entity_type": "ORGANIZATION",
      "value": "Acme Corp S.A.",
      "frequency": 8,
      "document_ids": ["sha256abc1"],
      "source_paths": ["/docs/facturas/f001.pdf"]
    },
    {
      "entity_type": "RUT",
      "value": "76543210-K",
      "frequency": 5,
      "document_ids": ["sha256abc3"],
      "source_paths": ["/docs/licitaciones/lic001.pdf"]
    }
  ]
}
```

### 9.2 Filtrar por tipo de entidad

```bash
# Solo personas
curl "http://localhost:8000/api/reports/$JOB_ID/contacts?entity_type=PERSON" | jq .

# Solo organizaciones
curl "http://localhost:8000/api/reports/$JOB_ID/contacts?entity_type=ORGANIZATION" | jq .

# Solo emails
curl "http://localhost:8000/api/reports/$JOB_ID/contacts?entity_type=EMAIL" | jq .
```

Tipos disponibles: `PERSON`, `ORGANIZATION`, `LOCATION`, `EMAIL`, `PHONE`, `RUT`, `DATE`, `MONEY`, `OTHER`.

### 9.3 Filtrar por frecuencia mínima

```bash
# Solo entidades que aparecen 3 o más veces
curl "http://localhost:8000/api/reports/$JOB_ID/contacts?min_frequency=3" | jq .

# Combinado: personas con 2+ apariciones
curl "http://localhost:8000/api/reports/$JOB_ID/contacts?entity_type=PERSON&min_frequency=2" | jq .
```

### 9.4 Ejemplo Python — extracción de directorio de contactos

```python
import requests
from collections import defaultdict

BASE_URL = "http://localhost:8000"
JOB_ID = "abc-123"

# Obtener todos los contactos del job
resp = requests.get(f"{BASE_URL}/api/reports/{JOB_ID}/contacts")
report = resp.json()

print(f"Documentos analizados: {report['total_documents_analyzed']}")
print(f"Entidades encontradas: {report['total_entities_found']}")

# Agrupar por tipo
by_type = defaultdict(list)
for contact in report["contacts"]:
    by_type[contact["entity_type"]].append(contact)

# Directorio de personas
print("\n=== PERSONAS ===")
for p in by_type["PERSON"]:
    print(f"  {p['value']} (aparece en {p['frequency']} documentos)")

# Directorio de organizaciones
print("\n=== ORGANIZACIONES ===")
for o in by_type["ORGANIZATION"]:
    print(f"  {o['value']} → {o['frequency']} menciones")

# Emails y RUTs (Layer 1 regex, alta precisión)
print("\n=== EMAILS ===")
for e in by_type["EMAIL"]:
    docs = ", ".join(e["document_ids"][:3])
    print(f"  {e['value']} — freq: {e['frequency']}, docs: {docs}")

print("\n=== RUTs ===")
for r in by_type["RUT"]:
    print(f"  {r['value']} — freq: {r['frequency']}")
```

### 9.5 Campos de `named_entities` en documentos individuales

Cada documento en `GET /api/reports/{job_id}/documents` incluye ahora el campo `named_entities`:

```bash
curl "http://localhost:8000/api/reports/$JOB_ID/documents" | \
  jq '.[0] | {id: .documento_id, entities: .named_entities}'
```

**Response**:
```json
{
  "id": "sha256abc1",
  "entities": [
    {"entity_type": "EMAIL", "value": "juan@empresa.cl", "confidence": 1.0, "source": "regex"},
    {"entity_type": "RUT",   "value": "12345678-9",      "confidence": 1.0, "source": "regex"},
    {"entity_type": "PERSON","value": "Juan Pérez",       "confidence": 0.92, "source": "gemini"},
    {"entity_type": "ORGANIZATION","value": "Empresa S.A.", "confidence": 0.88, "source": "gemini"}
  ]
}
```

### 9.6 Notas sobre el pipeline NER

- **Layer 1 (regex)** siempre se ejecuta sobre texto extraído, con precisión del 100% para emails y RUTs chilenos.
- **Layer 2 (Gemini)** se ejecuta durante la clasificación y queda embebido en la respuesta sin llamadas adicionales.
- Las entidades se **deduplicam** por `(entity_type, valor_normalizado)` conservando la mayor confianza.
- Los resultados en `/contacts` se ordenan por `frequency` descendente.

---

## Última Actualización

Documentación actualizada el 06 de abril de 2026 para endpoints:
- `/api/search` (POST)
- `/api/rag/query` (POST)
- `/api/jobs/{job_id}/logs/ws` (WebSocket)
- `/api/reports/{job_id}/contacts` (GET) — **NER Fase 1**

Para consultas adicionales o reportar discrepancias, abrir un issue en el repositorio.
