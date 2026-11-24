-- OFFICE01: modo de la oficina (trabajar o pausa global: desayuno, almuerzo, dormir).
-- app_settings limitaba `key` a ('project','limits'); se reconstruye admitiendo 'office_mode'.
CREATE TABLE app_settings_new (
  key        TEXT PRIMARY KEY CHECK (key IN ('project','limits','office_mode')),
  value      TEXT NOT NULL,
  updated_by TEXT,
  updated_at TEXT NOT NULL
);
INSERT INTO app_settings_new (key, value, updated_by, updated_at)
  SELECT key, value, updated_by, updated_at FROM app_settings;
DROP TABLE app_settings;
ALTER TABLE app_settings_new RENAME TO app_settings;
INSERT INTO app_settings (key, value, updated_by, updated_at)
  VALUES ('office_mode', 'work', NULL, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
