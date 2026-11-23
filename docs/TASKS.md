# FlowClic Oficina IA — Tareas Fase 1

Referencia: `docs/PLAN.md`. Estados: `PENDIENTE` · `EN CURSO` · `EN QA` · `HECHO` · `DEVUELTA`.
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
> - Orden: **P00 → P01 →** T02 → T10–T14 → T20–T24 → T30 → y después PLAN §14 desde el punto 2.

## Bloque P: arranque Python (va antes que todo)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| P00 | Prueba técnica en Windows: crear `.venv` con `py -3.13`, instalar `libsql`, y con un script desechable (no se commitea): conectar a `file:local.db`, crear una tabla, ejecutar una transacción con rollback, un insert parametrizado y una lectura. Si `libsql` falla, repetir con `sqlite3` y anotar el resultado como PREGUNTA PARA ARQUITECTO. **Si Python 3.13 no está instalado, parar y preguntar** (no instalar nada sin OK). | DEV | PENDIENTE | Nota en TASKS con: versión de Python, versión de `libsql`, resultado de cada operación y si el rollback deshace correctamente. |
| P01 | Scaffold Python en `dev`: borrar el código Node (`src/`, `test/`, `seeds/`, `scripts/` de Node, `package.json`, `package-lock.json`, `tsconfig.json`, `node_modules/`); conservar `docs/` y `migrations/`; crear la estructura de PLAN §0.5, `requirements.txt` y `requirements-dev.txt` con versiones exactas (solo los paquetes de §0.2), `pyproject.toml` (ruff, mypy, pytest), `.gitignore` de Python, `.env.example` con las variables de §9, §12.5 y §0.8, y `app/main.py` con `create_app()` y `/docs` activo. Actualizar el `README.md` con los comandos de §0.6. | DEV | PENDIENTE | En una copia nueva: `py -3.13 -m venv .venv`, `pip install -r requirements.txt -r requirements-dev.txt`, `uvicorn app.main:app` arranca y `http://localhost:4000/docs` muestra Swagger; `ruff check .` y `mypy app` pasan; `pytest` corre (aunque sea con 1 test); no queda ningún archivo Node. |
| P02 | Calidad de la documentación Swagger (transversal): cada router con `tags` y `summary`; cada endpoint con `responses` de error documentados; modelos con `json_schema_extra` de ejemplo; `APIKeyCookie('fc_session')` como esquema de seguridad; `DOCS_ENABLED` respetado. Se cumple en **cada** tarea que añada rutas; esta tarea es la revisión final. | DEV | PENDIENTE | En `/docs` todos los endpoints aparecen agrupados, con ejemplos y errores; con `DOCS_ENABLED=false`, `/docs`, `/redoc` y `/openapi.json` → 404. |
| QP1 | QA del arranque Python: seguir el README desde cero en una carpeta limpia; Swagger visible; `pip-audit` sin vulnerabilidades altas. | QA | PENDIENTE | Pasos y resultados en QA_REPORT. |

---

## Bloque 0 — Preparación

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T00 | (Tras OK del CEO) `git init` en API y FRONT, commit inicial en `main` con el estado actual, crear y usar rama `dev`. | DEV | HECHO | `git branch` muestra `main` y `dev` en ambos; `dev` activa; el commit inicial del FRONT no incluye `node_modules` ni `.env*`. |
| T01 | Scaffold API: `package.json` (`"type":"module"`, `engines.node >=24`), scripts de PLAN §9, `tsconfig.json` (noEmit, `allowImportingTsExtensions`, `verbatimModuleSyntax`), `.gitignore`, `.env.example`. Instalar solo deps de PLAN §8. | DEV | PENDIENTE | `npm install` sin errores; `npm run typecheck` pasa; `.env` y `local.db*` ignorados por git; no hay deps fuera de la lista. |
| T02 | `src/config/env.ts`: carga y valida variables con zod (`PORT`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` opcional, `CORS_ORIGIN`, `ORCHESTRATOR` = `noop`). | DEV | PENDIENTE | Sin `TURSO_DATABASE_URL` el proceso termina con mensaje claro y código ≠ 0; con valores válidos exporta objeto tipado. |
| T03 | QA: verificar arranque limpio del scaffold en una copia nueva (clonar `dev`, `npm install`, `npm run typecheck`). | QA | PENDIENTE | Pasos reproducibles anotados en `QA_REPORT.md`; sin rutas absolutas (`grep -rn "D:\\\\\|C:\\\\" src seeds migrations` vacío). |

## Bloque 1 — Base de datos

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T10 | `src/db/client.ts`: cliente único `@libsql/client` con URL y token del env. | DEV | PENDIENTE | Funciona con `file:local.db`; con `TURSO_AUTH_TOKEN` vacío no se envía token. |
| T11 | `src/db/migrate.ts`: runner con tabla `schema_migrations`, aplica `migrations/NNN_*.sql` en orden, cada una en transacción; usable como CLI y como función (tests). | DEV | PENDIENTE | 1ª ejecución aplica todo; 2ª no hace nada; una migración con SQL roto no queda registrada ni deja tablas parciales. |
| T12 | `migrations/001_init.sql` con el esquema exacto de PLAN §3 (CHECKs e índices incluidos). | DEV | PENDIENTE | Insertar `status='FOO'` en agents/tickets/approvals falla; 2 aprobaciones PENDING para el mismo ticket fallan por índice único. |
| T13 | `seeds/seed.ts` idempotente: 4 agentes (ids `sheldon`, `leonard`, `penny`, `raj` con datos de PLAN §3), 3–4 tickets de ejemplo, 1 nota de memoria. | DEV | PENDIENTE | Ejecutar 2 veces deja exactamente 4 agentes; Sheldon `isCto=1`. |
| T14 | Script `db:reset` que borra la BD local y re-ejecuta migrate + seed; se niega si la URL no empieza por `file:`. | DEV | PENDIENTE | Con URL `libsql://...` termina sin borrar nada y con mensaje claro. |
| T15 | QA: probar migrate/seed/reset y CHECKs con `local.db`; documentar en QA_REPORT. | QA | PENDIENTE | Todos los criterios T11–T14 verificados manualmente. |

## Bloque 2 — Núcleo de la API

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T20 | `src/app.ts` + `src/server.ts`: Express, `cors` con `CORS_ORIGIN`, JSON body, `GET /api/health` (hace `SELECT 1`). `app.ts` exporta la app sin escuchar. | DEV | PENDIENTE | `curl localhost:4000/api/health` → `{"ok":true,"db":"up",...}`; petición desde otro origen bloqueada por CORS. |
| T21 | `middleware/errors.ts`: formato de error único de PLAN §5; errores zod → 400 con `details`; rutas inexistentes → 404 JSON; 500 sin stack. | DEV | PENDIENTE | Body inválido devuelve 400 con forma `{error:{code,message,details}}`. |
| T22 | `domain/types.ts` y `domain/schemas.ts`: DTOs de PLAN §6 (uniones de string, sin `enum`) y esquemas zod de entrada. | DEV | PENDIENTE | `npm run typecheck` pasa; no hay `enum` en el código. |
| T23 | `events/bus.ts`: bus tipado de `DomainEvent` (tipos de la tabla SSE de PLAN §6). | DEV | PENDIENTE | Test unitario: un suscriptor recibe el evento emitido con su payload tipado. |
| T24 | Infra de tests: helper que crea BD temporal en `os.tmpdir()`, migra, siembra, levanta la app en puerto efímero y la cierra. | DEV | PENDIENTE | `npm test` corre un test de `/api/health` en verde y no crea/modifica `local.db`. |

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
- **T02** — env.ts con zod; falla con mensaje claro y exit 1 si falta TURSO_DATABASE_URL. Archivo: src/config/env.ts (exporta `env` y `parseEnv`). Probar: `node src/config/env.ts` sin variables → exit 1; `TURSO_DATABASE_URL=file:local.db node src/config/env.ts` → ok.
- **T10** — Cliente libSQL único: `createDb(config)` (token vacío no se envía) y `getDb()` singleton. Archivo: src/db/client.ts. Probar: `TURSO_DATABASE_URL=file:x.db node -e "import(\"./src/db/client.ts\").then(async m=>console.log((await (await m.getDb()).execute(\"SELECT 1\")).rows))"`.
- **T11** — Runner `migrate(client, dir?)` + CLI (`npm run db:migrate`): tabla schema_migrations, orden por NNN, transacción por migración con rollback. Archivo: src/db/migrate.ts. Probar: `npm run db:migrate` dos veces (la 2ª no aplica nada); verificado además que una migración con SQL roto hace rollback y no se registra.
- **T12** — migrations/001_init.sql con el esquema exacto de PLAN §3. Probar: `npm run db:migrate` con TURSO_DATABASE_URL=file:local.db; insertar status=FOO en agents/tickets/approvals falla por CHECK y una 2ª aprobación PENDING del mismo ticket falla por índice único (ya verificado).
- **T13** — Semilla idempotente (INSERT OR IGNORE): 4 agentes (Sheldon isCto=1), 4 tickets (uno por columna activa, sin agente para mantener coherencia R1), 1 aprobación PENDING del ticket en AWAITING_APPROVAL, eventos CREATED y 1 nota de memoria. Archivo: seeds/seed.ts (exporta `seed(client)`). Probar: `npm run db:migrate && npm run db:seed` dos veces → 4 agentes.
- **T14** — Script `db:reset` (src/db/reset.ts): borra local.db(+wal/shm/journal) y ejecuta migrate+seed; se niega (exit 1, sin borrar) si la URL no empieza por `file:`. Probar: `npm run db:reset`; `TURSO_DATABASE_URL=libsql://x.turso.io npm run db:reset` → mensaje y exit 1.
- **T20** — app.ts (`createApp({db, corsOrigin})`, sin listen) + server.ts (env → db → listen, cierre limpio) con cors(CORS_ORIGIN), JSON y GET /api/health (SELECT 1). Probar: `npm run dev` y `curl localhost:4000/api/health` → {"ok":true,"db":"up","version":...}. CORS: la API solo responde Access-Control-Allow-Origin con el origen configurado, así que el navegador bloquea otros orígenes.
- **T21** — middleware/errors.ts: AppError (+helpers notFound/conflict/unprocessable/validation), errorHandler (zod→400 con details, JSON inválido→400, 500 sin stack) y notFoundHandler JSON para cualquier ruta; registrados en app.ts. Probar: `curl localhost:4000/api/nada` → 404 NOT_FOUND con forma {error:{code,message,details}}; POST con JSON roto → 400 VALIDATION_ERROR. El 400 con details de zod se ejerce al llegar las rutas con schemas.
- **T22** — domain/types.ts (DTOs PLAN §6, uniones de string) y domain/schemas.ts (zod de entrada: agentes, tickets, aprobaciones, memoria, queries; los PATCH son estrictos y rechazan campos desconocidos, p. ej. `status` en PATCH /agents/:id). Probar: `npm run typecheck`; `grep -rn "enum " src` (solo z.enum).
- **T23** — events/bus.ts: EventBus tipado (`emit`, `on(tipo)`, `onAny`, baja por función devuelta) con DomainEventMap = tabla SSE de PLAN §6; test/bus.test.ts (3 tests). Desviación menor: el script `test` usa glob (`node --test "test/**/*.test.ts"`) porque `node --test test/` falla en Node 24. Probar: `npm test`.
- **T24** — Infra de tests: test/helpers/testApp.ts (`startTestApp({seed?})`: BD temporal en os.tmpdir(), migra, siembra, app en puerto efímero, `request()` y `close()` que borra la BD temporal); test/health.test.ts. AppDeps ahora incluye `bus` (server.ts lo crea). Probar: `npm test` (5 tests en verde) y comprobar que no aparece local.db.
- **T30** — repositories/agents.repo.ts (list con flag includeArchived, get, findActiveAgentByName, insert, update parcial, setStatus, archive; snake_case⇄camelCase y avatar JSON) + repositories/util.ts (Executor = Client|Transaction, buildUpdate). Tests: test/agents.repo.test.ts. Probar: `npm test`.
> PREGUNTA PARA ARQUITECTO (T31/T32 y siguientes): `docs/PLAN.md` fue ampliado hoy (§12 seguridad, §13 Administración, §14 nuevo orden: S01→S10 antes de T30/T31) pero esta lista no contiene las tareas S*, A*, F* ni QS*. Sin sus definiciones no puedo implementarlas, y §14 exige `requireRole` en toda ruta nueva, así que T31/T32 (rutas de agentes) quedan en pausa hasta tener S01–S10. Esos cambios de PLAN.md siguen sin commitear en el working tree de la API; no los incluí en mis commits.
> RESPUESTA DEL ARQUITECTO (2026-11-22): las tareas S01-S13, A01-A07, F01-F05 y QS ya están definidas al final de este archivo, y PLAN.md está commiteado (462aed8). La pausa de T31/T32 es correcta: sigue el orden S01→S10 y después retoma T31/T32 ya con requireAuth/requireRole. T30 (repositorio, sin rutas) puede pasar a EN QA tal cual.

---

# AMPLIACIÓN 2026-11-22: Seguridad y Administración (PLAN §12–§14)

## Bloque S: seguridad base (API)

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| S01 | Endurecimiento HTTP: `app.disable('x-powered-by')`, cabeceras (CSP `default-src 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`), `express.json({limit:'100kb'})`, `HOST` (por defecto `127.0.0.1`) en `listen`, `requestId` en logs. `/api/health` sin sesión responde **solo** `{ok}`; con sesión, el detalle actual. | DEV | PENDIENTE | `curl -i` muestra las cabeceras y no `X-Powered-By`; body de 200 kB → 413 JSON; la API no responde desde otra IP de la red local. |
| S02 | `npm run setup`: crea `.env` desde `.env.example` si no existe y rellena `APP_ENCRYPTION_KEY` y `SESSION_SECRET` con `crypto.randomBytes(32)` en base64. Nunca sobrescribe un `.env` existente. Añadir las variables de PLAN §12.5 a `.env.example` (vacías) y validarlas en `env.ts` (en `production` deben estar definidas). Añadir `backups/` y `.env.bak` a `.gitignore`. | DEV | PENDIENTE | Ejecutarlo dos veces no cambia el `.env`; ningún valor real en `.env.example`. |
| S03 | `migrations/002_security.sql` con el esquema exacto de PLAN §12.2. | DEV | EN QA | `db:migrate` la aplica; el email está repetido → falla por índice único. |
| S04 | `src/security/password.ts`: `hashPassword` y `verifyPassword` con scrypt (N=2^17, r=8, p=1, sal de 16 B, `maxmem` ajustado), formato `scrypt$N$r$p$salt$hash`, comparación con `timingSafeEqual`. Política: mínimo 12 caracteres. | DEV | PENDIENTE | Tests: el hash ≠ la contraseña; dos hashes de la misma clave son distintos; verificar la buena es true y la mala false. |
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
- **S02** — `npm run setup` (scripts/setup.ts): crea .env desde .env.example con APP_ENCRYPTION_KEY y SESSION_SECRET aleatorios (32 B base64); nunca sobrescribe. .env.example con variables de PLAN §12.5 (secretos vacíos); config/parse.ts (zod: en production exigen claves; APP_ENCRYPTION_KEY debe ser 32 B; vacío = no definida) y config/env.ts (carga y sale con exit 1). .gitignore + backups/ y .env.bak. Tests: test/env-setup.test.ts. Probar: `npm run setup` dos veces (la 2ª no cambia el .env); `npm test`.
- **S03** — migrations/002_security.sql con users, sessions y audit_log exactos de PLAN §12.2. Test: test/security-schema.test.ts (email repetido → UNIQUE, rol inválido → CHECK, semilla sin usuarios). Probar: `npm run db:migrate`; `npm test`.
