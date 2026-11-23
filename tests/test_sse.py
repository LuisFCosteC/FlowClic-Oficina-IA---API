import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database
from app.events.bus import DomainEvent, EventBus
from app.main import create_app
from app.realtime.sse import MAX_QUEUE, SSEHub, format_event


@dataclass
class Live:
    url: str
    app: FastAPI
    bus: EventBus

    @property
    def hub(self) -> SSEHub:
        hub: SSEHub = self.app.state.sse_hub
        return hub


def wait_for(cond: Callable[[], bool], seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture
def live(migrated_db: Database, test_settings: Settings) -> Iterator[Live]:
    """Servidor uvicorn real en un hilo (TestClient se bloquea con streams infinitos)."""
    bus = EventBus()
    app = create_app(test_settings, migrated_db, bus=bus)
    app.state.sse_hub.heartbeat = 0.3
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    assert wait_for(lambda: server.started and bool(server.servers))
    port = server.servers[0].sockets[0].getsockname()[1]
    yield Live(f"http://127.0.0.1:{port}", app, bus)
    server.should_exit = True
    thread.join(10)
    assert not thread.is_alive()


@contextmanager
def open_stream(live: Live) -> Iterator[Iterator[str]]:
    with httpx.stream("GET", live.url + "/api/events", timeout=httpx.Timeout(5.0)) as r:
        assert r.status_code == 200
        yield r.iter_lines()


def read_frame(lines: Iterator[str]) -> dict[str, str]:
    """Lee un mensaje SSE completo (hasta la línea en blanco)."""
    frame: dict[str, str] = {}
    for line in lines:
        if line == "":
            if frame:
                return frame
            continue
        if line.startswith(":"):
            frame.setdefault("comment", line[1:].strip())
            continue
        key, _, value = line.partition(": ")
        frame[key] = value
    raise AssertionError("el stream terminó")


def read_until(lines: Iterator[str], event: str) -> dict[str, str]:
    for _ in range(50):
        frame = read_frame(lines)
        if frame.get("event") == event:
            return frame
    raise AssertionError(f"no llegó {event}")


def test_cabeceras_sse(live: Live) -> None:
    with httpx.stream("GET", live.url + "/api/events", timeout=5.0) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "no-cache" in r.headers["cache-control"]
        assert r.headers["x-accel-buffering"] == "no"
        assert next(r.iter_lines()) == ": connected"


def test_muestra_agent_updated_al_cambiar_el_estado_desde_otra_peticion(live: Live) -> None:
    created = httpx.post(live.url + "/api/agents", json={"name": "Howard", "role": "Hw"}).json()
    with open_stream(live) as lines:
        assert read_frame(lines)["comment"] == "connected"
        r = httpx.patch(
            live.url + f"/api/agents/{created['id']}/status", json={"status": "WORKING"}
        )
        assert r.status_code == 200
        frame = read_until(lines, "agent.updated")
    assert json.loads(frame["data"])["status"] == "WORKING"
    assert json.loads(frame["data"])["id"] == created["id"]


def test_los_ids_son_incrementales_y_el_data_es_json_compacto(live: Live) -> None:
    with open_stream(live) as lines:
        read_frame(lines)
        for i in range(3):
            live.bus.emit("ticket.deleted", {"id": f"t{i}"})
        frames = [read_until(lines, "ticket.deleted") for _ in range(3)]
    ids = [int(f["id"]) for f in frames]
    assert ids == sorted(ids) and len(set(ids)) == 3
    assert ids[1] == ids[0] + 1 and ids[2] == ids[1] + 1
    assert frames[0]["data"] == '{"id":"t0"}'


def test_heartbeat_ping(live: Live) -> None:
    with open_stream(live) as lines:
        assert read_frame(lines)["comment"] == "connected"
        assert read_frame(lines)["comment"] == "ping"


def test_dos_clientes_reciben_el_mismo_evento_con_el_mismo_id(live: Live) -> None:
    with open_stream(live) as a, open_stream(live) as b:
        read_frame(a)
        read_frame(b)
        assert wait_for(lambda: live.hub.client_count == 2)
        live.bus.emit("memory.deleted", {"id": "m1"})
        fa = read_until(a, "memory.deleted")
        fb = read_until(b, "memory.deleted")
    assert fa["id"] == fb["id"] and fa["data"] == fb["data"]


def test_cerrar_el_cliente_no_deja_listeners_colgados(live: Live) -> None:
    base = live.bus.subscriber_count  # el hub
    for _ in range(3):
        with open_stream(live) as lines:
            read_frame(lines)
            assert wait_for(lambda: live.hub.client_count == 1)
        assert wait_for(lambda: live.hub.client_count == 0), "el cliente cerrado sigue registrado"
    assert live.bus.subscriber_count == base == 1


def test_los_eventos_emitidos_desde_hilos_del_pool_llegan(live: Live) -> None:
    with open_stream(live) as lines:
        read_frame(lines)
        r = httpx.post(live.url + "/api/agents", json={"name": "Raj", "role": "QA"})
        assert r.status_code == 201
        frame = read_until(lines, "agent.created")
    assert json.loads(frame["data"])["name"] == "Raj"


def test_cliente_lento_se_desconecta_al_llenarse_la_cola() -> None:
    async def scenario() -> list[str]:
        bus = EventBus()
        hub = SSEHub(bus, heartbeat=5.0)
        hub.start()
        stream = hub.stream()
        assert await anext(stream) == ": connected\n\n"
        for i in range(MAX_QUEUE + 50):  # el cliente no lee: la cola se llena
            bus.emit("ticket.updated", {"i": i})
            await asyncio.sleep(0)
        await asyncio.sleep(0.05)
        frames = [f async for f in stream]  # termina solo
        assert hub.client_count == 0
        hub.stop()
        return frames

    frames = asyncio.run(scenario())
    # el stream se cortó solo (sin hub.stop): el cliente lento se desconecta y pedirá /snapshot
    assert len(frames) <= MAX_QUEUE


def test_stop_cierra_los_streams_y_se_da_de_baja_del_bus() -> None:
    async def scenario() -> None:
        bus = EventBus()
        hub = SSEHub(bus, heartbeat=5.0)
        hub.start()
        stream = hub.stream()
        await anext(stream)
        assert bus.subscriber_count == 1
        hub.stop()
        assert bus.subscriber_count == 0
        assert [f async for f in stream] == []
        assert hub.client_count == 0

    asyncio.run(scenario())


def test_formato_de_un_mensaje() -> None:
    frame = format_event(7, DomainEvent("agent.updated", {"name": "Ñandú", "n": 1}))
    assert frame == 'id: 7\nevent: agent.updated\ndata: {"name":"Ñandú","n":1}\n\n'


def test_en_modo_setup_events_da_503(test_settings: Settings, tmp_path: Any) -> None:
    from app.db.database import clear_db
    from app.security.crypto import SecretBox, generate_master_key
    from app.security.vault import Vault

    clear_db()
    key = generate_master_key()
    vault = Vault(tmp_path / "v.db", SecretBox.from_base64(key))
    app = create_app(test_settings, None, vault, bus=EventBus())
    with TestClient(app) as c:
        r = c.get("/api/events")
    vault.close()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SETUP_REQUIRED"


def test_openapi_documenta_events(client: TestClient) -> None:
    op = client.get("/openapi.json").json()["paths"]["/api/events"]["get"]
    assert "text/event-stream" in op["responses"]["200"]["content"]
