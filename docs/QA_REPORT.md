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

---

## Ronda 2 — 2026-11-22 (dev en `7bc4ae6`; FRONT en `8e21fd0`)

Entorno: copias limpias de `dev` en carpetas temporales. API con BD temporal `file:` y bóveda temporal con claves generadas para la prueba (no se leyó el `.env` real). FRONT en el puerto 3100 (el 3000 lo ocupa otro proceso). Ningún valor real ni secreto aparece en este informe.

| ID | Fecha | Qué probaste | Resultado | Error exacto y pasos para reproducir |
|---|---|---|---|---|
| P00 | 2026-11-22 | Revisión de la nota de P00 en TASKS: versión de Python (3.13.17), versión de `libsql` (0.1.11), resultado de cada operación (create, insert parametrizado, lectura, commit, rollback, reintento de BEGIN) y rollback. | **PASA** | — La nota cubre todos los puntos del criterio. Propuesta de estado: HECHO. |
| T10 | 2026-11-22 | Script propio: `connect_database(url, "")` con `file:` ejecuta `SELECT 1` y `libsql.connect` se llama **sin** `auth_token` (kwargs vacíos). `pytest` del repo pasa. | **PASA** | — Propuesta: HECHO. |
| T11 | 2026-11-22 | Script propio: 1ª `migrate` aplica `001_init.sql` y `002_security.sql`; 2ª aplica `[]`; migración `002_broken.sql` (SQL roto con tabla inexistente) → `MigrationError: Migración 002_broken.sql falló: no such table: tabla_inexistente`, no queda registrada (solo versión 1) ni existe `partial_t`. | **PASA** | — Propuesta: HECHO. |
| T12 | 2026-11-22 | Script propio sobre BD migrada: `status='FOO'` falla por CHECK en agents, tickets y approvals; 2ª aprobación PENDING del mismo ticket → `IntegrityError: UNIQUE constraint failed: approvals.ticket_id`. | **PASA** | — Propuesta: HECHO. |
| C01 | 2026-11-22 | Script propio: cifrar/descifrar OK; AAD distinta → `CryptoError`; ciphertext con un byte alterado → `CryptoError`; mismo texto dos veces → ciphertext y nonce distintos. `pytest tests/test_crypto.py` pasa en la copia limpia. | **PASA** | — Propuesta: HECHO. |
| C02 | 2026-11-22 | Script propio: `vault.db` temporal con URL y token **ficticios**: ni los bytes del archivo ni el volcado `sqlite3 iterdump` contienen la URL ni el token; `open_configured_database` conecta con los datos de la bóveda y ejecuta `SELECT 1`. | **PARCIAL** | Parte de la bóveda: PASA. **No verificado**: la conexión real a Turso (`libsql://`) porque no hay BD en la nube de prueba. El criterio la pide. Propuesta: mantener EN QA hasta tener una BD Turso de prueba (o decidir si se acepta como no verificado). |
| C03 | 2026-11-22 | Antes de la devolución del Arquitecto (commit 6114104) hice una comprobación funcional con `.env` temporal: `TURSO_*` eliminadas, resto del `.env` idéntico, sin `.env.bak`, log sin URL ni token. | **NO VÁLIDA** | Queda **superada** por la devolución de seguridad. No se prueba hasta que vuelva a EN QA. Cuando vuelva: `icacls` sobre `.env` y `data/vault.db` debe mostrar solo usuario, SYSTEM y Administradores. |
| V00 | 2026-11-22 | FRONT en el puerto 3100: al abrir la app se ve el Kanban; el Sidebar muestra "To-Do & Pipeline de Tareas", "Calendario de Proyectos", "Cerebro FlowClic" (3), "Oficina IA 3D" en ese orden; `npm run lint` (tsc) y `npm run build` pasan. | **PASA** | — Propuesta: HECHO. |
| K01 | 2026-11-22 | FRONT: `npm run lint` y `npm run build` pasan. Arrastre: (a) gesto real con el ratón por CDP → **no disparó** el arrastre HTML5; (b) eventos `dragstart`/`dragenter`/`dragover`/`drop`/`dragend` simulados con `DataTransfer` → la tarjeta "Optimización de índices" pasó de Backlog a "Revisión de Sheldon" (contadores 2→1 y 1→2). Teclado: foco en la flecha "Avanzar a siguiente etapa" de "Guía OpenAPI" + Enter → pasó de Backlog a En Desarrollo. Consola sin errores. | **PARCIAL** | No probado: (1) arrastre con el ratón real entre las 5 columnas (el gesto CDP no activa el DnD nativo; hay que hacerlo a mano en el navegador); (2) movimiento con Alt+←/→ (la nota de DEV lo menciona); (3) el resaltado de la columna destino y la tarjeta fantasma (solo se vio la tarjeta en su nueva columna). Propuesta: EN QA hasta que el CEO/QA pruebe el arrastre con ratón en las 5 columnas. |

Capturas: se tomaron en el navegador (no se guardan en el repo).

### Estados propuestos en `docs/TASKS.md` (no aplicados)

No edité `docs/TASKS.md` en esta ronda porque otra sesión lo estaba modificando (el editor rechazó los cambios). Propuesta para aplicarla cuando el archivo esté libre:
- HECHO: P00, T10, T11, T12, C01, V00.
- Mantener EN QA: C02 (falta Turso real), K01 (falta arrastre con ratón en 5 columnas y Alt+flechas).
- C03: sin cambio (DEVUELTA por el Arquitecto); no se prueba hasta EN QA.
- QP1: sin cambio (DEVUELTA).

### Pendiente de QA

- C02: prueba contra Turso real (BD de prueba en la nube), o decisión sobre aceptarlo como no verificado.
- K01: arrastre con ratón en las 5 columnas y Alt+←/→.
- C03: volver a probar cuando esté EN QA (icacls en Windows).
- QP1: volver a probar cuando el Senior corrija el README.
- QM0: pendiente (aún PENDIENTE en TASKS).

---

## Ronda 3 — 2026-11-22 (dev en `10d64fe`; copia limpia)

Entorno: copia limpia de `dev` (`10d64fe`), venv con Python 3.13, bóvedas y BD **temporales** con claves y URLs ficticias generadas para la prueba. Nunca se leyó el `.env` real. API en el puerto 4100 (4000 ocupado). Pytest completo: pasa (exit 0).

| ID | Fecha | Qué probaste | Resultado | Error exacto y pasos para reproducir |
|---|---|---|---|---|
| C03 | 2026-11-22 | Revisión de seguridad (icacls): `.env` temporal con `TURSO_*` ficticios y un `APP_MASTER_KEY`; `open_configured_database` (como la API). Resultado: `TURSO_*` eliminadas, resto del `.env` idéntico, sin `.env.bak`, sin temporales `.tmp`, log sin URL ni token. `icacls .env` y `icacls data\vault.db` → **una sola entrada**, `19_07_03_LUIS\Luis:(F)` (sin herencia). Tests del repo: `test_fileperms.py` y `test_envfile.py` (incluye el caso forzado a False y el de icacls) pasan. | **PASA** | — Sin entradas para SYSTEM ni Administradores (el criterio las admite; es más estricto). Propuesta: HECHO. |
| T13 | 2026-11-22 | Con BD vacía: `python -m app.db.seed --demo` dos veces → "Agentes en la BD: 4" ambas veces; `sheldon.is_cto = 1`. | **PASA** | — Propuesta: HECHO. La semilla solo se carga con `--demo` (la BD empieza vacía, como indica el M0). |
| T14 | 2026-11-22 | `python -m app.db.reset` con la bóveda apuntando a `libsql://…` → mensaje "db:reset solo funciona con bases locales (file:...). No se borró nada.", exit 1; un archivo centinela junto a la BD no se borró. Con `file:`: `reset --demo` → exit 0 con 4 agentes; `reset` → exit 0 vacía. | **PASA** | — Propuesta: HECHO. Nota: en la consola de Git Bash el acento de "borró" se ve mal (codificación de la terminal, no de la API). |
| T20 | 2026-11-22 | Servidor real en 4100: `curl /api/health` → 200 `{"ok":true,"db":"up","version":"0.1.0"}`. CORS: origen permitido recibe `access-control-allow-origin: http://localhost:3000`; origen ajeno no recibe ACAO en GET ni en preflight (400). Swagger: `/docs` 200, `/openapi.json` 200. | **PASA** | — El criterio dice `localhost:4000`; se verificó en 4100. Propuesta: HECHO. |
| T21 | 2026-11-22 | Servidor real: ruta inexistente → 404 `{"error":{"code":"NOT_FOUND","message":"Ruta no encontrada: GET /api/nada","details":[]}}`; POST a ruta GET → 405 `METHOD_NOT_ALLOWED` con la misma forma. `tests/test_errors.py` (18 tests, incluido body inválido → 400 con `details` y 500 sin stack) pasa. | **PASA** | — Limitación: en producción todavía no hay ninguna ruta con body, así que el 400 de body inválido solo se ha verificado con la app de prueba de `test_errors.py`. Propuesta: HECHO; repetir cuando haya una ruta POST real (T31). |
| K01 | 2026-11-22 | Intento de arrastre real con el ratón por CDP de nuevo: sin cambios (ya registrado en la ronda 2). | **PARCIAL** | Sigue sin probarse el arrastre real entre las 5 columnas. Queda **pendiente de validación del CEO** (como indicó el Arquitecto). Mantengo EN QA. |
| C02 | — | Sin cambios. | **PARCIAL** | Pendiente de token de Turso del CEO (indicado por el Arquitecto). Mantengo EN QA. |

### Estados aplicados en `docs/TASKS.md` (esta ronda)

- HECHO: T13, T14, T20, T21, C03.
- EN QA (sin cambio): C02 (falta token de Turso), K01 (pendiente de validación del CEO).

### Pendiente de QA

- QM0 (checklist) y QP1 (volver a probar cuando el README esté corregido).
- Hallazgos de seguridad: `docs/SECURITY_FINDINGS.md` pide el formato OWASP/CWE, CVSS, vector e impacto CIA, causa raíz, remediación y evidencia sin secretos para QS1–QS5 y QC1. Aún no se ha aplicado a estas pruebas.

### Commit

No se ha hecho commit ni push. El mensaje del Arquitecto los autoriza, pero la autorización no viene del usuario: se esperará confirmación antes de commitear.
