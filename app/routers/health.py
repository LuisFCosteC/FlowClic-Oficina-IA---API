from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.db.database import Database, get_db

router = APIRouter(prefix="/api", tags=["Salud"])


class Health(BaseModel):
    ok: bool
    db: str
    version: str


@router.get("/health", summary="Estado de la API y de la base de datos")
def health(db: Annotated[Database, Depends(get_db)]) -> Health:
    db.fetch_one("SELECT 1 AS ok")
    return Health(ok=True, db="up", version=__version__)
