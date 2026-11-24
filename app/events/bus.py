"""Bus de eventos de dominio en memoria (PLAN §6: tabla SSE).

Las rutas son síncronas y FastAPI las ejecuta en hilos, así que `emit` puede llamarse desde
cualquier hilo. Los suscriptores son funciones síncronas y rápidas; el SSE (T60) registra uno que
reenvía a una `asyncio.Queue` con `loop.call_soon_threadsafe`.

Los errores de un suscriptor se registran y NUNCA rompen a quien emite (ni a los demás).
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

log = logging.getLogger("flowclic")

EventType = Literal[
    "agent.created",
    "agent.updated",
    "agent.archived",
    "ticket.created",
    "ticket.updated",
    "ticket.deleted",
    "ticket.event",
    "approval.created",
    "approval.updated",
    "memory.created",
    "memory.updated",
    "memory.deleted",
    "message.created",
    "settings.updated",
    "rule.created",
    "rule.updated",
    "rule.deleted",
    "system.db_changed",
    "project.created",
    "project.updated",
    "project.archived",
    "key.updated",
]


@dataclass(frozen=True)
class DomainEvent:
    """Evento de dominio: `payload` es JSON ya serializado (camelCase), listo para el SSE."""

    type: EventType
    payload: dict[str, Any]


Subscriber = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Registra un suscriptor. Devuelve la función para darse de baja (idempotente)."""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def emit(self, type_: EventType, payload: dict[str, Any]) -> None:
        event = DomainEvent(type_, payload)
        with self._lock:
            targets = list(self._subscribers)  # copia: se puede (des)suscribir durante la emisión
        for callback in targets:
            try:
                callback(event)
            except Exception:
                log.exception("fallo en un suscriptor del bus (%s)", type_)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


_default_bus = EventBus()


def get_bus() -> EventBus:
    """Dependencia de FastAPI / acceso global al bus de la aplicación."""
    return _default_bus
