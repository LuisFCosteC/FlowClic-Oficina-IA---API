from fastapi.testclient import TestClient

from app.db.database import Database
from app.db.seed import main as seed_main
from app.domain.agent_templates import TEMPLATES


def test_get_agent_templates_devuelve_las_5_en_camel_case(client: TestClient) -> None:
    r = client.get("/api/agent-templates")
    assert r.status_code == 200
    body = r.json()
    assert [t["roleType"] for t in body] == ["CTO", "DEV_BACKEND", "DEV_FRONTEND", "QA", "CUSTOM"]
    sheldon = body[0]
    assert sheldon["name"] == "Sheldon"
    assert sheldon["functions"][0].startswith("Convertir los pedidos del CEO")
    assert sheldon["model"] == {
        "primary": "claude-sonnet-5-5",
        "fallback": "claude-opus-5-5",
        "fallbackCondition": "Solo en compuertas 2 y 4.",
    }
    assert sheldon["limits"] == {
        "maxTokensPerTicket": 200000,
        "maxUsdPerDay": 10.0,
        "maxRetries": 3,
    }
    assert sheldon["permissions"]["ticketTransitions"] == [
        ["IN_REVIEW", "DONE"],
        ["IN_REVIEW", "RETURNED"],
    ]
    assert body[-1]["functions"] == [] and len(body) == len(TEMPLATES)


def test_cargar_equipo_base_dos_veces_deja_4_agentes(
    client: TestClient, migrated_db: Database
) -> None:
    first = client.post("/api/admin/agents/load-base-team")
    assert first.status_code == 200
    assert [a["id"] for a in first.json()["created"]] == ["sheldon", "leonard", "penny", "raj"]
    assert first.json()["skipped"] == []
    second = client.post("/api/admin/agents/load-base-team")
    assert second.json() == {"created": [], "skipped": ["Sheldon", "Leonard", "Penny", "Raj"]}
    n = migrated_db.fetch_one("SELECT COUNT(*) AS n FROM agents")
    assert n == {"n": 4}
    created = first.json()["created"][0]
    assert created["isCto"] is True and created["status"] == "IDLE"
    assert created["systemPrompt"].endswith("al llegar a su tope de costo.")


def test_el_endpoint_aparece_en_openapi(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/agent-templates" in paths
    assert "/api/admin/agents/load-base-team" in paths


def test_seed_agents_carga_solo_el_equipo_base_y_demo_agrega_tickets(
    migrated_db: Database,
) -> None:
    from app.db.seed import seed

    seed(migrated_db)
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM agents") == {"n": 4}
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM tickets") == {"n": 4}
    assert callable(seed_main)
