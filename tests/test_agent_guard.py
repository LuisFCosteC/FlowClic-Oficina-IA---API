import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.events.bus import DomainEvent, get_bus


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


@pytest.fixture
def agent(client: TestClient) -> dict[str, Any]:
    r = client.post("/api/agents", json={"name": "Howard", "role": "Hw"})
    return r.json()  # type: ignore[no-any-return]


def report(client: TestClient, agent_id: str, **body: Any) -> Any:
    return client.post(f"/api/agents/{agent_id}/failures", json=body)


def fail(client: TestClient, agent_id: str) -> dict[str, Any]:
    r = report(client, agent_id, outcome="failure")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_tres_fallos_seguidos_bloquean_y_emiten_evento(
    client: TestClient, agent: dict[str, Any], events: list[DomainEvent]
) -> None:
    events.clear()
    a1 = fail(client, agent["id"])
    a2 = fail(client, agent["id"])
    assert (a1["consecutiveFailures"], a1["status"]) == (1, "IDLE")
    assert (a2["consecutiveFailures"], a2["status"]) == (2, "IDLE")
    a3 = fail(client, agent["id"])
    assert (a3["consecutiveFailures"], a3["status"]) == (3, "BLOCKED")
    assert [e.type for e in events] == ["agent.updated"] * 3
    assert events[-1].payload["status"] == "BLOCKED"
    assert events[-1].payload["consecutiveFailures"] == 3


def test_un_exito_intermedio_reinicia_el_contador(
    client: TestClient, agent: dict[str, Any]
) -> None:
    fail(client, agent["id"])
    fail(client, agent["id"])
    ok = report(client, agent["id"], outcome="success").json()
    assert ok["consecutiveFailures"] == 0 and ok["status"] == "IDLE"
    fail(client, agent["id"])
    fail(client, agent["id"])
    still = client.get(f"/api/agents/{agent['id']}").json()
    assert still["status"] == "IDLE" and still["consecutiveFailures"] == 2
    assert fail(client, agent["id"])["status"] == "BLOCKED"


def test_el_bloqueo_deja_auditoria_sin_secretos(
    client: TestClient, agent: dict[str, Any], migrated_db: Database
) -> None:
    for _ in range(3):
        fail(client, agent["id"])
    rows = migrated_db.fetch_all("SELECT * FROM audit_log")
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "agent.auto_blocked"
    assert (row["target_type"], row["target_id"]) == ("agent", agent["id"])
    meta = json.loads(row["meta"])
    assert meta == {"reason": "consecutive_failures", "failures": 3}


def test_un_agente_ya_bloqueado_no_se_vuelve_a_bloquear(
    client: TestClient, agent: dict[str, Any], migrated_db: Database
) -> None:
    for _ in range(5):
        fail(client, agent["id"])
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM audit_log") == {"n": 1}
    got = client.get(f"/api/agents/{agent['id']}").json()
    assert got["status"] == "BLOCKED" and got["consecutiveFailures"] == 5


def test_el_tope_de_coste_bloquea(
    client: TestClient, agent: dict[str, Any], migrated_db: Database, events: list[DomainEvent]
) -> None:
    limit = agent["limits"]["maxUsdPerDay"]  # 8 por defecto
    below = report(client, agent["id"], outcome="success", usdToday=limit - 0.01).json()
    assert below["status"] == "IDLE"
    events.clear()
    at = report(client, agent["id"], outcome="success", usdToday=limit).json()
    assert at["status"] == "BLOCKED"
    assert events[-1].payload["status"] == "BLOCKED"
    meta = json.loads(migrated_db.fetch_all("SELECT meta FROM audit_log")[0]["meta"])
    assert meta["reason"] == "budget" and meta["maxUsdPerDay"] == limit


def test_el_tope_respeta_los_limites_propios_del_agente(client: TestClient) -> None:
    body = {
        "name": "Raj",
        "role": "QA",
        "limits": {"maxTokensPerTicket": 80000, "maxUsdPerDay": 3, "maxRetries": 3},
    }
    raj = client.post("/api/agents", json=body).json()
    assert report(client, raj["id"], outcome="success", usdToday=2.99).json()["status"] == "IDLE"
    assert report(client, raj["id"], outcome="success", usdToday=3).json()["status"] == "BLOCKED"


def test_desbloquear_a_mano_y_volver_a_empezar(client: TestClient, agent: dict[str, Any]) -> None:
    for _ in range(3):
        fail(client, agent["id"])
    unblocked = client.patch(f"/api/agents/{agent['id']}/status", json={"status": "IDLE"}).json()
    assert unblocked["status"] == "IDLE" and unblocked["consecutiveFailures"] == 0
    assert fail(client, agent["id"])["status"] == "IDLE"  # vuelve a contar desde cero


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"outcome": "FOO"},
        {"outcome": "failure", "usdToday": -1},
        {"outcome": "failure", "x": 1},
    ],
)
def test_cuerpo_invalido_400(
    client: TestClient, agent: dict[str, Any], body: dict[str, Any]
) -> None:
    r = report(client, agent["id"], **body)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_404_y_archivado_409(client: TestClient, agent: dict[str, Any]) -> None:
    assert report(client, "nadie", outcome="failure").status_code == 404
    client.delete(f"/api/agents/{agent['id']}")
    assert report(client, agent["id"], outcome="failure").status_code == 409


def test_exito_sin_fallos_no_emite_eventos(
    client: TestClient, agent: dict[str, Any], events: list[DomainEvent]
) -> None:
    events.clear()
    report(client, agent["id"], outcome="success")
    assert events == []


def test_documentado_en_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/agents/{agent_id}/failures"]
