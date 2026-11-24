"""CEO-EDIT: el CEO edita sus tickets (título, requerimiento, prioridad, modelo, proyecto)."""

from fastapi.testclient import TestClient

from tests.test_requests_api import REQ, agent, project


def _pedido(c: TestClient) -> dict:  # type: ignore[type-arg]
    project(c)
    agent(c, "Sheldon", roleType="CTO")
    r = c.post("/api/tickets", json=REQ)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_editar_titulo_requerimiento_y_prioridad(client: TestClient) -> None:
    t = _pedido(client)
    r = client.patch(
        f"/api/tickets/{t['id']}",
        json={"title": "Landing v2", "requirement": "Más cosas", "priority": "HIGH"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["title"] == "Landing v2" and b["requirement"] == "Más cosas"
    assert b["description"] == "Más cosas" and b["priority"] == "HIGH"
    assert b["status"] == "PENDING"


def test_priority_null_vuelve_a_por_definir_y_modelo_invalido_da_400(client: TestClient) -> None:
    t = _pedido(client)
    client.patch(f"/api/tickets/{t['id']}", json={"priority": "LOW"})
    r = client.patch(f"/api/tickets/{t['id']}", json={"priority": None})
    assert r.status_code == 200 and r.json()["priorityLabel"] == "Por definir"
    bad = client.patch(f"/api/tickets/{t['id']}", json={"model": "no-existe"})
    assert bad.status_code == 400


def test_no_se_edita_un_ticket_hecho_ni_inexistente(client: TestClient) -> None:
    assert client.patch("/api/tickets/nada", json={"title": "x"}).status_code == 404
    t = _pedido(client)
    r = client.patch(f"/api/tickets/{t['id']}", json={"title": ""})
    assert r.status_code == 400
