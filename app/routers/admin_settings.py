"""Administración → proyecto, límites y reglas (PLAN §13.3). Pendiente de S09: solo ADMIN."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.db.database import Database, get_db
from app.domain.admin_schemas import (
    LimitsSettings,
    ProjectSettings,
    Rule,
    RuleCreate,
    RuleOrder,
    RuleUpdate,
)
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.services import settings_service as service

router = APIRouter(
    prefix="/api/admin",
    tags=["Administración"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]
NotFound: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "No existe"}
}


@router.get("/settings/project", summary="Datos del proyecto")
def get_project(db: Db) -> ProjectSettings:
    return service.get_project(db)


@router.put("/settings/project", summary="Guardar los datos del proyecto (emite settings.updated)")
def put_project(body: ProjectSettings, db: Db, bus: Bus) -> ProjectSettings:
    return service.put_project(db, bus, body)


@router.get("/settings/limits", summary="Límites que la API aplica")
def get_limits(db: Db) -> LimitsSettings:
    return service.get_limits(db)


@router.put("/settings/limits", summary="Guardar los límites (emite settings.updated)")
def put_limits(body: LimitsSettings, db: Db, bus: Bus) -> LimitsSettings:
    return service.put_limits(db, bus, body)


@router.get("/rules", summary="Reglas del proyecto, en orden")
def list_rules(db: Db) -> list[Rule]:
    return service.list_rules(db)


@router.post("/rules", status_code=201, summary="Crear una regla (emite rule.created)")
def create_rule(body: RuleCreate, db: Db, bus: Bus) -> Rule:
    return service.create_rule(db, bus, body)


@router.put(
    "/rules/order",
    summary="Reordenar las reglas: `ids` con TODAS las reglas en el orden nuevo",
)
def reorder_rules(body: RuleOrder, db: Db, bus: Bus) -> list[Rule]:
    return service.reorder_rules(db, bus, body)


@router.patch(
    "/rules/{rule_id}",
    summary="Editar una regla (parcial; emite rule.updated)",
    responses=NotFound,
)
def update_rule(rule_id: str, body: RuleUpdate, db: Db, bus: Bus) -> Rule:
    return service.update_rule(db, bus, rule_id, body)


@router.delete(
    "/rules/{rule_id}",
    status_code=204,
    summary="Borrar una regla (emite rule.deleted)",
    responses=NotFound,
)
def delete_rule(rule_id: str, db: Db, bus: Bus) -> Response:
    service.delete_rule(db, bus, rule_id)
    return Response(status_code=204)
