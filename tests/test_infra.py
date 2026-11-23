"""Infraestructura de tests: BD temporal, app en memoria y aislamiento del entorno real."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.database import Database

ROOT = Path(__file__).resolve().parent.parent


def snapshot(path: Path) -> tuple[int, int] | None:
    return (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None


def test_health_con_bd_temporal_sin_tocar_local_db_ni_el_env_real(
    client: TestClient, tmp_path: Path
) -> None:
    before = {p: snapshot(ROOT / p) for p in ("local.db", ".env", "data/vault.db")}
    assert client.get("/api/health").json()["ok"] is True
    after = {p: snapshot(ROOT / p) for p in before}
    assert before == after  # nada del repo real se creó ni se modificó
    assert not (Path.cwd() / "local.db").exists()  # cwd = carpeta temporal del test
    assert Path.cwd() == tmp_path


def test_la_bd_de_pruebas_empieza_vacia(client: TestClient, migrated_db: Database) -> None:
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM agents") == {"n": 0}


def test_seeded_client_trae_los_datos_de_demostracion(
    seeded_client: TestClient, migrated_db: Database
) -> None:
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM agents") == {"n": 4}


def test_cada_test_tiene_su_propia_bd(client: TestClient, migrated_db: Database) -> None:
    migrated_db.execute(
        "INSERT INTO project_memory (id, kind, title, created_at, updated_at)"
        " VALUES ('x', 'NOTE', 't', 'a', 'a')"
    )
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM project_memory") == {"n": 1}


def test_la_bd_del_test_anterior_no_se_filtra(client: TestClient, migrated_db: Database) -> None:
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM project_memory") == {"n": 0}
