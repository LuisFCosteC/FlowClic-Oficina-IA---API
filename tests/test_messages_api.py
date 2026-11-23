from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database, IntegrityError
from app.events.bus import DomainEvent, get_bus

NOW = "2026-11-22T10:00:00.000Z"


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


@pytest.fixture
def team(client: TestClient, migrated_db: Database) -> dict[str, str]:
    """Agentes demo cargados: ids sheldon, leonard, penny, raj."""
    from app.db.seed import seed_demo_agents

    seed_demo_agents(migrated_db)
    return {n: n for n in ("sheldon", "leonard", "penny", "raj")}


def send(client: TestClient, **body: Any) -> Any:
    return client.post("/api/messages", json=body)


def thread(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    r = client.get("/api/messages", params=params)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def bodies(entries: list[dict[str, Any]]) -> list[str]:
    return [e["body"] for e in entries]


def add_ticket_with_event(db: Database, agent_id: str, ticket_id: str = "t1") -> None:
    db.execute(
        "INSERT INTO tickets (id, title, status, assigned_agent_id, created_at, updated_at)"
        " VALUES (?, 'Plan API', 'IN_PROGRESS', ?, ?, ?)",
        (ticket_id, agent_id, NOW, NOW),
    )
    db.execute(
        "INSERT INTO ticket_events (id, ticket_id, type, from_value, to_value, actor, created_at)"
        " VALUES (?, ?, 'STATUS_CHANGED', 'PENDING', 'IN_PROGRESS', 'human',"
        " '2026-11-22T10:00:05.000Z')",
        (f"e-{ticket_id}", ticket_id),
    )


# ── POST ─────────────────────────────────────────────────────────────────────────────────────
def test_orden_global_se_guarda_pendiente(client: TestClient, team: dict[str, str]) -> None:
    r = send(client, scope="GLOBAL", kind="ORDER", body="Prioriza el login")
    assert r.status_code == 201
    m = r.json()
    assert m["scope"] == "GLOBAL" and m["agentId"] is None
    assert m["authorType"] == "HUMAN" and m["status"] == "PENDING" and m["kind"] == "ORDER"
    assert m["body"] == "Prioriza el login" and m["createdAt"]


def test_la_orden_global_aparece_en_el_hilo_de_sheldon_y_no_en_el_de_los_demas(
    client: TestClient, team: dict[str, str]
) -> None:
    send(client, scope="GLOBAL", body="Orden para todos")
    assert bodies(thread(client, agentId="sheldon")) == ["Orden para todos"]
    for other in ("leonard", "penny", "raj"):
        assert thread(client, agentId=other) == []
    assert bodies(thread(client, scope="GLOBAL")) == ["Orden para todos"]


def test_la_individual_va_al_agente_con_copia_para_sheldon(
    client: TestClient, team: dict[str, str]
) -> None:
    send(client, scope="AGENT", agentId="leonard", kind="QUESTION", body="¿Cómo va la API?")
    assert bodies(thread(client, agentId="leonard")) == ["¿Cómo va la API?"]
    sheldon = thread(client, agentId="sheldon")
    assert bodies(sheldon) == ["¿Cómo va la API?"] and sheldon[0]["agentId"] == "leonard"
    assert thread(client, agentId="raj") == []
    assert thread(client, scope="GLOBAL") == []  # no es global


@pytest.mark.parametrize("body", ["x" * 2001, "", "   "])
def test_texto_demasiado_largo_o_vacio_400(
    client: TestClient, team: dict[str, str], body: str
) -> None:
    r = send(client, scope="GLOBAL", body=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_2000_caracteres_exactos_se_aceptan(client: TestClient, team: dict[str, str]) -> None:
    assert send(client, scope="GLOBAL", body="x" * 2000).status_code == 201


@pytest.mark.parametrize(
    "extra",
    [
        {"scope": "AGENT"},  # falta agentId
        {"scope": "GLOBAL", "agentId": "leonard"},  # global no lleva agente
        {"scope": "GLOBAL", "kind": "STATUS"},  # STATUS/REPLY: solo sistema o agentes
        {"scope": "GLOBAL", "kind": "REPLY"},
        {"scope": "GLOBAL", "status": "DONE"},  # no se puede fijar el estado
        {"scope": "GLOBAL", "authorType": "AGENT"},  # ni suplantar al autor
        {"scope": "GLOBAL", "authorId": "sheldon"},
        {"scope": "OTRO"},
    ],
)
def test_cuerpos_invalidos_400(
    client: TestClient, team: dict[str, str], extra: dict[str, Any]
) -> None:
    r = send(client, body="hola", **extra)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert thread(client, scope="GLOBAL") == []


def test_agente_inexistente_404_y_archivado_409(client: TestClient, team: dict[str, str]) -> None:
    assert send(client, scope="AGENT", agentId="nadie", body="hola").status_code == 404
    client.delete("/api/agents/penny")
    assert send(client, scope="AGENT", agentId="penny", body="hola").status_code == 409


def test_el_texto_se_guarda_tal_cual_sin_interpretar_html(
    client: TestClient, team: dict[str, str]
) -> None:
    evil = '<script>alert(1)</script><img src=x onerror="x()"> & "comillas"'
    m = send(client, scope="GLOBAL", body=evil).json()
    assert m["body"] == evil
    assert bodies(thread(client, agentId="sheldon")) == [evil]


def test_emite_message_created(
    client: TestClient, team: dict[str, str], events: list[DomainEvent]
) -> None:
    events.clear()
    m = send(client, scope="AGENT", agentId="raj", body="Revisa el ticket").json()
    assert [e.type for e in events] == ["message.created"]
    assert events[0].payload["id"] == m["id"] and events[0].payload["agentId"] == "raj"
    events.clear()
    send(client, scope="GLOBAL", body="")  # inválido: no emite
    assert events == []


# ── GET: combinación con eventos de ticket, orden y límites ──────────────────────────────────
def test_el_hilo_combina_mensajes_y_eventos_de_ticket_por_fecha(
    client: TestClient, team: dict[str, str], migrated_db: Database
) -> None:
    add_ticket_with_event(migrated_db, "leonard")
    m = send(client, scope="AGENT", agentId="leonard", body="Sigue así").json()
    entries = thread(client, agentId="leonard")
    assert [e["entryType"] for e in entries] == ["TICKET_EVENT", "MESSAGE"]
    event = entries[0]
    assert event["kind"] == "STATUS_CHANGED" and event["ticketId"] == "t1"
    assert event["body"] == "«Plan API»: STATUS_CHANGED (PENDING → IN_PROGRESS)"
    assert entries[1]["id"] == m["id"]
    assert [e["createdAt"] for e in entries] == sorted(e["createdAt"] for e in entries)
    # los eventos del ticket de Leonard no salen en el hilo de Raj
    assert thread(client, agentId="raj") == []


def test_scope_global_incluye_los_eventos_de_todo_el_equipo(
    client: TestClient, team: dict[str, str], migrated_db: Database
) -> None:
    add_ticket_with_event(migrated_db, "penny")
    entries = thread(client, scope="GLOBAL")
    assert [e["entryType"] for e in entries] == ["TICKET_EVENT"]


def test_limit_devuelve_los_mas_recientes_en_orden_cronologico(
    client: TestClient, team: dict[str, str]
) -> None:
    for i in range(5):
        send(client, scope="AGENT", agentId="leonard", body=f"m{i}")
    assert bodies(thread(client, agentId="leonard", limit=2)) == ["m3", "m4"]
    assert bodies(thread(client, agentId="leonard")) == ["m0", "m1", "m2", "m3", "m4"]


@pytest.mark.parametrize("limit", [0, -1, 501])
def test_limit_fuera_de_rango_400(client: TestClient, team: dict[str, str], limit: int) -> None:
    r = client.get("/api/messages", params={"agentId": "sheldon", "limit": limit})
    assert r.status_code == 400


def test_hay_que_indicar_agente_o_scope_global(client: TestClient, team: dict[str, str]) -> None:
    assert client.get("/api/messages").status_code == 400
    assert client.get("/api/messages", params={"scope": "AGENT"}).status_code == 400
    assert client.get("/api/messages", params={"agentId": "nadie"}).status_code == 404


# ── status-summary ───────────────────────────────────────────────────────────────────────────
def summary(client: TestClient, agent_id: str) -> dict[str, Any]:
    r = client.get(f"/api/agents/{agent_id}/status-summary")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_resumen_sin_ticket(client: TestClient, team: dict[str, str]) -> None:
    s = summary(client, "leonard")
    assert s["ticket"] is None and s["openTickets"] == {} and s["pendingApprovals"] == []
    assert s["nextStep"] == "Sin ticket asignado: esperando asignación."
    assert "Leonard" in s["summary"] and s["blockedReason"] is None


def test_resumen_refleja_el_ticket_actual_y_el_siguiente_paso(
    client: TestClient, team: dict[str, str], migrated_db: Database
) -> None:
    add_ticket_with_event(migrated_db, "leonard")
    migrated_db.execute(
        "UPDATE tickets SET description = 'Criterio: login con scrypt' WHERE id='t1'"
    )
    s = summary(client, "leonard")
    assert s["ticket"]["id"] == "t1" and s["ticket"]["status"] == "IN_PROGRESS"
    assert s["ticket"]["description"] == "Criterio: login con scrypt"
    assert s["ticket"]["sinceSeconds"] >= 0
    assert s["openTickets"] == {"IN_PROGRESS": 1}
    assert s["nextStep"] == "Terminar y pasar a QA (IN_PROGRESS → IN_QA)."
    migrated_db.execute("UPDATE tickets SET status = 'IN_QA' WHERE id = 't1'")
    assert "revisión de QA" in summary(client, "leonard")["nextStep"]
    migrated_db.execute("UPDATE tickets SET status = 'RETURNED' WHERE id = 't1'")
    assert "retomar" in summary(client, "leonard")["nextStep"]


def test_el_ticket_en_curso_tiene_prioridad_sobre_el_pendiente(
    client: TestClient, team: dict[str, str], migrated_db: Database
) -> None:
    migrated_db.execute(
        "INSERT INTO tickets (id, title, status, assigned_agent_id, created_at, updated_at)"
        " VALUES ('p', 'Pendiente', 'PENDING', 'penny', ?, '2026-11-22T12:00:00.000Z')",
        (NOW,),
    )
    migrated_db.execute(
        "INSERT INTO tickets (id, title, status, assigned_agent_id, created_at, updated_at)"
        " VALUES ('c', 'En curso', 'IN_PROGRESS', 'penny', ?, ?)",
        (NOW, NOW),
    )
    s = summary(client, "penny")
    assert s["ticket"]["id"] == "c"
    assert s["openTickets"] == {"PENDING": 1, "IN_PROGRESS": 1}


def test_resumen_de_un_agente_bloqueado_muestra_el_motivo(
    client: TestClient, team: dict[str, str]
) -> None:
    for _ in range(3):
        client.post("/api/agents/raj/failures", json={"outcome": "failure"})
    s = summary(client, "raj")
    assert s["status"] == "BLOCKED" and s["blockedReason"] == "3 fallos seguidos"
    assert "Desbloquear" in s["nextStep"]
    client.patch("/api/agents/penny/status", json={"status": "BLOCKED"})
    assert summary(client, "penny")["blockedReason"] == "bloqueado manualmente"


def test_resumen_lista_las_aprobaciones_pendientes(
    client: TestClient, team: dict[str, str], migrated_db: Database
) -> None:
    add_ticket_with_event(migrated_db, "leonard")
    migrated_db.execute(
        "INSERT INTO approvals (id, ticket_id, agent_id, gate, title, requested_at)"
        " VALUES ('a1', 't1', 'sheldon', 2, 'Arquitectura del login', ?)",
        (NOW,),
    )
    s = summary(client, "leonard")  # la compuerta cuelga de un ticket suyo
    assert s["pendingApprovals"] == [{"id": "a1", "title": "Arquitectura del login", "gate": 2}]
    assert "Aprobaciones pendientes: 1" in s["summary"]
    assert summary(client, "sheldon")["pendingApprovals"][0]["id"] == "a1"  # y la creó Sheldon


def test_resumen_404_y_pausa(client: TestClient, team: dict[str, str]) -> None:
    assert client.get("/api/agents/nadie/status-summary").status_code == 404
    client.patch("/api/agents/leonard/status", json={"status": "SLEEP_QUOTA"})
    assert "Reanudar" in summary(client, "leonard")["nextStep"]


def test_esquema_006_valida_scope_y_agente(migrated_db: Database) -> None:
    def insert(scope: str, agent_id: str | None, kind: str = "ORDER") -> None:
        migrated_db.execute(
            "INSERT INTO agent_messages (id, scope, agent_id, author_type, author_id, kind, body,"
            " created_at) VALUES (lower(hex(randomblob(4))), ?, ?, 'HUMAN', 'human', ?, 'x', ?)",
            (scope, agent_id, kind, NOW),
        )

    insert("GLOBAL", None)
    with pytest.raises(IntegrityError):
        insert("GLOBAL", "algun-agente")
    with pytest.raises(IntegrityError):
        insert("AGENT", None)
    with pytest.raises(IntegrityError):
        insert("GLOBAL", None, kind="HACK")


def test_openapi_documenta_mensajes_y_resumen(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert set(paths["/api/messages"]) == {"get", "post"}
    assert "get" in paths["/api/agents/{agent_id}/status-summary"]
