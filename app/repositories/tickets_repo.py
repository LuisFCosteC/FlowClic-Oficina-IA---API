"""Repositorio de tickets (lectura; las escrituras llegan con G05)."""

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
