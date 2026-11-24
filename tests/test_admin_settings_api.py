"""A01–A03: proyecto, límites y reglas (Administración)."""

from collections.abc import Iterator
from typing import Any

import pytest
from conftest import make_ticket
from fastapi.testclient import TestClient

from app.db.database import Database
from app.events.bus import DomainEvent, get_bus

LIMITS = "/api/admin/settings/limits"
PROJECT = "/api/admin/settings/project"


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


# ── A01 / A02 ────────────────────────────────────────────────────────────────────────────────
def test_migracion_siembra_limites_y_proyecto_vacio(client: TestClient) -> None:
    assert client.get(LIMITS).json() == {
        "maxAgents": 20,
        "maxActiveTicketsPerAgent": 3,
        "requireApprovalForDone": False,
    }
    assert client.get(PROJECT).json() == {
        "companyName": "",
        "projectName": "",
        "description": "",
        "goals": [],
        "stack": [],
    }


def test_put_project_guarda_emite_evento_y_audita_solo_campos(
    client: TestClient, migrated_db: Database, events: list[DomainEvent]
) -> None:
    body = {
        "companyName": "FlowClic",
        "projectName": "Oficina IA",
        "description": "d",
        "goals": ["g1"],
        "stack": ["python"],
    }
    # PRJ01: solo se guarda la empresa; los campos de proyecto son compatibilidad y vuelven vacíos
    expected = {
        "companyName": "FlowClic",
        "projectName": "",
        "description": "",
        "goals": [],
        "stack": [],
    }
    assert client.put(PROJECT, json=body).json() == expected
    assert client.get(PROJECT).json() == expected
    stored = migrated_db.fetch_one("SELECT value FROM app_settings WHERE key = 'project'")
    assert stored is not None and stored["value"] == '{"companyName": "FlowClic"}'
    ev = [e for e in events if e.type == "settings.updated"]
    assert ev[-1].payload == {"key": "project", "value": expected}
    row = migrated_db.fetch_one(
        "SELECT meta FROM audit_log WHERE action = 'settings.project_updated'"
    )
    assert row is not None and "FlowClic" not in row["meta"] and "companyName" in row["meta"]


@pytest.mark.parametrize(
    "body",
    [
        {"companyName": "x" * 121},
        {"description": "x" * 2001},
        {"goals": ["x"] * 21},
        {"stack": ["x" * 61]},
        {"desconocido": 1},
    ],
)
def test_put_project_invalido_400(client: TestClient, body: dict[str, Any]) -> None:
    assert client.put(PROJECT, json=body).status_code == 400


@pytest.mark.parametrize(
    "patch",
    [
        {"maxAgents": 0},
        {"maxAgents": 101},
        {"maxActiveTicketsPerAgent": 0},
        {"requireApprovalForDone": "si"},
        {"maxAgents": 1.5},
    ],
)
def test_put_limits_fuera_de_rango_400(client: TestClient, patch: dict[str, Any]) -> None:
    body = {"maxAgents": 20, "maxActiveTicketsPerAgent": 3, "requireApprovalForDone": False}
    body.update(patch)
    assert client.put(LIMITS, json=body).status_code == 400


def test_put_limits_emite_evento_y_persiste(client: TestClient, events: list[DomainEvent]) -> None:
    _limits(client, maxAgents=5, requireApprovalForDone=True)
    assert client.get(LIMITS).json()["maxAgents"] == 5
    ev = [e for e in events if e.type == "settings.updated"][-1]
    assert ev.payload["key"] == "limits"


# ── A03 ──────────────────────────────────────────────────────────────────────────────────────
def test_crud_de_reglas_con_eventos(client: TestClient, events: list[DomainEvent]) -> None:
    r1 = client.post("/api/admin/rules", json={"title": "No secretos"})
    assert r1.status_code == 201
    assert r1.json()["severity"] == "MUST" and r1.json()["enabled"] is True
    r2 = client.post("/api/admin/rules", json={"title": "Tests", "severity": "SHOULD"}).json()
    assert [r["position"] for r in client.get("/api/admin/rules").json()] == [0, 1]
    upd = client.patch(f"/api/admin/rules/{r2['id']}", json={"enabled": False, "title": " T2 "})
    assert upd.json()["enabled"] is False and upd.json()["title"] == "T2"
    assert client.delete(f"/api/admin/rules/{r2['id']}").status_code == 204
    assert client.delete(f"/api/admin/rules/{r2['id']}").status_code == 404
    kinds = [e.type for e in events if e.type.startswith("rule.")]
    assert kinds == ["rule.created", "rule.created", "rule.updated", "rule.deleted"]


def test_regla_con_severidad_invalida_400(client: TestClient) -> None:
    assert (
        client.post("/api/admin/rules", json={"title": "x", "severity": "HIGH"}).status_code == 400
    )
    rid = client.post("/api/admin/rules", json={"title": "x"}).json()["id"]
    assert (
        client.patch(f"/api/admin/rules/{rid}", json={"severity": "OBLIGATORIA"}).status_code == 400
    )
    assert client.post("/api/admin/rules", json={"title": "  "}).status_code == 400
    assert client.patch("/api/admin/rules/nada", json={"title": "x"}).status_code == 404


def test_reordenar_persiste_y_valida_ids(client: TestClient) -> None:
    ids = [client.post("/api/admin/rules", json={"title": t}).json()["id"] for t in "abc"]
    new = [ids[2], ids[0], ids[1]]
    r = client.put("/api/admin/rules/order", json={"ids": new})
    assert r.status_code == 200
    assert [x["id"] for x in client.get("/api/admin/rules").json()] == new
    assert client.put("/api/admin/rules/order", json={"ids": new[:2]}).status_code == 400
    assert client.put("/api/admin/rules/order", json={"ids": [*new, "x"]}).status_code == 400
    assert client.put("/api/admin/rules/order", json={"ids": [new[0]] * 3}).status_code == 400
