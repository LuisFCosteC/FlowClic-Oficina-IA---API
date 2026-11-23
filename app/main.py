"""Fábrica de la aplicación FastAPI."""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, get_settings
from app.db.database import Database, clear_db, set_db, try_get_db
from app.errors import register_error_handlers
from app.middleware import SetupModeMiddleware
from app.routers import agent_templates, agents, health, setup, snapshot
from app.security.setup_gate import SetupGate
from app.security.vault import Vault
from app.services.setup_service import has_admin


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    vault: Vault | None = None,
) -> FastAPI:
    """Crea la aplicación (sin arrancar servidor; reutilizable en tests).

    - `settings`: por defecto, el entorno real (`get_settings()`).
    - `db`: conexión ya abierta (tests). Si se da, no se usa la bóveda ni el modo SETUP.
    - `vault`: bóveda ya abierta (tests del asistente de setup).
    Sin `db`, al arrancar se abre la bóveda y se conecta con la BD guardada en ella; si no hay
    ninguna, la API arranca en **modo SETUP** y muestra un código de un solo uso en la consola.
    """
    cfg = settings or get_settings()
    gate = SetupGate()
    if db is not None:
        set_db(db)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own_vault = False
        active_vault = vault
        opened_db = False
        if db is None:
            if active_vault is None:
                from app.db.bootstrap import load_vault
                from app.security.vault import VaultError

                try:
                    active_vault = load_vault(cfg)
                    own_vault = True
                except VaultError as exc:
                    print(f"No se pudo abrir la bóveda: {exc}", file=sys.stderr)
                    raise SystemExit(1) from None
            from app.db.bootstrap import open_database_from_vault

            opened = open_database_from_vault(active_vault, cfg.db_driver)
            if opened is not None:
                set_db(opened)
                opened_db = True
            else:
                clear_db()
            if not has_admin(try_get_db()):
                gate.issue()  # modo SETUP: el código solo se imprime en la consola
        app.state.vault = active_vault
        yield
        if opened_db and (current := try_get_db()) is not None:
            current.close()
        if own_vault and active_vault is not None:
            active_vault.close()

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
    app.state.vault = vault
    app.state.setup_gate = gate
    register_error_handlers(app)

    app.add_middleware(SetupModeMiddleware)
    app.add_middleware(  # el último en añadirse es el más externo: CORS envuelve al resto
        CORSMiddleware,
        allow_origins=[cfg.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(setup.router)
    app.include_router(agent_templates.router)
    app.include_router(agents.router)
    app.include_router(snapshot.router)
    return app


def _default_app() -> FastAPI:
    # `uvicorn app.main:app`: el entorno se lee al arrancar el servidor.
    return create_app()


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _default_app()
    raise AttributeError(name)
