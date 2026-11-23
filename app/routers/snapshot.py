"""Carga inicial del front en una sola petición (PLAN §5)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.domain.schemas import Agent, Approval, CamelModel, Ticket
from app.errors import ErrorResponse
from app.repositories import agents_repo, approvals_repo, tickets_repo
from app.util import now_iso

router = APIRouter(prefix="/api", tags=["Tiempo real"])


class Snapshot(CamelModel):
    agents: list[Agent]
    tickets: list[Ticket]
    approvals: list[Approval]
    server_time: str


@router.get(
    "/snapshot",
    summary="Estado completo (agentes activos, tickets y aprobaciones) para la carga inicial",
    responses={503: {"model": ErrorResponse, "description": "API en modo SETUP"}},
)
def snapshot(db: Annotated[Database, Depends(get_db)]) -> Snapshot:
    return Snapshot(
        agents=agents_repo.list_agents(db),
        tickets=tickets_repo.list_tickets(db),
        approvals=approvals_repo.list_approvals(db),
        server_time=now_iso(),
    )
