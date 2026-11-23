"""Asistente de primer arranque (modo SETUP). PLAN §16.3.

Solo desde 127.0.0.1/::1 y con el código de un solo uso impreso en la consola del servidor.
Cuando existen la BD y un ADMIN, el asistente se cierra: los POST devuelven 404.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.db.database import swap_db, try_get_db
from app.domain.schemas import CamelModel, StrictInput
from app.errors import AppError, ErrorResponse, conflict, not_found
from app.security.setup_gate import SetupGate
from app.security.vault import Vault
from app.services import setup_service

router = APIRouter(
    prefix="/api/setup",
    tags=["Configuración inicial"],
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)

LOCAL_HOSTS = {"127.0.0.1", "::1"}


class SetupStatus(CamelModel):
    setup_required: bool
    has_database: bool
    has_admin: bool


class SetupDatabaseBody(StrictInput):
    setup_code: Annotated[str, Field(min_length=1, max_length=64)]
    url: Annotated[str, Field(min_length=1, max_length=500)]
    auth_token: Annotated[str, Field(max_length=4000)] | None = None


class SetupAdminBody(StrictInput):
    setup_code: Annotated[str, Field(min_length=1, max_length=64)]
    email: Annotated[str, Field(min_length=3, max_length=254)]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


def _vault(request: Request) -> Vault | None:
    vault: Vault | None = request.app.state.vault
    return vault


def _gate(request: Request) -> SetupGate:
    gate: SetupGate = request.app.state.setup_gate
    return gate


def _status() -> SetupStatus:
    db = try_get_db()
    has_db = db is not None
    has_adm = setup_service.has_admin(db)
    return SetupStatus(
        setup_required=not (has_db and has_adm), has_database=has_db, has_admin=has_adm
    )


def _ensure_open(request: Request) -> SetupStatus:
    """404 si el asistente está cerrado (o no hay bóveda); 403 si la petición no es local."""
    status = _status()
    if _vault(request) is None or not status.setup_required:
        raise not_found("Ruta no encontrada")
    host = request.client.host if request.client else None
    if host not in LOCAL_HOSTS:
        raise AppError(
            "FORBIDDEN", "El asistente de configuración solo está disponible en localhost"
        )
    return status


@router.get("/status", summary="Estado del asistente de primer arranque")
def setup_status(request: Request) -> SetupStatus:
    status = _status()
    if status.setup_required:  # abierto: solo desde localhost
        host = request.client.host if request.client else None
        if host not in LOCAL_HOSTS:
            raise AppError("FORBIDDEN", "El asistente solo está disponible en localhost")
    return status


@router.post("/database", summary="Guardar la conexión de la base de datos")
def setup_database(
    body: SetupDatabaseBody,
    request: Request,
    gate: Annotated[SetupGate, Depends(_gate)],
) -> SetupStatus:
    status = _ensure_open(request)
    gate.verify(body.setup_code)
    if status.has_database:
        raise conflict("Ya hay una conexión de base de datos configurada")
    vault = _vault(request)
    assert vault is not None  # noqa: S101  (garantizado por _ensure_open)
    db = setup_service.connect_and_migrate(
        body.url, body.auth_token or None, request.app.state.settings.db_driver
    )
    try:
        vault.set_secret("db.url", body.url, updated_by="setup")
        if body.auth_token:
            vault.set_secret("db.auth_token", body.auth_token, updated_by="setup")
        else:
            vault.delete_secret("db.auth_token")
    except Exception:
        db.close()
        raise
    swap_db(db)
    return _status()


@router.post("/admin", summary="Crear el primer usuario ADMIN", status_code=201)
def setup_admin(
    body: SetupAdminBody,
    request: Request,
    gate: Annotated[SetupGate, Depends(_gate)],
) -> SetupStatus:
    status = _ensure_open(request)
    gate.verify(body.setup_code)
    db = try_get_db()
    if not status.has_database or db is None:
        raise conflict("Configura primero la base de datos")
    setup_service.create_first_admin(db, body.email, body.display_name, body.password)
    gate.close()  # BD + ADMIN: el asistente se cierra
    return _status()
