"""Punto 10: BD atrasada → 503 MIGRATION_REQUIRED (nunca 500) y aviso en consola."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database
from app.db.migrate import is_behind, migrate
from app.main import create_app
from app.middleware import MigrationGuardMiddleware


def _client(db: Database, test_settings: Settings) -> TestClient:
    return TestClient(
        create_app(test_settings, db), base_url="http://localhost", client=("127.0.0.1", 50000)
    )


def test_is_behind(raw_db: Database) -> None:
    assert is_behind(raw_db) is True  # sin tabla de migraciones
    migrate(raw_db)
    assert is_behind(raw_db) is False
    raw_db.execute(
        "DELETE FROM schema_migrations WHERE version = (SELECT MAX(version) FROM schema_migrations)"
    )
    assert is_behind(raw_db) is True


def test_bd_atrasada_responde_503_y_al_migrar_se_recupera(
    raw_db: Database, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(MigrationGuardMiddleware, "CACHE_SECONDS", 0.0)
    migrate(raw_db)
    raw_db.execute(
        "DELETE FROM schema_migrations WHERE version = (SELECT MAX(version) FROM schema_migrations)"
    )
    with _client(raw_db, test_settings) as c:
        for path in ("/api/snapshot", "/api/models", "/api/agents", "/api/admin/workspaces"):
            r = c.get(path)
            assert r.status_code == 503, path
            assert r.json()["error"]["code"] == "MIGRATION_REQUIRED"
            assert "python -m app.db.migrate" in r.json()["error"]["message"]
        assert c.get("/api/health").status_code == 200  # la salud sigue abierta
        migrate(raw_db)  # python -m app.db.migrate
        assert c.get("/api/snapshot").status_code == 200  # se recupera sin reiniciar
