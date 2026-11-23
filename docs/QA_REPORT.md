# Informe de QA — FlowClic Oficina IA

Formato: ID de tarea | fecha | qué probaste | resultado (PASA/FALLA) | error exacto y pasos para reproducirlo si falla.

Entorno de las pruebas: Windows 11, Python 3.13.17, copia limpia de `dev` en una carpeta temporal (no en el repo). La API se arrancó en el puerto **4100**, porque el 4000 lo ocupa todavía la API Node vieja (PID 36240). No se usó ningún `.env` real: se copió `.env.example` (sin secretos).

---

## Ronda 1 — 2026-11-22

| ID | Fecha | Qué probaste | Resultado | Error exacto y pasos para reproducir |
|---|---|---|---|---|
| P01 | 2026-11-22 | Copia limpia de `dev`. `py -3.13 -m venv .venv`; `pip install -r requirements.txt -r requirements-dev.txt`; `uvicorn app.main:app` en 127.0.0.1:4100 y `/docs`; `ruff check .`; `mypy app`; `pytest`; búsqueda de archivos Node (`package.json`, `package-lock.json`, `tsconfig.json`, `*.ts`, `*.js`). | **PASA** | — Resultados: pip OK (exit 0); `/docs` → 200 con Swagger UI; `ruff check .` → "All checks passed!"; `mypy app` → "Success: no issues found in 15 source files"; `pytest` → 38 pasan; no quedan archivos Node. Nota: el criterio dice `localhost:4000`; se verificó en 4100 por el puerto ocupado. |
| QP1 | 2026-11-22 | Seguir el README "Puesta en marcha" desde cero en una carpeta limpia (venv, install, `setup_env`, migrate, seed, `admin_create`, uvicorn), comprobar Swagger y `pip-audit`. | **FALLA** | Ver pasos abajo. |

### Detalle de QP1 (FALLA)

Pasos (PowerShell, en la carpeta limpia):
1. `py -3.13 -m venv .venv` → OK.
2. `.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt` → OK (exit 0).
3. `python scripts/setup_env.py` → **FALLA**: el archivo `scripts/setup_env.py` no existe. El README lo marca como "(cuando exista S02)".
4. Copiar `.env.example` a `.env` (paso manual, para poder seguir).
5. `python -m app.db.migrate` → OK: `Aplicada: 001_init.sql`, `Aplicada: 002_security.sql` (exit 0).
6. `python -m app.db.seed` → **FALLA** con el error exacto:
   ```
   C:\...\.venv\Scripts\python.exe: No module named app.db.seed
   ```
   Este comando sale en la sección "Puesta en marcha" sin marca de pendiente. El README solo lo marca en la nota de "Comandos" ("Algunos comandos… se irán habilitando con sus tareas (T02, T10–T14…)"). La semilla es T13 y sigue PENDIENTE en Python.
7. `python scripts/admin_create.py` → **FALLA**: el archivo no existe (S05, PENDIENTE).
8. `uvicorn app.main:app --reload --host 127.0.0.1 --port 4000` → arranca en 4100 (puerto cambiado, ver entorno). Log: `Application startup complete.`
9. Swagger: `GET /docs` → 200 (página Swagger UI). `GET /redoc` → 200. `GET /openapi.json` → 200, pero con `"paths": {}` (ningún endpoint todavía).
10. `GET /api/health` → **404** (la ruta aún no existe; es T20/T60 en Python).
11. `pip-audit -r requirements.txt` → OK: "No known vulnerabilities found" (exit 0).

Motivo de devolución: el README presenta como pasos de la puesta en marcha comandos que no existen todavía (`scripts/setup_env.py`, `app.db.seed`, `scripts/admin_create.py`). Por tanto, seguirlo tal cual no lleva a un arranque reproducible. Lo que sí se cumple: Swagger carga y `pip-audit` no encuentra vulnerabilidades.

Para pasar QP1, una de estas dos opciones (decisión del Arquitecto):
- Marcar en el README esos pasos como "pendiente (T13 / S02 / S05)" y dejar la puesta en marcha solo con migrate + uvicorn; o
- Implementar esos comandos antes de QP1.

Pendiente de QA (no se ha probado en esta ronda): P00 (revisar la nota de TASKS con versiones y resultados de rollback).
