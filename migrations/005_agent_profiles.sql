-- Perfiles de agentes (PLAN §19.1). `model_tier` queda obsoleto (el front deriva la etiqueta de `model.primary`).
ALTER TABLE agents ADD COLUMN role_type TEXT NOT NULL DEFAULT 'CUSTOM'
  CHECK (role_type IN ('CTO','DEV_BACKEND','DEV_FRONTEND','QA','CUSTOM'));
ALTER TABLE agents ADD COLUMN functions TEXT NOT NULL DEFAULT '[]';
ALTER TABLE agents ADD COLUMN rules TEXT NOT NULL DEFAULT '[]';
ALTER TABLE agents ADD COLUMN restrictions TEXT NOT NULL DEFAULT '[]';
ALTER TABLE agents ADD COLUMN permissions TEXT NOT NULL DEFAULT '{"workspaces":{},"actions":[],"ticketTransitions":[],"onlyAssignedTickets":true}';
ALTER TABLE agents ADD COLUMN model TEXT NOT NULL DEFAULT '{"primary":"claude-sonnet-5-5","fallback":null,"fallbackCondition":null}';
ALTER TABLE agents ADD COLUMN limits TEXT NOT NULL DEFAULT '{"maxTokensPerTicket":150000,"maxUsdPerDay":8,"maxRetries":3}';
ALTER TABLE agents ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0);
