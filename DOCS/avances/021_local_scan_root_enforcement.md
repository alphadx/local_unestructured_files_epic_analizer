# 021 - Enforce LOCAL_SCAN_ROOT para escaneo local en Docker

## Problema

En ejecuciones Docker, el volumen de analisis se monta en `/data/scan`, pero si el cliente enviaba una ruta relativa (por ejemplo `.`), el backend podia resolverla respecto al `WORKDIR` (`/app`) y terminar analizando una ruta no esperada.

## Cambios

### Backend

- Se agrego `LOCAL_SCAN_ROOT` en configuracion (`backend/app/config.py`), por defecto vacio.
- En `ScanRequest` (`backend/app/models/schemas.py`):
  - Si `source_provider=local` y `LOCAL_SCAN_ROOT` esta configurado:
    - rutas relativas se resuelven dentro de ese root,
    - rutas absolutas fuera del root se rechazan,
    - se bloquean intentos de escape con `..`.

### Docker Compose

- Se define `LOCAL_SCAN_ROOT=/data/scan` para:
  - `backend`
  - `worker`

### Frontend

- La ruta inicial del formulario se establece en `/data/scan` para reducir errores operativos en entorno Docker.

## Validacion

- Tests unitarios en `tests/test_source_service.py` cubren:
  - resolucion de ruta relativa dentro de root,
  - bloqueo de escape fuera de `LOCAL_SCAN_ROOT`.

## Resultado

El analisis local en Docker queda anclado a `/data/scan` y no cae accidentalmente a `/app` por rutas relativas.
