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

### Estructura de la API
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
**Sin dependencias nuevas:** todo se hace con `node:crypto` (scrypt, randomBytes, AES-256-GCM, HMAC para TOTP).

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

### 13.2 Conexión de BD desde el panel: cómo funciona
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
1. QA cierra lo que está EN QA (bloques 0–2).
2. **Seguridad base API:** S01 → S02 → S03 → S04 → S05 → S06 → S07 → S08 → S09 → S10.
3. Agentes y tiempo real: T30 → T31 → T32 → T60 → T61.
4. **Administración API:** A01 → A02 → A03 → A04 → A05 → A06 → A07.
5. **Front M1:** F05 → T70 → T71 → T72 → F01 → F02 → T73 → T74 → T75 → F03 → T77 → T79 → QS-M1.
6. Higiene: S11 → S12 → S13.
7. Resto del plan: T40–T46, T50–T54, T62–T64, T76, T78, T7A, T7B, QS1–QS5, T80.

Regla para toda tarea desde ahora: **cada ruta nueva declara `requireRole(...)`** y su test incluye el caso 401/403.
