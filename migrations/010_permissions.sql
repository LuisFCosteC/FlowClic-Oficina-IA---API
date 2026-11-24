-- PERM01: permisos por tipo de carpeta y alcance de proyectos.
-- Formato antiguo: workspaces {id: nivel}. Formato nuevo: folderAccess {api, front, docs, mobile,
-- other} (nivel MÁXIMO por tipo de carpeta) + projectScope ("ALL" para los agentes existentes).
-- Orden de niveles: none < read < tests < qa_report < write.
UPDATE agents SET permissions = json_object(
  'folderAccess', json_object(
      'api', CASE COALESCE((SELECT MAX(CASE je.value WHEN 'write' THEN 4 WHEN 'qa_report' THEN 3 WHEN 'tests' THEN 2 WHEN 'read' THEN 1 ELSE 0 END) FROM json_each(agents.permissions, '$.workspaces') je JOIN workspaces w ON w.id = je.key WHERE w.kind = 'api'), 0) WHEN 4 THEN 'write' WHEN 3 THEN 'qa_report' WHEN 2 THEN 'tests' WHEN 1 THEN 'read' ELSE 'none' END,
      'front', CASE COALESCE((SELECT MAX(CASE je.value WHEN 'write' THEN 4 WHEN 'qa_report' THEN 3 WHEN 'tests' THEN 2 WHEN 'read' THEN 1 ELSE 0 END) FROM json_each(agents.permissions, '$.workspaces') je JOIN workspaces w ON w.id = je.key WHERE w.kind = 'front'), 0) WHEN 4 THEN 'write' WHEN 3 THEN 'qa_report' WHEN 2 THEN 'tests' WHEN 1 THEN 'read' ELSE 'none' END,
      'docs', CASE COALESCE((SELECT MAX(CASE je.value WHEN 'write' THEN 4 WHEN 'qa_report' THEN 3 WHEN 'tests' THEN 2 WHEN 'read' THEN 1 ELSE 0 END) FROM json_each(agents.permissions, '$.workspaces') je JOIN workspaces w ON w.id = je.key WHERE w.kind = 'docs'), 0) WHEN 4 THEN 'write' WHEN 3 THEN 'qa_report' WHEN 2 THEN 'tests' WHEN 1 THEN 'read' ELSE 'none' END,
      'mobile', CASE COALESCE((SELECT MAX(CASE je.value WHEN 'write' THEN 4 WHEN 'qa_report' THEN 3 WHEN 'tests' THEN 2 WHEN 'read' THEN 1 ELSE 0 END) FROM json_each(agents.permissions, '$.workspaces') je JOIN workspaces w ON w.id = je.key WHERE w.kind = 'mobile'), 0) WHEN 4 THEN 'write' WHEN 3 THEN 'qa_report' WHEN 2 THEN 'tests' WHEN 1 THEN 'read' ELSE 'none' END,
      'other', CASE COALESCE((SELECT MAX(CASE je.value WHEN 'write' THEN 4 WHEN 'qa_report' THEN 3 WHEN 'tests' THEN 2 WHEN 'read' THEN 1 ELSE 0 END) FROM json_each(agents.permissions, '$.workspaces') je JOIN workspaces w ON w.id = je.key WHERE w.kind = 'other'), 0) WHEN 4 THEN 'write' WHEN 3 THEN 'qa_report' WHEN 2 THEN 'tests' WHEN 1 THEN 'read' ELSE 'none' END
  ),
  'projectScope', 'ALL',
  'actions', json(COALESCE(json_extract(permissions, '$.actions'), '[]')),
  'ticketTransitions', json(COALESCE(json_extract(permissions, '$.ticketTransitions'), '[]')),
  'onlyAssignedTickets', CASE WHEN json_extract(permissions, '$.onlyAssignedTickets') = 0
    THEN json('false') ELSE json('true') END
)
WHERE json_type(permissions, '$.workspaces') IS NOT NULL;

-- Rastro del resultado por agente (visible en GET /api/admin/audit; sin datos sensibles).
INSERT INTO audit_log (id, user_id, action, target_type, target_id, ip, meta, created_at)
SELECT 'perm01-' || id, NULL, 'agent.permissions_migrated', 'agent', id, NULL,
  json_object('name', name, 'folderAccess', json(json_extract(permissions, '$.folderAccess')),
              'projectScope', 'ALL'),
  strftime('%Y-%m-%dT%H:%M:%fZ','now')
FROM agents WHERE json_type(permissions, '$.folderAccess') IS NOT NULL;
