"""Administración → herramientas de agentes (GM01): probar `gemini_models` a mano.

Pendiente de S09: estas rutas exigirán ADMIN.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.errors import ErrorResponse
from app.events.bus import EventBus, get_bus
from app.orchestrator import tools
from app.routers.admin_keys import get_box
from app.security.crypto import SecretBox
from app.services.key_pool import KeyPool

router = APIRouter(
    prefix="/api/admin/tools",
    tags=["Administración"],
    responses={
        503: {"model": ErrorResponse, "description": "Sin clave disponible o sin APP_MASTER_KEY"},
        502: {"model": ErrorResponse, "description": "Error del proveedor"},
    },
)

Db = Annotated[Database, Depends(get_db)]
Bus = Annotated[EventBus, Depends(get_bus)]
Box = Annotated[SecretBox, Depends(get_box)]


def get_http_get() -> tools.HttpGet:
    return tools.default_http_get


@router.get("/gemini-models", summary="Herramienta gemini_models: modelos Gemini disponibles")
def gemini_models(
    db: Db, bus: Bus, box: Box, http_get: Annotated[tools.HttpGet, Depends(get_http_get)]
) -> list[tools.GeminiModelInfo]:
    return tools.gemini_models(KeyPool(db, box, bus), http_get)
