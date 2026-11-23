CREATE TABLE app_settings (
  key        TEXT PRIMARY KEY CHECK (key IN ('project','limits')),
  value      TEXT NOT NULL,
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

INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES
  ('limits', '{"maxAgents":20,"maxActiveTicketsPerAgent":3,"requireApprovalForDone":false}', NULL, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ('project', '{"companyName":"","projectName":"","description":"","goals":[],"stack":[]}', NULL, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
