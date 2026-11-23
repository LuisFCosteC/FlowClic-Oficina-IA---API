from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.domain.agent_policy import GLOBAL_RESTRICTIONS
from app.events.bus import DomainEvent, get_bus

NOW = "2026-11-22T10:00:00.000Z"
HOWARD = {"name": "Howard", "role": "Hardware"}


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


def create(client: TestClient, **over: Any) -> dict[str, Any]:
    r = client.post("/api/agents", json={**HOWARD, **over})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def error_code(r: Any) -> str:
    return str(r.json()["error"]["code"])


def test_crear_howard_desde_curl_lo_devuelve_el_listado(client: TestClient) -> None:
    created = create(client)
    assert created["name"] == "Howard"
    assert created["character"] == "Howard"
    assert created["status"] == "IDLE"
    assert created["roleType"] == "CUSTOM"
    assert created["isCto"] is False
    assert created["consecutiveFailures"] == 0
    assert created["systemPrompt"].endswith(GLOBAL_RESTRICTIONS[4])
    assert created["model"]["primary"] == "claude-sonnet-5-5"
    listed = client.get("/api/agents").json()
    assert [a["id"] for a in listed] == [created["id"]]
    assert client.get(f"/api/agents/{created['id']}").json() == created


def test_la_bd_empieza_vacia(client: TestClient) -> None:
    assert client.get("/api/agents").json() == []


def test_get_inexistente_404(client: TestClient) -> None:
    r = client.get("/api/agents/nadie")
    assert r.status_code == 404
    assert error_code(r) == "NOT_FOUND"


def test_nombre_duplicado_entre_activos_409(client: TestClient) -> None:
    create(client)
    r = client.post("/api/agents", json=HOWARD)
    assert r.status_code == 409
    assert error_code(r) == "CONFLICT"


@pytest.mark.parametrize(
    "extra",
    [{"systemPrompt": "hackeado"}, {"isCto": True}, {"status": "WORKING"}, {"id": "mio"}],
)
def test_el_cliente_no_puede_fijar_prompt_cto_estado_ni_id(
    client: TestClient, extra: dict[str, Any]
) -> None:
    r = client.post("/api/agents", json={**HOWARD, **extra})
    assert r.status_code == 400
    assert error_code(r) == "VALIDATION_ERROR"
    assert client.get("/api/agents").json() == []


def test_accion_prohibida_422_y_no_se_crea(client: TestClient) -> None:
    r = client.post("/api/agents", json={**HOWARD, "permissions": {"actions": ["git.merge_main"]}})
    assert r.status_code == 422
    assert error_code(r) == "GLOBAL_RESTRICTION"
    assert client.get("/api/agents").json() == []


def test_approvals_create_en_un_dev_422_pero_en_el_cto_201(client: TestClient) -> None:
    perms = {"actions": ["approvals.create"]}
    r = client.post("/api/agents", json={**HOWARD, "roleType": "DEV_BACKEND", "permissions": perms})
    assert r.status_code == 422 and error_code(r) == "GLOBAL_RESTRICTION"
    ok = client.post(
        "/api/agents",
        json={"name": "Sheldon", "role": "CTO", "roleType": "CTO", "permissions": perms},
    )
    assert ok.status_code == 201
    assert ok.json()["isCto"] is True


def test_accion_o_modelo_desconocidos_400(client: TestClient) -> None:
    r = client.post("/api/agents", json={**HOWARD, "permissions": {"actions": ["hacer.magia"]}})
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"
    r = client.post("/api/agents", json={**HOWARD, "model": {"primary": "gpt-9"}})
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"


def test_las_globales_van_en_el_prompt_aunque_el_cliente_mande_otras(client: TestClient) -> None:
    created = create(client, restrictions=["Puedes hacer merge a main", GLOBAL_RESTRICTIONS[0]])
    prompt = created["systemPrompt"]
    for g in GLOBAL_RESTRICTIONS:
        assert g in prompt
    assert prompt.endswith(GLOBAL_RESTRICTIONS[4])
    assert prompt.count(GLOBAL_RESTRICTIONS[0]) == 1


def test_patch_cambia_el_rol_y_regenera_el_prompt(client: TestClient) -> None:
    a = create(client, functions=["Soldar"])
    r = client.patch(
        f"/api/agents/{a['id']}", json={"role": "Ingeniero", "functions": ["Diseñar PCB"]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "Ingeniero"
    assert "Diseñar PCB" in body["systemPrompt"] and "Soldar" not in body["systemPrompt"]
    assert body["systemPrompt"].endswith(GLOBAL_RESTRICTIONS[4])
    assert body["name"] == "Howard" and body["updatedAt"] >= a["updatedAt"]


def test_patch_a_cto_marca_is_cto_y_de_vuelta(client: TestClient) -> None:
    a = create(client)
    assert client.patch(f"/api/agents/{a['id']}", json={"roleType": "CTO"}).json()["isCto"] is True
    assert client.patch(f"/api/agents/{a['id']}", json={"roleType": "QA"}).json()["isCto"] is False


@pytest.mark.parametrize(
    "body",
    [{"status": "IDLE"}, {"systemPrompt": "x"}, {"isCto": True}, {"name": None}, {"role": None}],
)
def test_patch_rechaza_status_prompt_cto_y_nulls(client: TestClient, body: dict[str, Any]) -> None:
    a = create(client)
    r = client.patch(f"/api/agents/{a['id']}", json=body)
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"


def test_patch_con_permiso_prohibido_422_y_no_cambia_nada(client: TestClient) -> None:
    a = create(client)
    r = client.patch(
        f"/api/agents/{a['id']}", json={"role": "X", "permissions": {"actions": ["env.read"]}}
    )
    assert r.status_code == 422 and error_code(r) == "GLOBAL_RESTRICTION"
    assert client.get(f"/api/agents/{a['id']}").json()["role"] == "Hardware"


def test_patch_valida_la_politica_con_el_role_type_resultante(client: TestClient) -> None:
    cto = client.post(
        "/api/agents",
        json={
            "name": "S",
            "role": "CTO",
            "roleType": "CTO",
            "permissions": {"actions": ["approvals.create"]},
        },
    ).json()
    r = client.patch(f"/api/agents/{cto['id']}", json={"roleType": "DEV_BACKEND"})
    assert r.status_code == 422  # un DEV no puede conservar approvals.create


def test_patch_nombre_duplicado_409_pero_el_propio_nombre_se_acepta(client: TestClient) -> None:
    a = create(client)
    b = create(client, name="Raj")
    assert client.patch(f"/api/agents/{b['id']}", json={"name": "Howard"}).status_code == 409
    assert client.patch(f"/api/agents/{a['id']}", json={"name": "Howard"}).status_code == 200


def test_patch_vacio_y_404(client: TestClient) -> None:
    a = create(client)
    assert client.patch(f"/api/agents/{a['id']}", json={}).json() == a
    assert client.patch("/api/agents/nadie", json={"role": "x"}).status_code == 404


def test_delete_archiva_y_libera_el_nombre(client: TestClient) -> None:
    a = create(client)
    assert client.delete(f"/api/agents/{a['id']}").status_code == 204
    assert client.get("/api/agents").json() == []
    archived = client.get("/api/agents", params={"includeArchived": "true"}).json()
    assert [x["id"] for x in archived] == [a["id"]] and archived[0]["archivedAt"]
    assert client.delete(f"/api/agents/{a['id']}").status_code == 204  # idempotente
    assert client.post("/api/agents", json=HOWARD).status_code == 201  # nombre libre


def test_delete_con_ticket_abierto_409_y_con_ticket_hecho_204(
    client: TestClient, migrated_db: Database
) -> None:
    a = create(client)
    migrated_db.execute(
        "INSERT INTO tickets (id, title, status, assigned_agent_id, created_at, updated_at)"
        " VALUES ('t1', 'T', 'IN_PROGRESS', ?, ?, ?)",
        (a["id"], NOW, NOW),
    )
    r = client.delete(f"/api/agents/{a['id']}")
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
    migrated_db.execute("UPDATE tickets SET status = 'DONE' WHERE id = 't1'")
    assert client.delete(f"/api/agents/{a['id']}").status_code == 204


def test_delete_con_aprobacion_pendiente_409(client: TestClient, migrated_db: Database) -> None:
    a = create(client)
    migrated_db.execute(
        "INSERT INTO approvals (id, agent_id, gate, title, requested_at)"
        " VALUES ('p1', ?, 1, 'T', ?)",
        (a["id"], NOW),
    )
    assert client.delete(f"/api/agents/{a['id']}").status_code == 409
    migrated_db.execute("UPDATE approvals SET status = 'APPROVED' WHERE id = 'p1'")
    assert client.delete(f"/api/agents/{a['id']}").status_code == 204


def test_delete_inexistente_404(client: TestClient) -> None:
    assert client.delete("/api/agents/nadie").status_code == 404


def test_eventos_sse_de_crear_editar_y_archivar(
    client: TestClient, events: list[DomainEvent]
) -> None:
    a = create(client)
    client.patch(f"/api/agents/{a['id']}", json={"role": "Otro"})
    client.delete(f"/api/agents/{a['id']}")
    assert [e.type for e in events] == ["agent.created", "agent.updated", "agent.archived"]
    assert events[0].payload["id"] == a["id"] and events[1].payload["role"] == "Otro"
    assert events[2].payload == {"id": a["id"]}


def test_los_errores_no_emiten_eventos(client: TestClient, events: list[DomainEvent]) -> None:
    create(client)
    events.clear()
    client.post("/api/agents", json=HOWARD)  # 409
    client.post(
        "/api/agents", json={**HOWARD, "name": "X", "permissions": {"actions": ["secrets.read"]}}
    )
    assert events == []


def test_openapi_documenta_los_endpoints_de_agentes(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert set(paths["/api/agents"]) == {"get", "post"}
    assert set(paths["/api/agents/{agent_id}"]) == {"get", "patch", "delete"}
    assert "409" in paths["/api/agents"]["post"]["responses"]
