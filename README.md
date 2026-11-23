# FlowClic Oficina IA — API (Python + FastAPI)

API de la Fase 1 (sin IA): agentes, tickets, aprobaciones, memoria, tiempo real (SSE), autenticación y administración.
Diseño completo en `docs/PLAN.md`; tareas en `docs/TASKS.md`.

## Requisitos
- **Python 3.13** (`py -3.13 --version`). No sirve la 3.14: `libsql` no publica binarios de Windows para ella.
- Windows: usa el lanzador `py`, no `python`.

## Puesta en marcha (PowerShell, desde esta carpeta)
```powershell
py -3.13 -m venv .venv                                   # una vez
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python scripts/setup_env.py                              # crea .env con claves aleatorias (cuando exista S02)
python -m app.db.migrate                                 # migraciones
python -m app.db.seed                                    # datos de ejemplo
python scripts/admin_create.py                           # tu usuario ADMIN (cuando exista S05)
uvicorn app.main:app --reload --host 127.0.0.1 --port 4000
```

Documentación interactiva (Swagger): <http://localhost:4000/docs> · ReDoc: <http://localhost:4000/redoc> · Esquema: <http://localhost:4000/openapi.json>

## Comandos
| Acción | Comando |
|---|---|
| Desarrollo | `uvicorn app.main:app --reload --host 127.0.0.1 --port 4000` |
| Tests | `pytest` |
| Lint y tipos | `ruff check .` · `mypy app` |
| Auditoría de dependencias | `pip-audit -r requirements.txt` |
| Migrar / sembrar / resetear | `python -m app.db.migrate` · `python -m app.db.seed` · `python -m app.db.reset` |
| Backup / restaurar | `python -m app.db.backup` · `python -m app.db.restore <ruta>` |

> Algunos comandos (`setup_env`, `db.*`, `admin_create`) se irán habilitando con sus tareas (T02, T10–T14, S02, S05, S12).

## Cambiar a Turso (nube)
En `.env`: `TURSO_DATABASE_URL=libsql://<db>-<org>.turso.io` y `TURSO_AUTH_TOKEN=<token>`; luego `python -m app.db.migrate`. Sin cambios de código.
