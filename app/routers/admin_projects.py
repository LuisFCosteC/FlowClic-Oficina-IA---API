"""Administración → Proyectos (PRJ01). Pendiente de S09: todas estas rutas exigirán ADMIN."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.db.database import Database, get_db
from app.domain.schemas import Project, ProjectCreate, ProjectUpdate
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.services import projects_service as service

router = APIRouter(
    prefix="/api/admin/projects",
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


@router.get("", summary="Listar proyectos (`?includeArchived=true` incluye los archivados)")
def list_projects(
    db: Db, include_archived: Annotated[bool, Query(alias="includeArchived")] = False
) -> list[Project]:
    return service.list_projects(db, include_archived)


@router.post(
    "",
    status_code=201,
    summary="Crear un proyecto (emite project.created)",
    responses={409: {"model": ErrorResponse, "description": "El id ya existe"}},
)
def create_project(body: ProjectCreate, db: Db, bus: Bus) -> Project:
    return service.create(db, bus, body)


@router.patch(
    "/{project_id}",
    summary="Editar un proyecto (parcial; emite project.updated)",
    responses=NotFound,
)
def update_project(project_id: str, body: ProjectUpdate, db: Db, bus: Bus) -> Project:
    return service.update(db, bus, project_id, body)


@router.post(
    "/{project_id}/archive",
    summary="Archivar (emite project.archived)",
    responses={
        **NotFound,
        409: {"model": ErrorResponse, "description": "Tiene tickets activos"},
    },
)
def archive_project(project_id: str, db: Db, bus: Bus) -> Project:
    return service.archive(db, bus, project_id)


@router.post(
    "/{project_id}/restore",
    summary="Restaurar un proyecto archivado (emite project.updated)",
    responses=NotFound,
)
def restore_project(project_id: str, db: Db, bus: Bus) -> Project:
    return service.restore(db, bus, project_id)
