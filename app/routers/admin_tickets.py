"""Administración → limpiar tickets (solo el CEO/ADMIN; los agentes no se tocan)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.events.bus import EventBus, get_bus
from app.services import tickets_service

router = APIRouter(prefix="/api/admin/tickets", tags=["Administración"])

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]


@router.delete("", summary="Borrar tickets: solo los HECHOS (done) o todos (all)")
def purge(scope: Literal["done", "all"], db: Db, bus: Bus) -> dict[str, int]:
    return {"deleted": tickets_service.purge_tickets(db, bus, scope)}
