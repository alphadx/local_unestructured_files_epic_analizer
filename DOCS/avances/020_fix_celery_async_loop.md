# 020 - Fix de event loop en Celery worker (SQLAlchemy async + asyncpg)

## Contexto

En el worker de Celery aparecian errores intermitentes al ejecutar multiples tareas en el mismo proceso:

- `RuntimeError: Event loop is closed`
- `got Future <Future pending ...> attached to a different loop`

La causa era el ciclo `asyncio.run(...)` por tarea. Ese patron crea y destruye un loop por invocacion, mientras que SQLAlchemy async y asyncpg pueden reutilizar conexiones del pool ligadas al loop anterior.

## Cambios aplicados

### 1) Loop persistente por proceso de worker

Archivo: `backend/app/workers/tasks.py`

- Se reemplazo `asyncio.run(...)` por un runner interno que reutiliza un `event loop` persistente por proceso (`_get_worker_loop`, `_run_in_worker_loop`).
- Todas las corrutinas de tarea (`_async_pipeline` y `_mark_job_failed`) se ejecutan en ese mismo loop.

### 2) Cierre ordenado de recursos async al apagar worker

Archivo: `backend/app/workers/tasks.py`

- Se agrego hook `worker_process_shutdown` para:
  - Hacer dispose del engine async.
  - Cerrar el event loop persistente.

Archivo: `backend/app/db/session.py`

- Se agrego helper `dispose_engine()` para exponer `engine.dispose()` al shutdown del worker.

## Resultado esperado

- El mismo proceso de Celery deja de mezclar conexiones/pool entre loops distintos.
- Se evita el error `Future attached to a different loop` cuando el worker procesa tareas consecutivas.
- Se reduce riesgo de `Event loop is closed` durante terminacion de conexiones asyncpg.

## Notas operativas

- Este fix esta orientado a `prefork` (pool por procesos), que es el modo recomendado con CPU-bound + I/O mixto.
- Si se cambia el pool de Celery (por ejemplo a gevent/eventlet), se debe reevaluar la estrategia de loop async.
