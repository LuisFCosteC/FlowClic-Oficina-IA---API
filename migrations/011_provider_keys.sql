-- KEY01: bolsa GLOBAL de claves API por proveedor (sustituye a agent_credentials de F07/C05).
-- La clave en claro NUNCA se guarda: AES-256-GCM (HKDF "provider-keys"), AAD "provider|id".
CREATE TABLE provider_keys (
  id                  TEXT PRIMARY KEY,
  provider            TEXT NOT NULL CHECK (provider IN ('google','anthropic','openai','other')),
  label               TEXT NOT NULL,
  ciphertext          BLOB NOT NULL,
  nonce               BLOB NOT NULL,
  key_version         INTEGER NOT NULL,
  last4               TEXT NOT NULL,
  position            INTEGER NOT NULL DEFAULT 0,
  status              TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REVOKED','INVALID')),
  daily_request_limit INTEGER CHECK (daily_request_limit IS NULL OR daily_request_limit >= 1),
  daily_token_limit   INTEGER CHECK (daily_token_limit IS NULL OR daily_token_limit >= 1),
  created_at          TEXT NOT NULL,
  rotated_at          TEXT,
  revoked_at          TEXT
);
-- La etiqueta no se repite entre las claves NO revocadas del mismo proveedor.
CREATE UNIQUE INDEX ux_provider_keys_label ON provider_keys(provider, label) WHERE status <> 'REVOKED';
CREATE INDEX ix_provider_keys_pos ON provider_keys(provider, position);

CREATE TABLE key_usage (
  key_id          TEXT NOT NULL REFERENCES provider_keys(id),
  model           TEXT NOT NULL,
  day             TEXT NOT NULL,
  requests        INTEGER NOT NULL DEFAULT 0,
  input_tokens    INTEGER NOT NULL DEFAULT 0,
  output_tokens   INTEGER NOT NULL DEFAULT 0,
  cost_usd        REAL NOT NULL DEFAULT 0,
  exhausted_until TEXT,
  last_error_code TEXT,
  last_used_at    TEXT,
  PRIMARY KEY (key_id, model, day)
);

-- Las conexiones por agente se retiran (rutas 410). Las filas antiguas, si las hubiera, NO se
-- borran ni se mueven (están cifradas con otra AAD): queda constancia (solo si había alguna) de cuántas eran.
INSERT INTO audit_log (id, user_id, action, target_type, target_id, ip, meta, created_at)
SELECT 'key01-legacy-count', NULL, 'keys.legacy_credentials_counted', 'system', NULL, NULL,
  json_object('legacyActive', (SELECT COUNT(*) FROM agent_credentials WHERE revoked_at IS NULL),
              'legacyTotal', (SELECT COUNT(*) FROM agent_credentials)),
  strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE EXISTS (SELECT 1 FROM agent_credentials);
