"""Limpiar tickets desde Administración: no toca a los agentes."""

from fastapi.testclient import TestClient

from tests.test_requests_api import REQ, agent, project


def _setup(c: TestClient) -> str:
    project(c)
    agent(c, "Sheldon", roleType="CTO")
    t = c.post("/api/tickets", json=REQ).json()
    c.post(f"/api/tickets/{t['id']}/transition", json={"to": "IN_PROGRESS"})
    return str(t["id"])


def test_borrar_todos_deja_los_agentes_y_los_pone_en_descanso(client: TestClient) -> None:
    _setup(client)
    assert client.get("/api/agents").json()[0]["status"] == "WORKING"
    r = client.delete("/api/admin/tickets", params={"scope": "all"})
    assert r.status_code == 200 and r.json() == {"deleted": 1}
    assert client.get("/api/tickets").json() == []
    agents = client.get("/api/agents").json()
    assert len(agents) == 1 and agents[0]["status"] == "IDLE" and agents[0]["currentTask"] is None


def test_borrar_solo_hechos_respeta_los_demas(client: TestClient) -> None:
    keep = _setup(client)
    r = client.delete("/api/admin/tickets", params={"scope": "done"})
    assert r.json() == {"deleted": 0}
    assert [t["id"] for t in client.get("/api/tickets").json()] == [keep]


def test_scope_invalido_da_400(client: TestClient) -> None:
    assert client.delete("/api/admin/tickets", params={"scope": "x"}).status_code == 400
    assert client.delete("/api/admin/tickets").status_code == 400
