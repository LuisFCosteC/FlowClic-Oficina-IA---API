# FlowClic Oficina IA — Tareas Fase 1

Referencia: `docs/PLAN.md`. Estados: `PENDIENTE` · `EN CURSO` · `EN QA` · `HECHO` · `DEVUELTA`.
Reglas: rama `dev`; sin rutas absolutas en código; preguntar antes de añadir dependencias no listadas en PLAN §8.
Si hay una duda, añade debajo de la tarea una línea `> PREGUNTA PARA ARQUITECTO: ...` y sigue con otra tarea.
Cada tarea de DEV pasa a `EN QA`; QA la verifica contra su criterio y la marca `HECHO` o `DEVUELTA` (con detalle en `docs/QA_REPORT.md`).

---

## Bloque 0 — Preparación

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T00 | (Tras OK del CEO) `git init` en API y FRONT, commit inicial en `main` con el estado actual, crear y usar rama `dev`. | DEV | HECHO | `git branch` muestra `main` y `dev` en ambos; `dev` activa; el commit inicial del FRONT no incluye `node_modules` ni `.env*`. |
| T01 | Scaffold API: `package.json` (`"type":"module"`, `engines.node >=24`), scripts de PLAN §9, `tsconfig.json` (noEmit, `allowImportingTsExtensions`, `verbatimModuleSyntax`), `.gitignore`, `.env.example`. Instalar solo deps de PLAN §8. | DEV | EN QA | `npm install` sin errores; `npm run typecheck` pasa; `.env` y `local.db*` ignorados por git; no hay deps fuera de la lista. |
| T02 | `src/config/env.ts`: carga y valida variables con zod (`PORT`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` opcional, `CORS_ORIGIN`, `ORCHESTRATOR` = `noop`). | DEV | EN QA | Sin `TURSO_DATABASE_URL` el proceso termina con mensaje claro y código ≠ 0; con valores válidos exporta objeto tipado. |
| T03 | QA: verificar arranque limpio del scaffold en una copia nueva (clonar `dev`, `npm install`, `npm run typecheck`). | QA | PENDIENTE | Pasos reproducibles anotados en `QA_REPORT.md`; sin rutas absolutas (`grep -rn "D:\\\\\|C:\\\\" src seeds migrations` vacío). |

## Bloque 1 — Base de datos

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T10 | `src/db/client.ts`: cliente único `@libsql/client` con URL y token del env. | DEV | EN QA | Funciona con `file:local.db`; con `TURSO_AUTH_TOKEN` vacío no se envía token. |
| T11 | `src/db/migrate.ts`: runner con tabla `schema_migrations`, aplica `migrations/NNN_*.sql` en orden, cada una en transacción; usable como CLI y como función (tests). | DEV | EN QA | 1ª ejecución aplica todo; 2ª no hace nada; una migración con SQL roto no queda registrada ni deja tablas parciales. |
| T12 | `migrations/001_init.sql` con el esquema exacto de PLAN §3 (CHECKs e índices incluidos). | DEV | EN QA | Insertar `status='FOO'` en agents/tickets/approvals falla; 2 aprobaciones PENDING para el mismo ticket fallan por índice único. |
| T13 | `seeds/seed.ts` idempotente: 4 agentes (ids `sheldon`, `leonard`, `penny`, `raj` con datos de PLAN §3), 3–4 tickets de ejemplo, 1 nota de memoria. | DEV | EN QA | Ejecutar 2 veces deja exactamente 4 agentes; Sheldon `isCto=1`. |
| T14 | Script `db:reset` que borra la BD local y re-ejecuta migrate + seed; se niega si la URL no empieza por `file:`. | DEV | EN QA | Con URL `libsql://...` termina sin borrar nada y con mensaje claro. |
| T15 | QA: probar migrate/seed/reset y CHECKs con `local.db`; documentar en QA_REPORT. | QA | PENDIENTE | Todos los criterios T11–T14 verificados manualmente. |

## Bloque 2 — Núcleo de la API

| ID | Descripción | Responsable | Estado | Criterio de aceptación |
|---|---|---|---|---|
| T20 | `src/app.ts` + `src/server.ts`: Express, `cors` con `CORS_ORIGIN`, JSON body, `GET /api/health` (hace `SELECT 1`). `app.ts` exporta la app sin escuchar. | DEV | EN QA | `curl localhost:4000/api/health` → `{"ok":true,"db":"up",...}`; petición desde otro origen bloqueada por CORS. |
| T21 | `middleware/errors.ts`: formato de error único de PLAN §5; errores zod → 400 con `details`; rutas inexistentes → 404 JSON; 500 sin stack. | DEV | EN QA | Body inválido devuelve 400 con forma `{error:{code,message,details}}`. |
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
