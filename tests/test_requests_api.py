"""REQ01 (pedidos del CEO y subtareas) y RPT01 (reports_to, CTO único)."""

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


def agent(c: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    r = c.post("/api/agents", json={"name": name, "role": "R", **extra})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def project(c: TestClient, pid: str = "web") -> None:
    assert c.post("/api/admin/projects", json={"id": pid, "name": pid}).status_code == 201


REQ = {"title": "Landing", "requirement": "Quiero una landing", "projectId": "web"}


def test_pedido_sin_cto_da_409(client: TestClient) -> None:
    project(client)
    r = client.post("/api/tickets", json=REQ)
    assert r.status_code == 409
    assert "Crea primero un agente con rol CTO" in r.json()["error"]["message"]


def test_pedido_se_asigna_al_cto_con_prioridad_y_modelo_por_definir(
    client: TestClient, events: list[DomainEvent]
) -> None:
    project(client)
    cto = agent(client, "Sheldon", roleType="CTO")
    r = client.post("/api/tickets", json=REQ)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["kind"] == "REQUEST" and t["status"] == "PENDING"
    assert t["assignedAgentId"] == cto["id"] and t["parentTicketId"] is None
    assert t["priority"] is None and t["model"] is None
    assert t["priorityLabel"] == "Por definir" and t["modelLabel"] == "Por definir"
    assert t["requirement"] == "Quiero una landing" and t["projectId"] == "web"
    assert client.get("/api/snapshot").json()["tickets"][0] == t
    created = [e for e in events if e.type == "ticket.created"]
    assert created[-1].payload["kind"] == "REQUEST" and created[-1].payload["priority"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x", "requirement": "y"},  # falta projectId
        {"title": "x", "projectId": "web"},  # falta requirement
        {"title": "x", "requirement": "", "projectId": "web"},
        {"title": "x", "requirement": "y", "projectId": "web", "priority": "HIGH"},
        {"title": "x", "requirement": "y", "projectId": "web", "assignedAgentId": "a"},
        {"title": "x", "requirement": "y", "projectId": "Web Mal"},
    ],
)
def test_pedido_invalido_400(client: TestClient, body: dict[str, Any]) -> None:
    project(client)
    agent(client, "Sheldon", roleType="CTO")
    assert client.post("/api/tickets", json=body).status_code == 400


def test_pedido_con_proyecto_inexistente_400(client: TestClient) -> None:
    agent(client, "Sheldon", roleType="CTO")
    assert client.post("/api/tickets", json=REQ).status_code == 400


def test_solo_un_cto_activo(client: TestClient, migrated_db: Database) -> None:
    project(client)
    agent(client, "Sheldon", roleType="CTO")
    r = client.post("/api/agents", json={"name": "Otro", "role": "R", "roleType": "CTO"})
    assert r.status_code == 409
    other = agent(client, "Pepe")
    assert client.patch(f"/api/agents/{other['id']}", json={"roleType": "CTO"}).status_code == 409
    # defensa: si la BD llegara a tener dos CTO, el pedido da 409
    migrated_db.execute("UPDATE agents SET role_type = 'CTO' WHERE id = ?", (other["id"],))
    r = client.post("/api/tickets", json=REQ)
    assert r.status_code == 409 and "más de un" in r.json()["error"]["message"]
    migrated_db.execute("UPDATE agents SET role_type = 'CUSTOM' WHERE id = ?", (other["id"],))
    assert client.post("/api/tickets", json=REQ).status_code == 201


def test_subtareas(client: TestClient) -> None:
    project(client)
    cto = agent(client, "Sheldon", roleType="CTO")
    leonard = agent(client, "Leonard", roleType="DEV_BACKEND")
    penny = agent(client, "Penny", roleType="DEV_FRONTEND")
    req = client.post("/api/tickets", json=REQ).json()
    body = {
        "parentTicketId": req["id"],
        "title": "API",
        "objective": "Crear la API",
        "acceptanceCriteria": ["Tests en verde"],
        "assignedAgentId": penny["id"],
        "model": "gemini-flash",
        "priority": "HIGH",
    }
    ok = client.post("/api/tickets", json={**body, "actingAgentId": cto["id"]})
    assert ok.status_code == 201, ok.text
    sub = ok.json()
    assert sub["kind"] == "TASK" and sub["parentTicketId"] == req["id"]
    assert sub["projectId"] == "web" and sub["priority"] == "HIGH"
    by_leonard = client.post("/api/tickets", json={**body, "actingAgentId": leonard["id"]})
    assert by_leonard.status_code == 201
    # un agente sin permiso (Penny) no puede crear subtareas
    denied = client.post("/api/tickets", json={**body, "actingAgentId": penny["id"]})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "FORBIDDEN"
    # la subtarea no puede ser padre; el padre debe existir
    nested = client.post("/api/tickets", json={**body, "parentTicketId": sub["id"]})
    assert nested.status_code == 400
    assert client.post("/api/tickets", json={**body, "parentTicketId": "x"}).status_code == 404


# ── RPT01 ────────────────────────────────────────────────────────────────────────────────────
def test_reports_to_crear_editar_y_snapshot(client: TestClient) -> None:
    boss = agent(client, "Sheldon", roleType="CTO")
    dev = agent(client, "Leonard", reportsTo=boss["id"])
    assert dev["reportsTo"] == boss["id"] and boss["reportsTo"] is None  # null = CEO
    snap = {a["id"]: a for a in client.get("/api/snapshot").json()["agents"]}
    assert snap[dev["id"]]["reportsTo"] == boss["id"]
    r = client.patch(f"/api/agents/{dev['id']}", json={"reportsTo": None})
    assert r.status_code == 200 and r.json()["reportsTo"] is None
    r = client.patch(f"/api/agents/{dev['id']}", json={"reportsTo": boss["id"]})
    assert r.json()["reportsTo"] == boss["id"]


def test_reports_to_invalido_400(client: TestClient) -> None:
    a = agent(client, "A")
    b = agent(client, "B", reportsTo=a["id"])
    c = agent(client, "C", reportsTo=b["id"])
    unknown = client.post("/api/agents", json={"name": "X", "role": "R", "reportsTo": "no"})
    assert unknown.status_code == 400
    assert client.patch(f"/api/agents/{a['id']}", json={"reportsTo": a["id"]}).status_code == 400
    assert client.patch(f"/api/agents/{a['id']}", json={"reportsTo": b["id"]}).status_code == 400
    r = client.patch(f"/api/agents/{a['id']}", json={"reportsTo": c["id"]})
    assert r.status_code == 400 and "ciclo" in r.json()["error"]["message"]
    assert client.get(f"/api/agents/{a['id']}").json()["reportsTo"] is None


def test_no_se_archiva_un_agente_del_que_dependen_otros(client: TestClient) -> None:
    boss = agent(client, "Sheldon", roleType="CTO")
    dev = agent(client, "Leonard", reportsTo=boss["id"])
    r = client.delete(f"/api/agents/{boss['id']}")
    assert r.status_code == 409 and "Leonard" in r.json()["error"]["message"]
    assert client.delete(f"/api/agents/{dev['id']}").status_code == 204
    assert client.delete(f"/api/agents/{boss['id']}").status_code == 204
    # un jefe archivado no se puede asignar
    late = client.post("/api/agents", json={"name": "Z", "role": "R", "reportsTo": boss["id"]})
    assert late.status_code == 400
