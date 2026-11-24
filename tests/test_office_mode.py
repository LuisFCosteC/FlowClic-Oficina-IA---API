"""Modo de la oficina: desayuno/almuerzo/dormir detienen a todos sin perder nada."""

from typing import Any

from fastapi.testclient import TestClient

from app.db.database import Database
from tests.test_orchestrator import FakeLlm, make_request, mk, run, statuses, team  # noqa: F401


def agent_status(c: TestClient) -> dict[str, str]:
    return {a["name"]: a["status"] for a in c.get("/api/agents").json()}


def test_pausa_desactiva_a_todos_y_trabajar_deja_descansando_al_que_no_tiene_tareas(
    client: TestClient,
    team: dict[str, Any],  # noqa: F811
) -> None:
    mk(client, "Penny")  # sin tareas
    assert client.get("/api/office/mode").json() == {"mode": "work"}
    r = client.put("/api/office/mode", json={"mode": "lunch"})
    assert r.status_code == 200 and r.json() == {"mode": "lunch"}
    assert set(agent_status(client).values()) == {"IDLE"}
    # reanudar: nadie tiene tickets, así que nadie queda "activo"
    client.put("/api/office/mode", json={"mode": "work"})
    assert set(agent_status(client).values()) == {"IDLE"}


def test_la_pausa_no_pierde_el_trabajo_y_al_reanudar_cada_uno_vuelve_a_lo_suyo(
    client: TestClient,
    migrated_db: Database,
    team: dict[str, Any],  # noqa: F811
) -> None:
    make_request(client)
    llm = FakeLlm(team["worker"]["id"])
    run(migrated_db, llm, ticks=1)  # Sheldon toma el pedido y lo reparte
    before = statuses(client)
    assert before["Análisis"] == "IN_PROGRESS"
    assert agent_status(client)["Sheldon"] == "WORKING"

    client.put("/api/office/mode", json={"mode": "sleep"})
    assert set(agent_status(client).values()) == {"IDLE"}
    run(migrated_db, llm, ticks=6)  # en pausa el orquestador no avanza
    assert statuses(client) == before  # nada se perdió ni se movió

    client.put("/api/office/mode", json={"mode": "work"})
    assert agent_status(client)["Sheldon"] == "WORKING"  # su pedido sigue en curso
    run(migrated_db, llm, ticks=8)
    assert statuses(client)["Análisis"] == "IN_REVIEW"
    assert set(agent_status(client).values()) == {"IDLE"}  # terminado y aprobado: a descansar


def test_modo_invalido_da_400(client: TestClient) -> None:
    r = client.put("/api/office/mode", json={"mode": "fiesta"})
    assert r.status_code in (400, 422)
