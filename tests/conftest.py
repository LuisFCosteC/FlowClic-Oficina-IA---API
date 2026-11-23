from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.database import Database, connect_database


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
