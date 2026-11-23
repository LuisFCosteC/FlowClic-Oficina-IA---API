import json
from pathlib import Path

import pytest

from app.config import Settings
from app.db.bootstrap import build_vault
from app.db.database import Database, connect_database
from app.db.migrate import migrate
from app.db.seed import seed
from app.db.wipe import WIPE_ORDER, main, wipe_data
from app.security import audit
from app.security.crypto import generate_master_key


def count(db: Database, table: str) -> int:
    row = db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608
    assert row is not None
    return int(row["n"])


def _add_credential(db: Database) -> None:
    db.execute(
        "INSERT INTO agent_credentials (id, agent_id, provider, label, ciphertext, nonce,"
        " key_version, last4, created_by, created_at)"
        " VALUES ('c1', 'sheldon', 'google', 'x', ?, ?, 1, 'abcd', 'human', 'now')",
        (b"\x00\x01cipher", b"nonce"),
    )


def test_wipe_vacia_las_tablas_de_datos_y_conserva_esquema_y_auditoria(
    migrated_db: Database, tmp_path: Path
) -> None:
    seed(migrated_db)
    _add_credential(migrated_db)
    audit.record(migrated_db, "previa")
    versions = count(migrated_db, "schema_migrations")

    counts = wipe_data(migrated_db, tmp_path / "bk")

    assert counts["agents"] == 4 and counts["agent_credentials"] == 1
    for table in WIPE_ORDER:
        assert count(migrated_db, table) == 0
    assert count(migrated_db, "schema_migrations") == versions
    actions = [r["action"] for r in migrated_db.fetch_all("SELECT action FROM audit_log")]
    assert actions == ["previa", "db.wiped"]
    meta = migrated_db.fetch_one("SELECT meta FROM audit_log WHERE action = 'db.wiped'")
    assert meta is not None
    assert json.loads(meta["meta"])["rows"]["agents"] == 4


def test_backup_json_por_tabla_con_los_blobs_en_base64(
    migrated_db: Database, tmp_path: Path
) -> None:
    seed(migrated_db)
    _add_credential(migrated_db)
    wipe_data(migrated_db, tmp_path / "bk")
    agents = json.loads((tmp_path / "bk" / "agents.json").read_text(encoding="utf-8"))
    assert {a["id"] for a in agents} == {"sheldon", "leonard", "penny", "raj"}
    cred = json.loads((tmp_path / "bk" / "agent_credentials.json").read_text(encoding="utf-8"))
    assert cred[0]["ciphertext"] == {"$base64": "AAFjaXBoZXI="}


def test_el_backup_se_hace_antes_de_borrar(migrated_db: Database, tmp_path: Path) -> None:
    seed(migrated_db)
    (tmp_path / "bk").write_text("estorba", encoding="utf-8")  # no se puede crear la carpeta
    try:
        wipe_data(migrated_db, tmp_path / "bk")
    except OSError:
        pass
    assert count(migrated_db, "agents") == 4  # sin backup no se borra nada


def test_sin_permisos_restringidos_aborta_antes_de_borrar(
    migrated_db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(migrated_db)
    monkeypatch.setattr("app.security.fileperms.restrict_to_owner", lambda _p: False)
    with pytest.raises(OSError, match="permisos"):
        wipe_data(migrated_db, tmp_path / "bk")
    assert count(migrated_db, "agents") == 4
    assert not list((tmp_path / "bk").glob("*.json")) or all(
        f.read_text(encoding="utf-8") == "" for f in (tmp_path / "bk").glob("*.json")
    )


def test_bd_ya_vacia_no_falla(migrated_db: Database, tmp_path: Path) -> None:
    counts = wipe_data(migrated_db, tmp_path / "bk")
    assert sum(counts.values()) == 0


def test_cli_cancela_si_no_se_escribe_borrar_y_borra_si_si(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = generate_master_key()
    monkeypatch.setenv("APP_MASTER_KEY", key)
    url = "file:" + (tmp_path / "w.db").as_posix()
    vault = build_vault(Settings(_env_file=None, app_master_key=key))  # type: ignore[call-arg]
    vault.set_secret("db.url", url)
    vault.close()
    db = connect_database(url)
    migrate(db)
    seed(db)
    db.close()

    backups = str(tmp_path / "b")
    monkeypatch.setattr("builtins.input", lambda _prompt="": "no")
    assert main(["--backup-dir", backups]) == 1
    db = connect_database(url)
    assert count(db, "agents") == 4
    db.close()

    monkeypatch.setattr("builtins.input", lambda _prompt="": "BORRAR")
    assert main(["--backup-dir", backups]) == 0
    db = connect_database(url)
    assert count(db, "agents") == 0
    db.close()
    assert any((tmp_path / "b").iterdir())
