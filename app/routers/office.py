"""Modo de la oficina: trabajar o pausa global (desayuno, almuerzo, dormir)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db.database import Database, get_db
from app.events.bus import EventBus, get_bus
from app.services import presence_service

router = APIRouter(prefix="/api/office", tags=["Oficina"])

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]


class ModeBody(BaseModel):
    mode: Literal["work", "breakfast", "lunch", "sleep"]


@router.get("/mode", summary="Modo actual de la oficina")
def get_mode(db: Db) -> dict[str, str]:
    return {"mode": presence_service.get_mode(db)}


@router.put("/mode", summary="work reanuda; breakfast/lunch/sleep pausan a todos sin perder nada")
def put_mode(body: ModeBody, db: Db, bus: Bus) -> dict[str, str]:
    return {"mode": presence_service.set_mode(db, bus, body.mode)}
