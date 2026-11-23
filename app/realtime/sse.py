"""Tiempo real por SSE (PLAN §6, D4).

Un único suscriptor del bus (`SSEHub`) asigna un `id` incremental a cada evento y lo reparte a
una cola por cliente. Es seguro entre hilos: las rutas síncronas emiten desde hilos del pool y
la entrega al bucle de eventos se hace con `call_soon_threadsafe`.

- Heartbeat `: ping` cada 25 s para mantener viva la conexión.
- Un cliente demasiado lento (cola llena) se desconecta: al reconectar el front vuelve a pedir
  `/api/snapshot`, que cubre la brecha (no se reenvían eventos perdidos; `Last-Event-ID` se ignora).
- Al cerrar la conexión (o al apagar el servidor) el cliente se elimina: no quedan listeners.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Callable

from app.events.bus import DomainEvent, EventBus

HEARTBEAT_SECONDS = 25.0
MAX_QUEUE = 256


def format_event(seq: int, event: DomainEvent) -> str:
    data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {seq}\nevent: {event.type}\ndata: {data}\n\n"


class _Client:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=MAX_QUEUE)
        self.overflow = False

    def push(self, frame: str | None) -> None:  # se ejecuta en el hilo del bucle
        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            self.overflow = True


class SSEHub:
    def __init__(self, bus: EventBus, heartbeat: float = HEARTBEAT_SECONDS) -> None:
        self._bus = bus
        self.heartbeat = heartbeat
        self._lock = threading.Lock()
        self._clients: set[_Client] = set()
        self._seq = 0
        self._unsubscribe: Callable[[], None] | None = None

    def start(self) -> None:
        if self._unsubscribe is None:
            self._unsubscribe = self._bus.subscribe(self._on_event)

    def stop(self) -> None:
        """Se da de baja del bus y cierra todos los streams abiertos."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            self._deliver(client, None)  # centinela: el stream termina

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @staticmethod
    def _deliver(client: _Client, frame: str | None) -> None:
        try:
            client.loop.call_soon_threadsafe(client.push, frame)
        except RuntimeError:  # el bucle del cliente ya se cerró
            pass

    def _on_event(self, event: DomainEvent) -> None:
        with self._lock:
            self._seq += 1
            frame = format_event(self._seq, event)
            clients = list(self._clients)
        for client in clients:
            self._deliver(client, frame)

    async def stream(self) -> AsyncIterator[str]:
        client = _Client(asyncio.get_running_loop())
        with self._lock:
            self._clients.add(client)
        try:
            yield ": connected\n\n"
            while not client.overflow:
                try:
                    frame = await asyncio.wait_for(client.queue.get(), timeout=self.heartbeat)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if frame is None:
                    break
                yield frame
        finally:
            with self._lock:
                self._clients.discard(client)
