import json

import pytest

from app.db.database import Database, IntegrityError

NOW = "2026-11-22T10:00:00.000Z"


def agent(db: Database, id_: str = "a1", name: str = "A", status: str = "IDLE") -> None:
    db.execute(
        "INSERT INTO agents (id, name, character, role, status, created_at, updated_at)"
        " VALUES (?, ?, ?, 'r', ?, ?, ?)",
        (id_, name, name, status, NOW, NOW),
    )


def ticket(db: Database, id_: str = "t1", status: str = "PENDING") -> None:
    db.execute(
        "INSERT INTO tickets (id, title, status, created_at, updated_at) VALUES (?, 'T', ?, ?, ?)",
        (id_, status, NOW, NOW),
    )


def approval(
    db: Database, id_: str, ticket_id: str | None, status: str = "PENDING", gate: int = 1
) -> None:
    db.execute(
        "INSERT INTO approvals (id, ticket_id, gate, title, status, requested_at)"
        " VALUES (?, ?, ?, 'T', ?, ?)",
        (id_, ticket_id, gate, status, NOW),
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


def test_dos_aprobaciones_pending_de_la_misma_compuerta_y_ticket_fallan(
    migrated_db: Database,
) -> None:
    ticket(migrated_db)
    approval(migrated_db, "p1", "t1", gate=2)
    with pytest.raises(IntegrityError):
        approval(migrated_db, "p2", "t1", gate=2)
    # otra compuerta del mismo ticket sí; una ya decidida no bloquea una nueva PENDING;
    # y las compuertas sin ticket no chocan entre sí
    approval(migrated_db, "p4", "t1", gate=3)
    migrated_db.execute("UPDATE approvals SET status='APPROVED' WHERE id='p1'")
    approval(migrated_db, "p3", "t1", gate=2)
    approval(migrated_db, "g1", None)
    approval(migrated_db, "g2", None)


def test_estado_antiguo_de_ticket_y_compuerta_fuera_de_rango_fallan(migrated_db: Database) -> None:
    for old in ("BACKLOG", "REVIEW", "AWAITING_APPROVAL"):
        with pytest.raises(IntegrityError):
            ticket(migrated_db, status=old)
    ticket(migrated_db)
    for bad_gate in (0, 5, -1):
        with pytest.raises(IntegrityError):
            approval(migrated_db, f"b{bad_gate}", "t1", gate=bad_gate)
    with pytest.raises(IntegrityError):  # gate es obligatoria
        migrated_db.execute(
            "INSERT INTO approvals (id, title, requested_at) VALUES ('x', 'T', ?)", (NOW,)
        )


def test_los_seis_estados_de_ticket_y_las_cuatro_compuertas_son_validos(
    migrated_db: Database,
) -> None:
    for i, st in enumerate(["PENDING", "IN_PROGRESS", "IN_QA", "IN_REVIEW", "DONE", "RETURNED"]):
        ticket(migrated_db, f"t{i}", st)
    assert migrated_db.fetch_one("SELECT status FROM tickets WHERE id = 't0'") == {
        "status": "PENDING"
    }
    for gate in (1, 2, 3, 4):
        approval(migrated_db, f"a{gate}", None, gate=gate)


def test_el_ticket_nuevo_empieza_en_pending(migrated_db: Database) -> None:
    migrated_db.execute(
        "INSERT INTO tickets (id, title, created_at, updated_at) VALUES ('t', 'T', ?, ?)",
        (NOW, NOW),
    )
    assert migrated_db.fetch_one("SELECT status FROM tickets") == {"status": "PENDING"}


def test_005_columnas_de_perfil_con_valores_por_defecto(migrated_db: Database) -> None:
    agent(migrated_db)
    row = migrated_db.fetch_one("SELECT * FROM agents WHERE id = 'a1'")
    assert row is not None
    assert row["role_type"] == "CUSTOM"
    assert row["functions"] == "[]" and row["rules"] == "[]" and row["restrictions"] == "[]"
    assert row["consecutive_failures"] == 0
    for col in ("permissions", "model", "limits"):
        assert json.loads(row[col])  # JSON válido y no vacío
    assert json.loads(row["permissions"])["onlyAssignedTickets"] is True
    assert json.loads(row["model"])["primary"] == "claude-sonnet-5-5"
    assert json.loads(row["limits"])["maxRetries"] == 3


def test_005_role_type_y_contador_de_fallos_validan(migrated_db: Database) -> None:
    for rt in ("CTO", "DEV_BACKEND", "DEV_FRONTEND", "QA", "CUSTOM"):
        migrated_db.execute(
            "INSERT INTO agents (id, name, character, role, role_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'r', ?, ?, ?)",
            (rt, rt, rt, rt, NOW, NOW),
        )
    with pytest.raises(IntegrityError):
        migrated_db.execute(
            "INSERT INTO agents (id, name, character, role, role_type, created_at, updated_at)"
            " VALUES ('x', 'X', 'X', 'r', 'HACKER', ?, ?)",
            (NOW, NOW),
        )
    with pytest.raises(IntegrityError):
        migrated_db.execute("UPDATE agents SET consecutive_failures = -1 WHERE id = 'QA'")


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
            "INSERT INTO approvals (id, gate, title, category, requested_at)"
            " VALUES ('x', 1, 'T', 'Otra', ?)",
            (NOW,),
        )
