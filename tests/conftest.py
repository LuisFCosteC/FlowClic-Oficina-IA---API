from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.config import Settings, get_settings
from app.db.database import Database, connect_database

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _hermetic_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cada test corre en una carpeta temporal: nunca lee ni modifica el .env real ni data/."""
    from app.db.database import clear_db

    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    clear_db()
    yield
    get_settings.cache_clear()
    clear_db()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """URL de una BD temporal (nunca local.db)."""
    return "file:" + (tmp_path / "test.db").as_posix()


@pytest.fixture(params=["libsql", "sqlite"])
def raw_db(request: pytest.FixtureRequest, db_url: str) -> Iterator[Database]:
    """BD vacía con ambos drivers (libsql y el respaldo sqlite3)."""
    db = connect_database(db_url, driver=request.param)
    yield db
    db.close()


@pytest.fixture
def migrated_db(raw_db: Database) -> Database:
    """BD temporal con todas las migraciones aplicadas (ambos drivers)."""
    from app.db.migrate import migrate

    migrate(raw_db)
    return raw_db


@pytest.fixture
def test_settings() -> Settings:
    """Settings de pruebas: sin leer .env ni claves reales."""
    from app.config import Settings

    return Settings(_env_file=None, node_env="test")  # type: ignore[call-arg]


@pytest.fixture
def client(migrated_db: Database, test_settings: Settings) -> Iterator[TestClient]:
    """Cliente HTTP contra la app, con una BD temporal migrada y VACÍA."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(test_settings, migrated_db)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        yield c


@pytest.fixture
def seeded_client(client: TestClient, migrated_db: Database) -> TestClient:
    """Como `client`, pero con los datos de DEMOSTRACIÓN (4 agentes, tickets...)."""
    from app.db.seed import seed

    seed(migrated_db)
    return client


@pytest.fixture
def master_key() -> str:
    from app.security.crypto import generate_master_key

    return generate_master_key()


@pytest.fixture
def kclient(migrated_db: Database, master_key: str) -> Iterator[TestClient]:
    """Cliente con APP_MASTER_KEY (bolsa de claves, KEY01)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(_env_file=None, node_env="test", app_master_key=master_key)  # type: ignore[call-arg]
    with TestClient(
        create_app(settings, migrated_db), base_url="http://localhost", client=("127.0.0.1", 50000)
    ) as c:
        yield c
