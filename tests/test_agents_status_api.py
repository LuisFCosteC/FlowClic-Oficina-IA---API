from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.events.bus import DomainEvent, get_bus

STATUSES = ["IDLE", "WORKING", "REVIEW", "BLOCKED", "SLEEP_QUOTA"]


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


@pytest.fixture
def agent(client: TestClient) -> dict[str, Any]:
    r = client.post("/api/agents", json={"name": "Howard", "role": "Hardware"})
    assert r.status_code == 201
    return r.json()  # type: ignore[no-any-return]


def patch(client: TestClient, agent_id: str, body: dict[str, Any]) -> Any:
    return client.patch(f"/api/agents/{agent_id}/status", json=body)


@pytest.mark.parametrize("status", STATUSES)
def test_los_5_estados_son_aceptados(
    client: TestClient, agent: dict[str, Any], status: str
) -> None:
    r = patch(client, agent["id"], {"status": status})
    assert r.status_code == 200
    assert r.json()["status"] == status
    assert client.get(f"/api/agents/{agent['id']}").json()["status"] == status


@pytest.mark.parametrize("bad", ["FOO", "idle", "", None, 3])
def test_estado_invalido_400(client: TestClient, agent: dict[str, Any], bad: object) -> None:
    r = patch(client, agent["id"], {"status": bad})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/api/agents/{agent['id']}").json()["status"] == "IDLE"


def test_sin_estado_o_con_campos_extra_400(client: TestClient, agent: dict[str, Any]) -> None:
    assert patch(client, agent["id"], {}).status_code == 400
    assert patch(client, agent["id"], {"status": "IDLE", "isCto": True}).status_code == 400


def test_idle_limpia_la_tarea_actual(client: TestClient, agent: dict[str, Any]) -> None:
    r = patch(client, agent["id"], {"status": "WORKING", "currentTask": "Soldar placa"})
    assert r.json()["currentTask"] == "Soldar placa"
    r = patch(client, agent["id"], {"status": "REVIEW"})
    assert r.json()["currentTask"] == "Soldar placa"  # sin tarea nueva se conserva
    r = patch(client, agent["id"], {"status": "IDLE", "currentTask": "ignorada"})
    assert r.json()["currentTask"] is None


def test_emite_agent_updated_con_el_estado_nuevo(
    client: TestClient, agent: dict[str, Any], events: list[DomainEvent]
) -> None:
    events.clear()
    patch(client, agent["id"], {"status": "BLOCKED"})
    assert [e.type for e in events] == ["agent.updated"]
    assert events[0].payload["id"] == agent["id"]
    assert events[0].payload["status"] == "BLOCKED"


def test_estado_invalido_no_emite_eventos(
    client: TestClient, agent: dict[str, Any], events: list[DomainEvent]
) -> None:
    events.clear()
    patch(client, agent["id"], {"status": "FOO"})
    assert events == []


def test_salir_de_blocked_a_mano_reinicia_el_contador_de_fallos(
    client: TestClient, agent: dict[str, Any], migrated_db: Database
) -> None:
    migrated_db.execute(
        "UPDATE agents SET status = 'BLOCKED', consecutive_failures = 3 WHERE id = ?",
        (agent["id"],),
    )
    r = patch(client, agent["id"], {"status": "WORKING"})
    assert r.json()["consecutiveFailures"] == 0
    migrated_db.execute("UPDATE agents SET consecutive_failures = 2 WHERE id = ?", (agent["id"],))
    r = patch(client, agent["id"], {"status": "REVIEW"})
    assert r.json()["consecutiveFailures"] == 2  # solo se reinicia al salir de BLOCKED


def test_inexistente_404_y_archivado_409(client: TestClient, agent: dict[str, Any]) -> None:
    assert patch(client, "nadie", {"status": "IDLE"}).status_code == 404
    client.delete(f"/api/agents/{agent['id']}")
    r = patch(client, agent["id"], {"status": "WORKING"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_openapi_documenta_el_endpoint(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "patch" in paths["/api/agents/{agent_id}/status"]
