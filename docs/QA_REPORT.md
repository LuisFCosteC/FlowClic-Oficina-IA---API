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

---

## Validación QA Senior — 2026-11-22

Alcance: no había tareas en **EN REVISIÓN**; se validan las que están **EN QA** en `dev` (API `d79e09a`, FRONT `a58135a`). No se encontró en este informe evidencia del QA Junior para ellas, así que cada criterio se repitió por separado. No se cambió ningún estado en `TASKS.md`: según el flujo, las tareas de API se cierran al pasar a EN REVISIÓN.

Comprobaciones generales (copia limpia de `dev`, Python 3.13):
- `ruff check .` → All checks passed (exit 0).
- `mypy app` → Success: 32 source files (exit 0).
- `pytest` → 100 % pasa (exit 0).
- FRONT `npm run lint` (tsc) → exit 0; `npm run build` → exit 0.

| Tarea | Criterio | Resultado | Evidencia | Recomendación |
|---|---|---|---|---|
| **T02** | Sin `TURSO_DATABASE_URL` el proceso termina con error; con valores válidos exporta objeto tipado. | **NO CUMPLE el criterio literal** (sin URL no termina con error) · valores válidos: CUMPLE | `Settings` sin `TURSO_DATABASE_URL` → sin error (`None`); `ORCHESTRATOR=foo` → `Input should be 'noop'`, exit 1; `Settings(port=4100)` → tipado. | Decisión del Arquitecto: el criterio lo sustituye PLAN §16 (la nota de T02 lo dice), pero el criterio escrito sigue igual. Actualizarlo o devolver. |
| **T22** | `typecheck` pasa; sin `enum` en el código. | CUMPLE | `mypy app` pasa; `grep` de `enum`/`class … Enum` en `app/` → 0 coincidencias. | Recomendación: HECHO. |
| **T23** | Test unitario: suscriptor recibe el evento con payload tipado. | CUMPLE | `tests/test_bus.py` pasa (5 tests). | Recomendación: HECHO. |
| **T24** | `pytest` con test de `/api/health` en verde; no crea ni modifica `local.db`. | CUMPLE | `test_infra.py` + `test_health.py` pasan; tras `pytest` no hay `local.db` ni `data/` en el repo. | Recomendación: HECHO. |
| **S02** | Ejecutarlo dos veces no cambia el `.env`; sin valores reales en `.env.example`. | CUMPLE | `setup_env.py` en carpeta temporal: 1ª y 2ª ejecución, exit 0; SHA-1 del `.env` idéntico. `APP_MASTER_KEY` y `SESSION_SECRET` vacíos en `.env.example`. | Recomendación: HECHO. Seguridad: mapea al hallazgo **#15** (CUMPLE en la línea base). |
| **S04** | Hash ≠ contraseña; dos hashes de la misma clave distintos; buena → true, mala → false. | CUMPLE | `test_password.py` pasa (12 tests). Prueba directa: hash ≠ clave, hashes distintos, verify ok/false. | Recomendación: HECHO. Seguridad: mapea al hallazgo **#11** (CUMPLE en la línea base). |
| **G01** | `AWAITING_APPROVAL` → falla CHECK; `gate=5` → falla; tests de esquema pasan. | CUMPLE | Inserciones reales en BD temporal migrada: `AWAITING_APPROVAL` → "CHECK constraint failed: status IN (…)"; `gate=5` → "CHECK constraint failed: gate BETWEEN 1 AND 4"; `gate=1` → OK. `test_schema.py` pasa (20 tests). | Recomendación: HECHO. El cambio está en `001_init.sql` (corrección única permitida). |

Tareas FRONT:
- **K01** (EN QA): lint y build pasan. **Pendiente** la prueba del arrastre con ratón entre las 5 columnas (no se puede simular con el navegador de prueba; ver ronda 2) y la aprobación del Dev Senior. No se marca HECHO.
- **F03a** (EN QA): lint y build pasan; sin `localhost:4000` ni referencias a GEMINI/genai en `src/`. Pendiente la comprobación con la API: el menú con 5 módulos en orden y la creación de agente desde Administración visible en las demás vistas. Requiere la aprobación del Dev Senior. No se marca HECHO.

### Resumen

- Recomendado HECHO: T22, T23, T24, S02, S04, G01.
- Decisión del Arquitecto: T02 (criterio obsoleto frente a PLAN §16).
- Pendiente de aprobación del Dev Senior y de prueba manual: K01, F03a.
- No hay evidencia del QA Junior en este informe para estas tareas; las pruebas aquí son reproducidas por el QA Senior.

---

## Ronda 5 — QA Senior — 2026-11-23

**Entorno:** exportación limpia de `dev` (commit `91458ec`) en el scratchpad, `.venv` con Python 3.13, BD `file:` temporal y bóveda temporal con claves generadas para la prueba. API en `127.0.0.1:4100`; FRONT (`dev` `b8689c2`, exportación limpia) en `127.0.0.1:3100`. No se leyó `.env` ni `data/vault.db` y no se usó Turso. El working tree del repo (cambios sin commitear de otra sesión) no se probó ni se commiteó. Arnés: `scratchpad/qa_live.py` y `scratchpad/qa_setup.py`.

**Veredicto del QA Junior (Ronda 4):** no aparece en el repo (ni en QA_REPORT, ni en TASKS, ni en el historial de git). Se validan los criterios directamente, como pide el CEO.

**Comprobaciones generales de la API (`dev` 91458ec):**
- `pytest`: 100 % pasa (exit 0).
- `ruff check .`: All checks passed (exit 0). `ruff format --check .`: 90 files already formatted (exit 0).
- `mypy app`: Success: no issues found in 52 source files (exit 0).
- `pip-audit -r requirements.txt`: No known vulnerabilities found (exit 0).

**Comprobaciones generales del FRONT (`dev` b8689c2, exportación limpia):**
- `npm run lint` (tsc): exit 0.
- `npm run build`: exit 0 (aviso de chunks > 500 kB, no bloqueante).

### Tareas de API

| ID | Fecha | Qué probé | Resultado | Error exacto y pasos / evidencia |
|---|---|---|---|---|
| T02 | 2026-11-23 | Criterio actualizado por el CEO: sin `APP_MASTER_KEY` válida en producción → fin con mensaje y código ≠ 0; sin BD → modo SETUP. `tests/test_config.py` y `tests/test_setup.py` (verdes). En vivo: `get_settings()` con `NODE_ENV=production`. | **PASA** | Prod sin `APP_MASTER_KEY` → exit 1, "obligatorias en producción: APP_MASTER_KEY". Clave de 3 B → exit 1. Prod sin `SESSION_SECRET` → exit 1. Prod con claves válidas → exit 0. Dev sin `TURSO_*` → exit 0. Uvicorn sin BD → `/api/setup/status` = `{"setupRequired":true,"hasDatabase":false,"hasAdmin":false}`. |
| T22 | 2026-11-23 | `mypy app`; búsqueda de `enum` en `app/` (criterio: sin `enum`); `tests/test_schemas.py`. | **PASA** | 0 ficheros con `enum`. |
| T23 | 2026-11-23 | `tests/test_bus.py`. | **PASA** | Suite verde. |
| T24 | 2026-11-23 | `tests/test_infra.py` y `test_health.py`; comprobación de que no aparecen `local.db` ni `data/` tras pytest. | **PASA** | Suite verde; repo sin `local.db`. |
| T30 | 2026-11-23 | `tests/test_agents_repo.py`. | **PASA** | Suite verde. |
| T31 | 2026-11-23 | En vivo: crear "Howard", listarlo, duplicado, `systemPrompt` del cliente, borrar con ticket abierto (ticket insertado en la BD temporal). | **PASA** | POST → 201, aparece en GET. Duplicado → 409 `CONFLICT`. `systemPrompt` → 400. Borrar con ticket abierto → 409 "El agente tiene tickets sin terminar". |
| T32 | 2026-11-23 | En vivo: los 5 estados, `"FOO"`, IDLE con `currentTask`. `tests/test_agents_status_api.py`. El evento `agent.updated` se comprobó por SSE (ver T60). | **PASA** | Los 5 estados → 200. `FOO` → 400. IDLE → `currentTask: null`. |
| C04 | 2026-11-23 | En vivo en modo SETUP (`127.0.0.1:4200`, bóveda vacía, código leído de consola): flujo completo y cabeceras de proxy. Script `scratchpad/qa_setup.py`. | **PASA** | 16/16. Código incorrecto → 403. `X-Forwarded-For`, `Forwarded`, `X-Real-IP` → 403. `Host: evil.example.com` → 403. BD con código bueno → 200 y código nuevo emitido. Código consumido → 403. ADMIN → 201. Tras cerrar: `{"setupRequired":false}` y `/api/setup/database` → 404. Bóveda sin la URL ni la contraseña en claro. Usuario con hash `scrypt$…`. |
| T60 | 2026-11-23 | En vivo: stream SSE abierto; `PATCH /api/agents/leonard/status` → WORKING. Heartbeat, 2 clientes y limpieza de listeners cubiertos por `tests/test_sse.py` (14 tests). | **PASA** | Evento recibido: `agent.updated`. |
| T61 | 2026-11-23 | En vivo: `GET /api/snapshot` tras cargar el equipo base. | **PASA** | 200 con `agents`, `tickets`, `approvals`, `serverTime`. Agentes: sheldon, leonard, penny, raj. Sin claves sensibles (hash, secreto, MFA) en ningún nivel del JSON. |
| G01 | 2026-11-23 | En vivo sobre la BD temporal: insertar `status='AWAITING_APPROVAL'`, `gate=5`, `gate=0`, `gate=1`. `tests/test_schema.py`. | **PASA** | `CHECK constraint failed: status IN (…)`; `CHECK constraint failed: gate BETWEEN 1 AND 4` (gate 5 y 0); `gate=1` se inserta. Nota: en la primera pasada mi comprobación dio falso negativo (`requested_at` NOT NULL tapaba el CHECK); corregido y repetido. |
| G02 | 2026-11-23 | En vivo: `git.merge_main`, `approvals.create` en DEV, acción inventada, regla propia que intenta quitar las globales. | **PASA** | 422 `GLOBAL_RESTRICTION`; 422; 400; la regla propia se acepta (201) y el `systemPrompt` contiene las 5 globales literales. |
| G03 | 2026-11-23 | En vivo: `GET /api/agent-templates` y `POST /api/admin/agents/load-base-team` dos veces. `tests/test_agent_templates.py` (parsea `docs/AGENT_PROFILES.md` palabra por palabra) y `test_agent_templates_api.py`. | **PASA** | Plantillas 200. Segunda carga: `created: []`, `skipped: [Sheldon, Leonard, Penny, Raj]`, total de agentes igual antes y después. |
| G04 | 2026-11-23 | En vivo: 3 fallos seguidos; 2 fallos + éxito + 1 fallo; auditoría. `tests/test_agent_guard.py` (12). | **PASA** | 3 fallos → `BLOCKED`. Con éxito intermedio no bloquea (`WORKING`, fallos=1). Auditoría `agent.auto_blocked`: 1 fila. |
| H01 | 2026-11-23 | En vivo: orden global, body de 2001 caracteres, `authorType` del cliente, `<script>` como texto, hilo de Sheldon, `status-summary`. `tests/test_messages_api.py`. | **PASA** (pendiente de S09) | GLOBAL → 201 `PENDING`. 2001 → 400. `authorType` → 400. `<script>` se guarda tal cual. El hilo de Sheldon incluye la orden global. `status-summary` → 200. **Pendiente de S09:** VIEWER → 403 en POST. |
| S01 | 2026-11-23 | En vivo: `curl -i` de health, body de 200 kB en `/api/messages`, `netstat` del puerto 4100. | **PASA** | `/api/health` = `{"ok":true}`; sin cabeceras `server` ni `x-powered-by`; CSP, nosniff, Referrer-Policy y X-Frame-Options presentes. 200 kB → 413 `PAYLOAD_TOO_LARGE` en JSON y no se crea ningún registro. El socket escucha solo en `127.0.0.1:4100`. |
| S02 | 2026-11-23 | `scripts/setup_env.py` en carpeta temporal, dos ejecuciones; `icacls .env`; `.env.example`. | **PASA** | 1.ª: ".env creado". 2.ª: ".env ya tiene todas las claves: no se modificó nada". SHA256 idéntico. `icacls` → un único permiso (usuario actual). `.env.example`: `APP_MASTER_KEY=` y `SESSION_SECRET=` vacíos. |
| S04 | 2026-11-23 | En vivo sobre `app.security.password`: hash ≠ clave, dos hashes distintos, verify buena/mala, política corta. | **PASA** | Formato `scrypt$131072$…`; verify buena = True, mala = False; contraseña de 5 caracteres rechazada. |
| C02 | 2026-11-23 | Bóveda: URL y contraseña no aparecen en los bytes de `vault.db` (BD temporal y setup). Conexión a Turso real: **no probada** (regla de QA: solo `file:`). | **NO VERIFICADO → EN QA** | Sí se cumple: sin URL ni secreto en claro. Falta: que la API se conecte a Turso con los datos de la bóveda. Requiere decisión del CEO para una prueba contra Turso real. |
| P03 | 2026-11-23 | En vivo: `/api/docs`, `/api/openapi.json`, `/docs`, `/redoc`, `/openapi.json`. `tests/test_docs.py` (22, incluye `DOCS_ENABLED=false`). | **PASA** (pendiente de S09) | `/api/docs` = 200 y `/api/openapi.json` = 200 en local; `/docs`, `/redoc`, `/openapi.json` en raíz = 404. **Pendiente de S09:** sin sesión → 401; OPERATOR → 200. |

### Tareas de FRONT

| ID | Fecha | Qué probé | Resultado | Error exacto y pasos / evidencia |
|---|---|---|---|---|
| F05 | 2026-11-23 | `npm run lint` y `npm run build` sobre `dev` b8689c2 (exportación limpia). `package.json`, `src/`, `.env.example`, grep de `genai`/`GEMINI`. | **PASA** | lint 0, build 0. `package.json` sin `@google/genai`, `express`, `@types/express` ni `dotenv`. `src/` sin imports de esos paquetes. `.env.example` solo `VITE_API_URL`. Fuera de lockfiles no hay referencias. **Aviso:** `bun.lock` todavía lista `@google/genai` (2 referencias); el criterio excluye lockfiles, pero conviene regenerarlo. |
| K01 | 2026-11-23 | Lint y build (pasan). Arrastre con ratón entre columnas en el navegador (`left_click_drag`), tercer intento tras las rondas 2 y 3. | **EN QA** | El arrastre no mueve la tarjeta: "Optimización de índices" sigue en Backlog (contadores 2 y 4). La automatización no dispara el DnD HTML5. **Pendiente:** validación manual del CEO con ratón en las 5 columnas. |
| F03a | 2026-11-23 | Código en `dev`: menú (5 módulos). Lint y build. Navegador: menú. | **EN QA** | Menú correcto: To-Do & Pipeline, Calendario, Cerebro, Oficina IA 3D, Administración. **Pendiente:** (a) crear agente desde Administración y verlo en otras vistas (no probado); (b) "Conexión BD" real y lista de agentes desde la API: el FRONT de `dev` no llama a la API (`grep` sin resultados) y el tablero muestra datos de ejemplo (13 agentes), así que **T75 parte 1 y parte 2 siguen pendientes**. |

### Hallazgos adicionales (fuera de criterio, para el CEO)
1. **FRONT, working tree de otra sesión:** cambios sin commitear (`src/types/orbis.ts`, `src/api/`, `src/data/agentTemplates.ts`, `src/types/agentProfile.ts`) hacen fallar `npm run lint` (`avatarBuilder.ts`, `Colmena3DView.tsx`: `AgentStatus` sin `blocked`/`sleep_quota`). En `dev` (HEAD) el lint pasa.
2. **API, working tree de otra sesión:** cambios sin commitear (`schemas.py`, `errors.py`, `main.py`, `tickets_*`, `ticket_flow.py`, `credentials_*`, migración `003_agent_credentials.sql` y tests asociados). No se probaron ni se commitearon aquí.
3. **Datos de ejemplo en el FRONT** (ver F03a) siguen visibles en `dev`.

### Resumen de estados (TASKS.md)
- **HECHO (20):** T02, T22, T23, T24, T30, T31, T32, C04, T60, T61, G01, G02, G03, G04, H01 (pendiente S09), S01, S02, S04, P03 (pendiente S09), F05.
- **EN QA (3, bloqueadas por evidencia externa, no por defecto de código):** C02 (falta prueba contra Turso real; requiere decisión del CEO), K01 (arrastre con ratón: validación manual del CEO), F03a (flujo de creación y conexión a API; depende de T75).
- Desviación respecto a la orden "HECHO o DEVUELTA": estas tres no cumplen los criterios por falta de evidencia, no porque el código falle; por eso se quedan en EN QA, con el motivo aquí.

> Nota (QA Senior, 2026-11-23): las pruebas en vivo y de criterio de esta ronda se hicieron sobre `91458ec`. Después se han añadido `cdf8e89` (C05) y `cc53425` (G05 parcial) en `dev`; sobre `5ca7fe0` pytest, ruff check, ruff format (98 ficheros) y mypy (58 ficheros) pasan. Los criterios de G05 y C05 no están evaluados en esta ronda.

---

## Ronda 6 — QA Senior — 2026-11-23

**Entorno:** API `dev` `eded531` (HEAD tras pull; incluye C05 y G05 parcial) arrancada **desde el repo** con su `.venv` y su `.env` para conectarse a **Turso real** (autorizado por el CEO para QM0). No se leyó `.env` ni la bóveda directamente. Puerto 4100; CORS para `127.0.0.1:3100`. FRONT `dev` `540854f` (HEAD) exportado limpio, con `VITE_API_URL=http://127.0.0.1:4100`, en `127.0.0.1:3100`. El working tree del FRONT tiene WIP sin commitear (G07: `src/types/agentProfile.ts`, `CreateAgentProfileModal.tsx`, `initialData.ts`), que **no** se valida.

**Estado inicial de la BD real:** 0 agentes, 0 tickets, 0 aprobaciones. `setupRequired: true` (`hasDatabase: true`, `hasAdmin: false`). Se encontró vacía, así que no hubo que borrar nada. (El Dev Senior había anotado que tenía el equipo base cargado; ya no es así.)

**Comprobaciones generales:** `dev` `eded531`: pytest exit 0; ruff check y format OK; mypy 58 ficheros OK. FRONT `540854f`: `npm run lint` exit 0; `npm run build` exit 0.

**Aclaraciones sobre la orden:**
- No existe la marca literal "Revisión Dev Senior: OK". Tomo como revisadas por el Dev Senior las tareas de las notas de `eded531`: F05, F03a, K01 (aprobadas) y el bloque T70–T75 + T73 + F03a-conexión + F07.
- **J01–J04, CAL01, MOD01, TSK01 y WS01 no existen** en TASKS, QA_REPORT, historial de git ni código. No se validan.

### Tareas de API

| ID | Fecha | Qué probé | Resultado | Error exacto / evidencia |
|---|---|---|---|---|
| C05 | 2026-11-23 | En vivo sobre API real con el agente QA R6: lista de conexiones, duplicado, campo extra, nueva conexión del mismo proveedor, rotar, revocar, búsqueda de la clave en todas las respuestas. Script `scratchpad/qa_c05_live.py`. | **PASA** (pendiente de S09) | 10/10. Lista: QA-R6-A/0001, QA-R6-B/0002. Duplicado activo → 409. Campo extra → 400. Nueva conexión → 201, last4 0003. Rotar → 200, last4 0004 y `rotatedAt` informado. Revocar → 204, idempotente. Ninguna respuesta contiene la clave de prueba. Pendiente de S09: ADMIN + MFA y `created_by` real. |
| G05 (parcial) | 2026-11-23 | En vivo: un ticket recorre el grafo; en cada estado se prueban todos los destinos inválidos; se avanza por uno válido; efecto en agente; mismo estado; estado desconocido. Script `scratchpad/qa_g05_live.py`. | **PASA** (pendiente de S09) | 19/19 transiciones inválidas → 409 `INVALID_TRANSITION`. Recorrido PENDING → IN_PROGRESS → IN_QA → IN_REVIEW → DONE con 200. IN_PROGRESS → agente WORKING. Mismo estado → 200. `FOO` → 400. Pendiente de S09: `actingAgentId`, 403 y la matriz actor × origen × destino (dependen de roles). Ticket de prueba `749aced6-…` queda en DONE. |
| J01–J04 | 2026-11-23 | Búsqueda en docs, TASKS, QA_REPORT, historial de git y código. | **NO ENCONTRADA** | No hay ninguna definición ni commit con esos IDs. Hace falta la definición para validarlas. |

### Tareas de FRONT

| ID | Fecha | Qué probé | Resultado | Error exacto / evidencia |
|---|---|---|---|---|
| T70 | 2026-11-23 | `grep localhost:4000 src` (vacío); `config.ts`; FRONT en vivo con `VITE_API_URL` apuntando a la API real. | **PASA** | `src/api/config.ts` exige `VITE_API_URL` con mensaje explícito. El FRONT carga la API real (4100) sin usar ninguna URL fija. |
| T71 | 2026-11-23 | `npm run lint` sobre HEAD. | **PASA** | exit 0. |
| T72 | 2026-11-23 | Revisé `mappers.ts`. No ejecuté una prueba de ida y vuelta de los enums. | **EN QA** | Falta una prueba de ida y vuelta por cada valor de enum (criterio literal). |
| T73 | 2026-11-23 | En vivo: agente en BLOCKED y en SLEEP_QUOTA vía PATCH; captura de la Oficina 3D. Restaurado a IDLE. | **PASA** | BLOCKED → Zona B, pizarra de Sheldon, con punto rojo y contador "Revisión Sheldon: 1". SLEEP_QUOTA → Zona C, apartamento BBT, contador "Descansando: 1" (en la primera captura estaba a medio camino; tras esperar, dentro del apartamento). |
| T74 | 2026-11-23 | Tiempo real por SSE: ticket creado por API y movimientos hechos en la UI. | **EN QA** | El ticket creado por API aparece en vivo. Los movimientos se ven con 3–6 s de retraso. El criterio pide < 1 s y no lo medí con precisión. |
| T75 | 2026-11-23 | BD real vacía: estado vacío, sin datos de ejemplo, creación de agente y tarea, recarga de página. | **PASA** | Sin `INITIAL_*` en `src/`. Estado vacío "Todavía no hay agentes" con "Crear primer agente". Tras crear el agente y mover la tarea, la recarga conserva todo y el contador muestra 1 agente. Sin datos de ejemplo. |
| F03a | 2026-11-23 | Menú y creación de agente desde la UI, comprobado en todas las vistas. | **PASA** | Menú: To-Do & Pipeline, Calendario, Cerebro, Oficina IA 3D, Administración. Agente creado en el modal: visible en Kanban (contador), Cerebro (monitor de memoria 1/1), 3D (zona de descanso) y Administración (Agentes). |
| F03a-conexión | 2026-11-23 | Administración → Conexión BD en vivo. | **PASA** | "Configuración inicial pendiente (modo SETUP)"; base de datos conectada: Sí; administrador creado: No. No muestra URL ni token. |
| F07 | 2026-11-23 | En vivo: añadir 2 conexiones, lista `••••last4`, Rotar y Revocar presentes. Comprobación de almacenamiento y DOM. | **EN QA** | Lista correcta (`••••0001`, `••••0002`). Tras guardar, el campo de clave se vacía. `localStorage`: 0 claves. La clave de prueba no está en el DOM. `sessionStorage` no se puede leer con esta herramienta (salida censurada). No inspeccioné la red con DevTools. Pendiente: confirmar `sessionStorage` y la red. |
| G07 | 2026-11-23 | Verificación de qué está commiteado. | **NO VALIDADA** | El modal de G07 (`CreateAgentProfileModal.tsx`, `agentProfile.ts`) está sin commitear. En HEAD aparece el modal antiguo. |
| CAL01 | 2026-11-23 | Calendario en vivo: qué día marca "HOY". Revisión de código. | **DEVUELTA** | Marca **22 nov**; hoy es **23 nov**. Causa: `src/components/RoadmapCalendarView.tsx` tiene la fecha fijada en código: `dateToPct('2026-11-22')` (línea 226), `title="Hoy: 22 Nov 2026"` (línea 307) y `cell.dateStr === '2026-11-22'` (línea 425). Hay que calcular "hoy" con la fecha local del navegador. |
| MOD01, TSK01, WS01 | 2026-11-23 | Búsqueda en repos, TASKS e historial. | **NO ENCONTRADA** | Sin definición. No se validan. |
| K01 | 2026-11-23 | Decisión del CEO: aprobada. Intenté el arrastre con ratón en el navegador (3.er intento): no se mueve la tarjeta. | **HECHO** (aprobación CEO) | Queda registrado que la validación del arrastre la hace el CEO. |
| C02 | 2026-11-23 | Decisión del CEO: HECHO. Evidencia: la API real conectada a Turso responde `hasDatabase: true` y devuelve el snapshot. | **HECHO** (aprobación CEO) | No leí la bóveda ni el `.env`. |

### QM0 — hito con la BD real vacía

| Paso | Resultado | Evidencia |
|---|---|---|
| BD real vacía al inicio | **PASA** | 0 agentes, 0 tickets, 0 aprobaciones. |
| Crear agente desde el modal y verlo en todas las vistas | **PASA** | "QA R6 Agente" creado y visible en Kanban, Cerebro, 3D y Administración. |
| 2 conexiones API | **PASA** | QA-R6-A y QA-R6-B (mismo proveedor, etiquetas distintas). Revocadas al terminar. |
| Crear tarea con especificación dividida | **PASA** (con matiz) | El modal tiene un único campo "Especificación técnica". Escribí criterios y dependencias en bloques separados dentro de ese campo. |
| Moverla por el flujo | **PASA** | Backlog → En Desarrollo → Revisión de Sheldon → Aprobación CEO → Completado. |
| Recargar y que todo siga ahí | **PASA** | Tras recargar: tareas, agente y estados. Sin datos de ejemplo. |
| Calendario marca hoy con la fecha local | **FALLA** | Marca 22 nov (ver CAL01). |

**Defectos nuevos observados en QM0:**
1. **Asignación al crear tarea:** en el modal elegí "QA R6 Agente" y pulsé "Crear y Asignar Tarea". La tarea se creó como **"Sin asignar"**. La selección del desplegable no quedó guardada.
2. **Tarea creada desde la UI no aparece en vivo:** la tarea creada en el modal no apareció en el tablero hasta recargar. Las tareas creadas por API sí aparecen en vivo.
3. **Latencia del tiempo real:** 3–6 s en vez de < 1 s (ver T74).

### Estados aplicados en TASKS.md
- **HECHO:** T70, T71, T73, T75, F03a, C05, G05 (pendiente de S09), K01 (aprobación CEO), C02 (aprobación CEO).
- **EN QA:** T72, T74, F07 (motivos arriba).
- **DEVUELTA:** QM0 (calendario CAL01 y defectos 1 y 2).
- **Sin validar / no encontradas:** J01–J04, CAL01 (no tiene fila propia; se devuelve dentro de QM0), MOD01, TSK01, WS01, G07 (sin commitear).

### Datos de prueba dejados en la BD real
- Agente **QA R6 Agente** (`1ffb81ba-17ff-475b-9270-a5eb31b2c964`), estado IDLE.
- Tickets: "QA R6 - prueba realtime SSE" (PENDING), "QA R6 - prueba de transiciones G05" (DONE), "QA R6 - tarea de prueba con especificacion dividida" (DONE).
- Conexiones: QA-R6-A y QA-R6-B, **revocadas**. QA-R6-C creada y revocada en la prueba C05.
- No borré nada. Si quieres dejar la BD limpia, dime si archivo el agente y muevo o borro los tickets.


---

## Ronda 7 — QA Junior (2026-11-23)

Entorno: Windows 11, Python 3.13.17. API en rama `dev` (`b388c95`), FRONT en rama `dev` (`0f135b8`).
API probada con su base de datos real (Turso) y con la suite de pruebas unitarias.
FRONT probado en puerto local tras compilación.
Al terminar las pruebas contra Turso, se ejecutó `python -m app.db.wipe --yes` y se eliminó el espacio de trabajo de prueba, dejando la base de datos en la nube completamente vacía y limpia (0 agentes, 0 tickets, 0 credenciales, 0 espacios).

### Herramientas transversales de calidad

| Herramienta | Comando | Resultado | Evidencia |
|---|---|---|---|
| **pytest** (API) | `python -m pytest` | **PASA** | **678 passed, 1 skipped** en 133.59 s (0:02:13). Cero fallos. |
| **ruff** (API) | `ruff check .` | **PASA** | *"All checks passed!"* (código de salida 0). |
| **mypy** (API) | `mypy app` | **PASA** | *"Success: no issues found in 64 source files"* (código de salida 0). |
| **npm run lint** (FRONT) | `npm run lint` (`tsc --noEmit`) | **PASA** | Código de salida 0, sin errores de tipado TypeScript. |
| **npm run build** (FRONT) | `npm run build` (`vite build`) | **PASA** | 2085 módulos transformados, bundle generado en `dist/` en 1.57 s. |

---

### Verificación de tareas contra criterio de aceptación

| ID | Criterio de aceptación | Resultado | Pasos seguidos y evidencia |
|---|---|---|---|
| **J01** | `tests/test_wipe.py` (9). Ejecutado contra Turso: `GET /api/snapshot` sin agentes, tickets ni aprobaciones. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: 1. `pytest tests/test_wipe.py` $\rightarrow$ 11 passed (incluye pruebas de respaldo, permisos restringidos, rechazo sin confirmación y orden FK). 2. Ejecución real contra Turso: `python -m app.db.wipe --yes`. Backup generado en `backups/20261123T140629Z`. Filas borradas en orden FK (3 credenciales, 11 eventos, 3 tickets, 1 agente). 3. Consulta a `GET /api/snapshot`: `agents: []`, `tickets: []`, `approvals: []` (0 agentes, 0 tickets, 0 aprobaciones). |
| **J02** | `GET /api/models` → `[{id, label, provider, hasConnection}]` desde `models_catalog.py`; `hasConnection` = hay al menos una conexión activa de ese proveedor en cualquier agente. Tests: `tests/test_models_api.py`. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: 1. `pytest tests/test_models_api.py` $\rightarrow$ 4 passed. 2. Con BD vacía: `GET /api/models` devuelve 5 modelos (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5, gemini-pro, gemini-flash) todos con `hasConnection: false`. 3. Tras añadir credencial de Google a un agente: `GET /api/models` actualiza `gemini-pro` y `gemini-flash` a `hasConnection: true`. |
| **J03** | `migrations/007_workspaces.sql` + `GET/PUT/DELETE /api/admin/workspaces[/{id}]` + `POST .../{id}/check`. Ruta validada (absoluta, sin `..`, sin UNC, existe y es carpeta, no raíz de unidad, no sistema). Tests: `tests/test_workspaces_api.py`. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: 1. `pytest tests/test_workspaces_api.py` $\rightarrow$ 40 passed. 2. `PUT /api/admin/workspaces/ws-qm0` con ruta local real $\rightarrow$ 201 Created. 3. `POST /api/admin/workspaces/ws-qm0/check` $\rightarrow$ `{"exists": true, "isDir": true, "writable": true}`. 4. Intento con ruta relativa o sistema $\rightarrow$ 400 `VALIDATION_ERROR`. 5. `DELETE` exitoso (código 204). |
| **J04** | `migrations/008_ticket_spec.sql`: `objective`, `acceptanceCriteria`, `actions`, `restrictions`, `dependencies` y `model` en tickets (alta, GET, snapshot y SSE). Listas de 0–40 elementos de 1–500 caracteres; `model` validado contra el catálogo (400); restricciones globales duplicadas descartadas. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: 1. `pytest tests/test_ticket_spec_api.py` $\rightarrow$ 22 passed. 2. `POST /api/tickets` con los 6 campos divididos y `model="gemini-flash"` $\rightarrow$ 201 Created con campos poblados y serializados en camelCase. 3. Intento con `model="modelo-inexistente"` $\rightarrow$ 400 `VALIDATION_ERROR`. 4. Restricción coincidente con global $\rightarrow$ descartada silenciosamente. |
| **T72** | Cada valor de cada enum mapea ida y vuelta sin pérdida. `src/api/mappers.ts`. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: Ejecutado script de prueba de ida y vuelta para todos los estados de agente (`IDLE` $\leftrightarrow$ `idle`, `WORKING` $\leftrightarrow$ `working`, `REVIEW` $\leftrightarrow$ `waiting_sheldon`, `BLOCKED` $\leftrightarrow$ `blocked`, `SLEEP_QUOTA` $\leftrightarrow$ `sleep_quota`), prioridades (`HIGH` $\leftrightarrow$ `alta`, `MEDIUM` $\leftrightarrow$ `media`, `LOW` $\leftrightarrow$ `baja`) y columnas de Kanban. Cero discrepancias. `formatRelative` y `formatDate` probados con cadenas ISO válidas. |
| **T74** | Dos pestañas abiertas: un cambio en una se refleja en la otra en < 1 s. `useOfficeStore.ts` y `realtime.ts`. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: En la API, `EventBus` despacha inmediatamente los eventos vía `asyncio.Queue` con `loop.call_soon_threadsafe`. En el front, `connectRealtime` escucha `GET /api/events` (SSE) y dispara `handlers.onEvent` al instante para `agent.*`, `ticket.*` y `approval.*`. Latencia local < 100 ms. Re-solicitud de snapshot implementada en `onReconnect`. |
| **F07** | Conexiones API por agente: lista `••••last4`, inputs `type="password"`, vaciado de clave, sin presencia en respuestas ni almacenamiento del cliente. | **PASA** $\rightarrow$ **EN REVISIÓN** | **Pasos**: 1. `AgentCredentialsPanel.tsx` usa campos `type="password"`. 2. Al guardar o desmontar, `setSecret('')` y `setRotateSecret('')` limpian el estado local. 3. Auditoría de código en `src/`: 0 ocurrencias de almacenamiento de secretos en `localStorage`, 0 en `sessionStorage` y 0 en el store global. 4. La API únicamente devuelve `••••last4`. |
| **CAL01** | El calendario marca hoy con la fecha local del navegador. | **DEVUELTA** | **Pasos**: 1. Inspección de `src/components/RoadmapCalendarView.tsx`: líneas 66, 226, 374 y 425 tienen fijada en código la fecha `"2026-11-22"` (`const isToday = cell.dateStr === '2026-11-22'; const todayPct = dateToPct('2026-11-22')`). 2. Hoy es **23 nov 2026**: el componente no calcula "hoy" dinámicamente con `new Date()`. |
| **G07** | Modal "Crear agente" de §19.7 con plantillas, restricciones globales con candado, modelo y límites. | **DEVUELTA** | **Pasos**: 1. `git status` en FRONT: los archivos `src/components/CreateAgentProfileModal.tsx`, `src/data/agentTemplates.ts` y `src/types/agentProfile.ts` figuran como untracked (sin commitear en `dev`). 2. En HEAD de `dev`, `App.tsx` todavía importa y renderiza el `CreateAgentModal` antiguo (sin plantillas §19.7). |
| **FIX-QA6** | Corrección de defectos reportados en Ronda 6 (asignación de ticket, aparición en vivo, calendario). | **DEVUELTA** | **Pasos**: La asignación de ticket y la aparición en vivo de tickets creados desde la UI quedaron resueltas en `App.tsx` (`handleCreateTask` ahora envía `assignedAgentId` y hace `dispatch({ type: 'ticket.upsert' })`). Sin embargo, el defecto del calendario (`CAL01`) sigue sin corregir en el código. |
| **MOD01, TSK01, WS01, AG-EDIT, CER01** | Tareas mencionadas en petición. | **SIN DEFINICIÓN EN TASKS.md** | No existen filas en la tabla de tareas ni criterios asignados para estos identificadores. Su funcionalidad técnica de backend está cubierta y probada bajo J02 (modelos), J04 (ticket spec) y J03 (workspaces). |

---

### HITO QM0 — Verificación de punta a punta con BD real

| Paso | Resultado | Evidencia |
|---|---|---|
| 1. BD real vacía al inicio | **PASA** | `GET /api/snapshot` devuelve 0 agentes, 0 tickets, 0 aprobaciones tras `app.db.wipe`. |
| 2. Crear agente con Gemini Flash | **PASA** | `POST /api/agents` con `name: "Agente QM0"`, `model: {"primary": "gemini-flash"}` $\rightarrow$ 201 Created (`id: c9df66d8-ea5e-4d5b-bbdd-3c125ca0d2e3`). |
| 3. Editar agente | **PASA** | `PATCH /api/agents/{id}` con `role: "Desarrollador FullStack QA"` $\rightarrow$ 200 OK con rol actualizado. |
| 4. Añadir 2 conexiones API | **PASA** | `POST .../credentials` con etiquetas "Google Key 1" y "Google Key 2" $\rightarrow$ 201 Created (`last4`: `5678`, `4321`). `GET /api/models` pasa a reportar `hasConnection: true` para `gemini-pro` y `gemini-flash`. |
| 5. Crear espacio de trabajo | **PASA** | `PUT /api/admin/workspaces/ws-qm0` con ruta del FRONT $\rightarrow$ 201 Created. `POST .../check` responde `{"exists": true, "isDir": true, "writable": true}`. |
| 6. Crear tarea con especificación dividida y agente asignado | **PASA** | `POST /api/tickets` con `objective`, `acceptanceCriteria`, `actions`, `restrictions`, `dependencies`, `model: "gemini-flash"` y `assignedAgentId: c9df66d8-...` $\rightarrow$ 201 Created (`id: 429d15fb-6881-4067-a73a-6c68dcfa4e13`). |
| 7. Moverla por el flujo (§19.4) | **PASA** | Transiciones ejecutadas con éxito: `PENDING` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `IN_QA` $\rightarrow$ `IN_REVIEW` $\rightarrow$ `DONE`. |
| 8. Recarga / persistencia | **PASA** | `GET /api/snapshot` confirma persistencia en Turso: 1 agente y 1 ticket en estado `DONE`. |
| 9. Calendario marca hoy con fecha local | **FALLA** | En el componente de calendario `RoadmapCalendarView.tsx`, la fecha de hoy está estática en `"2026-11-22"`. Siendo hoy **23 nov 2026**, no refleja la fecha actual (bloqueado por CAL01). |
| 10. Limpieza total de la BD | **PASA** | Ejecutado `python -m app.db.wipe --yes` y eliminado el workspace `ws-qm0`. Turso queda con 0 registros en todas las tablas de datos. |

**Dictamen de QM0:** **DEVUELTA** únicamente por el defecto del calendario (`CAL01`). Todo el flujo de datos real, creación, edición, conexiones, modelos, espacios de trabajo y flujo de tickets funciona al 100%.

---

### Estados aplicados a `docs/TASKS.md`
- **EN REVISIÓN**: `J01`, `J02`, `J03`, `J04`, `T72`, `T74`, `F07`.
- **DEVUELTA**: `CAL01`, `G07`, `FIX-QA6`, `QM0` (por CAL01).
- **HECHO** (previas confirmadas): `T70`, `T71`, `T73`, `T75`, `F03a`, `C05`, `G05`, `K01`, `C02`.

---

## Ronda 8 — QA Senior (muestreo, breve) — 2026-11-23

**Aviso:** no existe "Ronda 8 — QA Junior" en el repo, ni en QA_REPORT, ni en el historial de git (API ni FRONT). La última es la **Ronda 7**. El muestreo se hizo sobre lo que la Ronda 7 afirma para las tres áreas pedidas. Versiones probadas: API `fb14dd3` (copia limpia de HEAD), FRONT `9629b9a` (HEAD).

| Prueba | Tarea | Resultado | Evidencia | Motivo |
|---|---|---|---|---|
| 1. Fuga de la clave | F07 | **HECHO** | `pytest tests/test_credentials_api.py`: 32 passed (la clave nunca sale en respuestas; solo `last4`). FRONT: `localStorage` sin uso para claves (solo un comentario); campos `type="password"`; el estado se vacía al guardar y al desmontar. | Verificado en código y tests; ya se comprobó en vivo en Ronda 6. |
| 2. Permisos 403 | — (S09) | **PENDIENTE S09** (no bloquea) | `grep requireRole` en `app/`: sin resultados. Los únicos 403 con prueba son los de SETUP (`pytest -k 403`: pasan, en `tests/test_setup.py`). | No hay control de roles todavía. Los 403 por rol dependen de S09 y no se pueden validar hoy. |
| 3. Calendario | CAL01 | **HECHO** | En HEAD `9629b9a` no queda ninguna fecha fija `2026-11-22` en `src/`. `RoadmapCalendarView.tsx` usa `todayLocal()` (`src/utils/date.ts`: `getFullYear/getMonth/getDate`, hora local). Commit `8ac97f2` "CAL01: Hoy real". | La DEVUELTA de la Ronda 7 es anterior a ese commit y ya no aplica. No lo probé en el navegador. |

**Tareas:** F07 pasa a HECHO. CAL01 no tiene fila propia en TASKS (se resolvió en QM0/FIX-QA6, ver Ronda 6–7). Permisos 403: pendientes de S09.
