"""Administración → estado del orquestador: ¿está trabajando y, si no, por qué?"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.orchestrator.service import STATUS

router = APIRouter(prefix="/api/admin/orchestrator", tags=["Administración"])

Db = Annotated[Database, Depends(get_db)]


@router.get("", summary="Estado del orquestador y de su cola")
def orchestrator_status(db: Db) -> dict[str, Any]:
    pending = db.fetch_one(
        "SELECT COUNT(*) AS n FROM agent_messages"
        " WHERE author_type = 'HUMAN' AND status = 'PENDING'"
    )
    by_status = db.fetch_all(
        "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status ORDER BY status"
    )
    return {
        **STATUS,
        "pendingMessages": int(pending["n"]) if pending else 0,
        "tickets": {str(r["status"]): int(r["n"]) for r in by_status},
    }
