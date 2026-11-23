"""Flujo de eventos en tiempo real (SSE). Pendiente de auth (S09): exigirá sesión."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.errors import ErrorResponse
from app.realtime.sse import SSEHub

router = APIRouter(prefix="/api", tags=["Tiempo real"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # sin buffering si hay un proxy delante
}


@router.get(
    "/events",
    summary="Eventos en tiempo real (Server-Sent Events)",
    description=(
        "Cada mensaje: `id` incremental, `event` (p. ej. `agent.updated`, `ticket.created`...) y "
        "`data` con el JSON de la entidad. Heartbeat `: ping` cada 25 s. Al reconectar, pide "
        "`/api/snapshot`: no se reenvían los eventos perdidos."
    ),
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Flujo SSE"},
        503: {"model": ErrorResponse, "description": "API en modo SETUP"},
    },
)
def events(request: Request) -> StreamingResponse:
    hub: SSEHub = request.app.state.sse_hub
    return StreamingResponse(hub.stream(), media_type="text/event-stream", headers=SSE_HEADERS)
