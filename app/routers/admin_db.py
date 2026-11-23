"""Administración → conexión de BD y backup (A05). Pendiente de S09: ADMIN + MFA reciente."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import Settings
from app.db.database import Database, get_db
from app.domain.admin_schemas import BackupResult, DbStatus, DbTestBody, DbTestResult
from app.errors import AppError, ErrorResponse
from app.events.bus import EventBus, get_bus
from app.security.setup_gate import SetupGate
from app.security.vault import Vault
from app.services import db_admin_service as service

router = APIRouter(
    prefix="/api/admin",
    tags=["Administración"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        503: {"model": ErrorResponse, "description": "Sin bóveda (ENCRYPTION_UNAVAILABLE)"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]


def _vault(request: Request) -> Vault:
    vault: Vault | None = request.app.state.vault
    if vault is None:
        raise AppError("ENCRYPTION_UNAVAILABLE", "La bóveda cifrada no está disponible")
    return vault


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get(
    "/db",
    summary="Estado de la conexión de BD (nunca devuelve el token)",
)
def get_db_status(request: Request) -> DbStatus:
    return service.status(_vault(request), _settings(request))


@router.post(
    "/db/test",
    summary="Probar una conexión sin cambiar nada (solo file:, libsql:// y https://; máx. 5 s)",
    responses={422: {"model": ErrorResponse, "description": "No se pudo conectar"}},
)
def test_db(body: DbTestBody, request: Request) -> DbTestResult:
    return service.probe_connection(body.url, body.auth_token, _settings(request))


@router.put(
    "/db",
    summary="Cambiar de BD en caliente (prueba, migra y guarda en la bóveda)",
    description=(
        "Exige `ADMIN_ALLOW_DB_CHANGE=true` (si no, 403). `authToken` vacío conserva el token "
        "guardado solo si la URL es idéntica. Cambiar de BD no copia los datos."
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Cambio de BD desactivado"},
        422: {
            "model": ErrorResponse,
            "description": "No se pudo conectar o migrar (no cambia nada)",
        },
    },
)
def put_db(body: DbTestBody, request: Request, bus: Bus) -> DbStatus:
    gate: SetupGate | None = request.app.state.setup_gate
    return service.change_database(
        body.url,
        body.auth_token,
        vault=_vault(request),
        settings=_settings(request),
        bus=bus,
        gate=gate,
    )


@router.post(
    "/backup",
    summary="Backup manual inmediato (carpeta con permisos solo para el propietario)",
)
def create_backup(request: Request, db: Db) -> BackupResult:
    return service.manual_backup(db, _settings(request))
