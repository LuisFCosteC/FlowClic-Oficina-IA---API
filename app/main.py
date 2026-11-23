"""Fábrica de la aplicación FastAPI."""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, get_settings
from app.db.database import Database, set_db
from app.routers import health


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    """Crea la aplicación (sin arrancar servidor; reutilizable en tests).

    - `settings`: por defecto, el entorno real (`get_settings()`).
    - `db`: conexión ya abierta (tests). Si no se da, se abre desde la bóveda al arrancar.
    """
    cfg = settings or get_settings()
    if db is not None:
        set_db(db)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        vault = None
        if db is None:
            from app.db.bootstrap import open_configured_database
            from app.security.vault import VaultError

            try:
                opened = open_configured_database(cfg)
            except VaultError as exc:
                print(f"No se pudo abrir la bóveda: {exc}", file=sys.stderr)
                raise SystemExit(1) from None
            if opened is not None:
                opened_db, vault = opened
                set_db(opened_db)
        yield
        if vault is not None:
            vault.close()

    app = FastAPI(
        title="FlowClic Oficina IA - API",
        version=__version__,
        description="API de la Fase 1: agentes, tickets, aprobaciones y tiempo real.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = cfg

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    return app


def _default_app() -> FastAPI:
    # `uvicorn app.main:app`: el entorno se lee al arrancar el servidor.
    return create_app()


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _default_app()
    raise AttributeError(name)
