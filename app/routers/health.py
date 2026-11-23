from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.db.database import DatabaseError, try_get_db

router = APIRouter(prefix="/api", tags=["Salud"])


class Health(BaseModel):
    ok: bool


@router.get(
    "/health", summary="La API está viva (sin detalles: no revela versión ni estado interno)"
)
def health(response: Response) -> Health:
    """Sin sesión solo responde `{"ok": true}`. En modo SETUP (sin BD) la API vive igualmente."""
    db = try_get_db()
    if db is not None:
        try:
            db.fetch_one("SELECT 1 AS ok")
        except DatabaseError:
            response.status_code = 503
            return Health(ok=False)
    return Health(ok=True)
