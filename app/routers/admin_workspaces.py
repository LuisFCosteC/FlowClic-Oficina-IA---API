"""Administración → Espacios de trabajo (J03).

Pendiente de S09: todas estas rutas exigirán ADMIN. La ruta solo la usará el orquestador.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.db.database import Database, get_db
from app.domain.schemas import Workspace, WorkspaceBody, WorkspaceCheck
from app.errors import ErrorResponse
from app.services import workspaces_service as service

router = APIRouter(
    prefix="/api/admin/workspaces",
    tags=["Administración"],
    responses={
        400: {"model": ErrorResponse, "description": "Id o ruta no válidos"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)

Db = Annotated[Database, Depends(get_db)]


@router.get("", summary="Listar espacios de trabajo")
def list_workspaces(db: Db) -> list[Workspace]:
    return service.list_workspaces(db)


@router.put(
    "/{ws_id}",
    summary="Crear o actualizar un espacio de trabajo (id lógico → carpeta)",
    responses={201: {"model": Workspace, "description": "Creado"}},
)
def put_workspace(ws_id: str, body: WorkspaceBody, db: Db, response: Response) -> Workspace:
    ws, created = service.upsert(db, ws_id, body)
    response.status_code = 201 if created else 200
    return ws


@router.delete(
    "/{ws_id}",
    status_code=204,
    summary="Borrar un espacio de trabajo",
    responses={
        404: {"model": ErrorResponse, "description": "No existe"},
        409: {"model": ErrorResponse, "description": "Algún agente lo usa"},
    },
)
def delete_workspace(ws_id: str, db: Db) -> Response:
    service.delete(db, ws_id)
    return Response(status_code=204)


@router.post(
    "/{ws_id}/check",
    summary="Comprobar la carpeta (existe, es carpeta, es escribible; sin listar contenido)",
    responses={404: {"model": ErrorResponse, "description": "No existe"}},
)
def check_workspace(ws_id: str, db: Db) -> WorkspaceCheck:
    return service.check(db, ws_id)
