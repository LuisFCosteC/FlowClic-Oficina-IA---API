"""Tickets: alta y transiciones del grafo de PLAN §19.4 con efecto en el agente."""

import pytest
from conftest import make_ticket
from fastapi.testclient import TestClient

from app.db.database import Database
from app.domain.ticket_flow import can_transition


def _agent(c: TestClient, name: str = "Leonard") -> str:
    r = c.post("/api/agents", json={"name": name, "role": "Backend"})
    assert r.status_code == 201
    return str(r.json()["id"])


def _ticket(c: TestClient, agent_id: str | None = None, title: str = "Login") -> dict:
    return make_ticket(title=title, assigned_agent_id=agent_id)


def _move(c: TestClient, tid: str, to: str):
    return c.post(f"/api/tickets/{tid}/transition", json={"to": to})


def _agent_status(c: TestClient, aid: str) -> str:
    return str(c.get(f"/api/agents/{aid}").json()["status"])


@pytest.mark.parametrize(
    ("cur", "to", "expected"),
    [
        ("PENDING", "IN_PROGRESS", "ALLOWED"),
        ("IN_PROGRESS", "IN_QA", "ALLOWED"),
        ("IN_QA", "RETURNED", "ALLOWED"),
        ("RETURNED", "IN_PROGRESS", "ALLOWED"),
        ("IN_REVIEW", "DONE", "ALLOWED"),
        ("PENDING", "DONE", "INVALID"),
        ("DONE", "PENDING", "INVALID"),
        ("RETURNED", "IN_QA", "INVALID"),
        ("IN_QA", "IN_QA", "NOOP"),
    ],
)
def test_can_transition(cur: str, to: str, expected: str) -> None:
    assert can_transition(cur, to) == expected  # type: ignore[arg-type]


def test_create_starts_pending_with_event(client: TestClient, migrated_db: Database) -> None:
    t = _ticket(client)
    assert t["status"] == "PENDING"
    assert client.get("/api/snapshot").json()["tickets"][0]["id"] == t["id"]
    ev = migrated_db.fetch_all("SELECT type FROM ticket_events WHERE ticket_id = ?", (t["id"],))
    assert [e["type"] for e in ev] == ["CREATED"]


def test_create_rejects_free_form_tickets(client: TestClient) -> None:
    # REQ01: ya no se crean tickets con campos libres; solo pedidos y subtareas
    assert client.post("/api/tickets", json={"title": "x", "status": "DONE"}).status_code == 400
    bad = client.post("/api/tickets", json={"title": "x", "assignedAgentId": "n"})
    assert bad.status_code == 400
    assert client.post("/api/tickets", json={"title": ""}).status_code == 400


def test_full_flow_updates_agent(client: TestClient, migrated_db: Database) -> None:
    aid = _agent(client)
    tid = _ticket(client, aid)["id"]
    assert _move(client, tid, "IN_PROGRESS").status_code == 200
    assert _agent_status(client, aid) == "WORKING"
    assert _move(client, tid, "IN_QA").json()["status"] == "IN_QA"
    assert _agent_status(client, aid) == "REVIEW"
    assert _move(client, tid, "RETURNED").status_code == 200
    assert _agent_status(client, aid) == "WORKING"
    for to in ("IN_PROGRESS", "IN_QA", "IN_SENIOR_REVIEW", "IN_REVIEW", "DONE"):
        assert _move(client, tid, to).status_code == 200, to
    assert _agent_status(client, aid) == "IDLE"
    ev = migrated_db.fetch_all(
        "SELECT type FROM ticket_events WHERE ticket_id = ? AND type = 'STATUS_CHANGED'", (tid,)
    )
    assert len(ev) == 8


def test_invalid_transition_409(client: TestClient) -> None:
    tid = _ticket(client)["id"]
    r = _move(client, tid, "DONE")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"
    assert client.get(f"/api/tickets/{tid}").json()["status"] == "PENDING"


def test_noop_and_404(client: TestClient) -> None:
    tid = _ticket(client)["id"]
    assert _move(client, tid, "PENDING").status_code == 200
    assert _move(client, "nope", "IN_PROGRESS").status_code == 404


def test_done_keeps_agent_busy_with_other_active(client: TestClient) -> None:
    aid = _agent(client)
    t1 = _ticket(client, aid, "A")["id"]
    t2 = _ticket(client, aid, "B")["id"]
    _move(client, t2, "IN_PROGRESS")
    for to in ("IN_PROGRESS", "IN_QA", "IN_SENIOR_REVIEW", "IN_REVIEW", "DONE"):
        _move(client, t1, to)
    assert _agent_status(client, aid) != "IDLE"


def test_r1_blocked_agent_untouched(client: TestClient) -> None:
    aid = _agent(client)
    client.patch(f"/api/agents/{aid}/status", json={"status": "BLOCKED"})
    tid = _ticket(client, aid)["id"]
    _move(client, tid, "IN_PROGRESS")
    assert _agent_status(client, aid) == "BLOCKED"


def test_gate_pending_blocks_done(client: TestClient, migrated_db: Database) -> None:
    tid = _ticket(client)["id"]
    for to in ("IN_PROGRESS", "IN_QA", "IN_SENIOR_REVIEW", "IN_REVIEW"):
        _move(client, tid, to)
    migrated_db.execute(
        "INSERT INTO approvals (id, ticket_id, title, gate, requested_at)"
        " VALUES ('g1', ?, 'Merge', 3, '2026-11-23T00:00:00.000Z')",
        (tid,),
    )
    r = _move(client, tid, "DONE")
    assert r.status_code == 409 and r.json()["error"]["code"] == "GATE_PENDING"
