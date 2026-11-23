"""Agentes: CRUD (PLAN §5, §19). Pendiente de auth (S09): crear/editar/archivar serán solo ADMIN."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

from app.db.database import Database, get_db
from app.domain.schemas import (
    Agent,
    AgentCreate,
    AgentStatusBody,
    AgentUpdate,
    StatusSummary,
    StrictInput,
)
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.services import agents_service, messages_service
from app.services.agent_guard import AgentGuard

router = APIRouter(
    prefix="/api/agents",
    tags=["Agentes"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        404: {"model": ErrorResponse, "description": "Agente no encontrado"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]


@router.get("", summary="Listar agentes")
def list_agents(
    db: Db, include_archived: Annotated[bool, Query(alias="includeArchived")] = False
) -> list[Agent]:
    return agents_service.list_agents(db, include_archived)


@router.get("/{agent_id}", summary="Detalle de un agente")
def get_agent(agent_id: str, db: Db) -> Agent:
    return agents_service.get_agent_or_404(db, agent_id)


@router.post(
    "",
    status_code=201,
    summary="Crear un agente (el prompt lo genera el servidor)",
    responses={
        409: {"model": ErrorResponse, "description": "Ya existe un agente activo con ese nombre"},
        422: {"model": ErrorResponse, "description": "Viola una restricción global"},
    },
)
def create_agent(body: AgentCreate, db: Db, bus: Bus) -> Agent:
    return agents_service.create_agent(db, bus, body)


@router.patch(
    "/{agent_id}",
    summary="Editar un agente (parcial; no admite status ni system_prompt)",
    responses={
        409: {"model": ErrorResponse, "description": "Nombre duplicado"},
        422: {"model": ErrorResponse, "description": "Viola una restricción global"},
    },
)
def update_agent(agent_id: str, body: AgentUpdate, db: Db, bus: Bus) -> Agent:
    return agents_service.update_agent(db, bus, agent_id, body)


@router.delete(
    "/{agent_id}",
    status_code=204,
    summary="Archivar un agente (borrado lógico)",
    responses={
        409: {"model": ErrorResponse, "description": "Tiene tickets o aprobaciones abiertos"}
    },
)
def archive_agent(agent_id: str, db: Db, bus: Bus) -> Response:
    agents_service.archive_agent(db, bus, agent_id)
    return Response(status_code=204)


@router.post(
    "/{agent_id}/archive",
    summary="Archivar un agente (igual que DELETE, pero devuelve el agente archivado)",
    responses={
        409: {"model": ErrorResponse, "description": "Tiene tickets o aprobaciones abiertos"}
    },
)
def archive_agent_post(agent_id: str, db: Db, bus: Bus) -> Agent:
    agents_service.archive_agent(db, bus, agent_id)
    return agents_service.get_agent_or_404(db, agent_id)


@router.post(
    "/{agent_id}/restore",
    summary="Restaurar un agente archivado (respeta maxAgents y el nombre único)",
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Nombre en uso (CONFLICT) o máximo de agentes (LIMIT_EXCEEDED)",
        }
    },
)
def restore_agent(agent_id: str, db: Db, bus: Bus) -> Agent:
    return agents_service.restore_agent(db, bus, agent_id)


@router.patch(
    "/{agent_id}/status",
    summary="Cambio manual de estado (IDLE, WORKING, REVIEW, BLOCKED o SLEEP_QUOTA)",
    responses={409: {"model": ErrorResponse, "description": "El agente está archivado"}},
)
def set_agent_status(agent_id: str, body: AgentStatusBody, db: Db, bus: Bus) -> Agent:
    return agents_service.set_agent_status(db, bus, agent_id, body)


class FailureReport(StrictInput):
    """Cuerpo del endpoint de pruebas de la Fase 1 (lo ejercerá el orquestador en la Fase 2)."""

    outcome: Literal["failure", "success"]
    usd_today: Annotated[float, Field(ge=0, le=1_000_000)] | None = None


@router.post(
    "/{agent_id}/failures",
    summary="Registrar un fallo o un éxito del agente (pruebas de la Fase 1; solo ADMIN)",
    description=(
        "`failure` suma un fallo seguido (al 3.º el agente pasa a BLOCKED); `success` reinicia el "
        "contador. Si se envía `usdToday`, además se comprueba el tope diario de coste."
    ),
    responses={409: {"model": ErrorResponse, "description": "El agente está archivado"}},
)
def report_outcome(agent_id: str, body: FailureReport, db: Db, bus: Bus) -> Agent:
    guard = AgentGuard(db, bus)
    agent = (
        guard.record_failure(agent_id)
        if body.outcome == "failure"
        else guard.record_success(agent_id)
    )
    if body.usd_today is not None:
        agent = guard.check_budget(agent_id, body.usd_today)
    return agent


@router.get(
    "/{agent_id}/status-summary",
    summary='Resumen "qué hace / qué le falta" (ticket actual, bloqueo y siguiente paso)',
)
def status_summary(agent_id: str, db: Db) -> StatusSummary:
    return messages_service.status_summary(db, agent_id)
