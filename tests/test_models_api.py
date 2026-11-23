from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database
from app.db.seed import seed
from app.security.crypto import generate_master_key


def _by_id(client: TestClient) -> dict[str, dict[str, object]]:
    r = client.get("/api/models")
    assert r.status_code == 200
    return {m["id"]: m for m in r.json()}


def test_catalogo_completo_en_camel_case_sin_conexiones(client: TestClient) -> None:
    models = _by_id(client)
    assert list(models) == [
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "gemini-pro",
        "gemini-flash",
    ]
    assert models["claude-opus-5-5"] == {
        "id": "claude-opus-5-5",
        "label": "Claude Opus 5.5",
        "provider": "anthropic",
        "hasConnection": False,
    }
    assert models["gemini-flash"]["provider"] == "google"
    assert all(m["hasConnection"] is False for m in models.values())


def test_has_connection_por_proveedor_y_revocada_no_cuenta(
    migrated_db: Database, test_settings: Settings
) -> None:
    from fastapi.testclient import TestClient as TC

    from app.main import create_app

    seed(migrated_db)
    settings = test_settings.model_copy(update={"app_master_key": generate_master_key()})
    app = create_app(settings, migrated_db)
    with TC(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        r = c.post(
            "/api/admin/agents/leonard/credentials",
            json={"provider": "google", "label": "g1", "secret": "AIza-test-0001"},
        )
        assert r.status_code == 201
        models = _by_id(c)
        assert models["gemini-pro"]["hasConnection"] is True
        assert models["gemini-flash"]["hasConnection"] is True
        assert models["claude-sonnet-5-5"]["hasConnection"] is False
        c.delete(f"/api/admin/agents/leonard/credentials/{r.json()['id']}")
        assert _by_id(c)["gemini-pro"]["hasConnection"] is False
