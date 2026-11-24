"""Bucle de fondo del orquestador: arranca con la API y hace `tick()` cada pocos segundos.

Nunca falla en silencio: el motivo por el que NO está trabajando se imprime en la consola de la
API (una vez por cambio) y se puede consultar en `GET /api/admin/orchestrator`.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.db.database import try_get_db
from app.db.migrate import is_behind
from app.events.bus import EventBus
from app.orchestrator.llm import HttpLlmClient
from app.orchestrator.runner import Orchestrator, safe_error
from app.services import key_service
from app.services.key_pool import KeyPool

log = logging.getLogger("flowclic.orchestrator")
INTERVAL_SECONDS = 4.0

# Estado visible (una sola instancia por proceso).
STATUS: dict[str, Any] = {
    "mode": "off",  # off | llm
    "running": False,
    "reason": "El orquestador no ha arrancado",
    "lastTickAt": None,
    "lastActions": 0,
    "lastError": None,
}


def _set_reason(reason: str | None) -> None:
    text = reason or ""
    if STATUS["reason"] != text:
        STATUS["reason"] = text
        STATUS["running"] = reason is None
        print(
            "[ORQUESTADOR] "
            + (
                "Activo: Sheldon reparte los pedidos del CEO."
                if reason is None
                else f"En espera: {reason}"
            ),
            flush=True,
        )


async def run_forever(settings: Settings, bus: EventBus) -> None:
    """Espera a que haya BD migrada y clave maestra; después trabaja hasta que lo cancelen."""
    STATUS["mode"] = "llm"
    orch: Orchestrator | None = None
    built_for = 0
    while True:
        try:
            db = try_get_db()
            if not settings.app_master_key:
                _set_reason("falta APP_MASTER_KEY en el .env (ejecuta python scripts/setup_env.py)")
            elif db is None:
                _set_reason("la API aún no tiene base de datos (modo SETUP o bóveda sin abrir)")
            elif orch is None or built_for != id(db):
                if await asyncio.to_thread(is_behind, db):
                    _set_reason("faltan migraciones: .\\.venv\\Scripts\\python -m app.db.migrate")
                else:
                    box = key_service.box_from_key(settings.app_master_key)
                    orch = Orchestrator(db, bus, KeyPool(db, box, bus), HttpLlmClient())
                    built_for = id(db)
                    _set_reason(None)
            if orch is not None and db is not None:
                done = await asyncio.to_thread(orch.tick)
                STATUS["lastTickAt"] = datetime.now(UTC).isoformat()
                STATUS["lastActions"] = done
                STATUS["lastError"] = orch.last_error
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - el bucle nunca debe morir
            STATUS["lastError"] = safe_error(exc)
            log.exception("Fallo en el orquestador; se reintenta")
        await asyncio.sleep(INTERVAL_SECONDS)
