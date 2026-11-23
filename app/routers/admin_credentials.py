"""Administración → Agentes → Conexiones API (PLAN §16.6).

La clave se envía una sola vez y NUNCA se devuelve (solo `last4`).
Pendiente de S09: todas estas rutas exigirán ADMIN + MFA reciente.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.db.database import Database, get_db
from app.domain.schemas import AgentCredential, CredentialCreate, CredentialRotate
from app.errors import ErrorResponse
from app.security.crypto import SecretBox
from app.services import credentials_service as service

router = APIRouter(
    prefix="/api/admin",
    tags=["Administración"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        404: {"model": ErrorResponse, "description": "Agente o conexión no encontrados"},
        503: {"model": ErrorResponse, "description": "Modo SETUP o falta APP_MASTER_KEY"},
    },
)

Db = Annotated[Database, Depends(get_db)]


def get_box(request: Request) -> SecretBox:
    return service.box_from_key(request.app.state.settings.app_master_key)


Box = Annotated[SecretBox, Depends(get_box)]


@router.get("/credentials", summary="Todas las conexiones API activas (sin claves)")
def list_all(db: Db) -> list[AgentCredential]:
    return service.list_all_active(db)


@router.get("/agents/{agent_id}/credentials", summary="Conexiones API activas de un agente")
def list_for_agent(agent_id: str, db: Db) -> list[AgentCredential]:
    return service.list_credentials(db, agent_id)


@router.post(
    "/agents/{agent_id}/credentials",
    status_code=201,
    summary="Añadir una conexión API a un agente (la clave se guarda cifrada)",
    responses={
        409: {"model": ErrorResponse, "description": "Etiqueta repetida o agente archivado"}
    },
)
def add(agent_id: str, body: CredentialCreate, db: Db, box: Box) -> AgentCredential:
    return service.add_credential(db, box, agent_id, body)


@router.post(
    "/agents/{agent_id}/credentials/{cred_id}/rotate",
    summary="Rotar la clave de una conexión (sustituye la anterior)",
    responses={409: {"model": ErrorResponse, "description": "Conexión revocada"}},
)
def rotate(
    agent_id: str, cred_id: str, body: CredentialRotate, db: Db, box: Box
) -> AgentCredential:
    return service.rotate_credential(db, box, agent_id, cred_id, body)


@router.delete(
    "/agents/{agent_id}/credentials/{cred_id}",
    status_code=204,
    summary="Revocar una conexión (idempotente)",
)
def revoke(agent_id: str, cred_id: str, db: Db) -> Response:
    service.revoke_credential(db, agent_id, cred_id)
    return Response(status_code=204)
