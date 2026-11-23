import re

from fastapi.testclient import TestClient

from app.db.database import Database


def test_snapshot_de_la_bd_vacia(client: TestClient) -> None:
    r = client.get("/api/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["agents"] == [] and body["tickets"] == [] and body["approvals"] == []
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", body["serverTime"])
    assert set(body) == {"agents", "tickets", "approvals", "serverTime"}


def test_devuelve_los_4_agentes_del_equipo_base_tras_cargarlo(client: TestClient) -> None:
    client.post("/api/admin/agents/load-base-team")
    body = client.get("/api/snapshot").json()
    assert [a["name"] for a in body["agents"]] == ["Sheldon", "Leonard", "Penny", "Raj"]
    sheldon = body["agents"][0]
    assert sheldon["isCto"] is True and sheldon["roleType"] == "CTO"
    assert "systemPrompt" in sheldon and "consecutiveFailures" in sheldon


def test_snapshot_con_datos_de_demo_incluye_tickets_y_aprobaciones(
    seeded_client: TestClient,
) -> None:
    body = seeded_client.get("/api/snapshot").json()
    assert len(body["agents"]) == 4
    assert sorted(t["status"] for t in body["tickets"]) == [
        "IN_PROGRESS",
        "IN_QA",
        "IN_REVIEW",
        "PENDING",
    ]
    assert [t["status"] for t in body["tickets"]] == [
        "PENDING",
        "IN_PROGRESS",
        "IN_QA",
        "IN_REVIEW",
    ]
    assert len(body["approvals"]) == 1
    approval = body["approvals"][0]
    assert approval["gate"] == 4 and approval["status"] == "PENDING"
    assert approval["ticketId"] == "seed-ticket-4"
    ticket = body["tickets"][0]
    assert {"assignedAgentId", "estimatedCostUsd", "createdAt"} <= set(ticket)


def test_no_incluye_agentes_archivados(client: TestClient) -> None:
    a = client.post("/api/agents", json={"name": "Howard", "role": "Hw"}).json()
    client.delete(f"/api/agents/{a['id']}")
    assert client.get("/api/snapshot").json()["agents"] == []


def test_el_snapshot_no_expone_secretos(seeded_client: TestClient, migrated_db: Database) -> None:
    text = seeded_client.get("/api/snapshot").text.lower()
    for forbidden in ("password", "token_hash", "ciphertext", "vault", "auth_token"):
        assert forbidden not in text


def test_openapi_lo_documenta_con_su_modelo(client: TestClient) -> None:
    spec = client.get("/api/openapi.json").json()
    assert "get" in spec["paths"]["/api/snapshot"]
    assert "Snapshot" in spec["components"]["schemas"]
