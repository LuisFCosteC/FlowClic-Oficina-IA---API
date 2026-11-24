"""Fábrica de la aplicación FastAPI."""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, get_settings
from app.db.database import Database, clear_db, set_db, try_get_db
from app.db.migrate import MIGRATE_HINT, is_behind
from app.errors import register_error_handlers
from app.events.bus import EventBus, get_bus
from app.middleware import MigrationGuardMiddleware, SecurityMiddleware, SetupModeMiddleware
from app.realtime.sse import SSEHub
from app.routers import (
    admin_credentials,
    admin_db,
    admin_keys,
    admin_projects,
    admin_settings,
    admin_tools,
    admin_users,
    admin_workspaces,
    agent_templates,
    agents,
    docs,
    events,
    health,
    messages,
    models,
    setup,
    snapshot,
    tickets,
)
from app.security.setup_gate import SetupGate
from app.security.vault import Vault
from app.services.setup_service import has_admin


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    vault: Vault | None = None,
    bus: EventBus | None = None,
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
    the_bus = bus or get_bus()
    sse_hub = SSEHub(the_bus)
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
            if opened is not None and is_behind(opened):
                print(f"[MIGRACIONES] {MIGRATE_HINT}", flush=True)
            if not has_admin(try_get_db()):
                gate.issue()  # modo SETUP: el código solo se imprime en la consola
        app.state.vault = active_vault
        sse_hub.start()
        yield
        sse_hub.stop()
        if opened_db and (current := try_get_db()) is not None:
            current.close()
        if own_vault and active_vault is not None:
            active_vault.close()

    app = FastAPI(
        title="FlowClic Oficina IA - API",
        version=__version__,
        description="API de la Fase 1: agentes, tickets, aprobaciones y tiempo real.",
        docs_url=None,  # la documentación vive en /api/docs (routers/docs.py, P03)
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.vault = vault
    app.state.setup_gate = gate
    app.state.sse_hub = sse_hub
    app.dependency_overrides[get_bus] = lambda: the_bus  # rutas, SSE y tests: el mismo bus
    register_error_handlers(app)

    app.add_middleware(MigrationGuardMiddleware)
    app.add_middleware(SetupModeMiddleware)
    app.add_middleware(  # el último en añadirse es el más externo: CORS envuelve al resto
        CORSMiddleware,
        allow_origins=[cfg.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(SecurityMiddleware)  # el más externo: sus cabeceras salen en TODA respuesta
    app.include_router(health.router)
    app.include_router(docs.router)
    app.include_router(setup.router)
    app.include_router(agent_templates.router)
    app.include_router(agents.router)
    app.include_router(tickets.router)
    app.include_router(admin_credentials.router)
    app.include_router(admin_keys.router)
    app.include_router(admin_tools.router)
    app.include_router(admin_workspaces.router)
    app.include_router(admin_projects.router)
    app.include_router(admin_db.router)
    app.include_router(admin_settings.router)
    app.include_router(admin_users.router)
    app.include_router(snapshot.router)
    app.include_router(events.router)
    app.include_router(models.router)
    app.include_router(messages.router)
    return app


def _default_app() -> FastAPI:
    # `uvicorn app.main:app`: el entorno se lee al arrancar el servidor.
    return create_app()


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _default_app()
    raise AttributeError(name)
