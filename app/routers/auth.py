"""Autenticación: login, sesión y cambio de contraseña (S06).

La sesión viaja en una cookie HttpOnly (`flowclic_session`, SameSite=Lax); el front nunca ve el
token. `login` es público; el resto exige sesión (lo comprueba `AuthMiddleware`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.db.database import Database, get_db
from app.domain.schemas import StrictInput
from app.errors import AppError, ErrorResponse
from app.services import auth_service as service

router = APIRouter(
    prefix="/api/auth",
    tags=["Autenticación"],
    responses={503: {"model": ErrorResponse, "description": "API en modo SETUP"}},
)

Db = Annotated[Database, Depends(get_db)]


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class ChangePasswordBody(StrictInput):
    current_password: Annotated[str, Field(min_length=1, max_length=256)]
    new_password: Annotated[str, Field(min_length=1, max_length=256)]


def _principal(request: Request) -> service.Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:  # no debería ocurrir: el middleware ya exige sesión
        raise AppError("UNAUTHENTICATED", "Inicia sesión para continuar")
    assert isinstance(principal, service.Principal)  # noqa: S101
    return principal


@router.post(
    "/login",
    summary="Iniciar sesión (cookie HttpOnly)",
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales incorrectas"},
        429: {"model": ErrorResponse, "description": "Cuenta bloqueada temporalmente"},
    },
)
def login(body: LoginBody, request: Request, response: Response, db: Db) -> service.AuthUser:
    settings = request.app.state.settings
    user, token = service.login(
        db,
        settings,
        body.email,
        body.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        service.COOKIE_NAME,
        token,
        max_age=settings.session_max_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.api_public_origin.startswith("https://"),
        path="/api",
    )
    return user


@router.get("/me", summary="Usuario de la sesión actual")
def me(request: Request) -> service.AuthUser:
    return _principal(request).user


@router.post("/logout", status_code=204, summary="Cerrar sesión")
def logout(request: Request, db: Db) -> Response:
    service.logout(db, _principal(request).session_id)
    out = Response(status_code=204)
    out.delete_cookie(service.COOKIE_NAME, path="/api")
    return out


@router.post(
    "/change-password",
    summary="Cambiar la contraseña (obligatorio tras una contraseña temporal)",
    responses={
        400: {"model": ErrorResponse, "description": "Contraseña actual o nueva no válidas"}
    },
)
def change_password(body: ChangePasswordBody, request: Request, db: Db) -> service.AuthUser:
    return service.change_password(
        db, _principal(request), body.current_password, body.new_password
    )
