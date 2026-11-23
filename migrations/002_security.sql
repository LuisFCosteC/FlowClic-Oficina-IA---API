CREATE TABLE users (
  id               TEXT PRIMARY KEY,
  email            TEXT NOT NULL,
  display_name     TEXT NOT NULL,
  password_hash    TEXT NOT NULL,
  role             TEXT NOT NULL CHECK (role IN ('ADMIN','OPERATOR','VIEWER')),
  mfa_secret_enc   TEXT,
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
  token_hash      TEXT NOT NULL,
  mfa_verified_at TEXT,
  ip              TEXT,
  user_agent      TEXT,
  created_at      TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  expires_at      TEXT NOT NULL,
  revoked_at      TEXT
);
CREATE UNIQUE INDEX ux_sessions_token ON sessions(token_hash);
CREATE INDEX ix_sessions_user ON sessions(user_id);

CREATE TABLE audit_log (
  id          TEXT PRIMARY KEY,
  user_id     TEXT,
  action      TEXT NOT NULL,
  target_type TEXT,
  target_id   TEXT,
  ip          TEXT,
  meta        TEXT NOT NULL DEFAULT '{}',
  created_at  TEXT NOT NULL
);
CREATE INDEX ix_audit_created ON audit_log(created_at);
