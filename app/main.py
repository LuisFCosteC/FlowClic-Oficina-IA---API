from fastapi import FastAPI


def create_app() -> FastAPI:
    """Crea la aplicación FastAPI (sin arrancar servidor; reutilizable en tests)."""
    return FastAPI(
        title="FlowClic Oficina IA - API",
        version="0.1.0",
        description="API de la Fase 1: agentes, tickets, aprobaciones y tiempo real.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )


app = create_app()
