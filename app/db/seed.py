"""Datos de ejemplo idempotentes (`INSERT OR IGNORE`). Uso: `python -m app.db.seed`.

La semilla NO crea usuarios ni credenciales: el primer ADMIN se crea desde el asistente de
primer arranque o con `python scripts/admin_create.py` (PLAN §12.1 #13).
"""

import json
import sys
from typing import Any

from app.db.database import Database
from app.util import now_iso

AGENTS: list[dict[str, Any]] = [
    {
        "id": "sheldon",
        "name": "Sheldon",
        "character": "Sheldon Cooper",
        "role": "CTO",
        "avatar": {"color": "#F59E0B", "hairStyle": "parted"},
        "is_cto": 1,
    },
    {
        "id": "leonard",
        "name": "Leonard",
        "character": "Leonard Hofstadter",
        "role": "Senior Full-Stack",
        "avatar": {"color": "#38BDF8", "glasses": True, "hairStyle": "short"},
        "is_cto": 0,
    },
    {
        "id": "penny",
        "name": "Penny",
        "character": "Penny",
        "role": "Frontend web/móvil",
        "avatar": {"color": "#EC4899", "hairStyle": "long"},
        "is_cto": 0,
    },
    {
        "id": "raj",
        "name": "Raj",
        "character": "Rajesh Koothrappali",
        "role": "QA",
        "avatar": {"color": "#6366F1", "hairStyle": "short"},
        "is_cto": 0,
    },
]

# Tickets sin agente asignado: así los agentes semilla (IDLE) siguen coherentes con la regla R1.
TICKETS: list[dict[str, str]] = [
    {
        "id": "seed-ticket-1",
        "title": "Definir alcance de la landing",
        "description": "Reunir requisitos y secciones de la landing.",
        "status": "BACKLOG",
        "priority": "MEDIUM",
        "project": "FlowClic Web",
    },
    {
        "id": "seed-ticket-2",
        "title": "Diseñar modelo de datos de clientes",
        "description": "Tablas y relaciones iniciales.",
        "status": "IN_PROGRESS",
        "priority": "HIGH",
        "project": "FlowClic CRM",
    },
    {
        "id": "seed-ticket-3",
        "title": "Revisar flujo de autenticación",
        "description": "Pendiente de revisión técnica.",
        "status": "REVIEW",
        "priority": "MEDIUM",
        "project": "FlowClic CRM",
    },
    {
        "id": "seed-ticket-4",
        "title": "Plan de despliegue a producción",
        "description": "Requiere aprobación del CEO.",
        "status": "AWAITING_APPROVAL",
        "priority": "HIGH",
        "project": "FlowClic Web",
    },
]


def seed(db: Database) -> None:
    """Inserta los datos semilla en una sola transacción. Se puede ejecutar varias veces."""
    now = now_iso()
    with db.transaction() as tx:
        for a in AGENTS:
            tx.execute(
                "INSERT OR IGNORE INTO agents"
                " (id, name, character, role, status, avatar, is_cto, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'IDLE', ?, ?, ?, ?)",
                (
                    a["id"],
                    a["name"],
                    a["character"],
                    a["role"],
                    json.dumps(a["avatar"]),
                    a["is_cto"],
                    now,
                    now,
                ),
            )
        for i, t in enumerate(TICKETS):
            tx.execute(
                "INSERT OR IGNORE INTO tickets"
                " (id, title, description, status, priority, project, position, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    t["id"],
                    t["title"],
                    t["description"],
                    t["status"],
                    t["priority"],
                    t["project"],
                    i,
                    now,
                    now,
                ),
            )
            tx.execute(
                "INSERT OR IGNORE INTO ticket_events"
                " (id, ticket_id, type, from_value, to_value, actor, payload, created_at)"
                " VALUES (?, ?, 'CREATED', NULL, ?, 'human', '{}', ?)",
                (f"seed-event-{i + 1}", t["id"], t["status"], now),
            )
        tx.execute(
            "INSERT OR IGNORE INTO approvals (id, ticket_id, title, category, summary,"
            " reviewer_note, status, requested_at) VALUES ('seed-approval-1', 'seed-ticket-4',"
            " 'Plan de despliegue a producción', 'Despliegue', 'Despliegue inicial de la landing.',"
            " 'Revisar variables de entorno antes de aprobar.', 'PENDING', ?)",
            (now,),
        )
        tx.execute(
            "INSERT OR IGNORE INTO project_memory (id, kind, title, content, project, author,"
            " created_at, updated_at) VALUES ('seed-memory-1', 'NOTE', 'Convenciones del proyecto',"
            " 'Usar tipado estricto y commits pequeños.', 'FlowClic Web', 'human', ?, ?)",
            (now, now),
        )


def main() -> int:
    from app.config import get_settings
    from app.db.bootstrap import open_configured_database
    from app.security.vault import VaultError

    try:
        opened = open_configured_database(get_settings())
    except VaultError as exc:
        print(exc, file=sys.stderr)
        return 1
    if opened is None:
        print("No hay conexión de BD configurada (modo SETUP).", file=sys.stderr)
        return 1
    db, vault = opened
    try:
        seed(db)
        n = db.fetch_one("SELECT COUNT(*) AS n FROM agents")
        print(f"Semilla aplicada. Agentes en la BD: {n['n'] if n else 0}")
    finally:
        db.close()
        vault.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
