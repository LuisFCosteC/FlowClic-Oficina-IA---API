-- PRJ01: proyectos. Cada workspace pertenece (opcionalmente) a un proyecto y tiene un tipo (kind);
-- los tickets apuntan a un proyecto (project_id) en lugar de texto libre; la empresa queda sola
-- en app_settings.project.
CREATE TABLE projects (
  id          TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 32),
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  goals       TEXT NOT NULL DEFAULT '[]',
  stack       TEXT NOT NULL DEFAULT '[]',
  status      TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

ALTER TABLE workspaces ADD COLUMN project_id TEXT REFERENCES projects(id);
ALTER TABLE workspaces ADD COLUMN kind TEXT NOT NULL DEFAULT 'other'
  CHECK (kind IN ('api','front','docs','mobile','other'));
UPDATE workspaces SET kind = CASE WHEN id IN ('api','front','docs','mobile') THEN id ELSE 'other' END;

ALTER TABLE tickets ADD COLUMN project_id TEXT REFERENCES projects(id);

-- Proyecto "de proyecto" que vivía en app_settings.project (si tenía nombre).
INSERT OR IGNORE INTO projects (id, name, description, goals, stack, status, created_at, updated_at)
SELECT
  substr(CASE WHEN slug GLOB '[a-z]*' THEN slug ELSE 'p-' || slug END, 1, 32),
  pname, pdesc, pgoals, pstack, 'ACTIVE',
  strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
FROM (
  SELECT
    trim(json_extract(value, '$.projectName')) AS pname,
    COALESCE(json_extract(value, '$.description'), '') AS pdesc,
    COALESCE(json_extract(value, '$.goals'), '[]') AS pgoals,
    COALESCE(json_extract(value, '$.stack'), '[]') AS pstack,
    replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(
      lower(trim(json_extract(value, '$.projectName'))),
      ' ', '-'), 'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ñ', 'n'), 'ü', 'u'),
      '.', '-'), '/', '-') AS slug
  FROM app_settings WHERE key = 'project'
)
WHERE pname IS NOT NULL AND pname <> '';

-- Proyectos a partir del texto libre de los tickets existentes.
INSERT OR IGNORE INTO projects (id, name, description, goals, stack, status, created_at, updated_at)
SELECT
  substr(CASE WHEN slug GLOB '[a-z]*' THEN slug ELSE 'p-' || slug END, 1, 32),
  MIN(pname), '', '[]', '[]', 'ACTIVE',
  strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
FROM (
  SELECT
    trim(project) AS pname,
    replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(
      lower(trim(project)),
      ' ', '-'), 'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ñ', 'n'), 'ü', 'u'),
      '.', '-'), '/', '-') AS slug
  FROM tickets WHERE project IS NOT NULL AND trim(project) <> ''
)
GROUP BY slug;

UPDATE tickets SET project_id = (
  SELECT p.id FROM projects p WHERE lower(p.name) = lower(trim(tickets.project))
)
WHERE project IS NOT NULL AND trim(project) <> '';

-- app_settings.project: solo la empresa.
UPDATE app_settings
SET value = json_object('companyName', COALESCE(json_extract(value, '$.companyName'), ''))
WHERE key = 'project';
