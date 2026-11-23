-- Especificación del ticket dividida (J04). `description` se mantiene por compatibilidad.
-- Las listas son JSON string[]; `model` es un id del catálogo (models_catalog.py) o NULL.
ALTER TABLE tickets ADD COLUMN objective TEXT NOT NULL DEFAULT '';
ALTER TABLE tickets ADD COLUMN acceptance_criteria TEXT NOT NULL DEFAULT '[]';
ALTER TABLE tickets ADD COLUMN actions TEXT NOT NULL DEFAULT '[]';
ALTER TABLE tickets ADD COLUMN restrictions TEXT NOT NULL DEFAULT '[]';
ALTER TABLE tickets ADD COLUMN dependencies TEXT NOT NULL DEFAULT '[]';
ALTER TABLE tickets ADD COLUMN model TEXT;
