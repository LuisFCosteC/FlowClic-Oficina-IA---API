"""Repositorio de aprobaciones/compuertas (lectura; las escrituras llegan con G06)."""

from app.db.database import Database, Row
from app.domain.schemas import Approval


def row_to_approval(r: Row) -> Approval:
    return Approval.model_validate(
        {
            "id": r["id"],
            "ticket_id": r["ticket_id"],
            "agent_id": r["agent_id"],
            "gate": r["gate"],
            "title": r["title"],
            "category": r["category"],
            "summary": r["summary"],
            "reviewer_note": r["reviewer_note"],
            "estimated_tokens": r["estimated_tokens"],
            "status": r["status"],
            "decision_note": r["decision_note"],
            "decided_by": r["decided_by"],
            "requested_at": r["requested_at"],
            "decided_at": r["decided_at"],
        }
    )


def list_approvals(db: Database) -> list[Approval]:
    """Más recientes primero."""
    rows = db.fetch_all("SELECT * FROM approvals ORDER BY requested_at DESC, id")
    return [row_to_approval(r) for r in rows]


def get_approval(db: Database, approval_id: str) -> Approval | None:
    row = db.fetch_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    return row_to_approval(row) if row else None
