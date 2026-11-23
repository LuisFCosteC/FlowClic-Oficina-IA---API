# FlowClic Oficina IA — Plan de Arquitectura · Fase 1

> Estado: **BORRADOR, pendiente de aprobación del CEO**
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
Llamadas a modelos IA, orquestador real, automatizaciones/colas, autenticación/usuarios, roadmap/proyectos en BD, router de modelos real, UI de memoria del proyecto, UI de historial de ticket (el endpoint existe), despliegue.
