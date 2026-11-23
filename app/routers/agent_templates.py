"""Plantillas de agente por rol (PLAN §19.6). El equipo se siembra con scripts/seed_team.py."""

from fastapi import APIRouter

from app.domain.agent_templates import TEMPLATES, AgentTemplate
from app.errors import ErrorResponse

router = APIRouter(prefix="/api", responses={503: {"model": ErrorResponse}})


@router.get(
    "/agent-templates",
    tags=["Agentes"],
    summary="Plantillas de agente por rol (CTO, Dev Backend, Dev Frontend, QA, Personalizado)",
)
def list_templates() -> list[AgentTemplate]:
    return list(TEMPLATES)
