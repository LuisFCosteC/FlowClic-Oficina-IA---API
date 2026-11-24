"""Rutas antiguas de credenciales por agente (F07/C05): RETIRADAS por KEY01 → 410 Gone.

Las claves ahora son una bolsa global por proveedor en `/api/admin/keys`.
"""

from fastapi import APIRouter

from app.errors import AppError, ErrorResponse

router = APIRouter(
    prefix="/api/admin",
    tags=["Administración"],
    responses={410: {"model": ErrorResponse, "description": "Retirada: usa /api/admin/keys"}},
    deprecated=True,
)

_MESSAGE = (
    "Las credenciales por agente se retiraron: las claves API son una bolsa global por "
    "proveedor. Usa /api/admin/keys"
)


@router.api_route("/credentials", methods=["GET", "POST"], include_in_schema=False)
@router.api_route(
    "/agents/{agent_id}/credentials", methods=["GET", "POST"], summary="Retirada (410 Gone)"
)
@router.api_route(
    "/agents/{agent_id}/credentials/{cred_id}",
    methods=["GET", "PUT", "PATCH", "DELETE"],
    summary="Retirada (410 Gone)",
)
@router.api_route(
    "/agents/{agent_id}/credentials/{cred_id}/rotate",
    methods=["POST"],
    summary="Retirada (410 Gone)",
)
def gone() -> None:
    raise AppError("GONE", _MESSAGE)
