CREATE TABLE agents (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  character     TEXT NOT NULL,
  role          TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'IDLE'
                CHECK (status IN ('IDLE','WORKING','REVIEW','BLOCKED','SLEEP_QUOTA')),
  avatar        TEXT NOT NULL DEFAULT '{}',
  system_prompt TEXT NOT NULL DEFAULT '',
  model_tier    TEXT NOT NULL DEFAULT 'sonnet_pro'
                CHECK (model_tier IN ('opus_pro','sonnet_pro','haiku_flash')),
  is_cto        INTEGER NOT NULL DEFAULT 0,
  current_task  TEXT,
  project       TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  archived_at   TEXT
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
  position           INTEGER NOT NULL DEFAULT 0,
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
  actor      TEXT NOT NULL DEFAULT 'human',
  payload    TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX ix_ticket_events_ticket ON ticket_events(ticket_id, created_at);

CREATE TABLE approvals (
  id               TEXT PRIMARY KEY,
  ticket_id        TEXT REFERENCES tickets(id),
  agent_id         TEXT REFERENCES agents(id),
  title            TEXT NOT NULL,
  category         TEXT NOT NULL DEFAULT 'Arquitectura'
                   CHECK (category IN ('Arquitectura','Despliegue','Seguridad','Datos')),
  summary          TEXT NOT NULL DEFAULT '',
  reviewer_note    TEXT NOT NULL DEFAULT '',
  estimated_tokens INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
  decision_note    TEXT,
  decided_by       TEXT,
  requested_at     TEXT NOT NULL,
  decided_at       TEXT
);
CREATE INDEX ix_approvals_status ON approvals(status);
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
