import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.domain.agent_policy import GLOBAL_RESTRICTIONS


def create(client: TestClient, **extra: object) -> dict[str, object]:
    r = client.post("/api/tickets", json={"title": "Tarea", **extra})
    assert r.status_code == 201, r.text
    body: dict[str, object] = r.json()
    return body


def test_ticket_sin_especificacion_devuelve_valores_por_defecto(client: TestClient) -> None:
    t = create(client)
    assert t["objective"] == ""
    assert t["acceptanceCriteria"] == [] and t["actions"] == []
    assert t["restrictions"] == [] and t["dependencies"] == []
    assert t["model"] is None


def test_especificacion_completa_se_guarda_y_sale_en_get_y_snapshot(client: TestClient) -> None:
    t = create(
        client,
        objective="  Añadir el endpoint de modelos ",
        acceptanceCriteria=["Devuelve 5 modelos", " Tiene hasConnection "],
        actions=["Crear el router", "Añadir tests"],
        restrictions=["No tocar el FRONT"],
        dependencies=["J01"],
        model="gemini-pro",
        description="texto antiguo",
    )
    assert t["objective"] == "Añadir el endpoint de modelos"
    assert t["acceptanceCriteria"] == ["Devuelve 5 modelos", "Tiene hasConnection"]
    assert t["actions"] == ["Crear el router", "Añadir tests"]
    assert t["restrictions"] == ["No tocar el FRONT"]
    assert t["dependencies"] == ["J01"]
    assert t["model"] == "gemini-pro" and t["description"] == "texto antiguo"
    assert client.get(f"/api/tickets/{t['id']}").json() == t
    snap = client.get("/api/snapshot").json()
    assert snap["tickets"][0] == t


def test_las_restricciones_globales_se_descartan(client: TestClient) -> None:
    messy = "  " + GLOBAL_RESTRICTIONS[0].upper().replace(" ", "   ") + " "
    t = create(client, restrictions=[GLOBAL_RESTRICTIONS[1], messy, "Solo en la rama dev"])
    assert t["restrictions"] == ["Solo en la rama dev"]


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-9"},
        {"actions": [""]},
        {"actions": ["x" * 501]},
        {"acceptanceCriteria": ["a"] * 41},
        {"dependencies": "J01"},
        {"restrictions": [1]},
    ],
)
def test_validaciones_400(client: TestClient, payload: dict[str, object]) -> None:
    r = client.post("/api/tickets", json={"title": "T", **payload})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_40_elementos_de_500_caracteres_valen(client: TestClient) -> None:
    t = create(client, actions=["x" * 500] * 40)
    assert len(t["actions"]) == 40  # type: ignore[arg-type]


def test_evento_sse_lleva_los_campos_nuevos(client: TestClient, migrated_db: Database) -> None:
    from app.events.bus import get_bus

    seen: list[dict[str, object]] = []
    bus = client.app.dependency_overrides[get_bus]()  # type: ignore[attr-defined]
    bus.subscribe(lambda ev: seen.append(ev.payload) if ev.type == "ticket.created" else None)
    create(client, objective="Obj", actions=["a"], model="claude-haiku-5-5")
    assert seen and seen[0]["objective"] == "Obj"
    assert seen[0]["actions"] == ["a"] and seen[0]["model"] == "claude-haiku-5-5"
    assert "acceptanceCriteria" in seen[0] and "dependencies" in seen[0]
