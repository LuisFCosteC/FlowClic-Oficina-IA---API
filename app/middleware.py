"""Middlewares ASGI puros (sin BaseHTTPMiddleware: no interfieren con el streaming SSE)."""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.db.database import try_get_db
from app.errors import error_response

_ALWAYS_OPEN = ("/api/health", "/api/setup")


class SetupModeMiddleware:
    """Sin BD configurada (modo SETUP) solo responden /api/health y /api/setup/*; el resto 503."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and try_get_db() is None:
            path: str = scope["path"]
            if path.startswith("/api/") and not path.startswith(_ALWAYS_OPEN):
                response = error_response(
                    503, "SETUP_REQUIRED", "La API necesita configuración inicial (modo SETUP)"
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
