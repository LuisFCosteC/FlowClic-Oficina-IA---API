-- Credenciales API de los agentes (PLAN §16.2), cifradas con AES-256-GCM (HKDF "agent-credentials").
-- La clave en claro NUNCA se guarda: solo el texto cifrado, el nonce y los 4 últimos caracteres.
-- Cambio pedido por el CEO (2026-11-23): un agente puede tener VARIAS conexiones activas, también
-- del mismo proveedor; lo único que no se repite entre las activas de un agente es la etiqueta.
CREATE TABLE agent_credentials (
  id          TEXT PRIMARY KEY,
  agent_id    TEXT NOT NULL REFERENCES agents(id),
  provider    TEXT NOT NULL CHECK (provider IN ('anthropic','openai','google','other')),
  label       TEXT NOT NULL,
  ciphertext  BLOB NOT NULL,
  nonce       BLOB NOT NULL,
  key_version INTEGER NOT NULL,
  last4       TEXT NOT NULL,
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  rotated_at  TEXT,
  revoked_at  TEXT
);
CREATE UNIQUE INDEX ux_agent_cred_label_active ON agent_credentials(agent_id, label) WHERE revoked_at IS NULL;
CREATE INDEX ix_agent_cred_agent ON agent_credentials(agent_id);
