-- Espacios de trabajo (J03): id lógico (api, front, docs...) -> carpeta local.
-- La ruta solo la usará el orquestador en la Fase 2; nunca va al system_prompt ni a los agentes.
CREATE TABLE workspaces (
  id         TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 32),
  name       TEXT NOT NULL,
  path       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
