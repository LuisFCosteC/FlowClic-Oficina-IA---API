import json

from app.db.database import Database
from app.db.seed import seed


def count(db: Database, table: str) -> int:
    row = db.fetch_one(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608
    assert row is not None
    return int(row["n"])


def test_ejecutar_dos_veces_deja_exactamente_4_agentes_y_sheldon_es_cto(
    migrated_db: Database,
) -> None:
    seed(migrated_db)
    seed(migrated_db)
    assert count(migrated_db, "agents") == 4
    rows = migrated_db.fetch_all("SELECT id, is_cto, status, avatar FROM agents ORDER BY id")
    assert {r["id"] for r in rows} == {"sheldon", "leonard", "penny", "raj"}
    assert {r["id"]: r["is_cto"] for r in rows} == {
        "sheldon": 1,
        "leonard": 0,
        "penny": 0,
        "raj": 0,
    }
    assert all(r["status"] == "IDLE" for r in rows)
    leonard = next(r for r in rows if r["id"] == "leonard")
    assert json.loads(leonard["avatar"]) == {
        "color": "#38BDF8",
        "glasses": True,
        "hairStyle": "short",
    }


def test_tickets_aprobacion_y_memoria_de_ejemplo(migrated_db: Database) -> None:
    seed(migrated_db)
    seed(migrated_db)
    statuses = [r["status"] for r in migrated_db.fetch_all("SELECT status FROM tickets")]
    assert sorted(statuses) == ["AWAITING_APPROVAL", "BACKLOG", "IN_PROGRESS", "REVIEW"]
    assert count(migrated_db, "ticket_events") == 4
    pending = migrated_db.fetch_all("SELECT ticket_id FROM approvals WHERE status = 'PENDING'")
    assert pending == [{"ticket_id": "seed-ticket-4"}]
    assert count(migrated_db, "project_memory") == 1


def test_la_semilla_no_crea_usuarios_ni_credenciales(migrated_db: Database) -> None:
    seed(migrated_db)
    assert count(migrated_db, "users") == 0
    assert count(migrated_db, "sessions") == 0
