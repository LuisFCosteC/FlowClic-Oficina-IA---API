# FlowClic Oficina IA — Plan de Arquitectura · Fase 1

> Estado: **APROBADO por el CEO (2026-11-22)**: arranca la implementación.
>
> Decisiones por defecto (vigentes mientras el CEO no diga otra cosa):
> - Dependencias de §8 aprobadas. Cualquier otra requiere preguntar.
> - Añadidos mínimos al FRONT de D6/T76/T77 aprobados (mismos estilos existentes).
> - FRONT usa npm; `bun.lock` se **conserva** hasta que el CEO confirme borrarlo.
> - Repos: `origin` en GitHub (`FlowClic-Oficina-IA---API` y `---FRONT`). Trabajo en `dev`; nada se mergea a `main` sin dictamen del Arquitecto.
>
> **Ampliación 2026-11-22 (CEO):** la **seguridad pasa a ser prioridad 1** (§12) y se añade el **panel de Administración** (§13). El orden de ejecución vigente es el de **§14**. Autenticación y usuarios dejan de estar fuera de alcance.
>
> **⚠ CAMBIO DE STACK 2026-11-22 (CEO): la API pasa a Python + FastAPI, con Swagger.** Manda la **§0**. Donde el resto del documento diga Node, Express, zod, `node:test`, `npm run …` o `node:crypto`, aplica la tabla de equivalencias de §0.4. El esquema SQL, los endpoints, el contrato JSON, el SSE, las reglas de negocio y la seguridad **no cambian**. La implementación en Node queda archivada en la rama `archive/node-express`.

---

## 0. Stack de la API: Python + FastAPI (vigente)

### 0.1 Versiones y entorno
- **Python 3.13** en un entorno virtual `.venv` dentro de la carpeta API (ignorado por git).
  - Motivo: el SDK oficial de Turso para Python (`libsql` 0.1.11) solo trae binarios para Windows en **3.12 y 3.13**. Con la 3.14 que hay instalada no se puede instalar sin compilar Rust (verificado el 2026-11-22).
  - En Windows se usa el lanzador `py` (`py -3.13`), no `python`, porque `python` apunta al acceso directo de la Microsoft Store.
- Dependencias con versiones **exactas** en `requirements.txt` (ejecución) y `requirements-dev.txt` (desarrollo), gestionadas con `pip`. No se usan herramientas extra (uv/poetry).

### 0.2 Dependencias (todas ligeras; requieren el OK del CEO)
| Paquete | Para qué |
|---|---|
| `fastapi` | Framework. Genera **OpenAPI** y la documentación interactiva |
| `uvicorn[standard]` | Servidor ASGI (con `--reload` en desarrollo) |
| `pydantic-settings` | Leer y validar el `.env` (sustituye a zod/env.ts) |
| `libsql` | Cliente oficial de libSQL/Turso (local `file:` y remoto `libsql://`) |
| `cryptography` | AES-256-GCM para cifrar el secreto MFA (la biblioteca estándar de Python no trae AES) |
| *dev:* `pytest`, `httpx` | Tests con `TestClient` de FastAPI |
| *dev:* `pip-audit` | Auditar vulnerabilidades de dependencias (riesgo #9) |
| *dev:* `ruff`, `mypy` | Lint y chequeo de tipos (sustituyen a `tsc --noEmit`) |

Biblioteca estándar en lugar de paquetes: `hashlib.scrypt` (contraseñas), `hmac` + `base64` (TOTP), `secrets` (tokens), `sqlite3` (solo en el adaptador de respaldo, §0.3).

### 0.3 Acceso a datos: adaptador propio
`app/db/database.py` define una **interfaz `Database`**: `execute`, `fetch_all`, `fetch_one`, `transaction()` (context manager) y `close`. Implementaciones:
1. **`LibsqlDatabase`** (por defecto): usa `libsql.connect(url, auth_token=...)`. Sirve para `file:` y para Turso.
2. **`SqliteDatabase`** (respaldo, solo para URLs `file:`): biblioteca estándar `sqlite3`, para el caso de que `libsql` falle en algún equipo. Se activa con `DB_DRIVER=sqlite`.

Reglas:
- Ningún repositorio importa `libsql` directamente.
- Todos obtienen la conexión con `get_db()`, que es una dependencia de FastAPI. Así es posible el cambio en caliente de §13.2 (`swap_db`).
- Las rutas son `def` síncronas: FastAPI las ejecuta en un pool de hilos, porque `libsql` es síncrono.
- **La primera tarea (P00) verifica esto en Windows** antes de construir nada encima.

Las migraciones SQL (`migrations/NNN_*.sql`) **se conservan tal cual**: el SQL es el mismo.

### 0.4 Equivalencias Node → Python (aplican a todas las tareas)
| En el plan o en las tareas pone… | En Python significa… |
|---|---|
| Express, `app.ts`/`server.ts` | `app/main.py` con `create_app()` y `uvicorn` |
| middleware de Express | middleware de Starlette y **dependencias** de FastAPI (`Depends`) |
| zod `.strict()` | modelos **Pydantic v2** con `model_config = ConfigDict(extra='forbid')`, longitudes con `Field(max_length=…)` |
| `requireAuth` / `requireRole(...)` / `requireRecentMfa` | dependencias `current_user`, `require_role(...)` y `require_recent_mfa` |
| DTOs en camelCase | modelos con `alias_generator=to_camel` y `populate_by_name=True`; la API **responde en camelCase** (el contrato con el front no cambia) |
| `node:test` + `fetch` | `pytest` + `fastapi.testclient.TestClient`, con BD temporal en `tmp_path` |
| `node:crypto` scrypt / randomBytes / AES-GCM / HMAC | `hashlib.scrypt` / `secrets.token_bytes` / `cryptography` AESGCM / `hmac` |
| EventEmitter (`events/bus.ts`) | `app/events/bus.py`: bus en memoria con suscriptores; el SSE usa una `asyncio.Queue` por cliente |
| SSE en Express | `StreamingResponse(media_type='text/event-stream')` con heartbeat. Sin dependencia extra |
| `npm run X` | comandos de §0.6 |
| `tsc --noEmit` | `ruff check .` + `mypy app` |
| `npm audit` | `pip-audit -r requirements.txt` |
| `scripts/check-secrets.mjs` | `scripts/check_secrets.py` |
| `src/...` | `app/...` |

### 0.5 Estructura
```
FlowClic Oficina IA - API/
├─ docs/                      PLAN.md · TASKS.md · QA_REPORT.md · SECURITY.md · DRP.md
├─ migrations/                001_init.sql, 002_security.sql, 003_admin.sql (SQL sin cambios)
├─ app/
│   ├─ main.py                create_app(): middlewares, routers, OpenAPI, handlers de error
│   ├─ config.py              Settings (pydantic-settings)
│   ├─ db/database.py         interfaz Database + LibsqlDatabase + SqliteDatabase + get_db/swap_db
│   ├─ db/migrate.py          runner (python -m app.db.migrate)
│   ├─ db/seed.py · reset.py · backup.py · restore.py
│   ├─ domain/                enums (StrEnum/Literal) y schemas Pydantic (entrada y salida)
│   ├─ repositories/          SQL parametrizado, sin lógica
│   ├─ services/              reglas (workflow), transacciones, emisión de eventos
│   ├─ routers/               agents, tickets, approvals, memory, snapshot, events (SSE), auth, admin
│   ├─ security/              password.py, sessions.py, totp.py, crypto.py, ratelimit.py, deps.py, audit.py
│   ├─ events/bus.py
│   ├─ orchestrator/          base.py (Protocol Orchestrator, FASE 2), noop.py
│   └─ errors.py              AppError + formato único de error
├─ scripts/                   setup_env.py, admin_create.py, check_secrets.py, install_hooks.py
├─ tests/                     pytest
├─ requirements.txt · requirements-dev.txt · pyproject.toml (config de ruff/mypy/pytest)
├─ .env.example · .gitignore  (.venv/, .env, .env.bak, local.db*, backups/, __pycache__/, .pytest_cache/)
```

### 0.6 Comandos (PowerShell, desde la carpeta API)
| Acción | Comando |
|---|---|
| Crear el entorno (una vez) | `py -3.13 -m venv .venv` |
| Activarlo | `.\.venv\Scripts\Activate.ps1` |
| Instalar | `pip install -r requirements.txt -r requirements-dev.txt` |
| Crear el `.env` con claves aleatorias | `python scripts/setup_env.py` |
| Migrar / sembrar / resetear | `python -m app.db.migrate` · `python -m app.db.seed` · `python -m app.db.reset` |
| Crear tu usuario ADMIN | `python scripts/admin_create.py` |
| Desarrollo | `uvicorn app.main:app --reload --host 127.0.0.1 --port 4000` |
| Tests | `pytest` |
| Lint y tipos | `ruff check .` · `mypy app` |
| Auditoría de dependencias | `pip-audit -r requirements.txt` |
| Backup / restaurar | `python -m app.db.backup` · `python -m app.db.restore <ruta>` |

### 0.7 Documentación de la API (Swagger) (⚠ actualizado: se sirve en `/api/docs` y exige sesión desde S09; ver TASKS "RESPUESTAS (h)", tarea P03)
- **Swagger UI:** `http://localhost:4000/docs` · **ReDoc:** `http://localhost:4000/redoc` · **Esquema:** `http://localhost:4000/openapi.json`.
- Cada router lleva `tags` (Agentes, Tickets, Aprobaciones, Memoria, Tiempo real, Auth, Administración), `summary`, la descripción de errores posibles (`responses={401:…, 403:…, 409:…}`) y ejemplos en los modelos Pydantic.
- La autenticación por cookie se declara como esquema de seguridad `APIKeyCookie(name='fc_session')`. Así se puede hacer login desde Swagger (`POST /api/auth/login`) y probar el resto de endpoints con esa sesión.
- **Seguridad (riesgo #16):** la documentación se controla con `DOCS_ENABLED` (por defecto `true` en `development` y **`false` en `production`**). El esquema se puede ver sin sesión, pero **ningún endpoint funciona sin sesión**: ver la documentación no da acceso a nada.
- La comprobación CSRF de `Origin` (§12.4) acepta `CORS_ORIGIN` **y** el propio origen de la API (`http://localhost:4000`) cuando `DOCS_ENABLED=true`. Si no, Swagger no podría hacer peticiones POST.

### 0.8 Variables nuevas o cambiadas del `.env`
```dotenv
DB_DRIVER=libsql          # libsql | sqlite (respaldo, solo URLs file:)
DOCS_ENABLED=true         # false en producción
API_PUBLIC_ORIGIN=http://localhost:4000
```
(El resto de §9 y §12.5 se mantiene; `ORCHESTRATOR=noop` igual.)
> Alcance: app local (API + FRONT conectado). **Sin agentes IA**: ninguna llamada a modelos, sin orquestador, sin automatización.

---

## 1. Estado actual (lo que se encontró)

### FRONT (`FlowClic Oficina IA - FRONT`)
- Vite 8 + React 19 + TypeScript + Tailwind 4 + Three.js + motion. Exportado de AI Studio.
- **No es repo git.** Tiene `bun.lock` pero `bun` no está instalado en la máquina → se usará **npm**.
- Todo el estado vive en `src/App.tsx` con `useState(INITIAL_*)` sobre datos mock de `src/data/initialData.ts` (13 agentes, 10 tareas, 3 propuestas, 5 modelos, 4 proyectos).
- Módulos: `colmena3d` (oficina 3D = vigilador visual), `cerebro` (cola de aprobaciones + memoria de agentes + router de modelos mock), `kanban` (tablero/lista con crear y mover), `roadmap` (calendario), `CreateAgentModal`.
- Tipos en `src/types/orbis.ts`:
  - `AgentStatus = 'working' | 'waiting_sheldon' | 'idle'` (3 estados; la Fase 1 exige 5).
  - `TaskStage = backlog | in_dev | sheldon_review | ceo_approval | completed`.
  - `TaskPriority = alta | media | baja`.
- Reglas de negocio hoy en el cliente (`App.tsx`): mover tarea cambia el estado del agente; pasar a `ceo_approval` crea propuesta; aprobar ⇒ tarea completada y agente idle; rechazar ⇒ tarea a desarrollo y agente working. **Estas reglas se mueven a la API.**
- `avatarBuilder.ts` usa los ids `'raj'`, `'penny'`, `'bernadette'`, `'beverly'` para elegir apariencia ⇒ **los agentes semilla deben usar ids slug** (`sheldon`, `leonard`, `penny`, `raj`).
- `.env.example` actual solo trae `GEMINI_API_KEY` / `APP_URL` (AI Studio). `.gitignore` ya ignora `.env*` salvo `.env.example`.

### API (`FlowClic Oficina IA - API`)
- Carpeta vacía. **No es repo git.**

### Entorno
- Node **v24.16.0**, npm 11.13. Node 24 trae: `fetch`, `node:test`, `process.loadEnvFile()` / `--env-file`, y ejecución nativa de TypeScript por *type stripping* ⇒ no hacen falta `dotenv`, `tsx`, `nodemon` ni `jest`.

---

## 2. Arquitectura

```
┌──────────────────────────── FRONT (Vite :3000) ────────────────────────────┐
│ Componentes existentes (sin rediseño)                                       │
│   Colmena3DView · CerebroOrbisView · KanbanPipelineView · CreateAgentModal  │
│                 ▲ props (tipos UI de orbis.ts)                               │
│ src/state/useOfficeStore.ts  (useReducer: agents, tickets, approvals)        │
│        ▲ upsert por id                ▲ eventos                              │
│ src/api/client.ts (fetch REST)   src/api/realtime.ts (EventSource SSE)       │
│ src/api/mappers.ts  DTO API ⇄ tipos UI   ·  src/api/types.ts (DTOs)          │
└───────────────┬─────────────────────────────────────▲──────────────────────┘
                │ REST JSON (mutaciones + snapshot)   │ SSE /api/events
┌───────────────▼─────────────────────────────────────┴──────────────────────┐
│                         API Node 24 + Express (:4000)                       │
│ routes/  → validación (zod) → services/ (reglas de negocio, transacciones)  │
│                                   │ emite DomainEvent                       │
│                          events/bus.ts (EventEmitter interno)               │
│                     ┌─────────────┴──────────────┐                          │
│              realtime/sse.ts               orchestrator/ (Fase 2)           │
│              (broadcast a clientes)        NoopOrchestrator (no hace nada)  │
│ repositories/ (SQL puro) → db/client.ts (@libsql/client)                    │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │ TURSO_DATABASE_URL
                    file:local.db (dev)  |  libsql://<db>.turso.io (nube)
```

### Estructura de la API (⚠ OBSOLETA: Node. La vigente está en §0.5)
```
FlowClic Oficina IA - API/
├─ docs/PLAN.md · TASKS.md · QA_REPORT.md
├─ migrations/
│   ├─ 001_init.sql
│   └─ ...                       (NNN_descripcion.sql, solo se añaden, nunca se editan)
├─ seeds/seed.ts                 (idempotente)
├─ src/
│   ├─ server.ts                 (arranque: env → db → migrar? no, solo conectar → app.listen)
│   ├─ app.ts                    (crea Express app; exportable para tests)
│   ├─ config/env.ts             (lee y valida variables con zod; falla rápido)
│   ├─ db/client.ts              (createClient una sola vez)
│   ├─ db/migrate.ts             (runner de migraciones; CLI y función)
│   ├─ domain/types.ts           (enums como uniones de string + DTOs)
│   ├─ domain/schemas.ts         (zod: bodies de entrada)
│   ├─ repositories/*.repo.ts    (agents, tickets, ticketEvents, approvals, memory)
│   ├─ services/*.service.ts     (agents, tickets, approvals, memory, workflow)
│   ├─ routes/*.routes.ts
│   ├─ events/bus.ts             (DomainEvent tipado)
│   ├─ realtime/sse.ts           (GET /api/events, heartbeat)
│   ├─ orchestrator/Orchestrator.ts      (INTERFAZ Fase 2, sin implementar)
│   ├─ orchestrator/NoopOrchestrator.ts  (implementación vacía, registrada por defecto)
│   └─ middleware/errors.ts      (formato de error único)
├─ test/*.test.ts                (node:test, BD temporal por archivo)
├─ .env.example · .env (ignorado) · .gitignore
├─ package.json · tsconfig.json
```

Capas: **routes** (HTTP + validación) → **services** (reglas, transacciones, emite eventos) → **repositories** (SQL). Las rutas nunca escriben SQL; los repositorios nunca emiten eventos.

---

## 3. Base de datos (libSQL / Turso)

### Conexión
- `@libsql/client` → `createClient({ url: TURSO_DATABASE_URL, authToken: TURSO_AUTH_TOKEN || undefined })`.
- Dev: `TURSO_DATABASE_URL=file:local.db` (ruta **relativa** al cwd del proyecto), sin token.
- Nube: `TURSO_DATABASE_URL=libsql://<db>-<org>.turso.io` + `TURSO_AUTH_TOKEN`. **Mismo código.**
- Tests: archivo temporal en `os.tmpdir()` (nunca `local.db`).

### Convenciones
- IDs `TEXT`. Semillas usan slug (`sheldon`); nuevas filas usan `crypto.randomUUID()`.
- Fechas `TEXT` ISO-8601 UTC (`2026-11-22T19:30:00.000Z`), generadas en la app (no `CURRENT_TIMESTAMP`, para formato uniforme).
- Booleanos `INTEGER 0/1`. JSON en `TEXT` (validado en la app).
- Enumerados con `CHECK (... IN (...))`.
- **No se depende de `ON DELETE CASCADE`** ni de `PRAGMA foreign_keys` (en Turso remoto cada petición HTTP puede ser otra conexión). Se declaran `REFERENCES` como documentación y la integridad la hacen los services dentro de transacciones.
- Toda escritura múltiple (p. ej. mover ticket + evento + agente + aprobación) usa `client.transaction('write')` o `client.batch([...], 'write')`.

### Migraciones
- Archivos `migrations/NNN_nombre.sql`, aplicados en orden.
- Tabla de control:
  ```sql
  CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
  );
  ```
- `npm run db:migrate`: aplica pendientes, cada una en su transacción (falla ⇒ rollback y no se registra). Re-ejecutar no hace nada.
- **Una migración aplicada nunca se edita**; los cambios van en una nueva.

### Esquema (`001_init.sql`)

```sql
CREATE TABLE agents (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,                 -- "Sheldon"
  character     TEXT NOT NULL,                 -- personaje: "Sheldon Cooper"
  role          TEXT NOT NULL,                 -- "CTO"
  status        TEXT NOT NULL DEFAULT 'IDLE'
                CHECK (status IN ('IDLE','WORKING','REVIEW','BLOCKED','SLEEP_QUOTA')),
  avatar        TEXT NOT NULL DEFAULT '{}',    -- JSON: {"color":"#F59E0B","glasses":false,"hairStyle":"parted"}
  system_prompt TEXT NOT NULL DEFAULT '',      -- se guarda ya; se usará en Fase 2
  model_tier    TEXT NOT NULL DEFAULT 'sonnet_pro'
                CHECK (model_tier IN ('opus_pro','sonnet_pro','haiku_flash')),
  is_cto        INTEGER NOT NULL DEFAULT 0,
  current_task  TEXT,                          -- texto libre mostrado en el vigilador
  project       TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  archived_at   TEXT                           -- borrado lógico (preserva historial)
);
CREATE UNIQUE INDEX ux_agents_name_active ON agents(name) WHERE archived_at IS NULL;

CREATE TABLE tickets (
  id                 TEXT PRIMARY KEY,
  title              TEXT NOT NULL,
  description        TEXT NOT NULL DEFAULT '',
  status             TEXT NOT NULL DEFAULT 'BACKLOG'
                     CHECK (status IN ('BACKLOG','IN_PROGRESS','REVIEW','AWAITING_APPROVAL','DONE')),
  priority           TEXT NOT NULL DEFAULT 'MEDIUM'
                     CHECK (priority IN ('HIGH','MEDIUM','LOW')),
  assigned_agent_id  TEXT REFERENCES agents(id),
  project            TEXT,
  model_tier         TEXT NOT NULL DEFAULT 'sonnet_pro'
                     CHECK (model_tier IN ('opus_pro','sonnet_pro','haiku_flash')),
  estimated_cost_usd REAL NOT NULL DEFAULT 0,
  position           INTEGER NOT NULL DEFAULT 0,   -- orden dentro de la columna
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);
CREATE INDEX ix_tickets_status ON tickets(status);
CREATE INDEX ix_tickets_agent  ON tickets(assigned_agent_id);

CREATE TABLE ticket_events (
  id         TEXT PRIMARY KEY,
  ticket_id  TEXT NOT NULL REFERENCES tickets(id),
  type       TEXT NOT NULL CHECK (type IN (
               'CREATED','UPDATED','STATUS_CHANGED','ASSIGNED','CONTINUED',
               'APPROVAL_REQUESTED','APPROVAL_DECIDED','APPROVAL_CANCELLED','DELETED')),
  from_value TEXT,
  to_value   TEXT,
  actor      TEXT NOT NULL DEFAULT 'human',  -- Fase 1 siempre 'human'; Fase 2: id de agente u 'orchestrator'
  payload    TEXT NOT NULL DEFAULT '{}',     -- JSON con detalle (campos cambiados, nota, etc.)
  created_at TEXT NOT NULL
);
CREATE INDEX ix_ticket_events_ticket ON ticket_events(ticket_id, created_at);

CREATE TABLE approvals (
  id               TEXT PRIMARY KEY,
  ticket_id        TEXT REFERENCES tickets(id),   -- NULL = compuerta genérica
  agent_id         TEXT REFERENCES agents(id),    -- quién solicita
  title            TEXT NOT NULL,
  category         TEXT NOT NULL DEFAULT 'Arquitectura'
                   CHECK (category IN ('Arquitectura','Despliegue','Seguridad','Datos')),
  summary          TEXT NOT NULL DEFAULT '',
  reviewer_note    TEXT NOT NULL DEFAULT '',      -- "nota de Sheldon"
  estimated_tokens INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
  decision_note    TEXT,
  decided_by       TEXT,                          -- 'human' en Fase 1
  requested_at     TEXT NOT NULL,
  decided_at       TEXT
);
CREATE INDEX ix_approvals_status ON approvals(status);
-- Una sola aprobación PENDING por ticket:
CREATE UNIQUE INDEX ux_approvals_pending_ticket ON approvals(ticket_id) WHERE status = 'PENDING' AND ticket_id IS NOT NULL;

CREATE TABLE project_memory (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('NOTE','DECISION')),
  title      TEXT NOT NULL,
  content    TEXT NOT NULL DEFAULT '',
  project    TEXT,
  ticket_id  TEXT REFERENCES tickets(id),
  author     TEXT NOT NULL DEFAULT 'human',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### Semilla (`npm run db:seed`, idempotente con `INSERT OR IGNORE`)
| id | name | character | role | status | avatar | is_cto |
|---|---|---|---|---|---|---|
| sheldon | Sheldon | Sheldon Cooper | CTO | IDLE | `{"color":"#F59E0B","hairStyle":"parted"}` | 1 |
| leonard | Leonard | Leonard Hofstadter | Senior Full-Stack | IDLE | `{"color":"#38BDF8","glasses":true,"hairStyle":"short"}` | 0 |
| penny | Penny | Penny | Frontend web/móvil | IDLE | `{"color":"#EC4899","hairStyle":"long"}` | 0 |
| raj | Raj | Rajesh Koothrappali | QA | IDLE | `{"color":"#6366F1","hairStyle":"short"}` | 0 |

Más 3–4 tickets de ejemplo (uno por columna activa) y 1 nota en `project_memory`. Los agentes nuevos se crean desde la app (no hay listas fijas en código).

---

## 4. Reglas de negocio (viven en `services/workflow.service.ts`)

Las mismas que hoy hace `App.tsx`, ahora en el servidor y en **una transacción**:

| Acción | Efecto en ticket | Efecto en agente asignado | Aprobación | Eventos |
|---|---|---|---|---|
| Crear ticket | status dado (def. BACKLOG) | aplica regla R1 según status | si status=AWAITING_APPROVAL ⇒ crear PENDING | CREATED |
| Mover a IN_PROGRESS | status | → WORKING (R1) | cancela PENDING si había | STATUS_CHANGED |
| Mover a REVIEW / AWAITING_APPROVAL | status | → REVIEW (R1) | AWAITING_APPROVAL ⇒ crea PENDING si no existe | STATUS_CHANGED (+APPROVAL_REQUESTED) |
| Mover a BACKLOG / DONE | status | → IDLE **solo si** no tiene otro ticket IN_PROGRESS/REVIEW/AWAITING_APPROVAL (R1) | cancela PENDING si había | STATUS_CHANGED |
| Reasignar | assigned_agent_id | agente nuevo: R1; agente anterior: recalcula IDLE | — | ASSIGNED |
| **Continuar** (`POST /tickets/:id/continue`) | → IN_PROGRESS (permitido desde BACKLOG, IN_PROGRESS, REVIEW; 409 en AWAITING_APPROVAL y DONE; 422 sin agente) | → WORKING (incluso si estaba BLOCKED/SLEEP_QUOTA: es decisión humana explícita) | — | CONTINUED; llama `orchestrator.onTicketContinued` |
| Aprobar | → DONE | R1 (IDLE si no tiene más) | APPROVED, decided_at | APPROVAL_DECIDED |
| Rechazar | → IN_PROGRESS (devuelta) | → WORKING | REJECTED | APPROVAL_DECIDED |
| Cambio manual de estado de agente | — | cualquier estado → cualquier estado | — | evento SSE `agent.updated` |

**R1 – Protección de estados manuales:** las reglas automáticas **no tocan** agentes en `BLOCKED` o `SLEEP_QUOTA`; esos solo cambian por acción manual o por "Continuar". Decidir una aprobación ya decidida ⇒ 409.

`current_task` del agente: al pasar a WORKING por un ticket se guarda el título del ticket; al pasar a IDLE se pone `null`.

---

## 5. Endpoints REST (prefijo `/api`, JSON, camelCase)

### Salud
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` | `{ ok: true, db: "up", version }` (hace `SELECT 1`) |

### Agentes
| Método | Ruta | Body / Query | Respuesta |
|---|---|---|---|
| GET | `/api/agents` | `?includeArchived=true` | `Agent[]` |
| GET | `/api/agents/:id` | — | `Agent` / 404 |
| POST | `/api/agents` | `AgentCreate` | 201 `Agent` |
| PATCH | `/api/agents/:id` | `AgentUpdate` (parcial, sin `status`) | `Agent` |
| PATCH | `/api/agents/:id/status` | `{ status: AgentStatus, currentTask?: string }` | `Agent` |
| DELETE | `/api/agents/:id` | — | 204 (archiva). 409 si tiene tickets no DONE o aprobaciones PENDING |

### Tickets
| Método | Ruta | Body / Query | Respuesta |
|---|---|---|---|
| GET | `/api/tickets` | `?status=&agentId=&project=` | `Ticket[]` (orden: status, position, updatedAt desc) |
| GET | `/api/tickets/:id` | — | `Ticket` |
| POST | `/api/tickets` | `TicketCreate` | 201 `Ticket` |
| PATCH | `/api/tickets/:id` | `TicketUpdate` (title, description, priority, project, modelTier, estimatedCostUsd, position) | `Ticket` |
| PATCH | `/api/tickets/:id/status` | `{ status: TicketStatus }` | `Ticket` (aplica reglas §4) |
| PATCH | `/api/tickets/:id/assign` | `{ agentId: string \| null }` | `Ticket` |
| POST | `/api/tickets/:id/continue` | `{ note?: string }` | `Ticket` |
| DELETE | `/api/tickets/:id` | — | 204 (cancela aprobación PENDING; conserva eventos con tipo DELETED) |
| GET | `/api/tickets/:id/events` | — | `TicketEvent[]` (cronológico) |

### Aprobaciones
| Método | Ruta | Body / Query | Respuesta |
|---|---|---|---|
| GET | `/api/approvals` | `?status=PENDING` | `Approval[]` (recientes primero) |
| GET | `/api/approvals/:id` | — | `Approval` |
| POST | `/api/approvals` | `ApprovalCreate` (compuerta manual; `ticketId` opcional) | 201 `Approval` |
| PATCH | `/api/approvals/:id` | edición de title/summary/reviewerNote/category mientras PENDING | `Approval` |
| POST | `/api/approvals/:id/decision` | `{ decision: 'APPROVED' \| 'REJECTED', note?: string }` | `Approval` (aplica reglas §4) |
| DELETE | `/api/approvals/:id` | — | 204 (solo si PENDING ⇒ queda CANCELLED; si no, 409) |

### Memoria del proyecto (solo API en Fase 1; sin UI)
| Método | Ruta |
|---|---|
| GET | `/api/memory?kind=&project=` |
| POST | `/api/memory` |
| PATCH | `/api/memory/:id` |
| DELETE | `/api/memory/:id` |

### Snapshot y tiempo real
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/snapshot` | `{ agents, tickets, approvals, serverTime }` — carga inicial del front en 1 petición |
| GET | `/api/events` | **SSE** (`text/event-stream`). Heartbeat `: ping` cada 25 s |

### Formato de error (único)
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "status inválido", "details": [...] } }
```
Códigos: `VALIDATION_ERROR` 400 · `NOT_FOUND` 404 · `CONFLICT` 409 · `UNPROCESSABLE` 422 · `INTERNAL` 500 (sin stack en la respuesta).

---

## 6. Contrato de datos FRONT ⇄ API

### DTOs (JSON de la API, `src/domain/types.ts` en API y copia en `src/api/types.ts` del FRONT)
```ts
type AgentStatus  = 'IDLE' | 'WORKING' | 'REVIEW' | 'BLOCKED' | 'SLEEP_QUOTA';
type TicketStatus = 'BACKLOG' | 'IN_PROGRESS' | 'REVIEW' | 'AWAITING_APPROVAL' | 'DONE';
type Priority     = 'HIGH' | 'MEDIUM' | 'LOW';
type ModelTier    = 'opus_pro' | 'sonnet_pro' | 'haiku_flash';
type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

interface AgentAvatar { color: string; glasses?: boolean; hairStyle?: 'short'|'long'|'curly'|'bun'|'parted' }

interface Agent {
  id: string; name: string; character: string; role: string;
  status: AgentStatus; avatar: AgentAvatar;
  systemPrompt: string; modelTier: ModelTier; isCto: boolean;
  currentTask: string | null; project: string | null;
  createdAt: string; updatedAt: string; archivedAt: string | null;
}
type AgentCreate = Pick<Agent,'name'|'role'> & Partial<Pick<Agent,
  'character'|'status'|'avatar'|'systemPrompt'|'modelTier'|'isCto'|'project'|'currentTask'>>;

interface Ticket {
  id: string; title: string; description: string;
  status: TicketStatus; priority: Priority;
  assignedAgentId: string | null; project: string | null;
  modelTier: ModelTier; estimatedCostUsd: number; position: number;
  createdAt: string; updatedAt: string;
}
type TicketCreate = Pick<Ticket,'title'> & Partial<Omit<Ticket,'id'|'createdAt'|'updatedAt'|'position'>>;

interface TicketEvent {
  id: string; ticketId: string;
  type: 'CREATED'|'UPDATED'|'STATUS_CHANGED'|'ASSIGNED'|'CONTINUED'
      |'APPROVAL_REQUESTED'|'APPROVAL_DECIDED'|'APPROVAL_CANCELLED'|'DELETED';
  fromValue: string | null; toValue: string | null;
  actor: string; payload: Record<string, unknown>; createdAt: string;
}

interface Approval {
  id: string; ticketId: string | null; agentId: string | null;
  title: string; category: 'Arquitectura'|'Despliegue'|'Seguridad'|'Datos';
  summary: string; reviewerNote: string; estimatedTokens: number;
  status: ApprovalStatus; decisionNote: string | null; decidedBy: string | null;
  requestedAt: string; decidedAt: string | null;
}

interface MemoryEntry {
  id: string; kind: 'NOTE'|'DECISION'; title: string; content: string;
  project: string | null; ticketId: string | null; author: string;
  createdAt: string; updatedAt: string;
}
```

### Eventos SSE
Cada mensaje: `event: <tipo>` + `data: <JSON>` + `id: <secuencia>`.
| `event` | `data` |
|---|---|
| `agent.created` / `agent.updated` | `Agent` |
| `agent.archived` | `{ id }` |
| `ticket.created` / `ticket.updated` | `Ticket` |
| `ticket.deleted` | `{ id }` |
| `ticket.event` | `TicketEvent` |
| `approval.created` / `approval.updated` | `Approval` |
| `memory.created` / `memory.updated` / `memory.deleted` | `MemoryEntry` / `{ id }` |

El front aplica **upsert por id** (idempotente: si recibe la misma entidad por REST y por SSE no pasa nada). Al reconectar (`EventSource.onopen` tras error) vuelve a pedir `/api/snapshot`. Sin reenvío de eventos perdidos en Fase 1 (`Last-Event-ID` se ignora; el snapshot cubre la brecha).

### Mapeo API ⇄ UI (`src/api/mappers.ts` del FRONT; los componentes **no cambian sus props**)

| API | UI (`orbis.ts`) |
|---|---|
| Agent `IDLE` / `WORKING` / `REVIEW` | `idle` / `working` / `waiting_sheldon` |
| Agent `BLOCKED` / `SLEEP_QUOTA` | **nuevos** `blocked` / `sleep_quota` (ver §8-D6) |
| Ticket `BACKLOG` / `IN_PROGRESS` / `REVIEW` / `AWAITING_APPROVAL` / `DONE` | `backlog` / `in_dev` / `sheldon_review` / `ceo_approval` / `completed` |
| Priority `HIGH` / `MEDIUM` / `LOW` | `alta` / `media` / `baja` |
| `agent.role` | `Agent.title` |
| `agent.avatar.color/glasses/hairStyle` | `Agent.color/glasses/hairStyle` |
| `agent.isCto` | `Agent.isCTO` |
| `agent.currentTask ?? 'Memoria purgada — En espera de asignación'` | `Agent.currentTask` |
| — (derivado) | `Agent.ramKb` = 0 si idle/sleep_quota, si no valor determinista por nombre (misma fórmula que hoy en `App.tsx`) |
| — (derivado) | `Agent.tokensSavedToday` = 0 (no hay IA en Fase 1) |
| `ticket.assignedAgentId ?? ''` | `KanbanTask.assigneeId` |
| `ticket.updatedAt` (ISO) | `KanbanTask.updatedAt` formateado relativo ("Hace 4 min", "Hoy 14:20") |
| `Approval` + agente + ticket | `SheldonProposal` (`agentName` y `project` se resuelven en el mapper; `summary`, `sheldonNote ← reviewerNote`, `timestamp ← requestedAt` relativo, `status` en minúsculas; `CANCELLED` se oculta) |

Quedan **mock locales** (no tocan la API en Fase 1): modelos/router del Cerebro, `RoadmapCalendarView` y proyectos (`PROJECT_NAMES` sigue siendo la lista del selector de proyecto).

---

## 7. Punto de enganche Fase 2 (solo interfaz, sin implementar)

`src/orchestrator/Orchestrator.ts`:
```ts
/**
 * FASE 2 — Punto de conexión del orquestador de agentes IA.
 * En Fase 1 solo existe NoopOrchestrator. NO llamar a modelos aquí todavía.
 * Se suscribe al bus de dominio; nunca escribe en la BD directamente:
 * actuará llamando a los mismos services que usa la API REST (actor = id de agente).
 */
export interface Orchestrator {
  onTicketCreated(ticket: Ticket): Promise<void>;
  onTicketStatusChanged(ticket: Ticket, from: TicketStatus): Promise<void>;
  onTicketContinued(ticket: Ticket, note?: string): Promise<void>;
  onApprovalDecided(approval: Approval): Promise<void>;
  onAgentStatusChanged(agent: Agent, from: AgentStatus): Promise<void>;
}
```
- `NoopOrchestrator` implementa todo con `async () => {}`.
- Registro en `server.ts` según `ORCHESTRATOR=noop` (único valor válido en Fase 1).
- Errores del orquestador se registran en log y **nunca** rompen la petición HTTP.
- La columna `actor` de `ticket_events`, `system_prompt`/`model_tier` de agentes y el estado `SLEEP_QUOTA` ya quedan listos para la Fase 2.

---

## 8. Decisiones técnicas
> ⚠ D1, D2, D3 y D11, y la lista de dependencias de esta sección, quedan **sustituidas por §0** (Python + FastAPI). El resto de decisiones sigue vigente.

| # | Decisión | Motivo |
|---|---|---|
| D1 | **Node 24 + TypeScript ejecutado nativamente** (type stripping, `node --watch src/server.ts`). `tsc --noEmit` solo para chequeo. | Mismo lenguaje que el front, sin `tsx`/build step. Regla: usar `import type`, extensiones `.ts` en imports, nada de `enum`/`namespace` (no soportados por type stripping). |
| D2 | **Express 4** + `cors` | Conocido, ligero, suficiente. |
| D3 | **zod** para validar bodies y env | Ligero, mensajes claros, sin codegen. |
| D4 | **SSE** en vez de WebSocket | Flujo servidor→cliente es lo único necesario (las mutaciones van por REST); nativo en navegador (`EventSource`) y en Express; cero dependencias; reconexión automática. |
| D5 | **SQL a mano + repositorios**, sin ORM | Esquema pequeño; `@libsql/client` es la única capa; misma compatibilidad local/Turso garantizada. |
| D6 | El FRONT amplía `AgentStatus` con `blocked` y `sleep_quota` (+ entradas en `STATUS_META` y `STATUS_HEX`). En 3D: `blocked` → zona de pizarra (revisión), `sleep_quota` → zona apartamento (lounge). En los paneles de cambio manual se añaden 2 botones con **el mismo estilo existente**. | Requisito de 5 estados sin rediseñar; se reutilizan zonas y estilos ya existentes. |
| D7 | Reglas de negocio en el servidor, front "tonto" | Coherencia multi-pestaña y base para el orquestador. |
| D8 | Sin actualizaciones optimistas; el front aplica la respuesta REST y los eventos SSE (upsert) | Simplicidad; latencia local despreciable. |
| D9 | Borrado lógico de agentes (`archived_at`) | Conservar historial de tickets/eventos. |
| D10 | `VITE_API_URL` obligatoria en el front (sin URL de respaldo en código); si falta, error claro en consola y estado de error | Cumple "URL en variable de entorno" y "sin rutas absolutas". |
| D11 | Tests con `node:test` + `fetch` contra la app levantada en puerto efímero y BD temporal | Sin jest/supertest. |
| D12 | Front se gestiona con **npm** (bun no instalado); se genera `package-lock.json` y se borra `bun.lock` solo con OK del CEO | Evitar dos lockfiles divergentes. |
| D13 | No se tocan dependencias de AI Studio del front (`@google/genai`, `express`, `GEMINI_API_KEY`) en Fase 1 | Fuera de alcance; limpieza propuesta para después. |

### Dependencias nuevas (ninguna pesada — confirmar)
- **API runtime:** `@libsql/client`, `express`, `cors`, `zod`.
- **API dev:** `typescript`, `@types/express`, `@types/cors`, `@types/node`.
- **FRONT:** ninguna nueva.

---

## 9. Puertos, variables y comandos
> ⚠ Los scripts `npm` de la API quedan **sustituidos por §0.6**. Los puertos (API 4000, FRONT 3000), las variables y los comandos del FRONT siguen vigentes.

### Puertos
| Servicio | Puerto |
|---|---|
| FRONT (Vite) | **3000** (ya configurado en `package.json`) |
| API | **4000** (`PORT`) |

### API `.env.example`
```dotenv
PORT=4000
# Local: archivo relativo al proyecto. Nube: libsql://<db>-<org>.turso.io
TURSO_DATABASE_URL=file:local.db
# Vacío en local. Obligatorio con Turso en la nube.
TURSO_AUTH_TOKEN=
# Origen permitido por CORS (URL del front)
CORS_ORIGIN=http://localhost:3000
# Fase 2: único valor válido en Fase 1
ORCHESTRATOR=noop
```
`.gitignore` API: `node_modules/`, `.env`, `local.db*`, `*.log`, `coverage/`.

### FRONT `.env.example` (se añade)
```dotenv
VITE_API_URL=http://localhost:4000
```

### Scripts API (`package.json`)
| Script | Comando |
|---|---|
| `dev` | `node --env-file-if-exists=.env --watch src/server.ts` |
| `start` | `node --env-file-if-exists=.env src/server.ts` |
| `db:migrate` | `node --env-file-if-exists=.env src/db/migrate.ts` |
| `db:seed` | `node --env-file-if-exists=.env seeds/seed.ts` |
| `db:reset` | borra `local.db` y ejecuta migrate + seed. **Se niega** si la URL no empieza por `file:` |
| `typecheck` | `tsc --noEmit` |
| `test` | `node --test test/` |

### Arranque desde cero
```bash
# Terminal 1 — API
cd "FlowClic Oficina IA - API"
cp .env.example .env
npm install
npm run db:migrate
npm run db:seed
npm run dev            # http://localhost:4000/api/health

# Terminal 2 — FRONT
cd "FlowClic Oficina IA - FRONT"
cp .env.example .env.local   # contiene VITE_API_URL
npm install
npm run dev            # http://localhost:3000
```
Pasar a Turso nube: cambiar `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` en `.env`, `npm run db:migrate && npm run db:seed`. Ningún cambio de código.

---

## 10. Git y flujo de trabajo
- **Ninguna de las dos carpetas es repo git.** Propuesta (requiere OK): `git init` en cada una, commit inicial en `main` con el estado actual, y trabajo en rama **`dev`**.
- Flujo de tareas: DEV → `EN QA` → QA verifica criterio de aceptación → `HECHO` o `DEVUELTA` (con nota en `docs/QA_REPORT.md`). Dudas: el DEV marca la tarea con **"PREGUNTA PARA ARQUITECTO"** en `TASKS.md`.
- Merge `dev` → `main` solo con revisión del Arquitecto.

## 11. Fuera de alcance (Fase 1)
Llamadas a modelos IA, orquestador real, automatizaciones/colas, roadmap/proyectos en BD, router de modelos real, UI de memoria del proyecto, UI de historial de ticket (el endpoint existe), despliegue, pagos.
> **Cambio 2026-11-22:** autenticación y usuarios **entran** en la Fase 1 (ver §12).

---

## 12. Seguridad (PRIORIDAD 1, añadida 2026-11-22 por el CEO)

Principio: **ningún dato ni acción sin sesión válida y rol suficiente**, todo verificado en el servidor. El front solo oculta botones, nunca protege nada.
**Implementación en Python (§0):** `hashlib.scrypt`, `secrets`, `hmac` (biblioteca estándar) y `cryptography` (AES-256-GCM).

### 12.1 Matriz de riesgos del CEO → medida → tarea
| # | Riesgo | Medida en este proyecto | Tareas |
|---|---|---|---|
| 1 | Secretos en GitHub | `.env`, `local.db*`, `backups/` en `.gitignore`; hook `pre-commit` (script propio, sin deps) que bloquea patrones de secretos; GitHub *secret scanning + push protection* activado; repos **privados**. Historial auditado el 2026-11-22: limpio. | S11 |
| 2 | Secretos en el front | El front **no tiene secretos**: solo `VITE_API_URL` (todo `VITE_*` es público por diseño). Se elimina `GEMINI_API_KEY` del `.env.example` del front y la dependencia `@google/genai` (no se usa en `src/`). El token de BD nunca sale de la API (ni en el panel: campo solo escritura). | F05, A05 |
| 3 | BD expuesta / sin reglas | El navegador **nunca** habla con la BD. Archivo local no servido por HTTP. Turso solo con token (preferible token con alcance a esa BD y rotación). libSQL no tiene RLS ⇒ **las reglas de acceso viven en la API** (middleware de rol por ruta, §12.3). API escucha en `HOST=127.0.0.1` por defecto. | S01, S09 |
| 4 | IDOR / BOLA | Modelo de un solo inquilino: todos los usuarios ven la misma oficina, pero **cada ruta exige un rol** (§12.3). Recursos "propios" (sesiones, perfil, MFA) siempre se resuelven desde la sesión (`/api/auth/me/...`), **nunca** con un id de usuario en la URL. Ids UUID. Tests de acceso cruzado obligatorios. | S09, QS3 |
| 5 | Endpoints sin auth | `requireAuth` global; lista blanca explícita de rutas públicas: `POST /api/auth/login`, `POST /api/auth/mfa/verify` (con token de login a medio camino) y `GET /api/health` (que solo responde `{ok}`). SSE también exige sesión. | S09 |
| 6 | Pagos sin validar | **No aplica**: no hay pagos. Regla para el futuro: montos solo calculados en el servidor y webhooks con firma verificada. | — |
| 7 | Login sin rate limit | Limitador en memoria por IP (10 intentos / 15 min) **y** bloqueo por cuenta (5 fallos ⇒ 15 min, progresivo); mismo mensaje genérico para usuario inexistente o clave errónea; comparación en tiempo constante y hash ficticio para usuarios inexistentes (evita enumerar usuarios por tiempo de respuesta). También en verificación MFA. | S07 |
| 8 | Inputs sin validar (SQLi/XSS) | zod `.strict()` en **todo** body/query/param con longitudes máximas; SQL **solo parametrizado** (prohibido interpolar en `execute`); límite de body 100 kB; React escapa por defecto y queda **prohibido** `dangerouslySetInnerHTML`; cabeceras de seguridad (CSP `default-src 'none'` en la API, `nosniff`, `frame-ancestors 'none'`, `Referrer-Policy`). | S01, S09, QS3 |
| 9 | Dependencias vulnerables | `npm audit --audit-level=high` en ambos repos como paso de QA y antes de cada merge; `.github/dependabot.yml`; lockfiles versionados; se quitan dependencias sin uso del front (`@google/genai`, `express`, `dotenv`). | S11, F05 |
| 10 | Stack traces en errores | Middleware de errores ya definido (500 sin stack, sin rutas); `x-powered-by` desactivado; logs internos con `requestId`, sin secretos ni contraseñas. | S01 |
| 11 | Contraseñas en texto plano | `scrypt` (N=2^17, r=8, p=1, sal aleatoria de 16 B por usuario), formato `scrypt$N$r$p$salt$hash` para poder subir parámetros después. Política: mínimo 12 caracteres. | S04 |
| 12 | Sin backups / DRP | `npm run db:backup` (local: `VACUUM INTO backups/…`; remoto: exportación JSON de todas las tablas); backup automático programado por la API (`BACKUP_INTERVAL_HOURS`, retención `BACKUP_KEEP`); `npm run db:restore <archivo>`; `docs/DRP.md` con RPO 24 h / RTO 1 h y prueba de restauración como tarea de QA. Turso añade su recuperación a un punto en el tiempo. | S12, QS4 |
| 13 | Cuenta admin genérica | **No existe usuario por defecto ni clave en la semilla.** Cada persona tiene su usuario. El primer ADMIN se crea con `npm run admin:create` (pide email y contraseña por consola). Los demás se crean desde Administración → Usuarios. Auditoría de acciones por usuario. | S05, S10, A07 |
| 14 | Sin MFA | TOTP (RFC 6238, apps tipo Google Authenticator) **obligatorio para ADMIN** y opcional para el resto. Secreto cifrado en BD con AES-256-GCM (`APP_ENCRYPTION_KEY`). Las acciones críticas (cambiar URL de BD, usuarios y roles) exigen **reautenticación reciente** (MFA en los últimos 10 min). | S08 |
| 15 | Credenciales hardcodeadas | Todo secreto viene del `.env`; `npm run setup` genera `.env` a partir de `.env.example` con claves aleatorias (`APP_ENCRYPTION_KEY`, `SESSION_SECRET`). El hook S11 y QA buscan cadenas sospechosas. | S02, S11 |
| 16 | Panel admin público | `/api/admin/*` exige rol ADMIN, MFA activo y reautenticación reciente para lo crítico. La vista "Administración" del front solo se muestra a ADMIN, pero la protección real está en la API. | S09, A01–A07 |
| 17 | Sesiones eternas | Token opaco de 32 B aleatorios en cookie `HttpOnly; SameSite=Strict; Path=/api` (y `Secure` fuera de localhost). En BD solo se guarda su **SHA-256**. Expira tras **30 min de inactividad** y como máximo a las **8 h**. Logout, "cerrar todas mis sesiones", y revocación automática al cambiar contraseña, rol o desactivar el usuario. | S06 |
| 18 | IA con acceso total a la BD | Diseño para la Fase 2 (§7): el orquestador **no recibe cliente de BD**, solo llama a services con una identidad de servicio de rol `AGENT` (mínimo privilegio: tickets, eventos y memoria; nunca usuarios, ajustes, conexión de BD ni aprobaciones). Las salidas de un modelo son entrada no confiable (validación zod igual que HTTP). Las acciones destructivas pasan por la compuerta de aprobación humana. Nunca se apunta a una BD de producción durante las pruebas con IA. | Documentado; S13 |
| 19 | Sin evaluación periódica | `docs/SECURITY.md` con modelo de amenazas (STRIDE resumido) y checklist; al cerrar cada fase, QA ejecuta: `npm audit`, búsqueda de secretos, pruebas de IDOR/autenticación/rate limit/cabeceras (QS1–QS5). | S13, QS5 |

### 12.2 Esquema (`migrations/002_security.sql`)
```sql
CREATE TABLE users (
  id               TEXT PRIMARY KEY,
  email            TEXT NOT NULL,              -- guardado en minúsculas
  display_name     TEXT NOT NULL,
  password_hash    TEXT NOT NULL,              -- scrypt$N$r$p$salt$hash
  role             TEXT NOT NULL CHECK (role IN ('ADMIN','OPERATOR','VIEWER')),
  mfa_secret_enc   TEXT,                       -- AES-256-GCM (iv:tag:ciphertext, base64)
  mfa_enabled      INTEGER NOT NULL DEFAULT 0,
  failed_attempts  INTEGER NOT NULL DEFAULT 0,
  locked_until     TEXT,
  last_login_at    TEXT,
  password_changed_at TEXT NOT NULL,
  disabled_at      TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_users_email ON users(email);

CREATE TABLE sessions (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL REFERENCES users(id),
  token_hash      TEXT NOT NULL,               -- SHA-256 del token; el token nunca se guarda
  mfa_verified_at TEXT,                        -- base de la reautenticación reciente
  ip              TEXT,
  user_agent      TEXT,
  created_at      TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  expires_at      TEXT NOT NULL,               -- límite absoluto (8 h)
  revoked_at      TEXT
);
CREATE UNIQUE INDEX ux_sessions_token ON sessions(token_hash);
CREATE INDEX ix_sessions_user ON sessions(user_id);

CREATE TABLE audit_log (
  id          TEXT PRIMARY KEY,
  user_id     TEXT,                            -- NULL = anónimo (p. ej. login fallido)
  action      TEXT NOT NULL,                   -- 'auth.login_ok','auth.login_fail','admin.db_changed','user.role_changed',...
  target_type TEXT,
  target_id   TEXT,
  ip          TEXT,
  meta        TEXT NOT NULL DEFAULT '{}',      -- JSON SIN secretos
  created_at  TEXT NOT NULL
);
CREATE INDEX ix_audit_created ON audit_log(created_at);
```

### 12.3 Roles y permisos (aplicados por `requireRole` en cada ruta)
| Recurso / acción | VIEWER | OPERATOR | ADMIN |
|---|---|---|---|
| Leer agentes, tickets, aprobaciones, historial, snapshot, SSE | ✔ | ✔ | ✔ |
| Crear, mover, asignar, continuar o borrar tickets; cambio manual de estado de agente | ✖ | ✔ | ✔ |
| Decidir aprobaciones | ✖ | ✔ | ✔ |
| Memoria del proyecto (escribir) | ✖ | ✔ | ✔ |
| Crear, editar, archivar o restaurar agentes | ✖ | ✖ | ✔ |
| `/api/admin/*` (proyecto, reglas, límites, usuarios, auditoría) | ✖ | ✖ | ✔ (+MFA) |
| Conexión de BD, crear usuarios y cambiar roles | ✖ | ✖ | ✔ (+MFA reciente ≤10 min) |

Si falta la sesión ⇒ 401 `UNAUTHENTICATED`; si falta el rol ⇒ 403 `FORBIDDEN`; si falta MFA reciente ⇒ 403 `MFA_REQUIRED`. Un ADMIN no puede quitarse a sí mismo el rol ni desactivarse si es el **último ADMIN** (409).

### 12.4 Autenticación: endpoints
| Método | Ruta | Notas |
|---|---|---|
| POST | `/api/auth/login` | `{email, password}` → si no hay MFA: crea la sesión y pone la cookie. Si hay MFA: `{mfaRequired:true, loginTicket}` (válido 5 min, un solo uso). |
| POST | `/api/auth/mfa/verify` | `{loginTicket, code}` → crea la sesión. Con sesión activa y sin ticket: renueva `mfa_verified_at` (reautenticación). |
| POST | `/api/auth/logout` | Revoca la sesión actual. |
| POST | `/api/auth/logout-all` | Revoca todas las sesiones del usuario. |
| GET | `/api/auth/me` | `{id, email, displayName, role, mfaEnabled, mfaRecentUntil}` |
| POST | `/api/auth/me/password` | `{currentPassword, newPassword}`; revoca las demás sesiones. |
| POST | `/api/auth/me/mfa/setup` | Devuelve `{secret, otpauthUri}` **una sola vez** (el front lo muestra como texto para la app autenticadora; QR opcional más adelante). |
| POST | `/api/auth/me/mfa/enable` | `{code}` confirma y activa. |
| GET / DELETE | `/api/auth/me/sessions[/:id]` | Lista o revoca **mis** sesiones (el `:id` se filtra siempre por `user_id` de la sesión). |

Un ADMIN sin MFA activado solo puede usar `/api/auth/*` hasta activarlo (403 `MFA_SETUP_REQUIRED`).
**CSRF:** cookie `SameSite=Strict`, y además en métodos que modifican datos se exige que la cabecera `Origin` sea igual a `CORS_ORIGIN`; si no, 403. **CORS:** `credentials: true` con origen exacto (nunca `*`). El front usa `fetch(..., {credentials:'include'})` y `new EventSource(url, {withCredentials:true})`.

### 12.5 Nuevas variables `.env` (API)
```dotenv
HOST=127.0.0.1
NODE_ENV=development
APP_ENCRYPTION_KEY=        # 32 B base64; lo genera `npm run setup`
SESSION_IDLE_MINUTES=30
SESSION_MAX_HOURS=8
BACKUP_DIR=backups
BACKUP_INTERVAL_HOURS=24
BACKUP_KEEP=14
ADMIN_ALLOW_DB_CHANGE=true # false = la conexión solo se ve en el panel, no se cambia
```

---

## 13. Panel "Administración" (añadido 2026-11-22)

Vista nueva del FRONT `admin` (entrada **"Administración"** en el Sidebar, solo visible para ADMIN), con los **mismos componentes visuales y estilos** del resto de la app (tarjetas, inputs, botones y pestañas existentes). Pestañas:

| Pestaña | Contenido | Persistencia |
|---|---|---|
| **Conexión BD** | Estado actual (modo local o remoto, host, conexión OK/KO, versión de esquema, último backup). Formulario con URL y token (solo escritura; vacío = conservar el actual). Botones **Probar conexión** y **Guardar y conectar**. Aviso: "cambiar de BD no copia los datos". | `.env` de la API (ver §13.2) |
| **Proyecto** | Nombre de la empresa u oficina, nombre del proyecto, descripción, objetivos y stack tecnológico. En la Fase 2 será el contexto de los agentes. | `app_settings.project` |
| **Reglas** | Lista ordenable de restricciones: título, descripción, severidad `OBLIGATORIA` o `RECOMENDADA`, activa sí/no. En la Fase 1 solo se guardan; la Fase 2 las inyecta en el orquestador. | `project_rules` |
| **Límites** | Límites que **la API aplica ya**: `maxAgents` (máximo de agentes activos), `maxActiveTicketsPerAgent` (tickets IN_PROGRESS/REVIEW/AWAITING_APPROVAL por agente) y `requireApprovalForDone` (si está activo, un ticket solo llega a DONE al aprobarse su aprobación; moverlo a mano ⇒ 409). | `app_settings.limits` |
| **Agentes** | Tabla de agentes (incluidos los archivados): editar nombre, personaje, rol, avatar y system prompt; archivar y restaurar. | `agents` |
| **Usuarios** | Crear usuario (email, nombre, rol, contraseña inicial), cambiar rol, desactivar, revocar sesiones. | `users` |
| **Auditoría** | Últimas 200 entradas de `audit_log` (solo lectura). | `audit_log` |

### 13.1 Esquema (`migrations/003_admin.sql`)
```sql
CREATE TABLE app_settings (
  key        TEXT PRIMARY KEY CHECK (key IN ('project','limits')),
  value      TEXT NOT NULL,          -- JSON validado con zod por clave
  updated_by TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE project_rules (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  severity    TEXT NOT NULL DEFAULT 'MUST' CHECK (severity IN ('MUST','SHOULD')),
  enabled     INTEGER NOT NULL DEFAULT 1,
  position    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```
Valores por defecto sembrados: `limits = {"maxAgents":20,"maxActiveTicketsPerAgent":3,"requireApprovalForDone":false}`. Si se supera un límite ⇒ 409 `LIMIT_EXCEEDED` con un mensaje claro.

### 13.2 Conexión de BD desde el panel: cómo funciona (⚠ ahora se guarda en la bóveda cifrada, ver §16; donde aquí dice `.env`, léase bóveda)
1. `POST /api/admin/db/test {url, authToken?}`: crea un cliente temporal, ejecuta `SELECT 1`, lee `schema_migrations` y lo cierra. No cambia nada. Solo acepta los esquemas `file:`, `libsql://` y `https://`. Tiempo máximo de espera: 5 s.
2. `PUT /api/admin/db {url, authToken?, copyMyAdmin: true}` (ADMIN + MFA reciente + `ADMIN_ALLOW_DB_CHANGE=true`):
   1. Prueba la conexión (igual que el paso 1). Si falla ⇒ 422 y no se toca nada.
   2. Ejecuta las migraciones sobre la BD nueva.
   3. Si la BD nueva **no tiene usuarios**, copia el ADMIN actual (con su hash y su MFA) para que **no te quedes fuera**. Si tiene usuarios pero no existe tu email ⇒ 409, salvo confirmación explícita.
   4. Hace un backup del `.env` (`.env.bak`) y escribe solo `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` de forma atómica (archivo temporal + renombrado), sin tocar el resto.
   5. Cambia en caliente el cliente: `db/client.ts` expone `getDb()` y `swapDb(newClient)`. **Ningún repositorio guarda el cliente en una variable de módulo**; todos llaman a `getDb()`. El cliente viejo se cierra tras 5 s.
   6. Cierra todas las sesiones, porque pertenecían a la BD anterior, y emite el evento SSE `system.db_changed`. El front vuelve a pedir el login y el snapshot.
   7. Registra `admin.db_changed` en la auditoría (host nuevo, **sin token**).
3. `GET /api/admin/db`: `{mode:'local'|'remote', host, connected, schemaVersion, hasToken, lastBackupAt}`. **Nunca** devuelve el token.
4. Si la API **arranca sin poder conectar**, no se puede iniciar sesión (los usuarios viven en la BD) ⇒ se corrige editando `.env` a mano. Esto es intencionado: no hay forma de saltarse el login.

### 13.3 Endpoints admin (todos ADMIN + MFA)
| Método | Ruta |
|---|---|
| GET / PUT | `/api/admin/settings/project` |
| GET / PUT | `/api/admin/settings/limits` |
| GET / POST | `/api/admin/rules` · PATCH / DELETE `/api/admin/rules/:id` · PUT `/api/admin/rules/order` `{ids:[]}` |
| GET / PUT | `/api/admin/db` · POST `/api/admin/db/test` |
| GET / POST | `/api/admin/users` · PATCH `/api/admin/users/:id` (rol, nombre, desactivar) · POST `/api/admin/users/:id/revoke-sessions` |
| GET | `/api/admin/audit?limit=200` |
| POST | `/api/agents/:id/restore` (restaura un agente archivado) |
| POST | `/api/admin/backup` (backup manual inmediato) |

Eventos SSE nuevos: `settings.updated`, `rule.created/updated/deleted`, `system.db_changed`. Las reglas y el proyecto quedan disponibles para la Fase 2 a través de una interfaz `ProjectContextProvider` (solo declarada).

---

## 14. Orden de ejecución prioritario (CEO 2026-11-22)
Objetivo **M1 = "probar en local con login y Administración"** lo antes posible, con la seguridad desde el primer endpoint:
0. **(Cambio de stack)** P00 → P01. Después se reimplementan en Python T02, T10–T14, T20–T24 y T30, con los mismos criterios de aceptación (traducidos con §0.4). QA no prueba nada de la versión Node.
1. QA verifica esas tareas reimplementadas cuando estén EN QA.
2. **Seguridad base API:** S01 → S02 → S03 → S04 → S05 → S06 → S07 → S08 → S09 → S10.
3. Agentes y tiempo real: T30 → T31 → T32 → T60 → T61.
4. **Administración API:** A01 → A02 → A03 → A04 → A05 → A06 → A07.
5. **Front M1:** F05 → T70 → T71 → T72 → F01 → F02 → T73 → T74 → T75 → F03 → T77 → T79 → QS-M1.
6. Higiene: S11 → S12 → S13.
7. Resto del plan: T40–T46, T50–T54, T62–T64, T76, T78, T7A, T7B, QS1–QS5, T80.

Regla para toda tarea desde ahora: **cada ruta nueva declara `requireRole(...)`** y su test incluye el caso 401/403.

> **Prioridad confirmada por el CEO (2026-11-22): "primero que funcione".**
> Orden global: **V00** (menú, cambio trivial) → **M1** (P00, P01, núcleo de la API en Python, seguridad, Administración y front conectado: puntos 0–5 de arriba) → **V3D** (nueva oficina 3D, §15.3) → **VUI** (mejora visual del resto, §15.2) → resto del plan.
> Python 3.13 y las dependencias de §0.2 quedaron **aprobados e instalados por el Arquitecto**.

---

## 15. Rediseño visual y nueva oficina 3D (CEO 2026-11-22)

> Esto **sustituye** la regla inicial "no rediseñar el FRONT": ahora el CEO pide mejorar la parte visual de todo el proyecto. Siguen sin añadirse dependencias: Tailwind, motion, lucide y three ya están instalados.

### 15.1 Orden de módulos (V00)
Orden del Sidebar y de `ActiveModule`:
1. **To-Do & Pipeline de Tareas** (`kanban`). Es el módulo **por defecto** al entrar.
2. **Calendario de Proyectos** (`roadmap`)
3. **Cerebro FlowClic** (`cerebro`)
4. **Oficina IA 3D** (`colmena3d`)
5. **Administración** (`admin`, solo ADMIN, F03)

El botón de la cabecera ("Ver Oficina 3D" / "Abrir Cerebro") se mantiene.

### 15.2 Sistema visual de toda la app (VUI)
Dirección: **centro de mando tecnológico, sobrio y legible**. Base oscura actual (`#070B12`), un solo acento principal (cian), colores de estado consistentes y sin efectos que dificulten la lectura.
- **Tokens** en `src/index.css` con `@theme` de Tailwind 4:
  - colores: fondo, superficie 1/2/3, borde, texto 1/2/3, acento, y estados `working`, `review`, `blocked`, `sleep`, `idle`, `danger`, `success`;
  - radios, sombras y espaciado;
  - tipografía: Plus Jakarta Sans para el texto y JetBrains Mono para datos y ids, que ya están cargadas.
  - **Prohibido** usar hex sueltos en los componentes: todo sale de los tokens.
- **Kit de UI** en `src/ui/`: `Button` (primary, secondary, ghost, danger; tamaños), `Card`, `Badge` y `StatusPill` (los 5 estados), `Input`, `Textarea`, `Select`, `Modal`, `Tabs`, `Table`, `EmptyState`, `Skeleton`, `Toast` (para errores de API), `Tooltip` y `Avatar` (color e iniciales del agente). Todas las vistas usan el kit.
- **Layout:** Sidebar con grupos e indicadores (agentes activos, aprobaciones pendientes), cabecera con buscador global de tickets, menú de usuario y estado de conexión en tiempo real (punto verde, ámbar o rojo según el SSE).
- **Kanban:** columnas con contador y color de estado; tarjetas con prioridad, agente (avatar), proyecto y tiempo relativo; **arrastrar y soltar con HTML5 nativo** (sin librería), conservando los botones de flecha como alternativa accesible; panel lateral de detalle del ticket con su **historial** (`GET /tickets/:id/events`).
- **Calendario, Cerebro y Administración:** se rehacen con el kit, manteniendo sus funciones.
- **Accesibilidad:** contraste AA, foco visible, todo usable con teclado y `prefers-reduced-motion` respetado (desactiva animaciones y la cámara automática del 3D).
- **Responsive:** utilizable a partir de 1280 px de ancho. En móvil, Sidebar plegable y Kanban en lista.
- **Estados vacíos, de carga y de error** en cada vista. Nada de pantallas en blanco.

### 15.3 Nueva Oficina IA 3D (V3D)
Se eliminan los rótulos "ZONA A/B/C". Quedan **tres espacios con nombre propio**:

| Espacio | Quién está ahí | Ambiente |
|---|---|---|
| **Laboratorio** | Agentes `WORKING`, cada uno **en su puesto** | Tecnológico: piso con retícula luminosa, tiras LED, racks de servidores con LEDs parpadeantes, bandejas de cables, monitores emisivos |
| **Oficina de Sheldon** | Sheldon (en su escritorio); los agentes `REVIEW` y `BLOCKED` frente a sus pizarras | Inspirada en su oficina universitaria (detalle abajo) |
| **Zona de descanso** | Agentes `IDLE` y `SLEEP_QUOTA` (Sheldon, cuando está IDLE, **en su sitio del sofá**) | Inspirada en la sala de un apartamento geek de Pasadena (detalle abajo) |

**Puestos con nombre (Laboratorio):**
- Cada agente tiene un **puesto fijo**: el índice se asigna por orden de creación del agente, con los 9 slots actuales; si hay más de 9, se crea una fila nueva.
- Cada escritorio lleva una **placa** con "Puesto de *Nombre*" y su rol (p. ej. "Puesto de Leonard · Senior Full-Stack"). La placa sigue visible aunque el agente no esté.
- **El monitor del puesto muestra lo que está haciendo:** una textura de canvas con el título de su ticket IN_PROGRESS, el id corto, la prioridad y una animación de "código". Si no tiene ticket: "Sin asignación". Se actualiza con el SSE.
- **Etiqueta flotante** sobre cada avatar: nombre, rol, `StatusPill` y la tarea actual truncada. Al pasar el ratón se amplía; al hacer clic se abre el panel lateral existente (con su ticket y botones de estado).
- Un agente `BLOCKED` muestra un aviso rojo intermitente en su puesto. `SLEEP_QUOTA` muestra un icono de batería baja en la zona de descanso.

**Oficina de Sheldon** (sala rectangular cerrada con puerta abierta hacia el laboratorio):
- Paredes crema/beige, estanterías de madera empotradas con libros y archivadores metálicos grises.
- **Escritorio impecable y simétrico:** monitor, teléfono fijo, portalápices alineado y taza roja con un rayo.
- **Pizarras verdes de tiza** con cálculos de física (textura de canvas con ecuaciones dibujadas: Schrödinger, Einstein, Maxwell…). En la Fase 2 podrán mostrar el ticket en revisión.
- **Decoración:** dos diplomas enmarcados, un retrato enmarcado de un científico, un banderín universitario naranja y una pequeña figura de superhéroe roja sobre los libros.

**Zona de descanso** (sala de apartamento):
- **Sofá de cuero marrón** frente al televisor, con "el sitio de Sheldon" en el extremo izquierdo (cojín marcado).
- **Mesa de centro** de madera baja con cajas de comida para llevar, laptops y cómics.
- **Cocina abierta** al fondo: barra alta con taburetes y nevera con imanes.
- **Escritorios junto a los ventanales** con monitores y torres de PC, y **pizarras blancas con ruedas** con fórmulas (cuerdas, materia oscura).
- **Estanterías** con cajas blancas de cómics y figuras de acción; **espada** decorativa colgada; **maqueta de ADN** (ya existe la hélice, se reubica) y un **busto** decorativo.
- **Puerta** al descansillo, con un ascensor fuera de servicio y cinta amarilla de precaución.

**Restricciones técnicas del 3D:**
- **Todo procedural con Three.js** (geometrías y texturas de canvas), sin descargar modelos.
- **Sin logos ni marcas registradas** (Flash, Linterna Verde, Caltech, Star Wars/Trek, Game of Thrones, Spock, fotos reales de Einstein…): se usan elementos genéricos que evocan el ambiente (taza con rayo, banderín sin escudo, figura genérica, retrato estilizado). Así se evitan problemas de propiedad intelectual si el proyecto se publica.
- **Rendimiento:** ≤ 150 000 triángulos y ≤ 250 draw calls (`InstancedMesh` para libros, cómics, LEDs y sillas; geometrías estáticas fusionadas); 60 fps en GPU integrada a 1080p; las texturas de canvas solo se redibujan cuando cambian los datos.
- `sceneBuilder.ts` (1 030 líneas) se divide en `three/rooms/lab.ts`, `three/rooms/sheldonOffice.ts`, `three/rooms/restZone.ts`, `three/props/*.ts` y `three/textures/*.ts`.
- La animación de "ciclo de demo" (que hace caminar a un agente por las tres zonas) se elimina o queda solo con datos de ejemplo: el estado real viene de la API.


---

## 16. Secretos cifrados: conexión de BD y claves API de agentes (CEO 2026-11-22)

> **Sustituye** lo que §9, §12.5 y §13.2 decían sobre guardar `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` en el `.env`. Requisito del CEO: **la URL y el token de la BD no viven en el `.env`**, se modifican desde el front, y **las claves API de los agentes se guardan cifradas en la BD**.

### 16.1 Dónde vive cada cosa
| Dato | Dónde | Cómo |
|---|---|---|
| **Clave maestra** `APP_MASTER_KEY` (32 B, base64) | `.env`. Es **el único secreto** que queda ahí: algo tiene que abrir la caja fuerte. La genera `scripts/setup_env.py`, con permisos solo para el usuario (icacls/0600). | — |
| URL y token de la BD | **Bóveda local** `data/vault.db` (SQLite de la biblioteca estándar, ignorada por git), fuera de la BD principal: la API necesita la URL antes de poder conectarse | AES-256-GCM, clave derivada con HKDF (`info="flowclic/vault/v1"`), AAD = nombre del secreto |
| Claves API de los agentes (Anthropic, OpenAI, Google…) | **BD principal** (Turso), tabla `agent_credentials` | AES-256-GCM, HKDF (`info="flowclic/agent-credentials/v1"`), AAD = `agent_id|provider|id` (un texto cifrado no se puede mover a otra fila) |
| Secreto MFA de los usuarios | BD principal, `users.mfa_secret_enc` | Igual, con `info="flowclic/mfa/v1"` |

- Cada texto cifrado guarda `key_version`. El comando `python -m app.security.rotate_key` vuelve a cifrar todo con una clave maestra nueva.
- **Riesgo aceptado y documentado:** si se pierde `APP_MASTER_KEY`, la bóveda y las credenciales no se pueden leer. Debe guardarse en un gestor de contraseñas; se indica en `docs/DRP.md`. Los backups de la BD llevan las credenciales **cifradas**: un backup robado no las expone.
- Evolución posible: guardar la clave maestra en el Administrador de credenciales de Windows (paquete `keyring`), con OK del CEO.

### 16.2 Esquema
`data/vault.db` (local):
```sql
CREATE TABLE secrets (
  name        TEXT PRIMARY KEY CHECK (name IN ('db.url','db.auth_token')),
  ciphertext  BLOB NOT NULL,
  nonce       BLOB NOT NULL,
  key_version INTEGER NOT NULL,
  updated_by  TEXT,
  updated_at  TEXT NOT NULL
);
```
`migrations/003_agent_credentials.sql` (BD principal; la de Administración pasa a ser la `004_admin.sql`):
```sql
CREATE TABLE agent_credentials (
  id          TEXT PRIMARY KEY,
  agent_id    TEXT NOT NULL REFERENCES agents(id),
  provider    TEXT NOT NULL CHECK (provider IN ('anthropic','openai','google','other')),
  label       TEXT NOT NULL,
  ciphertext  BLOB NOT NULL,
  nonce       BLOB NOT NULL,
  key_version INTEGER NOT NULL,
  last4       TEXT NOT NULL,          -- solo para mostrar "••••abcd"
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  rotated_at  TEXT,
  revoked_at  TEXT
);
CREATE UNIQUE INDEX ux_agent_cred_label_active ON agent_credentials(agent_id, label) WHERE revoked_at IS NULL;
```

**Decisión del CEO (2026-11-23):** un agente puede tener **VARIAS conexiones API activas**, también del mismo proveedor (p. ej. dos claves de Anthropic). Lo único que no se repite entre las activas de un agente es la **etiqueta**: el índice único es `(agent_id, label)` y no `(agent_id, provider)`. Una etiqueta repetida devuelve 409; al revocar una conexión su etiqueta queda libre.

### 16.3 Primer arranque: modo SETUP
- Si la bóveda no tiene `db.url`, la API arranca en **modo SETUP**: solo responden `/api/health` y `/api/setup/*`, y todo lo demás devuelve 503 `SETUP_REQUIRED`.
- Al arrancar en ese modo, la API **imprime en su consola un código de un solo uso** (p. ej. `K7Q2-9XMP-4HDL`), que caduca en 30 min. El código se exige en cada llamada de setup, y solo se aceptan peticiones desde `127.0.0.1`/`::1`.
- Endpoints:
  - `GET /api/setup/status` → `{setupRequired, hasDatabase, hasAdmin}`.
  - `POST /api/setup/database {setupCode, url, authToken}` → prueba la conexión, la guarda cifrada en la bóveda, migra y cambia en caliente.
  - `POST /api/setup/admin {setupCode, email, displayName, password}` → crea el **primer** ADMIN, que debe activar MFA en su primer login.
- Cuando existe la BD y un ADMIN, **el setup se cierra**: los endpoints devuelven 404. Solo se reabre borrando la bóveda a mano.
- El FRONT muestra un **asistente de configuración** (F06) cuando `setupRequired=true`.

### 16.4 Importar el `.env` actual y dejarlo limpio
- Al arrancar, si el `.env` todavía tiene `TURSO_DATABASE_URL` o `TURSO_AUTH_TOKEN` y la bóveda está vacía:
  1. los importa cifrados a la bóveda;
  2. **elimina esas líneas del `.env`** con escritura atómica y **sin copia de seguridad** (la copia sería otro secreto en claro);
  3. registra en el log solo "conexión importada a la bóveda".
- `setup_env.py` y `.env.example` dejan de incluir `TURSO_*`.
- `admin:create` (CLI) se mantiene como alternativa al asistente.

### 16.5 Desde el FRONT (Administración)
- **Conexión BD** (A05, ahora sobre la bóveda):
  - muestra modo, host y estado, **nunca** el token;
  - permite **Probar** y **Guardar y conectar** (ADMIN + MFA reciente);
  - el token es un campo `type=password`, se envía una sola vez y se vacía al guardar.
- **Agentes → Credenciales API** (por agente):
  - lista con proveedor, etiqueta, `••••last4`, fecha de creación y de rotación;
  - acciones Añadir, Rotar (sustituye la clave) y Revocar;
  - la API **nunca devuelve la clave en claro**, ni siquiera al ADMIN;
  - cada operación queda en la auditoría **sin** el valor.
- El navegador no guarda secretos (ni en `localStorage` ni en el estado global); los campos se limpian al desmontar.

### 16.6 Endpoints nuevos
| Método | Ruta | Permiso |
|---|---|---|
| GET | `/api/admin/agents/{id}/credentials` | ADMIN + MFA |
| POST | `/api/admin/agents/{id}/credentials` `{provider,label,secret}` | ADMIN + MFA reciente |
| POST | `/api/admin/agents/{id}/credentials/{credId}/rotate` `{secret}` | ADMIN + MFA reciente |
| DELETE | `/api/admin/agents/{id}/credentials/{credId}` (revoca) | ADMIN + MFA reciente |
| GET/POST | `/api/setup/*` (§16.3) | Código de setup + localhost |

### 16.7 Fase 2
Interfaz `SecretsProvider.get_agent_key(agent_id, provider) -> str`, que solo se declara en la Fase 1. El orquestador descifra **en memoria** justo antes de llamar al modelo y nunca registra, devuelve ni pasa la clave a un modelo (refuerza el riesgo #18).

---

## 17. Kanban: arrastrar y soltar (CEO 2026-11-22, adelantado)
El drag & drop del Kanban (antes incluido en VUI04) se **adelanta** como tarea K01:
- HTML5 nativo, sin librerías.
- Al soltar en una columna: con la API conectada se llama a `PATCH /api/tickets/{id}/status`; antes de conectar, se actualiza el estado local.
- Resaltado de la columna destino, tarjeta "fantasma" y se mantienen las flechas y la alternativa por teclado.
- Si la API rechaza el movimiento (409/422), la tarjeta vuelve a su columna y se muestra el error.


---

## 18. Ruta rápida M0 y BD vacía (CEO 2026-11-22)
- La BD **empieza vacía**: el primer agente se crea desde la app. La semilla de §3 pasa a ser **opcional** (`python -m app.db.seed --demo`).
- El FRONT ya no tiene datos de ejemplo de agentes, tickets ni aprobaciones; cada vista muestra estados vacíos.
- El orden que manda es el de TASKS "AMPLIACIÓN (d)": API mínima de agentes y SSE → FRONT conectado → Administración visible (F03a) → seguridad S01–S10 inmediatamente después (API solo en 127.0.0.1 mientras tanto).


---

## 19. Perfiles de agentes, restricciones globales y flujo de tickets con permisos (CEO 2026-11-22)

> **Sin IA todavía.** En la Fase 1 se guardan los perfiles, se genera el prompt, y la API **aplica con código** las restricciones, los permisos y la máquina de estados. Los modelos solo se registran; nadie los llama.
> Distinción clave: **reglas y funciones = blandas** (van al prompt; el modelo intenta seguirlas). **Restricciones y permisos = duros** (los aplica la API; se bloquean aunque el modelo "quiera").

### 19.1 Ampliación de `agents` (migración `005_agent_profiles.sql`)
| Campo nuevo | Tipo | Contenido | Quién lo hace cumplir |
|---|---|---|---|
| `role_type` | TEXT CHECK (`CTO`,`DEV_BACKEND`,`DEV_FRONTEND`,`QA`,`CUSTOM`) | Plantilla de origen y rol funcional | App |
| `functions` | JSON `string[]` | Qué hace | Prompt |
| `rules` | JSON `string[]` | Cómo trabaja | Prompt |
| `restrictions` | JSON `string[]` | Qué no puede hacer nunca (propias del agente) | Prompt + app |
| `permissions` | JSON (ver 19.3) | Acciones, espacios de trabajo, transiciones de tickets | **App** |
| `model` | JSON `{primary, fallback, fallbackCondition}` | Modelo principal, respaldo y cuándo usarlo | Orquestador (Fase 2) |
| `limits` | JSON `{maxTokensPerTicket, maxUsdPerDay, maxRetries}` | Topes | **App** |
| `consecutive_failures` | INTEGER DEFAULT 0 | Contador para el bloqueo automático | App |
| `system_prompt` | TEXT (ya existe) | **Generado en el servidor** al guardar: functions + rules + restrictions propias + **restricciones globales**. No se edita a mano; el front lo muestra como vista previa | App |

`model_tier` queda obsoleto: el front deriva la etiqueta del `model.primary`.
Catálogo de modelos (`app/domain/models_catalog.py`, editable sin migración): `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `gemini-pro`, `gemini-flash`. Los ids exactos de Gemini se fijarán en la Fase 2.

### 19.2 Restricciones globales (en código, **no editables desde la app**)
Constante `GLOBAL_RESTRICTIONS` en `app/domain/agent_policy.py`:
1. Ningún agente hace merge a `main` ni despliega a producción (solo el CEO).
2. Ningún agente ve llaves de producción ni archivos `.env`.
3. Ningún agente contacta a clientes ni envía correos.
4. Solo el agente con `role_type=CTO` (Sheldon) habla con el CEO y crea aprobaciones.
5. Todo agente pasa a `BLOCKED` tras **3 fallos seguidos** o al llegar a su tope de coste (`maxUsdPerDay`).

Aplicación con código:
- **Al crear o editar** un agente: si `permissions.actions` contiene alguna acción prohibida (`git.merge_main`, `deploy.production`, `secrets.read`, `env.read`, `email.send`, `client.contact`) ⇒ **422 `GLOBAL_RESTRICTION`**. `approvals.create` solo se acepta con `role_type=CTO`.
- El prompt generado **siempre** termina con las 5 restricciones globales, aunque el cliente intente quitarlas: el servidor ignora lo que envíe el cliente para ellas.
- **Bloqueo automático:** `AgentGuard.record_failure(agent)` incrementa el contador y al 3.º fallo seguido pone `BLOCKED` (evento `agent.updated` + auditoría); `record_success` lo pone a 0. `AgentGuard.check_budget(agent, usd_today)` bloquea al alcanzar el tope. En la Fase 1 se ejercen con un endpoint de pruebas solo para ADMIN (`POST /api/agents/{id}/failures`); en la Fase 2 los llama el orquestador.
- **Espacios de trabajo:** los permisos de carpeta usan **identificadores lógicos** (`api`, `front`, `docs`), nunca rutas absolutas. Su ruta real se configurará en Administración en la Fase 2.

### 19.3 Formato de `permissions`
```json
{
  "workspaces": { "api": "write", "front": "none", "docs": "read" },
  "actions": ["tickets.create", "tickets.assign", "tickets.close", "approvals.create",
              "memory.write", "repo.read", "cmd.test", "cmd.lint", "cmd.build",
              "cmd.install_approved", "cmd.audit", "git.commit_dev", "git.push_dev"],
  "ticketTransitions": [["PENDING","IN_PROGRESS"], ["IN_PROGRESS","IN_QA"]],
  "onlyAssignedTickets": true
}
```
Acciones válidas = lista cerrada en `agent_policy.py`. Cualquier otra ⇒ 400.

### 19.4 Nuevo flujo de tickets (sustituye a los estados de §3 y §4)
```
PENDING → IN_PROGRESS → IN_QA → IN_REVIEW → DONE
              ▲            │         │
              └─ RETURNED ◄┴─────────┘
```
| Código | UI |
|---|---|
| `PENDING` | PENDIENTE |
| `IN_PROGRESS` | EN CURSO |
| `IN_QA` | EN QA |
| `IN_REVIEW` | EN REVISIÓN |
| `DONE` | HECHO |
| `RETURNED` | DEVUELTA |

**Grafo válido** (cualquier otra transición ⇒ **409 `INVALID_TRANSITION`**): PENDING→IN_PROGRESS · IN_PROGRESS→IN_QA · IN_QA→IN_REVIEW · IN_QA→RETURNED · IN_REVIEW→DONE · IN_REVIEW→RETURNED · RETURNED→IN_PROGRESS.

**Quién puede** (transición válida pero sin permiso ⇒ **403 `TRANSITION_FORBIDDEN`**):
| Actor | Transiciones |
|---|---|
| Dev (Leonard, Penny) | PENDING→IN_PROGRESS, IN_PROGRESS→IN_QA, RETURNED→IN_PROGRESS, **solo en tickets asignados a él** |
| QA (Raj) | IN_QA→IN_REVIEW, IN_QA→RETURNED |
| CTO (Sheldon) | crear y asignar; IN_REVIEW→DONE, IN_REVIEW→RETURNED; crear aprobaciones |
| Humano ADMIN/OPERATOR (CEO) | cualquier transición **válida del grafo** (también arrastrando en el Kanban); decide aprobaciones y merge |
| Humano VIEWER | ninguna |

- Función pura `can_transition(actor, ticket, to) -> Allowed | Forbidden | Invalid` en `app/domain/ticket_flow.py`, con tests de tabla.
- **Actor:** en la Fase 1 lo determina la sesión (humano). Para probar los permisos de agente, un ADMIN puede enviar `actingAgentId` (queda auditado como "simulado por X"). En la Fase 2, el orquestador actúa con la identidad de servicio del agente.
- Endpoint: `POST /api/tickets/{id}/transition {to, note?, actingAgentId?}`. Sustituye a `PATCH /status` y a `/continue`: "continuar" = `RETURNED→IN_PROGRESS`.
- Efecto en el agente asignado: IN_PROGRESS ⇒ WORKING; IN_QA / IN_REVIEW ⇒ REVIEW; DONE ⇒ IDLE si no tiene más tickets activos; RETURNED ⇒ WORKING. Se mantiene la protección R1 de BLOCKED y SLEEP_QUOTA.

### 19.5 Aprobaciones = compuertas
- `approvals.gate` INTEGER CHECK (1..4): **1 Alcance · 2 Arquitectura · 3 Merge · 4 Producción**.
- Solo un agente CTO o un humano ADMIN crean aprobaciones. Solo el humano las decide.
- Un ticket con una compuerta PENDING enlazada **no puede pasar a DONE** (409 `GATE_PENDING`). Una compuerta REJECTED pasa el ticket a RETURNED.
- Desaparece la columna "Aprobación CEO" del Kanban (las aprobaciones viven en su cola del Cerebro).
- `model.fallbackCondition` de Sheldon: respaldo con Opus **solo** en las compuertas 2 y 4.

### 19.6 Plantillas y semilla
- `app/domain/agent_templates.py` contiene las **4 plantillas por rol** con los perfiles exactos del CEO (Sheldon/CTO, Leonard/DEV_BACKEND, Penny/DEV_FRONTEND, Raj/QA): funciones, reglas, restricciones, permisos, modelo y límites.
- `GET /api/agent-templates` las sirve al modal.
- **La BD sigue empezando vacía (§18).** Para cargar el equipo base: botón **"Cargar equipo base"** en Administración → Agentes (ADMIN) o `python -m app.db.seed --agents`. Es idempotente y crea los 4 agentes desde las plantillas.
- Límites por defecto (editables): Sheldon 200k tokens/ticket y 10 USD/día; Leonard y Penny 150k y 8 USD; Raj 80k y 3 USD; `maxRetries` 3.

### 19.7 FRONT
- **Modal "Crear agente":**
  - selector de plantilla (CTO, Dev Backend, Dev Frontend, QA, Personalizado) que precarga todo;
  - listas editables de funciones, reglas y restricciones propias;
  - permisos con casillas (acciones), selectores (espacios de trabajo) y una matriz de transiciones;
  - modelo principal, respaldo y condición; límites;
  - las **5 restricciones globales se muestran bloqueadas** (candado, no editables);
  - vista previa del prompt generado;
  - los errores 422 de la API se muestran en el campo correspondiente.
- **Vista de detalle del agente:** se abre desde el 3D, el Cerebro, el Kanban y Administración → Agentes. Pestañas Funciones · Reglas · Restricciones (las globales marcadas) · Permisos · Modelo · Límites · Prompt, más el estado y el contador de fallos. ADMIN puede editar (salvo las globales).
- **Kanban** con las 6 columnas de 19.4. El arrastre solo acepta los destinos válidos (las demás columnas se ven atenuadas mientras se arrastra); si la API responde 403/409, la tarjeta vuelve a su sitio con el mensaje.

- Texto literal de los perfiles: `docs/AGENT_PROFILES.md`. La lista cerrada de acciones incluye también `cmd.dev`. Los niveles de espacio de trabajo son `none | read | tests | qa_report | write`.
