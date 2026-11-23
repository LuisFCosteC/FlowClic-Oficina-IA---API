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

---

## Auditoría de seguridad — línea base (QS0)

Alcance: código de `dev` en `3669a5a` (API) y FRONT `dev` en `8e21fd0`. Método: revisión de código, búsqueda de patrones en el historial (solo recuentos, sin valores), `pip-audit` y `npm audit`, y pruebas en vivo contra una API temporal (puerto 4100, bóveda de prueba con claves ficticias). Ningún secreto real se leyó ni aparece en este informe.

Leyenda de resultados: CUMPLE · NO CUMPLE · PENDIENTE DE IMPLEMENTAR · N/A.

Los 5 campos de cada hallazgo son los de `docs/SECURITY_FINDINGS.md`: clasificación, severidad, vector e impacto CIA, causa raíz y remediación.

### 1. Claves y secretos subidos a repositorios
- **Clasificación:** A05:2021 · A07:2021 · CWE-540, CWE-798, CWE-312.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** acceso de cualquiera con el repositorio o su historial. C total, I alta, D alta.
- **Causa raíz:** CI/CD y gestión de secretos.
- **Remediación:** secretos fuera del código, hook `pre-commit`, secret scanning, rotar antes de purgar.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S11). El historial está limpio, pero no hay hook `pre-commit` instalado.
- **CVSS:** sin instancia real.
- **Evidencia:** en el historial de la API hay 3 coincidencias de patrones (`sk-…`, `TURSO_AUTH_TOKEN=…`): son valores de prueba (`tests/test_crypto.py`, `tests/test_envfile.py`, README), no secretos. En el FRONT: 0 coincidencias de `AIza…`. `.env` y `data/vault.db` nunca estuvieron en git. Sin `.git/hooks/pre-commit`.

### 2. APIs, tokens y credenciales expuestos en el frontend
- **Clasificación:** A02:2021 · A05:2021 · CWE-200, CWE-522, CWE-798.
- **Severidad:** Alta–Crítica.
- **Vector e impacto CIA:** todo lo que llega al navegador es público. C alta, I alta, D media/alta.
- **Causa raíz:** diseño del frontend (falta un backend intermediario).
- **Remediación:** el cliente no recibe secretos; solo `VITE_API_URL`; cookie `HttpOnly`; nada en `localStorage`.
- **Resultado:** CUMPLE. El bundle del FRONT no contiene `AIza…` ni `GEMINI_API_KEY`, y `vite.config.ts` no inyecta variables con `define`.
- **CVSS:** sin instancia real.
- **Evidencia:** `dist/assets/*.js` → 0 coincidencias. Pendiente de limpieza (F05): `.env.example` del FRONT aún lista `GEMINI_API_KEY` y `APP_URL` (sin valores).

### 3. BD expuesta a internet o sin reglas de acceso
- **Clasificación:** A01:2021 · A05:2021 · CWE-284, CWE-668, CWE-306.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** conexión directa a la BD o reglas permisivas. C total, I total, D total.
- **Causa raíz:** BD y gestión de accesos (IAM).
- **Remediación:** el navegador nunca habla con la BD; la API escucha en `127.0.0.1`; denegación por defecto en la API.
- **Resultado:** CUMPLE en exposición. `HOST` por defecto es `127.0.0.1`. `/app.db`, `/data/vault.db`, `/local.db`, `/.env` y `/.env.example` devuelven 404. El control por rol llega con S09 (ver #5).
- **CVSS:** sin instancia real.
- **Evidencia:** pruebas en vivo sobre la API de auditoría (puerto 4100): las cinco rutas → 404.

### 4. Acceso a registros ajenos (IDOR / BOLA)
- **Clasificación:** A01:2021 · API1:2023 (BOLA) · CWE-639, CWE-862.
- **Severidad:** Alta.
- **Vector e impacto CIA:** leer o modificar datos ajenos. C alta, I alta, D media.
- **Causa raíz:** autorización a nivel de objeto en el backend.
- **Remediación:** `WHERE id = ? AND owner = <sesión>`; recursos propios desde `/me/...`; tests de acceso cruzado.
- **Resultado:** N/A por ahora. No hay rutas con `{id}` ni recursos por usuario (aplicará desde T31/T42/S06).
- **CVSS:** sin instancia real.
- **Evidencia:** única ruta de la API: `GET /api/health` (en `app/routers/health.py`).

### 5. Endpoints de la API sin autenticación
- **Clasificación:** A07:2021 · A01:2021 · CWE-306.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** ejecución de operaciones sin sesión. C alta, I alta, D alta.
- **Causa raíz:** backend (sin autenticación global).
- **Remediación:** `requireAuth` global con denegación por defecto y lista blanca explícita; test que recorre todas las rutas y exige 401.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S09). Hoy solo existe `/api/health` (lista blanca) y no hay operaciones sensibles. No hay `requireAuth` todavía.
- **CVSS:** sin instancia de operación sensible. Sí hay exposición de documentación: ver #16.
- **Evidencia:** `GET /api/agents`, `/api/events`, `/api/snapshot`, `/api/admin/users`, `/api/login`, `/api/auth/login` → 404 (no existen aún).

### 6. Pagos sin validación en el servidor
- **Clasificación:** A04:2021 · A08:2021 · CWE-602, CWE-345, CWE-347.
- **Severidad:** Crítica cuando hay pagos.
- **Vector e impacto CIA:** importes manipulables y webhooks sin firma. C baja, I crítica, D baja.
- **Causa raíz:** backend y diseño de la integración.
- **Remediación:** importes en el servidor, firma HMAC, anti-replay.
- **Resultado:** N/A. FlowClic Fase 1 no tiene pagos.
- **CVSS:** sin instancia real.
- **Evidencia:** no hay rutas de pago ni webhooks en `app/`.

### 7. Login sin límite de intentos ni protección contra fuerza bruta
- **Clasificación:** A07:2021 · CWE-307.
- **Severidad:** Alta.
- **Vector e impacto CIA:** prueba automatizada de contraseñas. C alta, I alta, D media.
- **Causa raíz:** backend y gestión de accesos.
- **Remediación:** límite por IP (429 + `Retry-After`), bloqueo por cuenta, mensajes genéricos, hash ficticio para usuarios inexistentes.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S07). No hay ruta de login todavía.
- **CVSS:** sin instancia real.
- **Evidencia:** `POST /api/login` y `POST /api/auth/login` → 404.

### 8. Formularios e inputs sin validación (SQLi, XSS)
- **Clasificación:** A03:2021 · CWE-89, CWE-79, CWE-20.
- **Severidad:** Crítica (SQLi) / Alta (XSS almacenado).
- **Vector e impacto CIA:** SQLi o ejecución de JS en otro navegador. C alta, I alta, D media.
- **Causa raíz:** backend (consultas y validación) y frontend (codificación).
- **Remediación:** SQL parametrizado, Pydantic con `extra='forbid'`, límite de body, CSP, sin `dangerouslySetInnerHTML`.
- **Resultado:** PENDIENTE DE IMPLEMENTAR. Lo que existe ya cumple: no hay SQL interpolado en `app/` y el modelo de entrada rechaza campos extra (`extra="forbid"`). Faltan las rutas que reciban datos (T31+). La prueba de payloads de inyección se hace en QS3.
- **CVSS:** sin instancia real.
- **Evidencia:** búsqueda de `f"SELECT|INSERT|UPDATE|DELETE"` y `execute(f…)` en `app/` → 0 coincidencias. `app/domain/schemas.py` define `StrictInput`/`extra="forbid"`.

### 9. Dependencias obsoletas o con vulnerabilidades
- **Clasificación:** A06:2021 · CWE-1104, CWE-1395.
- **Severidad:** Alta (la del CVE heredado).
- **Vector e impacto CIA:** según el CVE. C/I/D hasta total.
- **Causa raíz:** CI/CD y cadena de suministro.
- **Remediación:** versiones exactas, `pip-audit` y `npm audit` en cada QA, quitar dependencias sin uso.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (F05). Las auditorías están limpias, pero el FRONT aún declara `@google/genai`, `express` y `dotenv`, que no se importan en `src/`.
- **CVSS:** sin instancia real (ninguna vulnerabilidad conocida).
- **Evidencia:** `pip-audit -r requirements.txt` y `requirements-dev.txt` → "No known vulnerabilities found". `npm audit` del FRONT → 0 vulnerabilities (con y sin dev). `src/` → 0 importaciones de esos tres paquetes.

### 10. Errores en producción que revelan información interna
- **Clasificación:** A05:2021 · CWE-209, CWE-497.
- **Severidad:** Media.
- **Vector e impacto CIA:** reconocimiento de versiones y estructura. C media, I baja, D baja.
- **Causa raíz:** backend (manejo de errores y configuración).
- **Remediación:** formato único, 500 genérico, sin cabeceras de versión, sin stack, `/docs` apagado en producción.
- **Resultado:** NO CUMPLE. Los errores sí van sin stack (500 y 404 con formato único), pero `GET /api/health` sin sesión devuelve `"version":"0.1.0"`, y las respuestas llevan `Server: uvicorn`. El criterio de S01 pide `{ok}` solo, sin sesión.
- **CVSS 3.1:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N` → **5.3 (Media)**.
- **Evidencia:** `GET http://127.0.0.1:4100/api/health` → `{"ok":true,"db":"up","version":"0.1.0"}`; cabecera `server: uvicorn`. Errores: `tests/test_errors.py` (500 sin stack) pasa.

### 11. Contraseñas en texto plano o sin hash moderno con sal
- **Clasificación:** A02:2021 · CWE-256, CWE-916, CWE-759.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** fuga de la BD expone todas las contraseñas. C crítica, I alta, D baja.
- **Causa raíz:** backend y base de datos.
- **Remediación:** scrypt (N=2^17, r=8, p=1) con sal única, parámetros en el hash, comparación en tiempo constante, mínimo 12 caracteres.
- **Resultado:** CUMPLE. Prueba directa: el formato es `scrypt$N=131072$r=8$p=1$…`, la sal es de 16 B (24 car. en base64), dos hashes de la misma clave son distintos, la clave correcta verifica y la incorrecta no. Política: `MIN_LENGTH = 12`, `MAX_LENGTH = 128`.
- **CVSS:** sin instancia real.
- **Evidencia:** `app/security/password.py` (líneas 12–13, 16). Prueba de hash/verificación sobre la copia de auditoría (sin imprimir claves).

### 12. Sin backups automáticos ni plan de recuperación (DRP)
- **Clasificación:** sin correspondencia directa en OWASP (lo más cercano: A04:2021) · ISO 27001 A.8.13, A.5.30 · NIST CSF PR.DS-11, RC.RP.
- **Severidad:** Alta.
- **Vector e impacto CIA:** ransomware o borrado sin recuperación. C baja, I alta, D crítica.
- **Causa raíz:** operaciones e infraestructura.
- **Remediación:** backups automáticos con retención, RPO 24 h / RTO 1 h, pruebas de restauración, DRP documentado.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S12). Hay variables de configuración (`BACKUP_DIR`, `BACKUP_KEEP`…) pero no hay código de backup ni `docs/DRP.md`.
- **CVSS:** sin instancia real.
- **Evidencia:** búsqueda de `VACUUM INTO`/`backup` en `app/`: solo aparece en `config.py`.

### 13. Cuenta administradora genérica con contraseña compartida
- **Clasificación:** A07:2021 · CWE-1391, CWE-1392, CWE-778.
- **Severidad:** Alta.
- **Vector e impacto CIA:** control total compartido, sin trazabilidad. C alta, I alta, D alta.
- **Causa raíz:** gestión de accesos (IAM).
- **Remediación:** cuentas nominativas; sin usuarios por defecto; primer ADMIN por consola o asistente con código de un solo uso; auditoría.
- **Resultado:** CUMPLE. La semilla no crea usuarios ni contraseñas. El primer ADMIN aún no existe porque llega con S05/C04; no hay una cuenta por defecto que se pueda usar.
- **CVSS:** sin instancia real.
- **Evidencia:** `app/db/seed.py` (cabecera: "La semilla NO crea usuarios ni credenciales"); búsqueda de `password`/`admin` en seed → sin credenciales.

### 14. Sin MFA en accesos privilegiados
- **Clasificación:** A07:2021 · CWE-308.
- **Severidad:** Alta.
- **Vector e impacto CIA:** una contraseña robada basta. C alta, I alta, D alta.
- **Causa raíz:** gestión de accesos (IAM).
- **Remediación:** TOTP obligatorio para ADMIN (RFC 6238) con secreto cifrado; reautenticación reciente para acciones críticas.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S08). No existe MFA ni `mfa/verify`.
- **CVSS:** sin instancia real.
- **Evidencia:** no hay rutas de MFA; `app/security/totp.py` no existe.

### 15. Credenciales, claves o cadenas de conexión hardcodeadas
- **Clasificación:** A07:2021 · CWE-798, CWE-259.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** quien lea el código obtiene la credencial. C alta, I alta, D alta.
- **Causa raíz:** backend y código fuente.
- **Remediación:** bóveda cifrada o variables de entorno; detección automática; rotación.
- **Resultado:** CUMPLE. `.env.example` solo tiene valores de configuración no sensibles (sin claves ni URLs). El código no tiene credenciales; los valores de prueba están en los tests y están marcados como ficticios.
- **CVSS:** sin instancia real.
- **Evidencia:** las claves no vacías de `.env.example` son `NODE_ENV`, `HOST`, `PORT`, `DB_DRIVER`, `CORS_ORIGIN`, `ORCHESTRATOR`, `DOCS_ENABLED`, `API_PUBLIC_ORIGIN`, `SESSION_*`, `BACKUP_*`, `ADMIN_ALLOW_DB_CHANGE`. Historial: ver #1.

### 16. Paneles administrativos accesibles sin sesión ni rol
- **Clasificación:** A01:2021 · CWE-425, CWE-862, CWE-306.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** conocer la URL da acceso. C alta, I alta, D alta.
- **Causa raíz:** backend (autorización real) y frontend (falsa sensación de seguridad).
- **Remediación:** autorización en el servidor en `/api/admin/*` (rol ADMIN + MFA); la documentación interactiva no da acceso sin sesión y se apaga en producción.
- **Resultado:** NO CUMPLE. Los paneles aún no existen (S09/F03), pero la documentación interactiva sí es accesible sin sesión en desarrollo, y la regla lo exige sin excepción. En producción quedaría apagada por defecto.
- **CVSS 3.1:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N` → **5.3 (Media)**.
- **Evidencia:** `GET /docs` → 200 (1024 B), `GET /openapi.json` → 200 (679 B), sin sesión, con `DOCS_ENABLED` por defecto en development. Las rutas `/api/admin/users` → 404.

### 17. Sesiones y tokens sin expiración ni revocación
- **Clasificación:** A07:2021 · CWE-613.
- **Severidad:** Media–Alta.
- **Vector e impacto CIA:** token robado válido para siempre. C alta, I alta, D baja.
- **Causa raíz:** backend y gestión de accesos.
- **Remediación:** token opaco de 32 B guardado como hash; expiración por inactividad (30 min) y absoluta (8 h); logout y revocación; cookie `HttpOnly; Secure; SameSite=Strict`.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S06). No hay sesiones todavía.
- **CVSS:** sin instancia real.
- **Evidencia:** `/api/auth/me`, `/api/auth/logout` → 404.

### 18. IA con permisos totales sobre la BD de producción
- **Clasificación:** OWASP LLM 2025 LLM01, LLM06, LLM02 · A01:2021 · CWE-250, CWE-269, CWE-1427.
- **Severidad:** Crítica.
- **Vector e impacto CIA:** inyección de prompt con acceso total. C crítica, I crítica, D alta.
- **Causa raíz:** gestión de accesos y arquitectura de integración de IA.
- **Remediación:** la IA nunca recibe un cliente de BD; identidad de servicio `AGENT` de mínimo privilegio; salidas del modelo como entrada no confiable; aprobación humana para lo sensible.
- **Resultado:** N/A en Fase 1. No hay SDK de IA ni llamadas a modelos en `app/` ni en `requirements.txt`. Se revisa en Fase 2.
- **CVSS:** sin instancia real.
- **Evidencia:** búsqueda de `anthropic|openai|genai|gemini|langchain` en `app/` y `requirements.txt` → 0 coincidencias.

### 19. Sin evaluaciones periódicas de seguridad
- **Clasificación:** A04:2021 · A09:2021 · sin CWE (control de proceso). Marcos: NIST SSDF, OWASP SAMM, ASVS 4.0.
- **Severidad:** Media.
- **Vector e impacto CIA:** debilidades acumuladas sin detectar. C/I/D indirecto.
- **Causa raíz:** gobierno de seguridad y CI/CD.
- **Remediación:** STRIDE al inicio de fase, auditoría de dependencias y de secretos en cada merge, checklist ASVS en QA, revisión automática de commits, pentest antes de exponer.
- **Resultado:** PENDIENTE DE IMPLEMENTAR (S11, S13). Este análisis existe (`docs/SECURITY_FINDINGS.md`) y esta auditoría es la línea base. Falta el hook `pre-commit` de revisión automática y el checklist de QS1–QS5.
- **CVSS:** sin instancia real.
- **Evidencia:** sin `.git/hooks/pre-commit` en API ni en FRONT.

---

### Resumen de la línea base

| Resultado | Hallazgos |
|---|---|
| CUMPLE | 2, 3, 11, 13, 15 |
| NO CUMPLE | 10, 16 (instancias reales, CVSS 5.3 cada una) |
| PENDIENTE DE IMPLEMENTAR | 1, 5, 7, 8, 9, 12, 14, 17, 19 |
| N/A | 4, 6, 18 |

Todos los PENDIENTE tienen tarea asociada (S06, S07, S08, S09, S11, S12, F05, T31+). Las dos instancias NO CUMPLE se corrigen con S01/S09 (health sin sesión → solo `{ok}`; docs sin sesión y apagadas fuera de desarrollo).

### Pendiente

- Probar después los PENDIENTE al implementarse (QS1–QS5).
- Mantener C02 (token de Turso) y K01 (validación del CEO) como están.
- Antes de cerrar esta auditoría: confirmar con el Arquitecto si el commit/push de este informe lo hago yo o lo hace él (no lo he hecho).
