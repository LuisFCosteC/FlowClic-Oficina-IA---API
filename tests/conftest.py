from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.db.database import Database, connect_database


@pytest.fixture(autouse=True)
def _hermetic_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cada test corre en una carpeta temporal: nunca lee ni modifica el .env real ni data/."""
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
