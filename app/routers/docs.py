"""Documentación de la API bajo `/api/docs` (P03).

Se sirve en `/api/...` para que reciba la cookie de sesión (`Path=/api`). Reglas:
- `DOCS_ENABLED=false` → 404 (por defecto, apagada en producción).
- Hasta que exista la autenticación (S09): solo desde 127.0.0.1. Con S09 exigirá sesión
  ADMIN u OPERATOR (sin sesión → 401).
- `/docs`, `/redoc` y `/openapi.json` en la raíz NO existen (404).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from app.errors import not_found
from app.security.localhost import is_local_request


def _guard(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.docs_active or not is_local_request(request):
        raise not_found("Ruta no encontrada")  # no se revela que la documentación existe


router = APIRouter(prefix="/api", include_in_schema=False, dependencies=[Depends(_guard)])

OPENAPI_URL = "/api/openapi.json"


@router.get("/openapi.json")
def openapi_schema(request: Request) -> JSONResponse:
    return JSONResponse(request.app.openapi())


@router.get("/docs")
def swagger_ui(request: Request) -> HTMLResponse:
    return get_swagger_ui_html(openapi_url=OPENAPI_URL, title=f"{request.app.title} - Swagger UI")


@router.get("/redoc")
def redoc(request: Request) -> HTMLResponse:
    return get_redoc_html(openapi_url=OPENAPI_URL, title=f"{request.app.title} - ReDoc")
