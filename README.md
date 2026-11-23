# FlowClic Oficina IA — API (Python + FastAPI)

API de la Fase 1 (sin IA): agentes, tickets, aprobaciones, memoria, tiempo real (SSE), autenticación y administración.
Diseño completo en `docs/PLAN.md`; tareas y estado en `docs/TASKS.md`.

> **Estado:** la API se está construyendo por tareas. Este README solo describe comandos que **ya existen**;
> lo futuro va marcado como *(pendiente: tarea X)*. Hoy `uvicorn` sirve únicamente la documentación Swagger (`/docs`);
> los endpoints llegan con T20, T30… y el asistente de primer arranque con C04.

## Requisitos
- **Python 3.13** (`py -3.13 --version`). No sirve la 3.14: `libsql` no publica binarios de Windows para ella.
- Windows: usa el lanzador `py`, no `python`.

## Puesta en marcha (PowerShell, desde esta carpeta)
```powershell
py -3.13 -m venv .venv                                   # una vez
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python scripts/setup_env.py                              # crea .env con APP_MASTER_KEY y SESSION_SECRET aleatorios
uvicorn app.main:app --reload --host 127.0.0.1 --port 4000
```
Swagger: <http://localhost:4000/docs> · ReDoc: <http://localhost:4000/redoc> · Esquema: <http://localhost:4000/openapi.json>

### La base de datos
La URL y el token de la BD **no van en el `.env`**: se guardan cifrados en `data/vault.db` (clave: `APP_MASTER_KEY`).
La BD **empieza vacía**: `migrate` solo crea el esquema, sin datos de ejemplo.

- **Asistente de primer arranque** *(pendiente: C04 y F06)*: la API imprimirá un código de un solo uso y el front guiará hasta tener la BD y el primer ADMIN.
- **Atajo de desarrollo (disponible hoy)**: añade `TURSO_DATABASE_URL=file:local.db` a tu `.env` y ejecuta `python -m app.db.migrate`.
  La primera vez, la URL se importa cifrada a la bóveda y **esas líneas desaparecen del `.env`**.

```powershell
python -m app.db.migrate            # crea/actualiza el esquema (vacío)
python -m app.db.seed --demo        # OPCIONAL: datos de ejemplo (4 agentes, tickets...). Nunca se cargan por defecto
python -m app.db.reset              # solo bases file: — borra y recrea la BD vacía (con --demo, con ejemplos)
```

## Comandos disponibles
| Acción | Comando |
|---|---|
| Servidor (solo Swagger por ahora) | `uvicorn app.main:app --reload --host 127.0.0.1 --port 4000` |
| Crear `.env` con claves aleatorias | `python scripts/setup_env.py` |
| Migrar | `python -m app.db.migrate` |
| Datos de ejemplo (opcional) | `python -m app.db.seed --demo` |
| Reiniciar BD local | `python -m app.db.reset` · `python -m app.db.reset --demo` |
| Tests | `pytest` |
| Lint y tipos | `ruff check .` · `mypy app` |
| Auditoría de dependencias | `pip-audit -r requirements.txt` |

## Comandos futuros (aún NO existen)
| Acción | Comando | Tarea |
|---|---|---|
| Crear tu usuario ADMIN | `python scripts/admin_create.py` | pendiente: S05 |
| Backup / restaurar | `python -m app.db.backup` · `python -m app.db.restore <ruta>` | pendiente: S12 |
| Rotar la clave maestra | `python -m app.security.rotate_key` | pendiente |
| `GET /api/health` y resto de endpoints | — | pendiente: T20, T30… |

## Pasar a Turso (nube)
Con el asistente *(pendiente: C04/F06)* o desde Administración → Conexión BD *(pendiente: A05)*. Mientras tanto, para una prueba:
añade `TURSO_DATABASE_URL=libsql://<db>-<org>.turso.io` y `TURSO_AUTH_TOKEN=<token>` al `.env` **con la bóveda vacía** y ejecuta `python -m app.db.migrate` (se importan y se borran del `.env`).
