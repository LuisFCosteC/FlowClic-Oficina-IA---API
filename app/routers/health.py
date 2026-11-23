from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.db.database import try_get_db

router = APIRouter(prefix="/api", tags=["Salud"])


class Health(BaseModel):
    ok: bool
    db: str
    version: str


@router.get("/health", summary="Estado de la API y de la base de datos")
def health() -> Health:
    db = try_get_db()
    if db is None:  # modo SETUP: la API vive, pero aún no hay BD configurada
        return Health(ok=True, db="setup", version=__version__)
    db.fetch_one("SELECT 1 AS ok")
    return Health(ok=True, db="up", version=__version__)
