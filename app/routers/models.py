"""Catálogo de modelos para el FRONT (J02).

Los ids `gemini-pro` y `gemini-flash` son lógicos: los ids exactos de la API de Gemini se fijan
con el orquestador (Fase 2). En la Fase 1 los modelos solo se registran; nadie los llama.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.db.database import Database, get_db
from app.domain.models_catalog import MODELS_CATALOG
from app.domain.schemas import CamelModel
from app.errors import ErrorResponse
from app.services import key_pool

router = APIRouter(prefix="/api", tags=["Modelos"])


class ModelInfo(CamelModel):
    id: str
    label: str
    provider: str
    api_model: str
    has_connection: bool


@router.get(
    "/models",
    summary="Catálogo de modelos y si hay una clave usable (bolsa global) del proveedor",
    responses={503: {"model": ErrorResponse, "description": "API en modo SETUP"}},
)
def list_models(db: Annotated[Database, Depends(get_db)]) -> list[ModelInfo]:
    usable = key_pool.usable_models(db, [(m.id, m.provider) for m in MODELS_CATALOG])
    return [
        ModelInfo(
            id=m.id,
            label=m.label,
            provider=m.provider,
            api_model=m.api_model,
            has_connection=usable[m.id],
        )
        for m in MODELS_CATALOG
    ]
