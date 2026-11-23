from pathlib import Path

import pytest

from app.db.database import Database
from app.db.migrate import MIGRATIONS_DIR, MigrationError, migrate, schema_version
from app.db.sqlsplit import split_statements


def tables(db: Database) -> set[str]:
    rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


def test_split_respeta_comentarios_cadenas_y_triggers() -> None:
    sql = """
    -- comentario con ; dentro
    CREATE TABLE a (x TEXT DEFAULT 'a;b');
    /* bloque; */
    CREATE TRIGGER tg AFTER INSERT ON a BEGIN UPDATE a SET x = 'z'; END;
    -- comentario final
    """
    parts = split_statements(sql)
    assert len(parts) == 2
    assert parts[0].startswith("-- comentario") or parts[0].startswith("CREATE TABLE a")
    assert "END;" in parts[1]


def test_primera_ejecucion_aplica_todo_y_la_segunda_nada(raw_db: Database) -> None:
    first = migrate(raw_db)
    n_files = len(list(MIGRATIONS_DIR.glob("*.sql")))
    assert len(first.applied) == n_files
    assert first.applied[0] == "001_init.sql"
    second = migrate(raw_db)
    assert second.applied == []
    assert second.skipped == n_files
    assert {"agents", "tickets", "approvals", "schema_migrations"} <= tables(raw_db)
    assert schema_version(raw_db) == n_files


def test_migracion_rota_no_se_registra_ni_deja_tablas_parciales(
    raw_db: Database, tmp_path: Path
) -> None:
    d = tmp_path / "migs"
    d.mkdir()
    (d / "001_ok.sql").write_text("CREATE TABLE a (id INTEGER);", encoding="utf-8")
    (d / "002_rota.sql").write_text(
        "CREATE TABLE c (id INTEGER);\nCREATE TABLE d (id INTEGER) BROKEN;", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="002_rota.sql"):
        migrate(raw_db, d)
    assert "a" in tables(raw_db)
    assert "c" not in tables(raw_db)
    assert [r["version"] for r in raw_db.fetch_all("SELECT version FROM schema_migrations")] == [1]


def test_las_migraciones_se_aplican_en_orden_numerico(raw_db: Database, tmp_path: Path) -> None:
    d = tmp_path / "migs"
    d.mkdir()
    (d / "010_b.sql").write_text("CREATE TABLE b (id INTEGER);", encoding="utf-8")
    (d / "002_a.sql").write_text("CREATE TABLE a (id INTEGER);", encoding="utf-8")
    assert migrate(raw_db, d).applied == ["002_a.sql", "010_b.sql"]
