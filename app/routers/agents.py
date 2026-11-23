"""Agentes: CRUD (PLAN §5, §19). Pendiente de auth (S09): crear/editar/archivar serán solo ADMIN."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.db.database import Database, get_db
from app.domain.schemas import Agent, AgentCreate, AgentUpdate
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.services import agents_service

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
