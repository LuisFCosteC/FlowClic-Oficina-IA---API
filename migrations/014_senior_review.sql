-- GM02: flujo con REVISIÓN SENIOR y REVISIÓN CTO.
--   PENDING → IN_PROGRESS → IN_QA → IN_SENIOR_REVIEW → IN_REVIEW (CTO) → DONE
--   RETURNED desde IN_QA, IN_SENIOR_REVIEW e IN_REVIEW; RETURNED → IN_PROGRESS.
-- Se reconstruye `tickets` para ampliar el CHECK de `status` (los ids se conservan).
PRAGMA defer_foreign_keys = ON;
CREATE TABLE tickets_new (
  id                 TEXT PRIMARY KEY,
  title              TEXT NOT NULL,
  description        TEXT NOT NULL DEFAULT '',
  status             TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','IN_PROGRESS','IN_QA','IN_SENIOR_REVIEW','IN_REVIEW','DONE','RETURNED')),
  priority           TEXT CHECK (priority IS NULL OR priority IN ('HIGH','MEDIUM','LOW')),
  assigned_agent_id  TEXT REFERENCES agents(id),
  project            TEXT,
  model_tier         TEXT NOT NULL DEFAULT 'sonnet_pro'
                     CHECK (model_tier IN ('opus_pro','sonnet_pro','haiku_flash')),
  estimated_cost_usd REAL NOT NULL DEFAULT 0,
  position           INTEGER NOT NULL DEFAULT 0,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  objective          TEXT NOT NULL DEFAULT '',
  acceptance_criteria TEXT NOT NULL DEFAULT '[]',
  actions            TEXT NOT NULL DEFAULT '[]',
  restrictions       TEXT NOT NULL DEFAULT '[]',
  dependencies       TEXT NOT NULL DEFAULT '[]',
  model              TEXT,
  project_id         TEXT REFERENCES projects(id),
  kind               TEXT NOT NULL DEFAULT 'TASK' CHECK (kind IN ('REQUEST','TASK')),
  parent_ticket_id   TEXT REFERENCES tickets(id),
  requirement        TEXT NOT NULL DEFAULT ''
);
INSERT INTO tickets_new (id, title, description, status, priority, assigned_agent_id, project, model_tier, estimated_cost_usd, position, created_at, updated_at, objective, acceptance_criteria, actions, restrictions, dependencies, model, project_id, kind, parent_ticket_id, requirement)
SELECT id, title, description, status, priority, assigned_agent_id, project, model_tier, estimated_cost_usd, position, created_at, updated_at, objective, acceptance_criteria, actions, restrictions, dependencies, model, project_id, kind, parent_ticket_id, requirement FROM tickets;
DROP TABLE tickets;
ALTER TABLE tickets_new RENAME TO tickets;
CREATE INDEX ix_tickets_status ON tickets(status);
CREATE INDEX ix_tickets_agent  ON tickets(assigned_agent_id);
CREATE INDEX ix_tickets_parent ON tickets(parent_ticket_id);
CREATE INDEX ix_tickets_project ON tickets(project_id);

-- Los permisos guardados que usaban IN_QA→IN_REVIEW (QA) pasan a IN_QA→IN_SENIOR_REVIEW.
UPDATE agents SET permissions = replace(permissions, '["IN_QA","IN_REVIEW"]', '["IN_QA","IN_SENIOR_REVIEW"]');
UPDATE agents SET permissions = replace(permissions, '["IN_QA", "IN_REVIEW"]', '["IN_QA", "IN_SENIOR_REVIEW"]');
