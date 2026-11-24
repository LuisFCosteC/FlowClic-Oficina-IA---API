"""A04 y A06: aplicación de límites y archivar/restaurar agentes."""

from collections.abc import Iterator
from typing import Any

import pytest
from conftest import make_ticket
from fastapi.testclient import TestClient

from app.db.database import Database
from app.events.bus import DomainEvent, get_bus

LIMITS = "/api/admin/settings/limits"


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


def _limits(c: TestClient, **kw: Any) -> None:
    body = {"maxAgents": 20, "maxActiveTicketsPerAgent": 3, "requireApprovalForDone": False}
    body.update(kw)
    assert c.put(LIMITS, json=body).status_code == 200


def _agent(c: TestClient, name: str = "Leonard") -> dict[str, Any]:
    r = c.post("/api/agents", json={"name": name, "role": "Backend"})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _ticket(c: TestClient, agent_id: str, title: str = "T") -> str:
    return str(make_ticket(title=title, assigned_agent_id=agent_id)["id"])


def _move(c: TestClient, tid: str, to: str) -> Any:
    return c.post(f"/api/tickets/{tid}/transition", json={"to": to})


# ── A04 ──────────────────────────────────────────────────────────────────────────────────────
def test_max_agents_al_crear(client: TestClient) -> None:
    _limits(client, maxAgents=2)
    _agent(client, "A")
    _agent(client, "B")
    r = client.post("/api/agents", json={"name": "C", "role": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LIMIT_EXCEEDED"
    assert "2" in r.json()["error"]["message"]
    assert len(client.get("/api/agents").json()) == 2


def test_max_active_tickets_al_pasar_a_en_curso(client: TestClient) -> None:
    _limits(client, maxActiveTicketsPerAgent=2)
    aid = _agent(client)["id"]
    t = [_ticket(client, aid, f"T{i}") for i in range(3)]
    assert _move(client, t[0], "IN_PROGRESS").status_code == 200
    assert _move(client, t[1], "IN_PROGRESS").status_code == 200
    r = _move(client, t[2], "IN_PROGRESS")
    assert r.status_code == 409 and r.json()["error"]["code"] == "LIMIT_EXCEEDED"
    assert client.get(f"/api/tickets/{t[2]}").json()["status"] == "PENDING"
    # subir el límite lo permite
    _limits(client, maxActiveTicketsPerAgent=3)
    assert _move(client, t[2], "IN_PROGRESS").status_code == 200


def test_tickets_sin_agente_no_cuentan_para_el_limite(client: TestClient) -> None:
    _limits(client, maxActiveTicketsPerAgent=1)
    tid = make_ticket(title="x")["id"]
    assert _move(client, tid, "IN_PROGRESS").status_code == 200


def test_require_approval_for_done(client: TestClient, migrated_db: Database) -> None:
    aid = _agent(client)["id"]
    tid = _ticket(client, aid)
    for to in ("IN_PROGRESS", "IN_QA", "IN_SENIOR_REVIEW", "IN_REVIEW"):
        assert _move(client, tid, to).status_code == 200
    _limits(client, requireApprovalForDone=True)
    r = _move(client, tid, "DONE")
    assert r.status_code == 409 and r.json()["error"]["code"] == "LIMIT_EXCEEDED"
    migrated_db.execute(
        "INSERT INTO approvals (id, ticket_id, title, gate, status, requested_at)"
        " VALUES ('ap1', ?, 'Merge', 3, 'REJECTED', '2026-11-23T00:00:00.000Z')",
        (tid,),
    )
    assert _move(client, tid, "DONE").status_code == 409  # RECHAZADA no vale
    migrated_db.execute("UPDATE approvals SET status = 'APPROVED' WHERE id = 'ap1'")
    assert _move(client, tid, "DONE").status_code == 200


def test_sin_require_approval_se_puede_pasar_a_hecho(client: TestClient) -> None:
    tid = _ticket(client, _agent(client)["id"])
    for to in ("IN_PROGRESS", "IN_QA", "IN_SENIOR_REVIEW", "IN_REVIEW", "DONE"):
        assert _move(client, tid, to).status_code == 200


# ── A06 ──────────────────────────────────────────────────────────────────────────────────────
def test_archivar_listar_y_restaurar(client: TestClient, events: list[DomainEvent]) -> None:
    a = _agent(client, "Howard")
    r = client.post(f"/api/agents/{a['id']}/archive")
    assert r.status_code == 200 and r.json()["archivedAt"] is not None
    assert client.get("/api/agents").json() == []
    listed = client.get("/api/agents?includeArchived=true").json()
    assert [x["id"] for x in listed] == [a["id"]]
    back = client.post(f"/api/agents/{a['id']}/restore")
    assert back.status_code == 200 and back.json()["archivedAt"] is None
    assert [x["id"] for x in client.get("/api/agents").json()] == [a["id"]]
    assert client.post(f"/api/agents/{a['id']}/restore").status_code == 200  # idempotente
    assert [e.type for e in events if e.type.startswith("agent.")][-2:] == [
        "agent.archived",
        "agent.created",
    ]


def test_restaurar_respeta_nombre_unico_y_max_agents(client: TestClient) -> None:
    a = _agent(client, "Howard")
    client.post(f"/api/agents/{a['id']}/archive")
    _agent(client, "Howard")  # el nombre quedó libre
    r = client.post(f"/api/agents/{a['id']}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"

    b = _agent(client, "Bernadette")
    client.post(f"/api/agents/{b['id']}/archive")
    _limits(client, maxAgents=1)  # ya hay 1 activo (el segundo Howard)
    r2 = client.post(f"/api/agents/{b['id']}/restore")
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "LIMIT_EXCEEDED"


def test_restaurar_o_archivar_inexistente_404(client: TestClient) -> None:
    assert client.post("/api/agents/nada/restore").status_code == 404
    assert client.post("/api/agents/nada/archive").status_code == 404


def test_archivar_con_tickets_abiertos_409(client: TestClient) -> None:
    a = _agent(client)
    _ticket(client, a["id"])
    assert client.post(f"/api/agents/{a['id']}/archive").status_code == 409
