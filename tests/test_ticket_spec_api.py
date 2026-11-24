"""Especificación de las subtareas (J04 → REQ01): objetivo, criterios, acciones, modelo..."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.agent_policy import GLOBAL_RESTRICTIONS
from app.events.bus import get_bus


@pytest.fixture
def parent(client: TestClient) -> dict[str, str]:
    client.post("/api/admin/projects", json={"id": "web", "name": "Web"})
    cto = client.post("/api/agents", json={"name": "Sheldon", "role": "CTO", "roleType": "CTO"})
    dev = client.post("/api/agents", json={"name": "Leonard", "role": "Dev"})
    req = client.post("/api/tickets", json={"title": "P", "requirement": "R", "projectId": "web"})
    assert cto.status_code == dev.status_code == req.status_code == 201
    return {"parent": req.json()["id"], "dev": dev.json()["id"]}


def task_body(parent: dict[str, str], **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "parentTicketId": parent["parent"],
        "title": "Tarea",
        "objective": "Objetivo",
        "acceptanceCriteria": ["Hecho"],
        "assignedAgentId": parent["dev"],
        "model": "gemini-pro",
        "priority": "MEDIUM",
    }
    body.update(extra)
    return body


def create(client: TestClient, parent: dict[str, str], **extra: Any) -> dict[str, Any]:
    r = client.post("/api/tickets", json=task_body(parent, **extra))
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_especificacion_completa_se_guarda_y_sale_en_get_y_snapshot(
    client: TestClient, parent: dict[str, str]
) -> None:
    t = create(
        client,
        parent,
        objective="  Añadir el endpoint de modelos ",
        acceptanceCriteria=["Devuelve 5 modelos", " Tiene hasConnection "],
        actions=["Crear el router", "Añadir tests"],
        restrictions=["No tocar el FRONT"],
        dependencies=["J01"],
    )
    assert t["objective"] == "Añadir el endpoint de modelos"
    assert t["acceptanceCriteria"] == ["Devuelve 5 modelos", "Tiene hasConnection"]
    assert t["actions"] == ["Crear el router", "Añadir tests"]
    assert t["restrictions"] == ["No tocar el FRONT"]
    assert t["dependencies"] == ["J01"]
    assert t["model"] == "gemini-pro" and t["priority"] == "MEDIUM"
    assert t["kind"] == "TASK" and t["parentTicketId"] == parent["parent"]
    assert t["projectId"] == "web"  # hereda el proyecto del pedido
    assert client.get(f"/api/tickets/{t['id']}").json() == t
    snap = client.get("/api/snapshot").json()
    assert t in snap["tickets"]


def test_las_restricciones_globales_se_descartan(
    client: TestClient, parent: dict[str, str]
) -> None:
    messy = "  " + GLOBAL_RESTRICTIONS[0].upper().replace(" ", "   ") + " "
    t = create(client, parent, restrictions=[GLOBAL_RESTRICTIONS[1], messy, "Solo en la rama dev"])
    assert t["restrictions"] == ["Solo en la rama dev"]


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-9"},
        {"actions": [""]},
        {"actions": ["x" * 501]},
        {"acceptanceCriteria": ["a"] * 41},
        {"acceptanceCriteria": []},
        {"objective": ""},
        {"dependencies": "J01"},
        {"restrictions": [1]},
        {"priority": "URGENT"},
        {"assignedAgentId": "nadie"},
        {"parentTicketId": "nadie-existe"},
        {"proyecto": "x"},
    ],
)
def test_validaciones_400(
    client: TestClient, parent: dict[str, str], payload: dict[str, object]
) -> None:
    r = client.post("/api/tickets", json=task_body(parent, **payload))
    assert r.status_code in (400, 404)
    if r.status_code == 400:
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_40_elementos_de_500_caracteres_valen(client: TestClient, parent: dict[str, str]) -> None:
    t = create(client, parent, actions=["x" * 500] * 40)
    assert len(t["actions"]) == 40


def test_evento_sse_lleva_los_campos_nuevos(client: TestClient, parent: dict[str, str]) -> None:
    seen: list[dict[str, object]] = []
    bus = client.app.dependency_overrides[get_bus]()  # type: ignore[attr-defined]
    bus.subscribe(lambda ev: seen.append(ev.payload) if ev.type == "ticket.created" else None)
    create(client, parent, objective="Obj", actions=["a"], model="claude-haiku-5-5")
    assert seen and seen[0]["objective"] == "Obj"
    assert seen[0]["actions"] == ["a"] and seen[0]["model"] == "claude-haiku-5-5"
    assert "acceptanceCriteria" in seen[0] and "dependencies" in seen[0]
    assert seen[0]["kind"] == "TASK" and seen[0]["parentTicketId"] == parent["parent"]
