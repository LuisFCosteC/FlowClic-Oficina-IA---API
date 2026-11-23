"""Administración → usuarios y auditoría (A07). Pendiente de S09: solo ADMIN (+ MFA reciente)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.db.database import Database, get_db
from app.domain.admin_schemas import AdminUser, AuditEntry, UserCreate, UserUpdate
from app.errors import ErrorResponse
from app.services import audit_service, users_service

router = APIRouter(
    prefix="/api/admin",
    tags=["Administración"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)

Db = Annotated[Database, Depends(get_db)]
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "No existe"}
}


@router.get(
    "/audit",
    summary="Auditoría (solo lectura, más reciente primero; sin secretos)",
)
def list_audit(
    db: Db,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    action: Annotated[str, Query(max_length=80)] = "",
    date_from: Annotated[str, Query(alias="from", max_length=40)] = "",
    date_to: Annotated[str, Query(alias="to", max_length=40)] = "",
) -> list[AuditEntry]:
    return audit_service.list_entries(
        db, limit=limit, action=action or None, date_from=date_from, date_to=date_to
    )


@router.get("/users", summary="Listar usuarios (sin hash de contraseña ni secreto MFA)")
def list_users(db: Db) -> list[AdminUser]:
    return users_service.list_users(db)


@router.post(
    "/users",
    status_code=201,
    summary="Crear usuario (contraseña inicial de 12 caracteres como mínimo; no se devuelve)",
    responses={409: {"model": ErrorResponse, "description": "Email ya registrado"}},
)
def create_user(body: UserCreate, db: Db) -> AdminUser:
    return users_service.create_user(db, body)


@router.patch(
    "/users/{user_id}",
    summary="Editar nombre, rol o desactivar/reactivar",
    responses={
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Es el último ADMIN activo"},
    },
)
def update_user(user_id: str, body: UserUpdate, db: Db) -> AdminUser:
    return users_service.update_user(db, user_id, body)


@router.post(
    "/users/{user_id}/revoke-sessions",
    summary="Revocar todas las sesiones del usuario (501 hasta que exista S06)",
    responses={
        **_NOT_FOUND,
        501: {"model": ErrorResponse, "description": "Pendiente de S06"},
    },
)
def revoke_sessions(user_id: str, db: Db) -> None:
    users_service.revoke_sessions(db, user_id)
