"""Repositorio de tickets: lectura, alta y cambio de estado (G05 parcial)."""

import json

from app.db.database import Database, Row
from app.domain.schemas import Ticket

# Orden de columnas del tablero.
_STATUS_ORDER = (
    "CASE status WHEN 'PENDING' THEN 0 WHEN 'IN_PROGRESS' THEN 1 WHEN 'IN_QA' THEN 2"
    " WHEN 'IN_REVIEW' THEN 3 WHEN 'RETURNED' THEN 4 ELSE 5 END"
)


def row_to_ticket(r: Row) -> Ticket:
    return Ticket.model_validate(
        {
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "status": r["status"],
            "priority": r["priority"],
            "assigned_agent_id": r["assigned_agent_id"],
            "project": r["project"],
            "model_tier": r["model_tier"],
            "estimated_cost_usd": r["estimated_cost_usd"],
            "position": r["position"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "objective": r["objective"],
            "acceptance_criteria": json.loads(r["acceptance_criteria"]),
            "actions": json.loads(r["actions"]),
            "restrictions": json.loads(r["restrictions"]),
            "dependencies": json.loads(r["dependencies"]),
            "model": r["model"],
        }
    )


def list_tickets(db: Database) -> list[Ticket]:
    rows = db.fetch_all(
        f"SELECT * FROM tickets ORDER BY {_STATUS_ORDER}, position, updated_at DESC"  # noqa: S608
    )
    return [row_to_ticket(r) for r in rows]


def get_ticket(db: Database, ticket_id: str) -> Ticket | None:
    row = db.fetch_one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    return row_to_ticket(row) if row else None


def insert_ticket(db: Database, t: Ticket) -> None:
    db.execute(
        "INSERT INTO tickets (id, title, description, status, priority, assigned_agent_id,"
        " project, model_tier, estimated_cost_usd, position, created_at, updated_at,"
        " objective, acceptance_criteria, actions, restrictions, dependencies, model)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            t.id,
            t.title,
            t.description,
            t.status,
            t.priority,
            t.assigned_agent_id,
            t.project,
            t.model_tier,
            t.estimated_cost_usd,
            t.position,
            t.created_at,
            t.updated_at,
            t.objective,
            json.dumps(t.acceptance_criteria, ensure_ascii=False),
            json.dumps(t.actions, ensure_ascii=False),
            json.dumps(t.restrictions, ensure_ascii=False),
            json.dumps(t.dependencies, ensure_ascii=False),
            t.model,
        ),
    )


def set_status(db: Database, ticket_id: str, status: str, now: str) -> None:
    db.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, now, ticket_id)
    )


def count_active_for_agent(db: Database, agent_id: str, exclude_ticket: str) -> int:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM tickets WHERE assigned_agent_id = ? AND id <> ?"
        " AND status IN ('IN_PROGRESS','IN_QA','IN_REVIEW','RETURNED')",
        (agent_id, exclude_ticket),
    )
    return int(row["n"]) if row else 0


def has_approved(db: Database, ticket_id: str) -> bool:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM approvals WHERE ticket_id = ? AND status = 'APPROVED'",
        (ticket_id,),
    )
    return bool(row and int(row["n"]) > 0)


def count_pending_gates(db: Database, ticket_id: str) -> int:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM approvals WHERE ticket_id = ? AND status = 'PENDING'",
        (ticket_id,),
    )
    return int(row["n"]) if row else 0


def insert_event(
    db: Database,
    *,
    event_id: str,
    ticket_id: str,
    type_: str,
    from_value: str | None,
    to_value: str | None,
    payload: str,
    now: str,
) -> None:
    db.execute(
        "INSERT INTO ticket_events (id, ticket_id, type, from_value, to_value, actor, payload,"
        " created_at) VALUES (?, ?, ?, ?, ?, 'human', ?, ?)",
        (event_id, ticket_id, type_, from_value, to_value, payload, now),
    )
