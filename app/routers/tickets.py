"""Tickets: listar, crear y mover por el flujo de PLAN §19.4.

Pendiente de auth (S09): crear y mover serán ADMIN/OPERATOR; VIEWER solo lee.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.domain.schemas import Ticket, TicketCreate, TicketTransitionBody
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.repositories import tickets_repo
from app.services import tickets_service

router = APIRouter(
    prefix="/api/tickets",
    tags=["Tickets"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        404: {"model": ErrorResponse, "description": "Ticket no encontrado"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]


@router.get("", summary="Listar tickets (orden del tablero)")
def list_tickets(db: Db) -> list[Ticket]:
    return tickets_repo.list_tickets(db)


@router.get("/{ticket_id}", summary="Detalle de un ticket")
def get_ticket(ticket_id: str, db: Db) -> Ticket:
    return tickets_service.get_ticket_or_404(db, ticket_id)


@router.post("", status_code=201, summary="Crear un ticket (empieza en PENDIENTE)")
def create_ticket(body: TicketCreate, db: Db, bus: Bus) -> Ticket:
    return tickets_service.create_ticket(db, bus, body)


@router.post(
    "/{ticket_id}/transition",
    summary="Mover un ticket por el flujo (solo transiciones válidas del grafo)",
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Transición inválida (INVALID_TRANSITION) o compuertas pendientes",
        }
    },
)
def transition(ticket_id: str, body: TicketTransitionBody, db: Db, bus: Bus) -> Ticket:
    return tickets_service.transition(db, bus, ticket_id, body)
