import pytest

from app.db.database import Database, IntegrityError

NOW = "2026-11-22T10:00:00.000Z"


def agent(db: Database, id_: str = "a1", name: str = "A", status: str = "IDLE") -> None:
    db.execute(
        "INSERT INTO agents (id, name, character, role, status, created_at, updated_at)"
        " VALUES (?, ?, ?, 'r', ?, ?, ?)",
        (id_, name, name, status, NOW, NOW),
    )


def ticket(db: Database, id_: str = "t1", status: str = "BACKLOG") -> None:
    db.execute(
        "INSERT INTO tickets (id, title, status, created_at, updated_at) VALUES (?, 'T', ?, ?, ?)",
        (id_, status, NOW, NOW),
    )


def approval(db: Database, id_: str, ticket_id: str | None, status: str = "PENDING") -> None:
    db.execute(
        "INSERT INTO approvals (id, ticket_id, title, status, requested_at)"
        " VALUES (?, ?, 'T', ?, ?)",
        (id_, ticket_id, status, NOW),
    )


def test_status_invalido_falla_en_agents_tickets_y_approvals(migrated_db: Database) -> None:
    with pytest.raises(IntegrityError):
        agent(migrated_db, status="FOO")
    with pytest.raises(IntegrityError):
        ticket(migrated_db, status="FOO")
    ticket(migrated_db)
    with pytest.raises(IntegrityError):
        approval(migrated_db, "x", "t1", status="FOO")


def test_los_cinco_estados_de_agente_son_validos(migrated_db: Database) -> None:
    for i, st in enumerate(["IDLE", "WORKING", "REVIEW", "BLOCKED", "SLEEP_QUOTA"]):
        agent(migrated_db, f"a{i}", f"A{i}", st)


def test_dos_aprobaciones_pending_del_mismo_ticket_fallan(migrated_db: Database) -> None:
    ticket(migrated_db)
    approval(migrated_db, "p1", "t1")
    with pytest.raises(IntegrityError):
        approval(migrated_db, "p2", "t1")
    # una ya decidida no impide una nueva PENDING; y las sin ticket no chocan entre sí
    migrated_db.execute("UPDATE approvals SET status='APPROVED' WHERE id='p1'")
    approval(migrated_db, "p3", "t1")
    approval(migrated_db, "g1", None)
    approval(migrated_db, "g2", None)


def test_nombre_de_agente_unico_solo_entre_activos(migrated_db: Database) -> None:
    agent(migrated_db, "a1", "Howard")
    with pytest.raises(IntegrityError):
        agent(migrated_db, "a2", "Howard")
    migrated_db.execute("UPDATE agents SET archived_at = ? WHERE id = 'a1'", (NOW,))
    agent(migrated_db, "a2", "Howard")


def test_checks_de_prioridad_tier_y_categoria(migrated_db: Database) -> None:
    with pytest.raises(IntegrityError):
        migrated_db.execute(
            "INSERT INTO tickets (id, title, priority, created_at, updated_at)"
            " VALUES ('t', 'T', 'URGENT', ?, ?)",
            (NOW, NOW),
        )
    with pytest.raises(IntegrityError):
        migrated_db.execute(
            "INSERT INTO agents (id, name, character, role, model_tier, created_at, updated_at)"
            " VALUES ('a', 'A', 'A', 'r', 'gpt', ?, ?)",
            (NOW, NOW),
        )
    with pytest.raises(IntegrityError):
        migrated_db.execute(
            "INSERT INTO approvals (id, title, category, requested_at)"
            " VALUES ('x', 'T', 'Otra', ?)",
            (NOW,),
        )
