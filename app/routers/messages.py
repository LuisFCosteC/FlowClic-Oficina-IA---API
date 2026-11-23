"""Chat de mando de la Oficina 3D (H01).

Pendiente de auth (S09): ADMIN y OPERATOR envían; VIEWER solo lee (403 en POST).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.db.database import Database, get_db
from app.domain.schemas import Message, MessageCreate, ThreadEntry
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.services import messages_service

router = APIRouter(
    prefix="/api/messages",
    tags=["Mensajes"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]


@router.get(
    "",
    summary="Hilo de un agente o del equipo (mensajes + eventos de ticket, por fecha)",
    description=(
        "`agentId=<id>`: hilo de ese agente (el de Sheldon incluye las órdenes globales y una "
        "copia de las individuales). `scope=GLOBAL`: órdenes globales y eventos de todo el equipo."
    ),
    responses={404: {"model": ErrorResponse, "description": "Agente no encontrado"}},
)
def get_thread(
    db: Db,
    agent_id: Annotated[str | None, Query(alias="agentId", max_length=64)] = None,
    scope: Literal["GLOBAL", "AGENT"] | None = None,
    limit: int = messages_service.DEFAULT_LIMIT,
) -> list[ThreadEntry]:
    return messages_service.get_thread(db, agent_id=agent_id, scope=scope, limit=limit)


@router.post(
    "",
    status_code=201,
    summary="Enviar una orden, pregunta o nota (se guarda PENDING hasta la Fase 2)",
    responses={
        404: {"model": ErrorResponse, "description": "Agente no encontrado"},
        409: {"model": ErrorResponse, "description": "El agente está archivado"},
    },
)
def post_message(body: MessageCreate, db: Db, bus: Bus) -> Message:
    return messages_service.create_message(db, bus, body)
