"""Plantillas de agente y carga del equipo base (PLAN §19.6).

Pendiente de autenticación (S06–S09): "Cargar equipo base" será solo ADMIN.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.domain.agent_templates import TEMPLATES, AgentTemplate
from app.domain.schemas import Agent, CamelModel
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.services import agents_service

router = APIRouter(prefix="/api", responses={503: {"model": ErrorResponse}})


class LoadTeamResult(CamelModel):
    created: list[Agent]
    skipped: list[str]


@router.get(
    "/agent-templates",
    tags=["Agentes"],
    summary="Plantillas de agente por rol (CTO, Dev Backend, Dev Frontend, QA, Personalizado)",
)
def list_templates() -> list[AgentTemplate]:
    return list(TEMPLATES)


@router.post(
    "/admin/agents/load-base-team",
    tags=["Administración"],
    summary="Cargar el equipo base (Sheldon, Leonard, Penny y Raj). Idempotente",
)
def load_base_team(
    db: Annotated[Database, Depends(get_db)],
    bus: Annotated[EventBus, Depends(get_bus)],
) -> LoadTeamResult:
    created, skipped = agents_service.load_base_team(db, bus)
    return LoadTeamResult(created=created, skipped=skipped)
