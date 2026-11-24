-- RPT01: a quién reporta cada agente (id de otro agente). NULL = el CEO.
ALTER TABLE agents ADD COLUMN reports_to TEXT REFERENCES agents(id);
CREATE INDEX ix_agents_reports_to ON agents(reports_to);
