-- GM02 corregido: el senior revisa ANTES que QA.
--   PENDING → IN_PROGRESS → IN_SENIOR_REVIEW → IN_QA → IN_REVIEW (CTO) → DONE
-- La 014 ya estaba aplicada: aquí solo se reescriben los permisos guardados (JSON compacto o con
-- espacios). Se hace en este orden para no pisar los cambios entre sí.
--   dev:  IN_PROGRESS→IN_QA            pasa a IN_PROGRESS→IN_SENIOR_REVIEW
--   QA:   IN_QA→IN_SENIOR_REVIEW (014) vuelve a IN_QA→IN_REVIEW
UPDATE agents SET permissions = replace(permissions, '["IN_PROGRESS","IN_QA"]', '["IN_PROGRESS","IN_SENIOR_REVIEW"]');
UPDATE agents SET permissions = replace(permissions, '["IN_PROGRESS", "IN_QA"]', '["IN_PROGRESS", "IN_SENIOR_REVIEW"]');
UPDATE agents SET permissions = replace(permissions, '["IN_QA","IN_SENIOR_REVIEW"]', '["IN_QA","IN_REVIEW"]');
UPDATE agents SET permissions = replace(permissions, '["IN_QA", "IN_SENIOR_REVIEW"]', '["IN_QA", "IN_REVIEW"]');
