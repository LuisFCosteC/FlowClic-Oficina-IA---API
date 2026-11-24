"""Administración → Claves API (bolsa GLOBAL por proveedor, KEY01).

La clave se envía una sola vez y NUNCA se devuelve (solo `last4`).
Pendiente de S09: todas estas rutas exigirán ADMIN + MFA reciente.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app.db.database import Database, get_db
from app.domain.key_schemas import (
    KeyCreate,
    KeyOrder,
    KeyRotate,
    KeyTestResult,
    KeyUpdate,
    ProviderKey,
)
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.repositories import keys_repo
from app.security.crypto import CryptoError, SecretBox
from app.services import key_service as service
from app.services.key_tester import KeyTester, http_key_tester

router = APIRouter(
    prefix="/api/admin/keys",
    tags=["Administración"],
    responses={
        400: {"model": ErrorResponse, "description": "Datos inválidos"},
        503: {"model": ErrorResponse, "description": "Modo SETUP o falta APP_MASTER_KEY"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]
NotFound: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Clave no encontrada"}
}


def get_box(request: Request) -> SecretBox:
    return service.box_from_key(request.app.state.settings.app_master_key)


def get_key_tester() -> KeyTester:
    return http_key_tester


Box = Annotated[SecretBox, Depends(get_box)]
Tester = Annotated[KeyTester, Depends(get_key_tester)]


@router.get("", summary="Claves (sin el valor): metadatos, uso de hoy y total por modelo, estado")
def list_keys(db: Db) -> list[ProviderKey]:
    return service.list_keys(db)


@router.post(
    "",
    status_code=201,
    summary="Añadir una clave a la bolsa (se guarda cifrada)",
    responses={409: {"model": ErrorResponse, "description": "Etiqueta repetida en el proveedor"}},
)
def create_key(body: KeyCreate, db: Db, box: Box, bus: Bus) -> ProviderKey:
    return service.create_key(db, box, bus, body)


@router.put(
    "/order",
    summary="Reordenar: `ids` con TODAS las claves no revocadas, de la primera a la última",
)
def reorder(body: KeyOrder, db: Db, bus: Bus) -> list[ProviderKey]:
    return service.reorder(db, bus, body)


@router.patch(
    "/{key_id}",
    summary="Editar etiqueta y límites diarios (un límite en null lo quita)",
    responses=NotFound,
)
def update_key(key_id: str, body: KeyUpdate, db: Db, bus: Bus) -> ProviderKey:
    return service.update_key(db, bus, key_id, body)


@router.post(
    "/{key_id}/rotate",
    summary="Sustituir el valor de la clave",
    responses={**NotFound, 409: {"model": ErrorResponse, "description": "Clave revocada"}},
)
def rotate(key_id: str, body: KeyRotate, db: Db, box: Box, bus: Bus) -> ProviderKey:
    return service.rotate_key(db, box, bus, key_id, body)


@router.delete(
    "/{key_id}", status_code=204, summary="Revocar la clave (idempotente)", responses=NotFound
)
def revoke(key_id: str, db: Db, bus: Bus) -> Response:
    service.revoke_key(db, bus, key_id)
    return Response(status_code=204)


@router.post(
    "/{key_id}/reactivate",
    summary="Volver a activar una clave revocada, inválida o agotada",
    responses={**NotFound, 409: {"model": ErrorResponse, "description": "Etiqueta ya en uso"}},
)
def reactivate(key_id: str, db: Db, bus: Bus) -> ProviderKey:
    return service.reactivate_key(db, bus, key_id)


@router.post(
    "/{key_id}/test",
    summary="Probar la clave con una llamada que no gasta tokens (en Google, models.list)",
    responses=NotFound,
)
def test_key(key_id: str, db: Db, box: Box, tester: Tester) -> KeyTestResult:
    row = service.get_or_404(db, key_id)
    sealed = keys_repo.get_sealed(db, key_id)
    if sealed is None:
        service.get_or_404(db, key_id)
        return KeyTestResult(ok=False, status="ERROR", message="La clave guardada no existe")
    try:
        secret = box.decrypt_text("provider-keys", sealed, service.aad(row.provider, key_id))
    except CryptoError:
        return KeyTestResult(
            ok=False, status="ERROR", message="No se pudo descifrar la clave guardada"
        )
    return tester(row.provider, secret)
