-- Chat de mando de la Oficina 3D (TASKS ampliación g). En la Fase 1 no hay IA: las órdenes
-- se guardan con estado PENDING hasta que se conecte el orquestador (Fase 2).
CREATE TABLE agent_messages (
  id          TEXT PRIMARY KEY,
  scope       TEXT NOT NULL CHECK (scope IN ('GLOBAL','AGENT')),
  agent_id    TEXT REFERENCES agents(id),          -- NULL si GLOBAL
  author_type TEXT NOT NULL CHECK (author_type IN ('HUMAN','AGENT','SYSTEM')),
  author_id   TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('ORDER','QUESTION','NOTE','STATUS','REPLY')),
  body        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACK','DONE','REJECTED')),
  ticket_id   TEXT REFERENCES tickets(id),
  created_at  TEXT NOT NULL,
  CHECK ((scope = 'GLOBAL' AND agent_id IS NULL) OR (scope = 'AGENT' AND agent_id IS NOT NULL))
);
CREATE INDEX ix_agent_messages_agent ON agent_messages(agent_id, created_at);
CREATE INDEX ix_agent_messages_created ON agent_messages(created_at);
