"""GM02: REVISIÓN SENIOR y REVISIÓN CTO, 403 por actingAgentId y subtareas de un pedido."""

from typing import Any

import pytest
from conftest import make_ticket
from fastapi.testclient import TestClient

from app.domain.agent_policy import VALID_TRANSITIONS
from app.domain.ticket_flow import can_transition

T = "/api/tickets"


def agent(c: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    r = c.post("/api/agents", json={"name": name, "role": "R", **extra})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def perms(transitions: list[list[str]], only_assigned: bool = True) -> dict[str, Any]:
    return {"ticketTransitions": transitions, "onlyAssignedTickets": only_assigned}


def move(c: TestClient, tid: str, to: str, acting: str | None = None) -> Any:
    body: dict[str, Any] = {"to": to}
    if acting:
        body["actingAgentId"] = acting
    return c.post(f"{T}/{tid}/transition", json=body)


def test_el_grafo_tiene_las_dos_revisiones() -> None:
    # el senior revisa ANTES que QA
    assert ("IN_PROGRESS", "IN_SENIOR_REVIEW") in VALID_TRANSITIONS
    assert ("IN_SENIOR_REVIEW", "IN_QA") in VALID_TRANSITIONS
    assert ("IN_SENIOR_REVIEW", "RETURNED") in VALID_TRANSITIONS
    assert ("IN_QA", "IN_REVIEW") in VALID_TRANSITIONS
    assert ("IN_QA", "RETURNED") in VALID_TRANSITIONS
    assert ("IN_PROGRESS", "IN_QA") not in VALID_TRANSITIONS  # no se salta la revisión senior
    assert ("IN_SENIOR_REVIEW", "IN_REVIEW") not in VALID_TRANSITIONS  # ni la de QA
    assert can_transition("IN_PROGRESS", "IN_QA") == "INVALID"
    assert can_transition("IN_SENIOR_REVIEW", "DONE") == "INVALID"
    assert len(VALID_TRANSITIONS) == 9


def test_flujo_completo_con_las_dos_revisiones_y_efecto_en_el_agente(client: TestClient) -> None:
    dev = agent(client, "Penny")
    tid = str(make_ticket(assigned_agent_id=dev["id"])["id"])
    for to, agent_status in [
        ("IN_PROGRESS", "WORKING"),
        ("IN_SENIOR_REVIEW", "REVIEW"),
        ("IN_QA", "REVIEW"),
        ("IN_REVIEW", "REVIEW"),
        ("DONE", "IDLE"),
    ]:
        r = move(client, tid, to)
        assert r.status_code == 200, (to, r.text)
        assert r.json()["status"] == to
        assert client.get(f"/api/agents/{dev['id']}").json()["status"] == agent_status
    bad = move(client, make_ticket()["id"], "IN_QA")  # PENDING → QA: inválida
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INVALID_TRANSITION"
    assert "EN QA" in bad.json()["error"]["message"]


def test_devuelta_desde_cada_revision(client: TestClient) -> None:
    for stop in ("IN_SENIOR_REVIEW", "IN_QA", "IN_REVIEW"):
        tid = str(make_ticket()["id"])
        for to in ("IN_PROGRESS", "IN_SENIOR_REVIEW", "IN_QA", "IN_REVIEW"):
            move(client, tid, to)
            if to == stop:
                break
        assert move(client, tid, "RETURNED").status_code == 200
        assert move(client, tid, "IN_PROGRESS").status_code == 200


def test_403_por_actingagentid(client: TestClient) -> None:
    dev = agent(client, "Penny", permissions=perms([["PENDING", "IN_PROGRESS"]]))
    other = agent(client, "Otra", permissions=perms([["PENDING", "IN_PROGRESS"]]))
    senior = agent(
        client,
        "Leonard",
        permissions=perms([["IN_SENIOR_REVIEW", "IN_QA"], ["IN_SENIOR_REVIEW", "RETURNED"]], False),
    )
    tid = str(make_ticket(assigned_agent_id=dev["id"])["id"])
    # sin la pareja en sus permisos
    r = move(client, tid, "IN_PROGRESS", acting=senior["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "TRANSITION_FORBIDDEN"
    # solo tickets asignados a él
    r = move(client, tid, "IN_PROGRESS", acting=other["id"])
    assert r.status_code == 403 and "asignados" in r.json()["error"]["message"]
    assert client.get(f"{T}/{tid}").json()["status"] == "PENDING"
    # el dueño sí; el evento queda con el agente como actor
    ok = move(client, tid, "IN_PROGRESS", acting=dev["id"])
    assert ok.status_code == 200 and ok.json()["status"] == "IN_PROGRESS"
    # una transición inválida del grafo es 409 aunque el agente no tenga permiso
    inv = move(client, tid, "DONE", acting=other["id"])
    assert inv.status_code == 409 and inv.json()["error"]["code"] == "INVALID_TRANSITION"
    # agente inexistente → 400
    assert move(client, tid, "IN_SENIOR_REVIEW", acting="nadie").status_code == 400


def test_revisor_senior_no_asignado_si_only_assigned_false(client: TestClient) -> None:
    dev = agent(client, "Penny")
    senior = agent(
        client,
        "Leonard",
        permissions=perms([["IN_SENIOR_REVIEW", "IN_QA"], ["IN_SENIOR_REVIEW", "RETURNED"]], False),
    )
    tid = str(make_ticket(assigned_agent_id=dev["id"])["id"])
    for to in ("IN_PROGRESS", "IN_SENIOR_REVIEW"):
        move(client, tid, to)
    ok = move(client, tid, "IN_QA", acting=senior["id"])
    assert ok.status_code == 200


def test_el_evento_guarda_al_agente_como_actor(client: TestClient, migrated_db: Any) -> None:
    dev = agent(client, "Penny", permissions=perms([["PENDING", "IN_PROGRESS"]]))
    tid = str(make_ticket(assigned_agent_id=dev["id"])["id"])
    move(client, tid, "IN_PROGRESS", acting=dev["id"])
    move(client, tid, "IN_SENIOR_REVIEW")
    rows = migrated_db.fetch_all(
        "SELECT actor, payload FROM ticket_events WHERE ticket_id = ? AND type = 'STATUS_CHANGED'"
        " ORDER BY created_at",
        (tid,),
    )
    assert [r["actor"] for r in rows] == [dev["id"], "human"]
    assert dev["id"] in rows[0]["payload"]


@pytest.fixture
def request_with_subtasks(client: TestClient) -> dict[str, Any]:
    client.post("/api/admin/projects", json={"id": "web", "name": "Web"})
    agent(client, "Sheldon", roleType="CTO")
    dev = agent(client, "Penny")
    req = client.post(T, json={"title": "P", "requirement": "R", "projectId": "web"}).json()
    subs = []
    for i in range(2):
        r = client.post(
            T,
            json={
                "parentTicketId": req["id"],
                "title": f"S{i}",
                "objective": "O",
                "acceptanceCriteria": ["ok"],
                "assignedAgentId": dev["id"],
                "model": "gemini-flash",
                "priority": "LOW",
            },
        )
        assert r.status_code == 201, r.text
        subs.append(r.json()["id"])
    return {"request": req["id"], "subs": subs}


def finish(c: TestClient, tid: str) -> None:
    for to in ("IN_PROGRESS", "IN_SENIOR_REVIEW", "IN_QA", "IN_REVIEW", "DONE"):
        assert move(c, tid, to).status_code == 200


def test_un_pedido_no_se_cierra_con_subtareas_abiertas(
    client: TestClient, request_with_subtasks: dict[str, Any]
) -> None:
    req = request_with_subtasks["request"]
    for to in ("IN_PROGRESS", "IN_SENIOR_REVIEW", "IN_QA", "IN_REVIEW"):
        assert move(client, req, to).status_code == 200
    r = move(client, req, "DONE")
    assert r.status_code == 409 and r.json()["error"]["code"] == "SUBTASKS_PENDING"
    finish(client, request_with_subtasks["subs"][0])
    assert move(client, req, "DONE").status_code == 409  # queda una
    finish(client, request_with_subtasks["subs"][1])
    assert move(client, req, "DONE").status_code == 200
    assert client.get(f"{T}/{req}").json()["status"] == "DONE"
