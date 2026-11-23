"""Middlewares ASGI puros (sin BaseHTTPMiddleware: no interfieren con el streaming SSE)."""

import logging
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


# ── S01: endurecimiento HTTP ─────────────────────────────────────────────────────────────────
MAX_BODY_BYTES = 100 * 1024

_API_CSP = "default-src 'none'; frame-ancestors 'none'"
# Swagger UI / ReDoc cargan JS y CSS desde un CDN y usan scripts en línea.
_DOCS_CSP = (
    "default-src 'none'; frame-ancestors 'none'; connect-src 'self'; worker-src blob:; "
    "img-src 'self' data: https://fastapi.tiangolo.com; font-src https://cdn.jsdelivr.net data:; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
)
_DOCS_PREFIXES = ("/docs", "/redoc", "/api/docs", "/api/redoc")


log = logging.getLogger("flowclic")


class SecurityMiddleware:
    """Cabeceras de seguridad, `X-Request-Id`, límite de body (100 kB) y requestId para logs.

    - Pasado el límite el cuerpo se corta como una desconexión (la ruta NO se ejecuta, así que
      un cuerpo truncado no puede llegar a ser válido) y la respuesta se sustituye por un 413.
    - Los errores no controlados se responden aquí con 500 (sin detalles) para que también
      lleven las cabeceras y el `X-Request-Id`, y se registran con ese id.
    - No añade ninguna cabecera que revele el software o su versión (uvicorn se arranca con
      `--no-server-header`).
    """

    def __init__(self, app: ASGIApp, max_body: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        csp = _DOCS_CSP if scope["path"].startswith(_DOCS_PREFIXES) else _API_CSP
        started = False
        too_large = False
        replaced = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = request_id
                headers["Content-Security-Policy"] = csp
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Frame-Options"] = "DENY"
            await send(message)

        async def send_wrapper(message: Message) -> None:
            nonlocal replaced
            if too_large:  # se descarta la respuesta de la app y se responde 413
                if not replaced:
                    replaced = True
                    await self._too_large(scope, receive, send_with_headers)
                return
            await send_with_headers(message)

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body:
            await self._too_large(scope, receive, send_with_headers)
            return

        received = 0

        async def receive_wrapper() -> Message:
            nonlocal received, too_large
            if too_large:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception as exc:
            if too_large and not started and not replaced:
                await send_wrapper({"type": "http.response.start", "status": 0, "headers": []})
                return
            if started or replaced:
                raise
            log.error(
                "[%s] error no controlado en %s %s: %s",
                request_id,
                scope["method"],
                scope["path"],
                type(exc).__name__,
            )
            await error_response(500, "INTERNAL", "Error interno del servidor")(
                scope, receive, send_with_headers
            )
            return
        if too_large and not replaced and not started:
            await send_wrapper({"type": "http.response.start", "status": 0, "headers": []})

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = error_response(
            413, "PAYLOAD_TOO_LARGE", "El cuerpo de la petición es demasiado grande (máx. 100 kB)"
        )
        await response(scope, receive, send)
