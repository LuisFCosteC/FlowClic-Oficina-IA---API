import pytest

from app.db.database import (
    Database,
    DatabaseError,
    IntegrityError,
    LibsqlDatabase,
    connect_database,
    get_db,
    set_db,
    swap_db,
)


def test_funciona_con_file_y_devuelve_filas_como_dict(raw_db: Database) -> None:
    raw_db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL UNIQUE)")
    raw_db.execute("INSERT INTO t (v) VALUES (?)", ("hola",))
    assert raw_db.fetch_all("SELECT id, v FROM t") == [{"id": 1, "v": "hola"}]
    assert raw_db.fetch_one("SELECT v FROM t WHERE v = ?", ("hola",)) == {"v": "hola"}
    assert raw_db.fetch_one("SELECT v FROM t WHERE v = ?", ("nada",)) is None


def test_transaccion_commit_y_rollback(raw_db: Database) -> None:
    raw_db.execute("CREATE TABLE t (v TEXT NOT NULL)")
    with raw_db.transaction() as tx:
        tx.execute("INSERT INTO t VALUES (?)", ("a",))
    with pytest.raises(RuntimeError), raw_db.transaction() as tx:
        tx.execute("INSERT INTO t VALUES (?)", ("b",))
        raise RuntimeError("falla a mitad")
    assert [r["v"] for r in raw_db.fetch_all("SELECT v FROM t")] == ["a"]


def test_rollback_deshace_tambien_ddl(raw_db: Database) -> None:
    with pytest.raises(DatabaseError), raw_db.transaction() as tx:
        tx.execute("CREATE TABLE x (a)")
        tx.execute("CREATE TABLE y (b) BROKEN")
    names = [
        r["name"] for r in raw_db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    assert "x" not in names


def test_violaciones_se_traducen_a_integrity_error(raw_db: Database) -> None:
    raw_db.execute("CREATE TABLE t (v TEXT NOT NULL UNIQUE, k TEXT CHECK (k IN ('a','b')))")
    raw_db.execute("INSERT INTO t (v, k) VALUES ('x', 'a')")
    with pytest.raises(IntegrityError):
        raw_db.execute("INSERT INTO t (v, k) VALUES ('x', 'a')")  # UNIQUE
    with pytest.raises(IntegrityError):
        raw_db.execute("INSERT INTO t (v, k) VALUES ('y', 'zzz')")  # CHECK
    with pytest.raises(IntegrityError):
        raw_db.execute("INSERT INTO t (v) VALUES (NULL)")  # NOT NULL
    with pytest.raises(DatabaseError):
        raw_db.fetch_all("SELECT * FROM no_existe")
    # tras un error la conexión sigue usable y puede abrir transacciones
    with raw_db.transaction() as tx:
        tx.execute("INSERT INTO t (v, k) VALUES ('z', 'b')")
    assert len(raw_db.fetch_all("SELECT * FROM t")) == 2


def test_no_se_permiten_transacciones_anidadas(raw_db: Database) -> None:
    with raw_db.transaction(), pytest.raises(RuntimeError):
        with raw_db.transaction():
            pass


def test_token_vacio_no_se_envia(db_url: str) -> None:
    db = connect_database(db_url, auth_token="")
    assert isinstance(db, LibsqlDatabase)
    db.execute("SELECT 1")
    db.close()


def test_sqlite_solo_admite_file() -> None:
    with pytest.raises(ValueError, match="file:"):
        connect_database("libsql://x.turso.io", driver="sqlite")


def test_set_get_y_swap_db(db_url: str, tmp_path: object) -> None:
    a = connect_database(db_url)
    b = connect_database(db_url + "-b")
    set_db(a)
    assert get_db() is a
    swap_db(b, close_old_after=0.01)
    assert get_db() is b
    b.close()
