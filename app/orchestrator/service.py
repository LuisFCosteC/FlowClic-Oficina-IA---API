"""Bucle de fondo del orquestador: arranca con la API y hace `tick()` cada pocos segundos."""

import asyncio
import logging

from app.config import Settings
from app.db.database import try_get_db
from app.db.migrate import is_behind
from app.events.bus import EventBus
from app.orchestrator.llm import HttpLlmClient
from app.orchestrator.runner import Orchestrator
from app.services import key_service
from app.services.key_pool import KeyPool

log = logging.getLogger("flowclic.orchestrator")
INTERVAL_SECONDS = 4.0


async def run_forever(settings: Settings, bus: EventBus) -> None:
    """Espera a que haya BD migrada y clave maestra; después trabaja hasta que lo cancelen."""
    orch: Orchestrator | None = None
    built_for = 0
    announced = False
    while True:
        try:
            db = try_get_db()
            if db is not None and settings.app_master_key:
                if orch is None or built_for != id(db):
                    if await asyncio.to_thread(is_behind, db):
                        await asyncio.sleep(INTERVAL_SECONDS * 2)
                        continue
                    box = key_service.box_from_key(settings.app_master_key)
                    orch = Orchestrator(db, bus, KeyPool(db, box, bus), HttpLlmClient())
                    built_for = id(db)
                    if not announced:
                        print(
                            "[ORQUESTADOR] Activo: Sheldon reparte los pedidos del CEO.", flush=True
                        )
                        announced = True
                await asyncio.to_thread(orch.tick)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el bucle nunca debe morir
            log.exception("Fallo en el orquestador; se reintenta")
        await asyncio.sleep(INTERVAL_SECONDS)
