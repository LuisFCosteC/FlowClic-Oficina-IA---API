# FlowClic Oficina IA — Tareas Fase 1

Referencia: `docs/PLAN.md`. Estados: `PENDIENTE` · `EN CURSO` · `EN QA` · `EN REVISIÓN` · `HECHO` · `DEVUELTA`. **Equipo vigente: ver "AMPLIACIÓN (i)" al final (Dev Senior = Sonnet, Dev Junior = Antigravity, QA Junior = Antigravity, QA Senior = Haiku).**
Reglas: rama `dev`; sin rutas absolutas en código; preguntar antes de añadir dependencias no listadas en PLAN §8.
Si hay una duda, añade debajo de la tarea una línea `> PREGUNTA PARA ARQUITECTO: ...` y sigue con otra tarea.
Cada tarea de DEV pasa a `EN QA`; QA la verifica contra su criterio y la marca `HECHO` o `DEVUELTA` (con detalle en `docs/QA_REPORT.md`).

> **⚠ PRIORIDAD CAMBIADA (CEO, 2026-11-22):** la seguridad es prioridad 1 y se añade el panel de Administración.
> Seguir el **orden de PLAN §14**, no el orden de este archivo. Las tareas nuevas están en la sección "AMPLIACIÓN 2026-11-22", al final del archivo: Bloques **S**, **A**, **F** y **QS**.
> Regla desde ahora: toda ruta nueva usa `requireRole(...)` y su test cubre 401 y 403. Sin dependencias nuevas: todo con `node:crypto`.
> Senior: termina T30 (en curso) y después pasa a S01.

> **⚠ CAMBIO DE STACK (CEO, 2026-11-22): la API pasa a Python + FastAPI con Swagger (PLAN §0).**
> - La versión Node (T01–T30, S01, S02 y S03 empezada) queda archivada en la rama `archive/node-express`. **No se prueba ni se sigue.**
> - T02, T10–T14, T20–T24, T30, S01, S02 y S03 vuelven a `PENDIENTE` para **reimplementarse en Python con los mismos criterios de aceptación**, traducidos con la tabla de PLAN §0.4 (zod → Pydantic, `node:test` → pytest, `npm run` → comandos de §0.6…). T01 queda sustituida por P01.
> - Las notas DEV de la versión Node que hay más abajo son históricas.
> - Orden: **V00 (front, trivial) → P00 → P01 →** T02 → T10–T14 → T20–T24 → T30 → y después PLAN §14 desde el punto 2.

## Bloque P: arranque Python (va antes que todo)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| P00 | Prueba técnica en Windows: crear `.venv` con `py -3.13`, instalar `libsql`, y con un script desechable (no se commitea): conectar a `file:local.db`, crear una tabla, ejecutar una transacción con rollback, un insert parametrizado y una lectura. Si `libsql` falla, repetir con `sqlite3` y anotar el resultado como PREGUNTA PARA ARQUITECTO. **Si Python 3.13 no está instalado, parar y preguntar** (no instalar nada sin OK). | DEV | HECHO | Nota en TASKS con: versión de Python, versión de `libsql`, resultado de cada operación y si el rollback deshace correctamente. |
| P01 | Scaffold Python en `dev`: borrar el código Node (`src/`, `test/`, `seeds/`, `scripts/` de Node, `package.json`, `package-lock.json`, `tsconfig.json`, `node_modules/`); conservar `docs/` y `migrations/`; crear la estructura de PLAN §0.5, `requirements.txt` y `requirements-dev.txt` con versiones exactas (solo los paquetes de §0.2), `pyproject.toml` (ruff, mypy, pytest), `.gitignore` de Python, `.env.example` con las variables de §9, §12.5 y §0.8, y `app/main.py` con `create_app()` y `/docs` activo. Actualizar el `README.md` con los comandos de §0.6. | DEV | HECHO | En una copia nueva: `py -3.13 -m venv .venv`, `pip install -r requirements.txt -r requirements-dev.txt`, `uvicorn app.main:app` arranca y `http://localhost:4000/docs` muestra Swagger; `ruff check .` y `mypy app` pasan; `pytest` corre (aunque sea con 1 test); no queda ningún archivo Node. |
| P02 | Calidad de la documentación Swagger (transversal): cada router con `tags` y `summary`; cada endpoint con `responses` de error documentados; modelos con `json_schema_extra` de ejemplo; `APIKeyCookie('fc_session')` como esquema de seguridad; `DOCS_ENABLED` respetado. Se cumple en **cada** tarea que añada rutas; esta tarea es la revisión final. | DEV | PENDIENTE | En `/docs` todos los endpoints aparecen agrupados, con ejemplos y errores; con `DOCS_ENABLED=false`, `/docs`, `/redoc` y `/openapi.json` → 404. |
| QP1 | QA del arranque Python: seguir el README desde cero en una carpeta limpia; Swagger visible; `pip-audit` sin vulnerabilidades altas. | QA | DEVUELTA | Pasos y resultados en QA_REPORT. |

---

## Bloque 0 — Preparación

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T00 | (Tras OK del CEO) `git init` en API y FRONT, commit inicial en `main` con el estado actual, crear y usar rama `dev`. | DEV | HECHO | `git branch` muestra `main` y `dev` en ambos; `dev` activa; el commit inicial del FRONT no incluye `node_modules` ni `.env*`. |
| T01 | Scaffold API: `package.json` (`"type":"module"`, `engines.node >=24`), scripts de PLAN §9, `tsconfig.json` (noEmit, `allowImportingTsExtensions`, `verbatimModuleSyntax`), `.gitignore`, `.env.example`. Instalar solo deps de PLAN §8. | DEV | PENDIENTE | `npm install` sin errores; `npm run typecheck` pasa; `.env` y `local.db*` ignorados por git; no hay deps fuera de la lista. |
| T02 | `src/config/env.ts`: carga y valida variables con zod (`PORT`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` opcional, `CORS_ORIGIN`, `ORCHESTRATOR` = `noop`). | DEV | EN QA | Sin `TURSO_DATABASE_URL` el proceso termina con mensaje claro y código ≠ 0; con valores válidos exporta objeto tipado. |
| T03 | QA: verificar arranque limpio del scaffold en una copia nueva (clonar `dev`, `npm install`, `npm run typecheck`). | QA | PENDIENTE | Pasos reproducibles anotados en `QA_REPORT.md`; sin rutas absolutas (`grep -rn "D:\\\\\|C:\\\\" src seeds migrations` vacío). |

## Bloque 1 — Base de datos

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T10 | `src/db/client.ts`: cliente único `@libsql/client` con URL y token del env. | DEV | HECHO | Funciona con `file:local.db`; con `TURSO_AUTH_TOKEN` vacío no se envía token. |
| T11 | `src/db/migrate.ts`: runner con tabla `schema_migrations`, aplica `migrations/NNN_*.sql` en orden, cada una en transacción; usable como CLI y como función (tests). | DEV | HECHO | 1ª ejecución aplica todo; 2ª no hace nada; una migración con SQL roto no queda registrada ni deja tablas parciales. |
| T12 | `migrations/001_init.sql` con el esquema exacto de PLAN §3 (CHECKs e índices incluidos). | DEV | HECHO | Insertar `status='FOO'` en agents/tickets/approvals falla; 2 aprobaciones PENDING para el mismo ticket fallan por índice único. |
| T13 | `seeds/seed.ts` idempotente: 4 agentes (ids `sheldon`, `leonard`, `penny`, `raj` con datos de PLAN §3), 3–4 tickets de ejemplo, 1 nota de memoria. | DEV | HECHO | Ejecutar 2 veces deja exactamente 4 agentes; Sheldon `isCto=1`. |
| T14 | Script `db:reset` que borra la BD local y re-ejecuta migrate + seed; se niega si la URL no empieza por `file:`. | DEV | HECHO | Con URL `libsql://...` termina sin borrar nada y con mensaje claro. |
| T15 | QA: probar migrate/seed/reset y CHECKs con `local.db`; documentar en QA_REPORT. | QA | PENDIENTE | Todos los criterios T11–T14 verificados manualmente. |

## Bloque 2 — Núcleo de la API

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T20 | `src/app.ts` + `src/server.ts`: Express, `cors` con `CORS_ORIGIN`, JSON body, `GET /api/health` (hace `SELECT 1`). `app.ts` exporta la app sin escuchar. | DEV | HECHO | `curl localhost:4000/api/health` → `{"ok":true,"db":"up",...}`; petición desde otro origen bloqueada por CORS. |
| T21 | `middleware/errors.ts`: formato de error único de PLAN §5; errores zod → 400 con `details`; rutas inexistentes → 404 JSON; 500 sin stack. | DEV | HECHO | Body inválido devuelve 400 con forma `{error:{code,message,details}}`. |
| T22 | `domain/types.ts` y `domain/schemas.ts`: DTOs de PLAN §6 (uniones de string, sin `enum`) y esquemas zod de entrada. | DEV | EN QA | `npm run typecheck` pasa; no hay `enum` en el código. |
| T23 | `events/bus.ts`: bus tipado de `DomainEvent` (tipos de la tabla SSE de PLAN §6). | DEV | EN QA | Test unitario: un suscriptor recibe el evento emitido con su payload tipado. |
| T24 | Infra de tests: helper que crea BD temporal en `os.tmpdir()`, migra, siembra, levanta la app en puerto efímero y la cierra. | DEV | EN QA | `npm test` corre un test de `/api/health` en verde y no crea/modifica `local.db`. |

## Bloque 3 — Agentes

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T30 | `repositories/agents.repo.ts`: list (excluye archivados salvo flag), get, insert, update, setStatus, archive; mapea snake_case ⇄ camelCase y `avatar` JSON. | DEV | PENDIENTE | Tests de repo en verde. |
| T31 | `services/agents.service.ts` + rutas `GET/POST/PATCH/DELETE /api/agents` y `GET /api/agents/:id`. Nombre único entre activos (409). DELETE archiva; 409 si tiene tickets no DONE o aprobaciones PENDING. | DEV | PENDIENTE | Crear agente "Howard" desde curl lo devuelve en `GET /api/agents` sin tocar código; duplicar nombre → 409; borrar agente con ticket abierto → 409. |
| T32 | `PATCH /api/agents/:id/status`: cambio manual a cualquiera de los 5 estados; IDLE pone `currentTask=null`. Emite `agent.updated`. | DEV | PENDIENTE | Los 5 estados aceptados; `"FOO"` → 400; evento emitido (test con bus). |
| T33 | QA: probar CRUD y estados de agentes con curl/Postman; casos de error (400/404/409). | QA | PENDIENTE | Matriz de casos en QA_REPORT con resultado. |

## Bloque 4 — Tickets e historial

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T40 | `repositories/tickets.repo.ts` y `ticketEvents.repo.ts` (insert/list por ticket). | DEV | PENDIENTE | Tests de repo en verde. |
| T41 | `services/workflow.service.ts`: implementa la tabla de reglas de PLAN §4 incluida R1, todo en una transacción por acción. Funciones puras de decisión testeables aparte. | DEV | PENDIENTE | Tests: mover a IN_PROGRESS ⇒ agente WORKING; a DONE con otro ticket activo ⇒ agente sigue WORKING; agente BLOCKED no cambia por mover ticket; fallo a mitad ⇒ nada persiste. |
| T42 | Rutas tickets: `GET /api/tickets` (filtros), `GET /:id`, `POST`, `PATCH /:id`, `DELETE /:id`. Cada cambio escribe `ticket_events` (CREATED/UPDATED/DELETED) y emite eventos de bus. | DEV | PENDIENTE | Crear ticket con `assignedAgentId` inexistente → 422; cada operación deja su evento. |
| T43 | `PATCH /api/tickets/:id/status` y `PATCH /api/tickets/:id/assign` usando workflow. | DEV | PENDIENTE | Evento STATUS_CHANGED/ASSIGNED con `fromValue`/`toValue` correctos; reasignar recalcula estado del agente anterior. |
| T44 | `POST /api/tickets/:id/continue` según PLAN §4 (permitido desde BACKLOG/IN_PROGRESS/REVIEW; 409 en AWAITING_APPROVAL/DONE; 422 sin agente). Llama `orchestrator.onTicketContinued` vía bus. | DEV | PENDIENTE | Ticket en BACKLOG con agente SLEEP_QUOTA ⇒ ticket IN_PROGRESS, agente WORKING, evento CONTINUED. |
| T45 | `GET /api/tickets/:id/events` en orden cronológico. | DEV | PENDIENTE | Tras crear+mover+continuar devuelve 3 eventos en orden. |
| T46 | QA: flujos completos de ticket (crear, asignar, mover por las 5 columnas, continuar, borrar) verificando historial y estado del agente. | QA | PENDIENTE | Matriz en QA_REPORT; historial coincide con acciones. |

## Bloque 5 — Aprobaciones y memoria

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T50 | `repositories/approvals.repo.ts` + rutas `GET/POST/PATCH/DELETE /api/approvals` y `GET /:id`. | DEV | PENDIENTE | Crear compuerta sin ticket funciona; editar una no PENDING → 409. |
| T51 | Integración con workflow: mover ticket a AWAITING_APPROVAL crea PENDING (sin duplicar); salir de esa columna la cancela (CANCELLED + evento APPROVAL_CANCELLED). | DEV | PENDIENTE | Mover 2 veces a AWAITING_APPROVAL deja 1 sola PENDING. |
| T52 | `POST /api/approvals/:id/decision`: APPROVED ⇒ ticket DONE; REJECTED ⇒ ticket IN_PROGRESS y agente WORKING; decidir dos veces → 409. | DEV | PENDIENTE | Tests de ambos caminos + 409; evento APPROVAL_DECIDED en historial del ticket. |
| T53 | `project_memory`: repo + rutas `GET/POST/PATCH/DELETE /api/memory`. | DEV | PENDIENTE | CRUD funcional; `kind` inválido → 400. |
| T54 | QA: cola de aprobaciones de punta a punta por API y memoria. | QA | PENDIENTE | Matriz en QA_REPORT. |

## Bloque 6 — Tiempo real y enganche Fase 2

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T60 | `realtime/sse.ts`: `GET /api/events` (headers SSE, `id` incremental, heartbeat 25 s, limpia cliente al cerrar). Suscrito al bus; reenvía todos los eventos de PLAN §6. | DEV | PENDIENTE | `curl -N localhost:4000/api/events` muestra `agent.updated` al cambiar estado desde otra terminal; cerrar curl no deja listeners colgados. |
| T61 | `GET /api/snapshot` → `{agents, tickets, approvals, serverTime}`. | DEV | PENDIENTE | Devuelve los 4 agentes semilla tras seed. |
| T62 | `orchestrator/Orchestrator.ts` (interfaz con comentario FASE 2 de PLAN §7) + `NoopOrchestrator.ts`, registrado en `server.ts` según `ORCHESTRATOR`. Errores del orquestador se loguean y no rompen la petición. | DEV | PENDIENTE | Sin llamadas de red ni a modelos; test: un orquestador que lanza error no cambia la respuesta HTTP. |
| T63 | `README.md` de la API con comandos de PLAN §9 y cómo cambiar a Turso nube. | DEV | PENDIENTE | Un tercero arranca la API solo con el README. |
| T64 | QA: SSE con 2 clientes simultáneos; compatibilidad Turso (si hay BD de prueba en la nube: migrate+seed+health solo cambiando `.env`). | QA | PENDIENTE | Resultado en QA_REPORT (si no hay cuenta Turso, marcar como no verificado). |

## Bloque 7 — FRONT conectado (sin rediseño)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T70 | FRONT: añadir `VITE_API_URL` a `.env.example`; `src/api/config.ts` lee `import.meta.env.VITE_API_URL` (sin fallback en código; error claro si falta). Usar npm (ver PLAN D12). | DEV | PENDIENTE | Sin la variable, consola muestra error explícito; con ella, se usa esa URL. `grep -rn "localhost:4000" src` vacío. |
| T71 | `src/api/types.ts` (DTOs de PLAN §6) y `src/api/client.ts` (fetch tipado por endpoint, parsea el formato de error). | DEV | PENDIENTE | `npm run lint` (tsc) pasa. |
| T72 | `src/api/mappers.ts`: mapeos de la tabla de PLAN §6 (ambos sentidos donde aplique) + formato de fecha relativa. Tests simples o ejemplos verificables. | DEV | PENDIENTE | Cada valor de cada enum mapea ida y vuelta sin pérdida. |
| T73 | Ampliar `AgentStatus` con `blocked` y `sleep_quota`: `STATUS_META`, `STATUS_HEX` (avatarBuilder), `assignZoneSlots` (blocked→revisión, sleep_quota→lounge) y contadores. Sin cambios de layout. | DEV | PENDIENTE | `tsc` pasa; un agente BLOCKED se ve en la zona de pizarra con su color; SLEEP_QUOTA en el apartamento. |
| T74 | `src/state/useOfficeStore.ts` (useReducer: snapshot, upsert/remove por id) + `src/api/realtime.ts` (EventSource; al reconectar re-pide snapshot). | DEV | PENDIENTE | Dos pestañas abiertas: un cambio en una se refleja en la otra en < 1 s. |
| T75 | `App.tsx`: reemplazar `INITIAL_AGENTS/TASKS/PROPOSALS` por el store; los handlers llaman a la API (sin lógica de negocio local). Models/roadmap/proyectos siguen mock. Estados de carga/error con texto pequeño usando estilos existentes. | DEV | PENDIENTE | Al recargar la página persisten los cambios; aparecen solo los 4 agentes semilla (+ creados). |
| T76 | Kanban: crear ticket (POST), mover (PATCH status) con flechas y select existentes; **asignar**: select de agente en la vista lista y en la tarjeta, mismo estilo que el select de etapa; **continuar**: botón pequeño en tarjetas BACKLOG/IN_PROGRESS/REVIEW con estilo de las flechas existentes. | DEV | PENDIENTE | Las 4 acciones persisten y se reflejan por SSE en otra pestaña; errores 409/422 se muestran como texto, sin romper la vista. |
| T77 | Vigilador: Colmena 3D y panel de memoria del Cerebro reflejan estados en tiempo real; cambio manual llama `PATCH /agents/:id/status`; añadir botones Bloqueado / Sin cuota con el estilo existente. | DEV | PENDIENTE | Cambiar estado por curl mueve el avatar en la pantalla sin recargar; los 5 estados seleccionables desde la UI. |
| T78 | Cola de aprobaciones (Cerebro): lista de `GET /approvals` mapeada a `SheldonProposal`; aprobar/rechazar llama `POST /approvals/:id/decision`. | DEV | PENDIENTE | Aprobar mueve el ticket a Completado y actualiza contadores de Sidebar/cabecera en todas las pestañas. |
| T79 | `CreateAgentModal`: `onCreateAgent` hace `POST /api/agents` (name, role←title, systemPrompt, modelTier, avatar{color,glasses}, status mapeado, project); `character` = name si no se indica. Error de API (p. ej. nombre duplicado) se muestra en el `error` existente del modal. | DEV | PENDIENTE | Agente creado aparece en 3D, Kanban (selector) y Cerebro, y persiste tras recargar. |
| T7A | README del FRONT: sección "Fase 1" con `.env.local`, comando y requisito de API levantada. | DEV | PENDIENTE | Pasos reproducibles. |
| T7B | QA E2E manual: arranque desde cero (PLAN §9), recorrido completo (crear agente, crear/asignar/mover/continuar ticket, aprobar/rechazar, cambio manual de 5 estados, 2 pestañas en tiempo real, reinicio de API y reconexión SSE). | QA | PENDIENTE | Checklist completo en QA_REPORT con capturas o notas; ningún error en consola del navegador. |

## Bloque 8 — Cierre

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T80 | Revisión final de reglas: sin rutas absolutas, sin secretos versionados, sin llamadas a IA, `typecheck`/`lint`/`test` en verde en ambos repos. | QA | PENDIENTE | Comandos y resultados en QA_REPORT. |

Después de T80: el Arquitecto revisa el código, este archivo y `QA_REPORT.md`, responde las preguntas y da el dictamen de merge `dev` → `main`.

---

## Notas DEV

- **T01** — Scaffold API: package.json (scripts PLAN §9), tsconfig, .gitignore, .env.example, deps solo de PLAN §8 (express@4, @types/express@4). Archivos: package.json, package-lock.json, tsconfig.json, .gitignore, .env.example, src/server.ts (placeholder). Probar: `npm install && npm run typecheck`.
> PREGUNTA PARA ARQUITECTO (T31/T32 y siguientes): `docs/PLAN.md` fue ampliado hoy (§12 seguridad, §13 Administración, §14 nuevo orden: S01→S10 antes de T30/T31) pero esta lista no contiene las tareas S*, A*, F* ni QS*. Sin sus definiciones no puedo implementarlas, y §14 exige `requireRole` en toda ruta nueva, así que T31/T32 (rutas de agentes) quedan en pausa hasta tener S01–S10. Esos cambios de PLAN.md siguen sin commitear en el working tree de la API; no los incluí en mis commits.
> RESPUESTA DEL ARQUITECTO (2026-11-22): las tareas S01-S13, A01-A07, F01-F05 y QS ya están definidas al final de este archivo, y PLAN.md está commiteado (462aed8). La pausa de T31/T32 es correcta: sigue el orden S01→S10 y después retoma T31/T32 ya con requireAuth/requireRole. T30 (repositorio, sin rutas) puede pasar a EN QA tal cual.

---

# AMPLIACIÓN 2026-11-22: Seguridad y Administración (PLAN §12–§14)

## Bloque S: seguridad base (API)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| S01 | Endurecimiento HTTP: `app.disable('x-powered-by')`, cabeceras (CSP `default-src 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`), `express.json({limit:'100kb'})`, `HOST` (por defecto `127.0.0.1`) en `listen`, `requestId` en logs. `/api/health` sin sesión responde **solo** `{ok}`; con sesión, el detalle actual. | DEV | PENDIENTE | `curl -i` muestra las cabeceras y no `X-Powered-By`; body de 200 kB → 413 JSON; la API no responde desde otra IP de la red local. |
| S02 | `npm run setup`: crea `.env` desde `.env.example` si no existe y rellena `APP_ENCRYPTION_KEY` y `SESSION_SECRET` con `crypto.randomBytes(32)` en base64. Nunca sobrescribe un `.env` existente. Añadir las variables de PLAN §12.5 a `.env.example` (vacías) y validarlas en `env.ts` (en `production` deben estar definidas). Añadir `backups/` y `.env.bak` a `.gitignore`. | DEV | EN QA | Ejecutarlo dos veces no cambia el `.env`; ningún valor real en `.env.example`. |
> NOTA DEL ARQUITECTO (2026-11-22): criterio adicional para S02 en Python (`scripts/setup_env.py`). El `.env` se crea solo para el propietario: en Linux/macOS con `os.chmod(0o600)` y un aviso si un `.env` existente tiene permisos más amplios; **en Windows**, con `icacls .env /inheritance:r /grant:r "%USERNAME%:F"` vía `subprocess` (sin `shell=True`), porque la carpeta está en `D:\` y ahí los permisos heredados suelen dar acceso a "Usuarios autenticados". Test: en Windows, `icacls .env` muestra un único permiso, el del usuario actual. Documentarlo en SECURITY.md.
| S03 | `migrations/002_security.sql` con el esquema exacto de PLAN §12.2. | DEV | PENDIENTE | `db:migrate` la aplica; el email está repetido → falla por índice único. |
| S04 | `src/security/password.ts`: `hashPassword` y `verifyPassword` con scrypt (N=2^17, r=8, p=1, sal de 16 B, `maxmem` ajustado), formato `scrypt$N$r$p$salt$hash`, comparación con `timingSafeEqual`. Política: mínimo 12 caracteres. | DEV | EN QA | Tests: el hash ≠ la contraseña; dos hashes de la misma clave son distintos; verificar la buena es true y la mala false. |
| S05 | `npm run admin:create`: CLI que pide email, nombre y contraseña (dos veces, sin eco) y crea un usuario ADMIN. **No existe usuario por defecto**; la semilla no crea usuarios. | DEV | PENDIENTE | `grep -rni "password" seeds/` no encuentra credenciales; el usuario creado tiene un hash `scrypt$...`. |
| S06 | Sesiones (`src/security/sessions.ts`) + rutas `/api/auth/login`, `logout`, `logout-all`, `me`, `me/password`, `me/sessions` (PLAN §12.4): token de 32 B en una cookie `fc_session` `HttpOnly; SameSite=Strict; Path=/api` (+`Secure` si `NODE_ENV=production`); en la BD solo el SHA-256. Expira por inactividad (`SESSION_IDLE_MINUTES`) y por tiempo absoluto (`SESSION_MAX_HOURS`). Cambiar la contraseña revoca las demás sesiones. | DEV | PENDIENTE | Tests: login OK pone la cookie; con la sesión caducada (reloj simulado) → 401; tras logout el mismo token → 401; la tabla no contiene el token en claro. |
| S07 | Antifuerza bruta: limitador en memoria por IP (10 intentos / 15 min → 429 con `Retry-After`) en `login` y `mfa/verify`; bloqueo por cuenta (5 fallos → `locked_until` 15 min, el doble en cada bloqueo nuevo); mensaje genérico idéntico para usuario inexistente o clave errónea; verificación con hash ficticio cuando el usuario no existe. | DEV | PENDIENTE | Tests: el 11º intento desde la misma IP → 429; 5 fallos bloquean la cuenta incluso con la clave correcta; las respuestas de "no existe" y "clave mala" son idénticas. |
| S08 | MFA TOTP propio (`src/security/totp.ts`, RFC 6238, SHA-1, 6 dígitos, 30 s, ventana ±1) + cifrado AES-256-GCM (`src/security/crypto.ts`) del secreto con `APP_ENCRYPTION_KEY`. Rutas `me/mfa/setup`, `me/mfa/enable`, `mfa/verify` (con `loginTicket` de 5 min y un solo uso, o reautenticación con sesión). Un ADMIN sin MFA → 403 `MFA_SETUP_REQUIRED` fuera de `/api/auth/*`. Un código ya usado no vale dos veces. | DEV | PENDIENTE | Test con los vectores del RFC 6238; el secreto en BD no es legible; login de ADMIN con MFA exige el código; reutilizar el mismo código → 401. |
| S09 | Autorización: `requireAuth` **global** con lista blanca (login, mfa/verify, health básico); `requireRole` según la matriz de PLAN §12.3 en **todas** las rutas existentes (agentes, tickets, aprobaciones, memoria, snapshot, SSE); `requireRecentMfa(10 min)`; comprobación de `Origin` = `CORS_ORIGIN` en POST/PUT/PATCH/DELETE; CORS con `credentials:true`. Los recursos propios se resuelven desde la sesión, nunca con un id de usuario en la URL. | DEV | PENDIENTE | Test de tabla que recorre **todas** las rutas registradas: sin cookie → 401 (salvo la lista blanca); VIEWER en una ruta de escritura → 403; Origin ajeno → 403; DELETE `me/sessions/:id` de otro usuario → 404. |
| S10 | `audit_log`: helper `audit(req, action, target, meta)`; registrar login OK/fallido, logout, cambios de contraseña/MFA/rol/usuario, todo lo de `/api/admin/*` y el archivado de agentes. `meta` **nunca** lleva contraseñas, tokens ni URLs con credenciales. | DEV | PENDIENTE | Tras un login fallido aparece `auth.login_fail` con la IP; buscar el token en `audit_log` no da resultados. |
| S11 | Higiene de repositorio (API y FRONT): `scripts/check-secrets.mjs` (sin dependencias) que busca patrones (`AIza`, `sk-`, `eyJ` largos, `-----BEGIN`, `authToken=`, `TURSO_AUTH_TOKEN=<no vacío>`) en los archivos preparados para commit, instalado como hook `pre-commit` con `npm run hooks:install`; `.github/dependabot.yml` (npm, semanal); script `npm run audit` = `npm audit --audit-level=high`. | DEV | PENDIENTE | Un commit con `TURSO_AUTH_TOKEN=abc` en un archivo es rechazado; `npm run audit` funciona en ambos repos. |
| S12 | Backups y DRP: `npm run db:backup` (con `file:` → `VACUUM INTO 'backups/<ts>.db'`; remoto → JSON por tabla en `backups/<ts>/`), `npm run db:restore <ruta>` (pide confirmación y hace un backup previo), backup automático en `server.ts` cada `BACKUP_INTERVAL_HOURS` con retención `BACKUP_KEEP`; `docs/DRP.md` (RPO 24 h, RTO 1 h, pasos de restauración local y Turso). | DEV | PENDIENTE | El backup se crea y se restaura en una BD vacía con los mismos conteos por tabla; se conservan solo los últimos N. |
| S13 | `docs/SECURITY.md`: modelo de amenazas STRIDE resumido, matriz de PLAN §12.1 con su estado, reglas para la Fase 2 (rol `AGENT`, la IA nunca recibe el cliente de BD, salidas de modelo tratadas como entrada no confiable) y checklist de revisión por fase. | DEV | PENDIENTE | Documento revisado por el Arquitecto. |

## Bloque A: Administración (API)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| A01 | `migrations/003_admin.sql` (PLAN §13.1) + semilla de `limits` por defecto y de `project` vacío. | DEV | PENDIENTE | `GET /api/admin/settings/limits` devuelve los valores por defecto. |
| A02 | `GET/PUT /api/admin/settings/project` y `/limits` con zod por clave (`project`: companyName, projectName, description, goals[], stack[] con longitudes máximas; `limits`: enteros 1–100 y booleano). Emite `settings.updated`. | DEV | PENDIENTE | Un valor fuera de rango → 400; OPERATOR → 403; el cambio llega por SSE. |
| A03 | CRUD de `project_rules` + `PUT /api/admin/rules/order`. Emite `rule.*`. | DEV | PENDIENTE | Reordenar persiste el orden; severidad inválida → 400. |
| A04 | Aplicar límites: `maxAgents` al crear o restaurar un agente; `maxActiveTicketsPerAgent` y `requireApprovalForDone` en el workflow (T41/T43/T44: si ya están hechas, añadir la validación; si no, quedan como criterio de esas tareas). Respuesta 409 `LIMIT_EXCEEDED`. | DEV | PENDIENTE | Tests de cada límite. |
| A05 | Conexión de BD desde el panel (PLAN §13.2): refactorizar `db/client.ts` a `getDb()` y `swapDb()` y eliminar las capturas de `db` en `createApp`/repositorios; `GET /api/admin/db`, `POST /api/admin/db/test`, `PUT /api/admin/db` (migrar, copiar mi ADMIN si la BD nueva no tiene usuarios, `.env.bak`, escritura atómica de solo 2 claves, cambio en caliente, revocar sesiones, `system.db_changed`, auditoría sin token). Exige `requireRecentMfa` y `ADMIN_ALLOW_DB_CHANGE=true`. | DEV | PENDIENTE | Tests con 2 BD temporales: después del cambio, `GET /api/agents` lee de la nueva sin reiniciar; una URL que falla no toca el `.env`; ninguna respuesta ni log contiene el token; el resto de líneas del `.env` queda intacto. |
| A06 | `POST /api/agents/:id/restore` y `GET /api/agents?includeArchived=true` (solo ADMIN) para la pestaña Agentes. | DEV | PENDIENTE | Restaurar respeta `maxAgents` y la unicidad del nombre. |
| A07 | Usuarios y auditoría: `GET/POST /api/admin/users`, `PATCH /api/admin/users/:id`, `POST .../revoke-sessions`, `GET /api/admin/audit`. Crear o cambiar rol exige MFA reciente. No se puede dejar el sistema sin ADMIN activo (409). Desactivar revoca las sesiones. Nunca se devuelve `password_hash` ni `mfa_secret_enc`. | DEV | PENDIENTE | Tests: el último ADMIN no puede degradarse; un usuario desactivado → 401 en su siguiente petición; las respuestas no contienen campos sensibles. |

## Bloque F: FRONT (login y Administración, mismos estilos existentes)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| F05 | Limpieza del front: quitar `GEMINI_API_KEY` y `APP_URL` de `.env.example`, dejar solo `VITE_API_URL`; quitar las dependencias sin uso `@google/genai`, `express`, `@types/express` y `dotenv`. Verificar que nada de `src/` las importa. | DEV | PENDIENTE | `npm run lint` y `npm run build` pasan; `grep -rn "genai\|GEMINI" .` sin resultados (fuera de `node_modules`/lockfiles). |
| F01 | Pantalla de login (email, contraseña y, si `mfaRequired`, código de 6 dígitos) con el estilo del `CreateAgentModal`. `client.ts` usa `credentials:'include'`; ante un 401 en cualquier llamada vuelve al login; `EventSource` con `withCredentials:true`. Al cargar se consulta `GET /api/auth/me`. | DEV | PENDIENTE | Sin sesión no se ve ningún dato; tras el login aparece la app; al caducar la sesión vuelve al login sin errores en consola. La cookie no es accesible desde `document.cookie`. |
| F02 | Activación de MFA: si la API responde `MFA_SETUP_REQUIRED`, se muestran el secreto y la URI `otpauth://` como texto copiable y un campo para el código de confirmación. Menú de usuario (en el Sidebar, con el estilo existente): cambiar contraseña, cerrar sesión y cerrar todas las sesiones. | DEV | PENDIENTE | Un ADMIN nuevo puede activar MFA con Google Authenticator y entrar. |
| F03 | Vista **Administración** (`ActiveModule` `'admin'`, entrada en el Sidebar visible solo para ADMIN) con las pestañas de PLAN §13: Conexión BD, Proyecto, Reglas, Límites, Agentes, Usuarios y Auditoría. Las acciones críticas piden el código MFA cuando la API responde `MFA_REQUIRED` y reintentan. Al recibir `system.db_changed` → vuelve al login. El campo token es `type=password`, nunca se rellena con datos de la API y se vacía después de guardar. | DEV | PENDIENTE | Un OPERATOR no ve la entrada y, si fuerza la vista, la API devuelve 403 y se muestra un mensaje; cambiar a otra `file:` BD desde el panel funciona sin reiniciar la API; la pestaña Límites bloquea efectivamente (p. ej. con `maxAgents` alcanzado, crear un agente muestra el error). |
| F04 | Ocultar en la UI las acciones de escritura según el rol (VIEWER solo lee). Es solo UX; la protección real es S09. | DEV | PENDIENTE | Con un VIEWER no aparecen botones de crear, mover ni aprobar. |

## Bloque QS: QA de seguridad

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| QS-M1 | Hito M1 en local: `npm run setup`, migrate, seed, `admin:create`, `npm run dev` (API + FRONT); login con MFA; panel de Administración completo; cambio de BD a otro `file:`; los 4 agentes visibles en tiempo real. | QA | PENDIENTE | Checklist en QA_REPORT, sin errores en consola. |
| QS1 | Autenticación: rutas sin cookie, cookie manipulada, sesión caducada, logout, logout-all y reutilización del token tras el logout. | QA | PENDIENTE | Todo responde 401; evidencia con curl en QA_REPORT. |
| QS2 | Fuerza bruta: el rate limit por IP, el bloqueo por cuenta y los mensajes genéricos. | QA | PENDIENTE | Resultados documentados. |
| QS3 | IDOR, roles e inyección: VIEWER y OPERATOR contra cada ruta de escritura y admin; ids de otros usuarios en `me/sessions/:id`; payloads de SQLi (`OR 1=1--`) y `<script>` en todos los campos de texto (se guardan como texto y la UI no los ejecuta); campos extra en los bodies → 400. | QA | PENDIENTE | Matriz completa en QA_REPORT. |
| QS4 | Backups y DRP: ejecutar backup, borrar la BD y restaurar según `docs/DRP.md`, midiendo el tiempo. | QA | PENDIENTE | Restauración exitosa dentro del RTO. |
| QS5 | Revisión periódica (al cerrar la fase): `npm run audit` en ambos repos sin altas/críticas, `check-secrets` sobre todo el historial (`git log -p`), cabeceras de seguridad, errores 500 sin stack ni rutas, `HOST` local. | QA | PENDIENTE | Informe en QA_REPORT; cada hallazgo alto se convierte en tarea. |
- **S01** — middleware/security.ts (requestId + cabeceras CSP default-src 'none', nosniff, no-referrer, X-Frame-Options DENY), x-powered-by off, express.json 100kb (413 PAYLOAD_TOO_LARGE), HOST (def. 127.0.0.1) en env.ts/server.ts/.env.example, errores 500 logueados con requestId. /api/health ahora responde solo {ok:true}; el detalle con sesión se añade en S09 (cuando exista requireAuth). Tests en test/health.test.ts. Probar: `curl -i localhost:4000/api/health`; `npm test`.
- **S03** — migrations/002_security.sql con users, sessions y audit_log exactos de PLAN §12.2. Test: test/security-schema.test.ts (email repetido → UNIQUE, rol inválido → CHECK, semilla sin usuarios). Probar: `npm run db:migrate`; `npm test`.


---

# AMPLIACIÓN 2026-11-22 (b): Rediseño visual y nueva Oficina 3D (PLAN §15)

Orden global (CEO, "primero que funcione"): **V00 → M1 (P00, P01, T02… hasta QS-M1) → V3D01–V3D07 → VUI01–VUI08**.

## Bloque V: menú, sistema visual y 3D (FRONT)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| V00 | Reordenar `NAV_ITEMS` del Sidebar y `MODULE_HEADERS`: To-Do & Pipeline de Tareas, Calendario de Proyectos, Cerebro FlowClic, Oficina IA 3D (y Administración cuando exista F03). Módulo por defecto `kanban`. | DEV | HECHO | Al abrir la app se ve el Kanban; el Sidebar muestra el orden exacto de PLAN §15.1; `npm run lint` y `npm run build` pasan. |
| V3D01 | Refactor sin cambios visuales: dividir `sceneBuilder.ts` en `three/rooms/`, `three/props/` y `three/textures/` (PLAN §15.3). | DEV | PENDIENTE | La escena se ve igual que antes; ningún archivo de `three/` supera las 400 líneas. |
| V3D02 | Rótulos y textos: eliminar "ZONA A/B/C" en la escena, la leyenda, `STATUS_META`, `CreateAgentModal`, Cerebro y los mensajes. Nombres nuevos: **Laboratorio**, **Oficina de Sheldon**, **Zona de descanso**. | DEV | PENDIENTE | `grep -rni "zona [abc]\|apartamento bbt\|pizarra de sheldon" src` sin resultados. |
| V3D03 | Laboratorio tecnológico: piso con retícula luminosa, tiras LED, racks con LEDs parpadeantes instanciados y bandejas de cables. Puestos fijos por agente (orden de creación, fila extra si hay más de 9) con **placa** "Puesto de *Nombre* · *Rol*". | DEV | PENDIENTE | Cada agente de la API tiene su puesto con placa legible; un agente nuevo obtiene un puesto sin recargar. |
| V3D04 | "Qué está haciendo cada uno": textura de canvas en el monitor de cada puesto (título del ticket IN_PROGRESS, id corto, prioridad, animación de código; "Sin asignación" si no tiene) + etiqueta flotante sobre el avatar (nombre, rol, `StatusPill`, tarea truncada; se amplía al pasar el ratón; clic abre el panel). Aviso rojo en el puesto si está `BLOCKED`; icono de batería si está `SLEEP_QUOTA`. | DEV | PENDIENTE | Mover un ticket a IN_PROGRESS desde otra pestaña actualiza el monitor y la etiqueta en < 1 s; la textura solo se redibuja cuando cambian los datos. |
| V3D05 | **Oficina de Sheldon** según PLAN §15.3 (sala cerrada beige, estanterías empotradas, archivadores grises, escritorio simétrico con monitor, teléfono, portalápices y taza con rayo, pizarras verdes de tiza con ecuaciones, 2 diplomas, retrato, banderín y figura). Sheldon en su escritorio; los agentes `REVIEW`/`BLOCKED` frente a las pizarras. **Sin logos ni marcas.** | DEV | PENDIENTE | Revisión visual del CEO; no aparece ningún logo ni marca registrada. |
| V3D06 | **Zona de descanso** según PLAN §15.3 (sofá marrón con el sitio de Sheldon, TV, mesa de centro con comida, laptops y cómics, cocina abierta con barra, taburetes y nevera con imanes, escritorios junto a los ventanales, pizarras blancas con ruedas, estanterías con cajas de cómics y figuras, espada, ADN, busto, puerta con ascensor y cinta amarilla). `IDLE`/`SLEEP_QUOTA` sentados en el sofá o los taburetes; Sheldon IDLE en su sitio. Eliminar las literas/pods actuales. | DEV | PENDIENTE | Revisión visual del CEO; con 8 agentes IDLE ninguno se solapa. |
| V3D07 | Rendimiento y limpieza: medir triángulos y draw calls (`renderer.info`) y cumplir ≤150k/≤250; eliminar el "ciclo de demo"; respetar `prefers-reduced-motion`; liberar geometrías y texturas al desmontar la vista. | DEV | PENDIENTE | Cifras anotadas en TASKS; navegar 10 veces entre módulos no hace crecer la memoria de GPU (`renderer.info.memory`). |
| VUI01 | Tokens de diseño en `src/index.css` (`@theme`) según PLAN §15.2; reemplazar los hex sueltos. | DEV | PENDIENTE | `grep -rnE "#[0-9A-Fa-f]{6}" src/components src/ui` solo encuentra colores de avatar o datos, no estilos. |
| VUI02 | Kit `src/ui/` (Button, Card, Badge, StatusPill, Input, Textarea, Select, Modal, Tabs, Table, EmptyState, Skeleton, Toast, Tooltip, Avatar) con foco visible y soporte de teclado. | DEV | PENDIENTE | Cada componente usa solo tokens; el Modal atrapa el foco y se cierra con Esc. |
| VUI03 | Layout: Sidebar renovado (grupos, contadores), cabecera con buscador global de tickets, menú de usuario e indicador de conexión SSE. | DEV | PENDIENTE | Al parar la API, el indicador pasa a rojo y vuelve a verde al reconectar. |
| VUI04 | Kanban renovado: tarjetas nuevas, **drag & drop nativo** HTML5 (las flechas se mantienen), panel lateral de detalle con historial del ticket, asignar y continuar. | DEV | PENDIENTE | Arrastrar una tarjeta cambia el estado vía API y se refleja en otra pestaña; también se puede mover solo con teclado. |
| VUI05 | Calendario de Proyectos con el kit (misma funcionalidad). | DEV | PENDIENTE | Las funciones actuales siguen funcionando; estilo consistente. |
| VUI06 | Cerebro FlowClic con el kit (cola de aprobaciones, vigilador de agentes con los 5 estados). | DEV | PENDIENTE | Igual que arriba. |
| VUI07 | Administración y modales (crear agente, login, MFA) con el kit. | DEV | PENDIENTE | Igual que arriba. |
| VUI08 | Accesibilidad y responsive: contraste AA, navegación completa con teclado, `prefers-reduced-motion`, usable desde 1280 px; en móvil Sidebar plegable y Kanban en lista. Estados vacío, carga y error en cada vista. | DEV | PENDIENTE | Lighthouse Accessibility ≥ 90 en Kanban y Administración. |
| QV1 | QA visual y funcional del 3D: los 5 estados en sus espacios, placas, monitores en tiempo real, sin marcas, rendimiento (cifras de V3D07). | QA | PENDIENTE | Checklist con capturas en QA_REPORT. |
| QV2 | QA del rediseño: todas las vistas con el kit, teclado, contraste, responsive y Lighthouse. | QA | PENDIENTE | Resultados en QA_REPORT. |
- **V00** — (repo FRONT) NAV_ITEMS y MODULE_HEADERS en el orden de PLAN §15.1 (kanban, roadmap, cerebro, colmena3d; Administración llegará con F03), nombres exactos "To-Do & Pipeline de Tareas" y "Calendario de Proyectos", módulo por defecto `kanban`, unión ActiveModule reordenada. Archivos: src/components/Sidebar.tsx, src/App.tsx, src/types/orbis.ts. Probar: `npm run dev` → abre en el Kanban con el Sidebar en ese orden; `npm run lint` y `npm run build` pasan.
- **P00** — Python 3.13.17, `libsql` 0.1.11 (instalado en `.venv` con `py -3.13`). Con `file:` TODO OK: create, insert parametrizado (`?`), lectura (filas = tuplas, nombres en `cursor.description`), commit, rollback y reintentar `BEGIN` tras commit/rollback. HALLAZGOS que condicionan el adaptador `Database` (no son bloqueantes, `sqlite3` de respaldo no hizo falta): (1) **`executescript` NO lanza error con SQL roto y NO es atómico** (dejó `CREATE TABLE f1` aplicada pese al `SELEC 1;` inválido) ⇒ prohibido para migraciones; el runner debe trocear el SQL con `sqlite3.complete_statement` y ejecutar sentencia a sentencia. (2) **Sin `BEGIN` explícito el DDL se autocommitea y el rollback no lo deshace**; con `BEGIN` explícito + `execute` por sentencia el rollback sí deshace DDL y DML (probado: 0 tablas tras fallo). ⇒ `transaction()` hará `BEGIN` explícito, `commit()` o `rollback()` en `finally`. (3) Los errores SQL llegan como `ValueError`. (4) La conexión funciona desde otro hilo (no hay `check_same_thread`), pero no es seguro compartirla sin control: el adaptador usará un `threading.Lock` por conexión. Probado con scripts desechables fuera del repo.
- **P01** — Código Node eliminado (src, test, seeds, scripts, package*.json, tsconfig); se conservan docs/ y migrations/. Creados: estructura de PLAN §0.5 (paquetes app/* con __init__, scripts/, tests/), requirements.txt (fastapi 0.165.0, uvicorn[standard] 0.54.0, pydantic-settings 2.16.3, libsql 0.1.11, cryptography 50.0.2) y requirements-dev.txt (pytest 9.2.0, httpx 0.28.1, pip-audit 2.10.1, ruff 0.17.6, mypy 2.4.1), pyproject.toml (ruff, mypy strict, pytest), .gitignore de Python, .env.example (§9, §12.5, §0.8), app/main.py (`create_app()`, /docs, /redoc, /openapi.json), tests/test_smoke.py y README con los comandos de §0.6. Verificado: `ruff check .`, `mypy app`, `pytest` (1 test) y `pip-audit -r requirements.txt` sin vulnerabilidades; uvicorn en el puerto 4001 sirve /docs → 200 (el 4000 sigue ocupado por la API Node). Probar: `py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt -r requirements-dev.txt; uvicorn app.main:app --port 4001` y abrir /docs. Nota: `.env.example` conserva `NODE_ENV` tal como lo define PLAN §12.5.
- **T02** — app/config.py: `Settings` (pydantic-settings; lee .env, variable vacía = no definida) con PORT, HOST, TURSO_DATABASE_URL (obligatoria), TURSO_AUTH_TOKEN opcional, DB_DRIVER, CORS_ORIGIN, ORCHESTRATOR=noop, DOCS_ENABLED (por defecto apagada en production) y las variables de seguridad/backup de PLAN §12.5 (en production exigen APP_ENCRYPTION_KEY y SESSION_SECRET; la clave debe ser 32 B base64). `get_settings()` termina con mensaje claro y exit 1 si el entorno es inválido. Tests: tests/test_config.py (8). Probar: `pytest tests/test_config.py`; sin TURSO_DATABASE_URL: `python -c "from app.config import get_settings; get_settings()"` → exit 1. Añadido filtro de un DeprecationWarning de starlette.testclient (httpx2) en pyproject.
- **T10** — app/db/database.py: interfaz `Database` (execute, fetch_all→dict, fetch_one, transaction() con BEGIN explícito, close), `LibsqlDatabase` (token vacío no se envía), `SqliteDatabase` (respaldo, DB_DRIVER=sqlite, solo `file:`), `connect_database()`, y conexión activa `set_db/get_db/swap_db` (cambio en caliente, la vieja se cierra a los 5 s). Errores SQL → `DatabaseError`/`IntegrityError` (aplica lo aprendido en P00: sin executescript, BEGIN explícito, lock por conexión). app/util.py (now_iso, new_id). Tests con ambos drivers en tests/test_database.py y fixtures en tests/conftest.py. Probar: `pytest tests/test_database.py`. Remoto Turso (`libsql://`) no probado aquí (sin BD en la nube): pendiente en T64.


---

# AMPLIACIÓN 2026-11-22 (c): Secretos cifrados y drag & drop (PLAN §16–§17)

**Orden vigente desde ahora:** K01 → T02 → C01 → C02 → C03 → T10–T14 → T20–T24 → C04 → F06 → T30 → S01–S10 (S08 usa el módulo de C01) → T31, T32, T60, T61 → A01–A07 (A05 sobre la bóveda) → C05 → F07 → FRONT (F05, T70–T75, F01–F03, T77, T79) → QC1.
Las migraciones se renumeran: `003_agent_credentials.sql` (C05) y `004_admin.sql` (A01).

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| K01 | FRONT: **arrastrar y soltar** en el Kanban (PLAN §17), HTML5 nativo: columna destino resaltada, tarjeta fantasma, se mantienen las flechas y el teclado. Antes de conectar la API, cambia el estado local; después usa `PATCH /api/tickets/{id}/status` y, si la API rechaza el movimiento, la tarjeta vuelve a su columna. | DEV | EN QA | Se puede arrastrar una tarjeta entre las 5 columnas con el ratón; también se mueve con teclado; `npm run lint` y `npm run build` pasan. |
| C01 | `app/security/crypto.py`: AES-256-GCM + HKDF (`cryptography`) con `info` por uso (vault, agent-credentials, mfa), AAD obligatoria, `key_version`; `APP_MASTER_KEY` validada en `config.py` (32 B en base64). | DEV | HECHO | Tests: cifrar y descifrar; con otra AAD o con el texto cifrado alterado → error; la misma entrada da textos cifrados distintos (nonce aleatorio). |
| C02 | Bóveda local `data/vault.db` (PLAN §16.2): `app/security/vault.py` con `get_secret`, `set_secret`, `has`; `data/` en `.gitignore`. `get_db()` construye la conexión con la URL y el token de la bóveda. | DEV | EN QA | Abrir `vault.db` con sqlite3 y buscar la URL o el token en claro no da resultados; la API se conecta a Turso con los datos de la bóveda. |
| C03 | Importar desde el `.env` y limpiarlo (PLAN §16.4); `setup_env.py` y `.env.example` sin `TURSO_*`, con `APP_MASTER_KEY`. | DEV | HECHO | Arrancar con `TURSO_*` en el `.env` → quedan en la bóveda y las líneas desaparecen del `.env` (el resto queda igual, sin `.env.bak`); el log no contiene la URL ni el token. |
> DEVUELTA POR ARQUITECTO (revisión de seguridad, 2026-11-22): `atomic_write` (app/security/envfile.py) escribe el contenido (que incluye `APP_MASTER_KEY`) en un temporal con los permisos heredados de la carpeta y solo lo restringe después de `os.replace`; además ignora el `False` de `restrict_to_owner` (falla en abierto). Afecta también a `scripts/setup_env.py` y `app/security/vault.py`. Corrección exigida: (1) llamar a `restrict_to_owner(tmp)` justo después de `mkstemp` y ANTES de escribir; si devuelve False → borrar el temporal y lanzar error (falla en cerrado), sin reemplazar el `.env`; (2) lo mismo en `vault.py` al crear `vault.db` (si no se puede restringir, no se crea); (3) en Windows, conceder el permiso al SID del usuario actual (`whoami /user` o `win32` vía ctypes) en lugar del nombre `USERNAME`, e implementar `broader_than_owner` en Windows leyendo `icacls` (solo el SID del propietario, SYSTEM y Administradores permitidos); (4) tests: `restrict_to_owner` forzado a False ⇒ el `.env` original queda intacto y no quedan temporales; en Windows, `icacls` sobre el `.env` y el `vault.db` resultantes muestra solo esas entradas.
| C04 | Modo SETUP (PLAN §16.3): código de un solo uso impreso en consola, solo localhost, `GET /api/setup/status`, `POST /api/setup/database`, `POST /api/setup/admin`; se cierra al completarse (404). | DEV | EN QA | Tests: sin código → 403; desde una IP no local → 403; tras crear la BD y el ADMIN → 404; las demás rutas en modo SETUP → 503 `SETUP_REQUIRED`. |
> DEVUELTA POR ARQUITECTO (revisión de seguridad, 2026-11-22): (1) la comprobación de localhost se fía de `request.client.host`: arrancar uvicorn con `--no-proxy-headers` (también en el README) y rechazar con 403 las peticiones de setup que traigan `X-Forwarded-For`, `Forwarded` o `X-Real-IP`, o un `Host` distinto de localhost/127.0.0.1; (2) carrera TOCTOU: si dos peticiones de setup llegan a la vez, pueden crear dos conexiones o dos ADMIN. Usar un único lock de setup para toda la secuencia comprobación + escritura (`swap_db` y la creación del ADMIN), con la inserción como `INSERT ... WHERE NOT EXISTS (SELECT 1 FROM users WHERE role='ADMIN')` dentro de una transacción, y consumir el código tras cada paso exitoso. Tests: dos peticiones concurrentes → solo una tiene éxito; una cabecera de proxy → 403.
| F06 | FRONT: asistente de primer arranque (código de setup → URL y token de la BD → primer ADMIN → login → activar MFA). | DEV | PENDIENTE | Con la bóveda vacía, la app guía hasta tener la BD y el usuario sin tocar ningún archivo. |
| C05 | `migrations/003_agent_credentials.sql` + endpoints de PLAN §16.6 + interfaz `SecretsProvider` (solo declarada). Nunca se devuelve el valor; auditoría sin el valor. | DEV | PENDIENTE | Tests: ninguna respuesta contiene el secreto; en la BD, `ciphertext` no contiene el valor; copiar el texto cifrado a otra fila o agente → falla al descifrar; rotar actualiza `rotated_at` y `last4`. |
| F07 | FRONT: Administración → Agentes → **Credenciales API** (lista con `••••last4`, Añadir, Rotar, Revocar; campos `type=password` que se vacían; pide MFA si la API responde `MFA_REQUIRED`). | DEV | PENDIENTE | La clave no aparece en las respuestas de red (DevTools), ni en el estado de React, ni en `localStorage`. |
| QC1 | QA de secretos: el `.env` solo tiene `APP_MASTER_KEY` como secreto; ni `vault.db` ni la BD contienen secretos en claro; ningún endpoint ni log los devuelve; el setup se cierra; rotación de la clave maestra; restaurar un backup requiere la clave maestra. | QA | PENDIENTE | Evidencia en QA_REPORT (sin pegar ningún secreto). |

> NOTA DEL ARQUITECTO (2026-11-22): **A05** pasa a escribir en la bóveda (C02), no en el `.env`. **S02** genera `APP_MASTER_KEY` en lugar de `APP_ENCRYPTION_KEY`/`SESSION_SECRET` (`SESSION_SECRET` no hace falta: las sesiones son tokens opacos con hash). **S08** usa `crypto.py` de C01.
- **T11** — app/db/migrate.py: `migrate(db, dir)` + CLI (`python -m app.db.migrate`), tabla schema_migrations, orden numérico, una transacción por migración (rollback y no registro si falla → `MigrationError`), `schema_version()`. app/db/sqlsplit.py trocea el SQL con `sqlite3.complete_statement` (respeta comentarios, cadenas y triggers) porque `executescript` no es fiable (P00). Tests en tests/test_migrate.py con ambos drivers (incluye migración rota sin tablas parciales). Probar: `python -m app.db.migrate` dos veces (la 2ª: "Sin migraciones pendientes"); `pytest tests/test_migrate.py`.
- **T12** — `migrations/001_init.sql` (esquema exacto de PLAN §3, conservado del trabajo previo: el SQL es el mismo en Python) verificado con tests/test_schema.py sobre ambos drivers: status FOO falla en agents/tickets/approvals; los 5 estados de agente son válidos; 2 aprobaciones PENDING del mismo ticket fallan por índice único (una decidida no bloquea una nueva; las sin ticket no chocan); nombre de agente único solo entre activos; CHECK de prioridad, model_tier y categoría. Fixture `migrated_db` en tests/conftest.py. Probar: `pytest tests/test_schema.py`.
- **K01** — (repo FRONT, src/components/KanbanPipelineView.tsx) Tarjetas `draggable` (wrapper div; no choca con los eventos de `motion`), columna destino resaltada (borde/anillo cian) mientras se arrastra, tarjeta origen atenuada como "fantasma", drop llama a `onMoveTaskStage` solo si cambia de columna. Se conservan las flechas y el select; teclado: tarjeta enfocable y Alt+←/→ la mueve. Con la API conectada (T75/T76) no hay cambio optimista: la tarjeta solo se mueve al llegar la respuesta/SSE, así que si la API responde 409/422 se queda en su columna (el texto del error se muestra en T76). Verificado: `npm run lint` y `npm run build` pasan. NO probado en navegador por DEV: QA debe arrastrar entre las 5 columnas con el ratón.
- **C01** — app/security/crypto.py: `SecretBox` (AES-256-GCM + HKDF-SHA256 con `info` por uso: vault / agent-credentials / mfa; AAD obligatoria; nonce aleatorio de 12 B; `key_version` con varias claves maestras para rotar), `Sealed(ciphertext, nonce, key_version)`, `CryptoError` (mensajes sin datos sensibles), `generate_master_key()`, `decode_master_key()`. Config: `APP_ENCRYPTION_KEY` pasa a `APP_MASTER_KEY` (32 B base64; obligatoria en production) en config.py/.env.example/tests. Tests: tests/test_crypto.py (10): ida y vuelta, nonce distinto, otra AAD → error, texto/nonce alterado → error, usos separados, otra clave, rotación, validación de clave. Probar: `pytest tests/test_crypto.py`.
- **C02** — app/security/vault.py (`Vault`: get_secret / set_secret / has / delete_secret; SQLite estándar en data/vault.db con la tabla de PLAN §16.2; AES-256-GCM, AAD = nombre del secreto; el archivo nuevo se restringe al propietario), app/security/fileperms.py (`restrict_to_owner`: icacls en Windows / 0o600 en POSIX; `broader_than_owner`), app/db/bootstrap.py (`build_vault`, `open_database_from_vault`, `open_configured_database`: None = sin conexión → modo SETUP). `data/` en .gitignore; Settings: `vault_path` y `turso_*` pasan a opcionales/legado (solo para que C03 los importe); `python -m app.db.migrate` ahora usa la bóveda. tests/conftest.py: cada test corre en un tmp_path (nunca toca el .env real ni data/). Tests tests/test_vault.py (7): URL y token no aparecen en el archivo ni en un volcado SQLite, copiar el cifrado de un secreto a otro falla, otra clave maestra no abre, la conexión se abre con los datos de la bóveda y migra. Nota T02: su criterio "sin TURSO_DATABASE_URL termina con error" queda obsoleto por PLAN §16 (los tests se adaptaron: ahora el entorno no la exige). Probar: `pytest tests/test_vault.py`.
- **S02** — Hecho junto con C03 (misma pieza): `python scripts/setup_env.py` crea el .env desde .env.example con APP_MASTER_KEY y SESSION_SECRET aleatorios (32 B base64) y nunca sobrescribe: en un .env existente solo añade las claves que falten o estén vacías (el resto queda intacto) y una 2ª ejecución no cambia nada. Permisos (nota del Arquitecto): en Windows `icacls <.env> /inheritance:r /grant:r "<USUARIO>:F"` vía subprocess sin shell; en POSIX chmod 0o600 y aviso si un .env existente es más permisivo (app/security/fileperms.py). .env.example sin valores reales (y sin TURSO_*). Variables validadas en app/config.py (T02; en production exigen APP_MASTER_KEY y SESSION_SECRET). `backups/`, `.env.bak` y `data/` en .gitignore. Tests: tests/test_envfile.py (incluye el de icacls: un único permiso en Windows). PENDIENTE: documentarlo en docs/SECURITY.md (S13). Probar: `pytest tests/test_envfile.py`; `python scripts/setup_env.py` dos veces.


---

# AMPLIACIÓN 2026-11-22 (d): RUTA RÁPIDA M0 "ver datos reales" (CEO)

El CEO necesita **ver los datos de la BD en el front cuanto antes** y **crear el primer agente desde cero** (la BD empieza vacía, sin datos de ejemplo). Este orden **manda sobre cualquier otro**:

1. **API:** T13 (con el cambio de abajo) → T20 → T21 → T22 → T23 → T24 → C04 → T30 → T31 → T32 → T60 → T61.
   - Mientras no exista la autenticación, la API **solo escucha en 127.0.0.1**.
   - **S01–S10 van inmediatamente después de M0**. S09 recorre todas las rutas registradas, así que las rutas de M0 quedan cubiertas sin trabajo extra.
2. **FRONT:** F05 → T70 → T71 → T72 → T73 → T74 → T75 → T79 → F06 → F03a.
3. **QA de M0:** QM0.
4. Después: S01–S10 → T40–T46 → T50–T54 → A01–A07 → C05 → F01–F03 completo → resto.

Cambios de criterio:
- **T13 (cambio):** la BD **empieza vacía**. `python -m app.db.migrate` crea solo el esquema. La semilla de los 4 agentes y los tickets de ejemplo pasa a ser **opcional** (`python -m app.db.seed --demo`) y **no se ejecuta** en el arranque, en el setup ni en el README como paso obligatorio.
- **T75 (añadido):** se eliminan del FRONT los datos de ejemplo de agentes, tickets y aprobaciones (`INITIAL_AGENTS`, `INITIAL_TASKS`, `INITIAL_PROPOSALS`). Con la BD vacía, **cada vista muestra un estado vacío con un botón "Crear primer agente"** (que abre el `CreateAgentModal`), y nada se rompe con 0 agentes: el Kanban sin agentes no deja crear tickets y lo explica; la oficina 3D se ve vacía y sin errores; el Cerebro también.
- **README (corrige QP1):** lista solo los comandos que existen. Los futuros van marcados "(pendiente: tarea X)". QP1 se vuelve a probar cuando esté corregido.

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| F03a | FRONT: módulo **Administración** visible en el menú (5.º lugar) con dos pestañas operativas en M0: **Conexión BD** (estado de `GET /api/setup/status` y modo local o remoto; si hay setup pendiente, enlaza al asistente F06) y **Agentes** (lista real desde la API + crear). El resto de pestañas aparecen deshabilitadas con el texto "Disponible tras el login (S06)". Cuando exista la autenticación, el módulo pasa a ser solo para ADMIN (F03). | DEV | EN QA | El menú muestra los 5 módulos en el orden de PLAN §15.1; crear un agente desde Administración lo muestra al momento en las demás vistas. |
| QM0 | QA de M0: BD vacía en Turso o en `file:`; arrancar la API y el FRONT; asistente de setup; **crear el primer agente desde la app**; se ve en Kanban, Cerebro, 3D y Administración; recargar la página lo mantiene; ningún dato de ejemplo visible. | QA | PENDIENTE | Checklist en QA_REPORT. |
- **T14** — app/db/reset.py: `python -m app.db.reset` borra el archivo local (+wal/shm/journal) y ejecuta migrate + seed; la URL se lee de la bóveda y, si no empieza por `file:`, termina con código 1 y mensaje claro SIN borrar nada y SIN imprimir la URL (`ResetRefused`, validado antes de borrar). Tests: tests/test_reset.py (reset recrea el estado inicial; libsql://, https:// y postgres:// se niegan; CLI con bóveda remota no toca archivos; CLI con bóveda local funciona). Probar: `pytest tests/test_reset.py`.
- **T13** — Ruta M0 (Arquitecto): la BD empieza VACÍA. `migrate` solo crea el esquema; `python -m app.db.seed --demo` carga (opcional) los 4 agentes, 4 tickets, 1 aprobación PENDING y 1 nota; sin `--demo` el comando no hace nada ("Nada que hacer"). `python -m app.db.reset` deja la BD local vacía y `reset --demo` con ejemplos (sigue negándose con URL no `file:`). Tests actualizados (test_seed.py, test_reset.py: BD vacía tras migrar; CLI con/sin --demo). README corregido por la devolución de QP1: solo comandos que existen (setup_env, migrate, seed --demo, reset, pytest, ruff, mypy, pip-audit, uvicorn para Swagger) y sección "Comandos futuros" con tarea (S05, S12, C04/F06, A05, T20). Probar: `pytest`; `python -m app.db.seed` → "Nada que hacer".
- **C03** — CORRECCIÓN tras la devolución de seguridad (falla en cerrado): (1) `atomic_write` crea el temporal VACÍO, llama a `restrict_to_owner` ANTES de escribir ningún dato y, si devuelve False, borra el temporal y lanza `PermissionError` sin tocar el .env; el renombrado conserva la ACL del temporal. (2) `Vault` crea `vault.db` vacío, lo restringe antes de abrir SQLite/guardar secretos y, si falla, lo borra y lanza `VaultError`. setup_env.py usa `atomic_write` (mismo camino). (3) Windows: `restrict_to_owner` concede `icacls /inheritance:r /grant:r *<SID>:F` (SID obtenido con `whoami /user`, no `USERNAME`); `broader_than_owner` lee la ACL con icacls y devuelve True si hay otro principal o entradas heredadas, o si no puede comprobarlo. (4) Tests en tests/test_fileperms.py: fallo de restricción → el .env queda intacto y sin temporales; el temporal está vacío al restringirlo; la bóveda no se crea si falla; en Windows se concede al SID, queda 1 solo permiso, un archivo heredado se detecta como amplio y, si icacls falla, restrict=False/broader=True. Probar: `pytest tests/test_fileperms.py tests/test_envfile.py`.
- **T20** — app/main.py `create_app(settings=None, db=None)` (sin arrancar servidor; abre la BD desde la bóveda en el lifespan; CORS con CORS_ORIGIN y credentials), app/routers/health.py (`GET /api/health` hace SELECT 1 → {ok, db, version}), app/__main__.py (`python -m app` escucha en HOST/PORT del entorno, por defecto 127.0.0.1:4000; también `uvicorn app.main:app`). tests/conftest.py: fixtures `test_settings` y `client` (BD temporal migrada y vacía). Tests: tests/test_health.py (health, CORS: origen permitido recibe ACAO y el ajeno no, Swagger). Verificado a mano en el puerto 4010 (el 4000 sigue ocupado): arranca, importa TURSO_* a la bóveda y responde /api/health y /docs. Probar: `python -m app` y `curl localhost:4000/api/health`; `pytest tests/test_health.py`.
- **T21** — app/errors.py: `AppError` (+ helpers not_found/conflict/unprocessable/validation_error) con códigos estables y estado HTTP (VALIDATION_ERROR 400, NOT_FOUND 404, CONFLICT/LIMIT_EXCEEDED 409, UNPROCESSABLE 422, INTERNAL 500, y los de auth/setup ya previstos), handlers registrados en create_app: validación de Pydantic/FastAPI → 400 con `details` [{path, message}] (en vez del 422 por defecto), rutas inexistentes → 404 JSON, 405 JSON, errores no controlados → 500 sin stack ni detalles internos (el log solo guarda tipo y ruta). Modelo `ErrorResponse` para documentarlo en Swagger. Tests: tests/test_errors.py (forma {error:{code,message,details}} en 400/404/405/409/422/500; el 500 no contiene el texto de la excepción). Probar: `curl localhost:4000/api/nada` y `pytest tests/test_errors.py`.
- **T22** — app/domain/schemas.py: DTOs de PLAN §6 con Pydantic v2 (Agent, Ticket, TicketEvent, Approval, MemoryEntry) que se serializan en camelCase (`alias_generator=to_camel`, `populate_by_name`), y modelos de entrada `StrictInput` con `extra="forbid"` y longitudes máximas (AgentCreate/Update/StatusBody, TicketCreate/Update/StatusBody/AssignBody/ContinueBody, ApprovalCreate/Update/Decision, MemoryCreate/Update). Enumerados como `Literal` (sin `enum.Enum`). `AgentUpdate` rechaza `status`. Tests: tests/test_schemas.py (camelCase en salida y entrada, campos desconocidos, estados, límites, y un test que verifica que no hay clases `enum.Enum`). Probar: `pytest tests/test_schemas.py`; `ruff check .` y `mypy app`.
- **T23** — app/events/bus.py: `EventBus` en memoria (subscribe → función de baja idempotente, emit seguro entre hilos con copia de la lista, `onAny` no hace falta porque el suscriptor recibe `DomainEvent(type, payload)`), con los tipos de la tabla SSE de PLAN §6 (+ settings.*, rule.*, system.db_changed de §13). Un suscriptor que lanza excepción se registra en el log y no rompe al emisor ni a los demás. `get_bus()` para inyectarlo. El SSE (T60) se suscribirá reenviando a una asyncio.Queue con `loop.call_soon_threadsafe`. Tests: tests/test_bus.py (5). Probar: `pytest tests/test_bus.py`.
- **T24** — Infra de tests (tests/conftest.py): cada test corre en un tmp_path (nunca lee/escribe el .env real, data/ ni local.db), fixtures `raw_db`/`migrated_db` (BD temporal con ambos drivers, vacía y migrada), `test_settings`, `client` (app + TestClient con BD vacía) y `seeded_client` (con datos de DEMO). tests/test_infra.py: health en verde y comprobación de que local.db, .env y data/vault.db del repo no cambian (mtime/tamaño), cada test tiene su BD propia y sin filtraciones entre tests. Probar: `pytest` (136 tests) y comprobar que no aparece local.db nuevo.

> **ARQUITECTO 2026-11-22 (e):**
> - **F03a se adelanta**: va justo después de T22 (antes que T23). El CEO no ve el módulo Administración. Mientras no existan T61, T75 ni C04, la pestaña Agentes lista los agentes que haya en el estado del front y Conexión BD muestra "pendiente de C04"; se conectan solos cuando esas tareas estén hechas.
> - **Seguridad, formato obligatorio para QA**: QS1–QS5 y QC1 se reportan con los 5 campos de `docs/SECURITY_FINDINGS.md` (OWASP/CWE, severidad CVSS, vector e impacto CIA, causa raíz, remediación) más el resultado, el vector CVSS de la instancia y la evidencia sin secretos.
> - C02 queda EN QA hasta tener el token de Turso del CEO (se verificará con la API, sin ver los valores). K01: QA usa un arrastre real (`left_click_drag` de Claude in Chrome); si la herramienta no puede, lo valida el CEO a mano.
- **S04** — app/security/password.py: `hash_password` / `verify_password` con hashlib.scrypt (N=2^17, r=8, p=1, sal aleatoria de 16 B, maxmem ajustado), formato `scrypt$N$r$p$salt$hash` (la verificación usa los parámetros guardados en cada hash), comparación con `hmac.compare_digest`, política 12–128 caracteres (`PasswordPolicyError`), hash mal formado → False sin lanzar, y `DUMMY_HASH` para igualar tiempos con usuario inexistente (S07). Tests: tests/test_password.py (hash ≠ clave, dos hashes distintos, buena/mala, parámetros reales del plan, formatos rotos, política, unicode). Probar: `pytest tests/test_password.py`.
- **F03a** — (repo FRONT) Nuevo src/components/AdminView.tsx y entrada "Administración" (icono ShieldCheck) en 5.º lugar del Sidebar (PLAN §15.1), `ActiveModule` con 'admin', cabecera "Administración" y render en App.tsx. Pestañas: **Conexión BD** (texto "pendiente de C04", sin mostrar nunca URL/token) y **Agentes** (tabla con los agentes del estado del front + botón "Crear agente" que abre el modal existente; estado vacío "Aún no hay agentes"). Proyecto, Reglas, Límites, Usuarios y Auditoría aparecen deshabilitadas con el texto "Disponible tras el login (S06)" (tooltip y, en pantallas anchas, junto a la pestaña). Mismos estilos que el resto de la app. Pasará a usar T61/T75/C04 al conectarse a la API. Verificado: `npm run lint` y `npm run build` pasan; no probado en navegador por DEV. Probar: `npm run dev` → menú con 5 módulos; Administración → Agentes → Crear agente.


---

# AMPLIACIÓN 2026-11-22 (f): Perfiles de agentes, restricciones globales y flujo de tickets (PLAN §19)

**Decisión del Arquitecto sobre `001_init.sql`:** como **todavía no existe ninguna BD persistente** (la local se borró y Turso aún no está creada), se permite **una única vez** corregir `001_init.sql` con los estados nuevos de ticket (`PENDING, IN_PROGRESS, IN_QA, IN_REVIEW, DONE, RETURNED`) y `approvals.gate`, en lugar de reconstruir tablas con una migración. Los campos de perfil van en `005_agent_profiles.sql`. A partir de que se cree la BD en Turso, la regla "las migraciones aplicadas no se editan" vuelve a ser absoluta.

**Orden:** se intercala en M0 así: … T30 → **G01 → G02 → G03** → T31, T32 (ya con perfiles) → T60, T61 → **G04** → FRONT (… T75 → **G07 → G08** → T79 sustituida por G07) … → los tickets (T40–T46) se implementan **directamente con G05** y las aprobaciones (T50–T54) **con G06**.

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| G01 | Esquema: corregir `001_init.sql` (estados de ticket de §19.4 y `approvals.gate` 1..4) + `005_agent_profiles.sql` (campos de §19.1). Actualizar los tests de esquema. | DEV | EN QA | `status='AWAITING_APPROVAL'` → falla el CHECK; `gate=5` → falla; los tests de esquema pasan. |
| G02 | `app/domain/agent_policy.py` (GLOBAL_RESTRICTIONS, lista cerrada de acciones, acciones prohibidas, validación de permisos por `role_type`) + `models_catalog.py` + generación de `system_prompt` en el servidor. | DEV | PENDIENTE | Tests: un permiso `git.merge_main` → 422; `approvals.create` en un DEV → 422; el prompt siempre contiene las 5 globales aunque el cliente envíe otras; acción desconocida → 400. |
| G03 | `app/domain/agent_templates.py` con los 4 perfiles **exactos** del CEO (funciones, reglas, restricciones, permisos, modelo, límites de §19.6) + `GET /api/agent-templates` + seed `--agents` y endpoint "Cargar equipo base" (ADMIN, idempotente). | DEV | PENDIENTE | Las plantillas reproducen literalmente el texto del CEO; cargar el equipo dos veces deja 4 agentes. |
| G04 | `AgentGuard`: `record_failure` / `record_success` (BLOCKED al 3.º fallo seguido), `check_budget`; `POST /api/agents/{id}/failures` solo ADMIN (pruebas Fase 1); auditoría y evento SSE. | DEV | PENDIENTE | 3 fallos seguidos → BLOCKED y evento; un éxito intermedio reinicia el contador. |
| G05 | `app/domain/ticket_flow.py` (`can_transition`, grafo y matriz de §19.4) + `POST /api/tickets/{id}/transition` con `actingAgentId` (solo ADMIN, auditado) + efectos en el agente. Sustituye a `PATCH /status` y `/continue`. | DEV | PENDIENTE | Test de tabla con todas las combinaciones de actor × origen × destino: grafo inválido → 409, sin permiso → 403, dev en un ticket no asignado → 403, humano ADMIN cualquier transición válida → 200. |
| G06 | Compuertas: `gate` en aprobaciones; solo CTO o ADMIN las crean (403); solo un humano las decide; `GATE_PENDING` bloquea DONE; REJECTED → RETURNED. | DEV | PENDIENTE | Tests de cada regla. |
| G07 | FRONT: modal "Crear agente" de §19.7 (plantillas, editores de listas, permisos, modelo, límites, globales bloqueadas con candado, vista previa del prompt, errores 422 por campo). Sustituye a T79. | DEV | PENDIENTE | Crear con la plantilla "Dev Frontend" precarga el perfil de Penny; las globales no se pueden editar ni quitar (ni manipulando el DOM: la API las vuelve a aplicar); el agente aparece en todas las vistas. |
| G08 | FRONT: vista de detalle del agente (pestañas de §19.7), accesible desde 3D, Cerebro, Kanban y Administración; edición para ADMIN. | DEV | PENDIENTE | Muestra todo el perfil y el prompt generado; editar y guardar persiste. |
| G09 | FRONT: Kanban con las 6 columnas de §19.4; el arrastre solo acepta destinos válidos (los inválidos se ven atenuados); 403/409 devuelven la tarjeta a su sitio con el mensaje. Ajusta K01 y VUI04. | DEV | PENDIENTE | Arrastrar PENDIENTE→HECHO no se permite; EN QA→DEVUELTA sí. |
| QG1 | QA de perfiles y flujo: globales inviolables (API y UI), matriz de transiciones completa (incluido `actingAgentId`), bloqueo por fallos, compuertas, plantillas literales. | QA | PENDIENTE | Matriz en QA_REPORT. |
| QS0 | **Auditoría inicial de seguridad AHORA** sobre el código actual de `dev` (API y FRONT): los 19 hallazgos con los 5 campos de `docs/SECURITY_FINDINGS.md` + resultado (CUMPLE / NO CUMPLE / PENDIENTE DE IMPLEMENTAR / N/A) + vector CVSS si hay una instancia real + evidencia sin secretos. Es la línea base contra la que se medirán QS1–QS5. | QA | PENDIENTE | Sección "Auditoría de seguridad — línea base" en QA_REPORT con los 19 puntos completos. |


---

# AMPLIACIÓN 2026-11-22 (g): Panel de chat del 3D y cambio de equipo

## Cambio de equipo (CEO)
- **Junior A** (DEV) implementa y **Junior QA** (QA) prueba. Los antiguos Senior y QA (Claude) pasan a **REVISORES**: no implementan; validan el trabajo de los junior.
- Flujo de cada tarea: **Junior A** `EN CURSO → EN QA` → **Junior QA** `EN QA → EN REVISIÓN` (o `DEVUELTA`) → **Revisor Claude** `EN REVISIÓN → HECHO` (o `DEVUELTA`, con el motivo bajo la tarea).
- Se añade el estado `EN REVISIÓN` a las tareas de este archivo. Una tarea solo es `HECHO` cuando un revisor la valida.
- Antes de parar, cada sesión anterior escribe su traspaso en la sección "TRASPASO" del final de este archivo.

## Panel derecho de la Oficina 3D: chat de mando (CEO)
La barra inferior actual (cámara, "Simular recorrido", selector de agente y botones de zona) **se sustituye** por un **panel lateral derecho** plegable (≈380 px) con:
1. **Cámara** (parte superior compacta): Vista general · Laboratorio · Oficina de Sheldon · Zona de descanso · restablecer. Se elimina "Simular recorrido completo".
2. **Selector de destinatario:** "Todo el equipo (global)" o un agente concreto (con avatar y `StatusPill`).
3. **Tarjeta "Qué está haciendo / qué le falta"** del agente seleccionado (o resumen del equipo en modo global), calculada a partir de los datos reales: ticket actual, estado, tiempo en ese estado, criterio de aceptación pendiente, si está bloqueado (motivo), aprobaciones pendientes y siguiente paso según el flujo (§19.4).
4. **Hilo de chat:** mensajes del CEO + eventos del agente (cambios de ticket y de estado, desde `ticket_events`) + respuestas de los agentes (Fase 2).
5. **Caja de órdenes:** texto + tipo (Orden · Pregunta · Nota). Atajos: "Continuar", "Pausar" (→ SLEEP_QUOTA), "Reanudar", "Prioridad alta".

**Reglas (coherentes con las restricciones globales):**
- Las **órdenes globales van a Sheldon** (CTO), que las reparte. Las individuales van al agente, con copia visible para Sheldon.
- **Solo Sheldon responde en conversación** (restricción global 4). Los demás agentes solo aportan eventos de estado.
- **En la Fase 1 no hay IA:** la orden se guarda con estado `PENDIENTE` y se muestra "Se ejecutará cuando se conecte el orquestador (Fase 2)". Los atajos que cambian el estado del agente sí actúan ya, a través de la API (cambio de estado o transición válida).
- Permisos: ADMIN y OPERATOR envían; VIEWER solo lee. Texto máximo de 2 000 caracteres, guardado como texto y nunca renderizado como HTML.

**Datos:** `migrations/006_agent_messages.sql`:
```sql
CREATE TABLE agent_messages (
  id         TEXT PRIMARY KEY,
  scope      TEXT NOT NULL CHECK (scope IN ('GLOBAL','AGENT')),
  agent_id   TEXT REFERENCES agents(id),          -- NULL si GLOBAL
  author_type TEXT NOT NULL CHECK (author_type IN ('HUMAN','AGENT','SYSTEM')),
  author_id  TEXT NOT NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('ORDER','QUESTION','NOTE','STATUS','REPLY')),
  body       TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACK','DONE','REJECTED')),
  ticket_id  TEXT REFERENCES tickets(id),
  created_at TEXT NOT NULL
);
CREATE INDEX ix_agent_messages_agent ON agent_messages(agent_id, created_at);
```

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| H01 | API: migración 006 + `GET /api/messages?agentId=&scope=&limit=` (mensajes + eventos de ticket del agente, combinados por fecha) + `POST /api/messages` + evento SSE `message.created` + `GET /api/agents/{id}/status-summary` ("qué hace / qué le falta"). Las órdenes globales se dirigen a Sheldon. | DEV | PENDIENTE | Tests: VIEWER → 403 en POST; body > 2000 → 400; una orden global aparece en el hilo de Sheldon; `status-summary` refleja el ticket actual y el siguiente paso. |
| H02 | FRONT: panel derecho de la Oficina 3D (sustituye a la barra inferior), con cámara renombrada, selector global/individual, tarjeta de estado, hilo, caja de órdenes y atajos; se pliega; tiempo real por SSE. Se elimina "Simular recorrido". | DEV | PENDIENTE | Enviar una orden la muestra al instante en otra pestaña; "Pausar" pone al agente en SLEEP_QUOTA y lo mueve a la Zona de descanso; con el panel plegado el 3D ocupa todo el ancho. |
| QH1 | QA del panel de mando: órdenes globales e individuales, permisos, XSS en el texto, tiempo real, atajos. | QA | PENDIENTE | Resultados en QA_REPORT. |

**Orden actualizado (prioridad del CEO: que se vea el cambio visual del 3D):** terminar lo que está EN CURSO (T30, G01) → **V3D02 (rótulos) → H01 → H02 → V3D03 → V3D04 → V3D05 → V3D06 → V3D01 → V3D07** → después continúa la ruta M0 (G02, G03, T31…). V3D01 (refactor) puede hacerse después porque no cambia nada visible.

## TRASPASO
_(Cada sesión que se detiene escribe aquí: tareas EN CURSO y su estado exacto, archivos a medias, comandos para probar, dudas abiertas.)_
- **G01** — Corrección ÚNICA de `001_init.sql` permitida por PLAN §19: `tickets.status` pasa a PENDING·IN_PROGRESS·IN_QA·IN_REVIEW·DONE·RETURNED (defecto PENDING) y `approvals.gate` INTEGER NOT NULL CHECK (1..4); el índice único pasa a ser por (ticket_id, gate) entre PENDING (decisión mía, ver pregunta). Nueva `migrations/005_agent_profiles.sql` con role_type (CHECK), functions, rules, restrictions, permissions, model, limits y consecutive_failures (con valores por defecto válidos). Semilla (demo) adaptada al flujo nuevo y cambiada de `INSERT OR IGNORE` a `ON CONFLICT DO NOTHING`: el primero ignora EN SILENCIO las violaciones de CHECK (así los tickets antiguos "desaparecían" sin error y luego fallaba la FK); libSQL sí aplica las claves foráneas. Modelos Pydantic: TicketStatus nuevo y `gate` en Approval/ApprovalCreate. Tests: tests/test_schema.py (estado antiguo → CHECK; gate 0/5/-1 y gate ausente → falla; 6 estados y 4 compuertas válidos; defecto PENDING; columnas de la 005 con defaults; role_type y contador validados) y ajustes en test_migrate/test_seed. PREGUNTA PARA ARQUITECTO (no bloquea): ¿un ticket puede tener a la vez compuertas PENDING de distinto número? Yo lo permito (índice único por ticket+compuerta). Probar: `pytest tests/test_schema.py`.


---

# RESPUESTAS DEL ARQUITECTO (2026-11-22, h)

**Preguntas del Senior:**
1. *¿`GET /api/setup/status` sigue en 200 tras cerrarse el asistente?* **Sí, 200, pero solo con `{"setupRequired": false}`**: sin `hasDatabase` ni `hasAdmin`, y sin exigir localhost. El front lo necesita al cargar para decidir si muestra el asistente. El resto de `/api/setup/*` → 404 una vez cerrado.
2. *¿Un ticket puede tener a la vez compuertas pendientes de distinto número?* **Sí.** Como máximo una PENDING por **(ticket, gate)**: índice único `(ticket_id, gate) WHERE status='PENDING'`. El ticket no puede pasar a DONE mientras tenga **cualquier** compuerta PENDING (`GATE_PENDING`).

**Desviaciones del Senior aceptadas:** G01 antes que T30; la semilla con `ON CONFLICT DO NOTHING` en lugar de `INSERT OR IGNORE` (mejor: no oculta violaciones de CHECK).

**QS0 (línea base de seguridad):** aceptada. Hay dos instancias reales; se corrigen así:
- **#10 (CVSS 5.3), se amplía S01:** `/api/health` sin sesión responde **solo** `{"ok": true}` (sin `version` ni `db`); uvicorn se arranca con `--no-server-header` (README y cualquier script de arranque) y no se envía ninguna cabecera que revele el software o su versión. Criterio añadido a S01: `curl -i` no muestra `server:` ni la versión.
- **#16 (CVSS 5.3), nueva tarea P03:** la documentación se mueve a **`/api/docs`, `/api/redoc` y `/api/openapi.json`** (así recibe la cookie `fc_session`, que tiene `Path=/api`). Cuando exista S09, exigen **sesión ADMIN u OPERATOR**; hasta entonces solo se sirven a `127.0.0.1` y con `DOCS_ENABLED=true`. `/docs`, `/redoc` y `/openapi.json` en la raíz → 404. Para usar Swagger: iniciar sesión en el front y abrir `/api/docs`. Esto **sustituye** a PLAN §0.7, que permitía ver el esquema sin sesión.
- Ajuste de clasificación: **#4 (IDOR)** pasa de N/A a **PENDIENTE DE IMPLEMENTAR**: aplica en cuanto existan `me/sessions/{id}` y las credenciales por agente (S06, C05).

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| P03 | Documentación de la API bajo `/api/docs` (ver arriba): rutas movidas, `/docs` en la raíz → 404, acceso solo local hasta S09 y con sesión ADMIN/OPERATOR desde S09; `DOCS_ENABLED=false` → 404 también en `/api/docs`. | DEV | PENDIENTE | Sin sesión (después de S09) `/api/docs` y `/api/openapi.json` → 401; con OPERATOR → 200; `/docs` → 404. |

**Orden para Junior A:** terminar lo de "AMPLIACIÓN (g)" (V3D02 → H01 → H02 → V3D03–V3D06) **corrigiendo antes C04** (DEVUELTA) y añadiendo **P03** y la ampliación de **S01** en cuanto toque la seguridad.


---

# AMPLIACIÓN 2026-11-22 (i): EQUIPO NUEVO Y PRIORIDAD "DATOS REALES YA" (manda sobre (g) y (h))

**BD en Turso creada por el Arquitecto (2026-11-22):** esquema `001`, `002` y `005` aplicado; **9 tablas y 0 filas**. No hay datos de ejemplo. La URL y el token siguen en el `.env` hasta que la API arranque y C03 los importe a la bóveda (antes hay que ejecutar `python scripts/setup_env.py` para añadir `APP_MASTER_KEY`). **Nadie lee el `.env` ni `data/vault.db`.**

## Equipo
| Rol | Herramienta | Repo principal | Hace | Mueve tareas |
|---|---|---|---|---|
| **Desarrollador Senior** | Claude Sonnet | API | Implementa la API y **revisa** al Junior | API: `EN CURSO → EN QA`; revisión del FRONT: `EN REVISIÓN → HECHO / DEVUELTA` |
| **Desarrollador Junior** | Antigravity | FRONT | Implementa el FRONT | `EN CURSO → EN QA` |
| **QA Junior** | Antigravity | ambos | Prueba contra el criterio | `EN QA → EN REVISIÓN / DEVUELTA` |
| **QA Senior** | Claude Haiku | ambos | Valida el veredicto del QA Junior y las auditorías de seguridad (5 campos) | `EN REVISIÓN → HECHO / DEVUELTA` (las tareas de API las cierra el QA Senior; las de FRONT, el Dev Senior **y** el QA Senior) |

Reglas para no pisarse: cada uno hace `git pull` antes de empezar y antes de cada commit; solo edita **su fila** de estado y sus notas en TASKS.md; el Junior Dev no toca la API y el Senior Dev no toca el FRONT (salvo revisión).

## Prioridad: borrar los datos de ejemplo y crear agentes reales en la BD
**Desarrollador Senior (API):** C04 (corregir la DEVUELTA) → T30 → G02 → G03 (plantillas + "Cargar equipo base") → T31 → T32 → T61 → T60 → G04 → después H01 y S01 (con #10) y P03.
**Desarrollador Junior (FRONT):**
1. **F05**
2. **T75-parte 1 YA:** eliminar del FRONT `INITIAL_AGENTS`, `INITIAL_TASKS` e `INITIAL_PROPOSALS`, con estados vacíos y el botón "Crear primer agente" en Kanban, Cerebro, 3D y Administración, sin errores con 0 agentes.
3. T70 → T71 → T72 → T74 → T75-parte 2 (conectar a `/api/snapshot` y SSE cuando T61/T60 estén EN QA).
4. **G07** (modal con plantillas) → F03a-conexión (pestaña Agentes real + botón "Cargar equipo base" → `POST` de G03) → G08.
5. Después V3D02 → H02 → V3D03–V3D06.

**Hito "agentes reales" (QM0):** con la BD de Turso, crear un agente desde el modal (o cargar el equipo base), verlo en todas las vistas, recargar y que siga ahí; ningún dato de ejemplo visible.
- **C04** — CORRECCIÓN (devolución de seguridad): (1) Localhost ya no se fía solo de `request.client.host`: se rechaza con 403 cualquier petición de setup con `Forwarded`, `X-Real-IP` o cualquier `X-Forwarded-*`, o con un `Host` distinto de localhost/127.0.0.1/[::1] (se admite puerto); `python -m app` arranca uvicorn con `proxy_headers=False, server_header=False` y el README usa `--no-proxy-headers --no-server-header`. (2) TOCTOU: un único `gate.operation` (lock) envuelve comprobación + verificación del código + escritura de cada paso (conexión + `swap_db`, y creación del ADMIN); el ADMIN se inserta con `INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM users WHERE role='ADMIN')` dentro de una transacción y se comprueba `changes()`; el código se consume tras cada paso correcto (tras la BD se emite uno nuevo en la consola; tras el ADMIN se cierra). Tests nuevos en tests/test_setup.py: 5 cabeceras de proxy → 403, 3 Host ajenos → 403, 4 Host locales válidos, código consumido tras cada paso, dos peticiones simultáneas de /database → solo una 200, dos de /admin → solo un ADMIN, y la inserción atómica del servicio con dos hilos. Probar: `pytest tests/test_setup.py`.
