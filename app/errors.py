"""Formato único de error (PLAN §5): `{"error": {"code", "message", "details"}}`."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("flowclic")

STATUS_BY_CODE: dict[str, int] = {
    "VALIDATION_ERROR": 400,
    "UNAUTHENTICATED": 401,
    "FORBIDDEN": 403,
    "MFA_REQUIRED": 403,
    "MFA_SETUP_REQUIRED": 403,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "CONFLICT": 409,
    "LIMIT_EXCEEDED": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "UNPROCESSABLE": 422,
    "GLOBAL_RESTRICTION": 422,
    "INVALID_TRANSITION": 409,
    "TRANSITION_FORBIDDEN": 403,
    "GATE_PENDING": 409,
    "SUBTASKS_PENDING": 409,
    "TOO_MANY_REQUESTS": 429,
    "INTERNAL": 500,
    "NOT_IMPLEMENTED": 501,
    "GONE": 410,
    "UPSTREAM_ERROR": 502,
    "NO_KEY_AVAILABLE": 503,
    "SETUP_REQUIRED": 503,
    "MIGRATION_REQUIRED": 503,
    "ENCRYPTION_UNAVAILABLE": 503,
}

_CODE_BY_STATUS = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    429: "TOO_MANY_REQUESTS",
}


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[Any]


class ErrorResponse(BaseModel):
    """Cuerpo de todas las respuestas de error (documentado en Swagger)."""

    error: ErrorDetail


class AppError(Exception):
    """Error de negocio con código estable y estado HTTP asociado."""

    def __init__(self, code: str, message: str, details: list[Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []

    @property
    def status_code(self) -> int:
        return STATUS_BY_CODE.get(self.code, 500)


def not_found(message: str) -> AppError:
    return AppError("NOT_FOUND", message)


def conflict(message: str) -> AppError:
    return AppError("CONFLICT", message)


def unprocessable(message: str) -> AppError:
    return AppError("UNPROCESSABLE", message)


def validation_error(message: str, details: list[Any] | None = None) -> AppError:
    return AppError("VALIDATION_ERROR", message, details)


def error_response(
    status: int, code: str, message: str, details: list[Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        details.append({"path": ".".join(loc), "message": str(err["msg"])})
    return details


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        details = _validation_details(exc)
        first = details[0] if details else None
        message = (
            f"{first['path'] or 'solicitud'}: {first['message']}" if first else "Datos inválidos"
        )
        return error_response(400, "VALIDATION_ERROR", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(req: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODE_BY_STATUS.get(
            exc.status_code, "INTERNAL" if exc.status_code >= 500 else "ERROR"
        )
        if exc.status_code == 404 and exc.detail == "Not Found":
            message = f"Ruta no encontrada: {req.method} {req.url.path}"
        elif exc.status_code == 405:
            message = f"Método no permitido: {req.method} {req.url.path}"
        else:
            message = str(exc.detail)
        return error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(req: Request, exc: Exception) -> JSONResponse:
        # Sin stack ni detalles internos en la respuesta; el log lleva solo el tipo y la ruta.
        rid = getattr(req.state, "request_id", "-")
        log.error(
            "[%s] error no controlado en %s %s: %s",
            rid,
            req.method,
            req.url.path,
            type(exc).__name__,
        )
        return error_response(500, "INTERNAL", "Error interno del servidor")
