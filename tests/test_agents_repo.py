import pytest

from app.db.database import Database, IntegrityError
from app.domain.schemas import Agent, AgentAvatar, Limits, ModelConfig, Permissions
from app.repositories import agents_repo as repo

NOW = "2026-11-22T10:00:00.000Z"
LATER = "2026-11-22T11:00:00.000Z"


def make(id_: str = "howard", name: str = "Howard", **over: object) -> Agent:
    base: dict[str, object] = {
        "id": id_,
        "name": name,
        "character": "Howard Wolowitz",
        "role": "Hardware",
        "role_type": "CUSTOM",
        "status": "IDLE",
        "avatar": AgentAvatar(color="#10B981", glasses=False, hair_style="bun"),
        "functions": ["Soldar", "Diseñar PCB"],
        "rules": ["Un ticket por sesión"],
        "restrictions": ["No tocar producción"],
        "permissions": Permissions(
            workspaces={"api": "write", "docs": "read"},
            actions=["repo.read", "git.commit_dev"],
            ticket_transitions=[("PENDING", "IN_PROGRESS"), ("IN_PROGRESS", "IN_QA")],
            only_assigned_tickets=True,
        ),
        "model": ModelConfig(
            primary="claude-sonnet-5-5", fallback="claude-opus-5-5", fallback_condition="gate 2"
        ),
        "limits": Limits(max_tokens_per_ticket=150000, max_usd_per_day=8, max_retries=3),
        "system_prompt": "prompt generado",
        "is_cto": False,
        "current_task": None,
        "project": "X",
        "consecutive_failures": 0,
        "created_at": NOW,
        "updated_at": NOW,
        "archived_at": None,
    }
    base.update(over)
    return Agent.model_validate(base)


def test_insert_y_get_ida_y_vuelta_con_todos_los_campos_de_perfil(migrated_db: Database) -> None:
    a = make()
    repo.insert_agent(migrated_db, a)
    got = repo.get_agent(migrated_db, "howard")
    assert got == a
    assert got is not None
    assert got.permissions.ticket_transitions == [
        ("PENDING", "IN_PROGRESS"),
        ("IN_PROGRESS", "IN_QA"),
    ]
    assert got.model.fallback == "claude-opus-5-5"
    assert got.limits.max_usd_per_day == 8
    assert got.functions == ["Soldar", "Diseñar PCB"]  # acentos intactos


def test_get_inexistente_devuelve_none(migrated_db: Database) -> None:
    assert repo.get_agent(migrated_db, "nadie") is None


def test_list_excluye_archivados_salvo_flag_y_ordena_por_creacion(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make("b", "B", created_at="2026-11-22T10:00:02.000Z"))
    repo.insert_agent(migrated_db, make("a", "A", created_at="2026-11-22T10:00:01.000Z"))
    repo.insert_agent(migrated_db, make("c", "C", created_at="2026-11-22T10:00:03.000Z"))
    assert [x.id for x in repo.list_agents(migrated_db)] == ["a", "b", "c"]
    repo.archive_agent(migrated_db, "b", LATER)
    assert [x.id for x in repo.list_agents(migrated_db)] == ["a", "c"]
    assert [x.id for x in repo.list_agents(migrated_db, include_archived=True)] == ["a", "b", "c"]
    assert repo.count_active(migrated_db) == 2


def test_archivar_libera_el_nombre_y_restaurar_lo_recupera(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make("a1", "Howard"))
    assert repo.find_active_by_name(migrated_db, "Howard") is not None
    repo.archive_agent(migrated_db, "a1", LATER)
    assert repo.find_active_by_name(migrated_db, "Howard") is None
    archived = repo.get_agent(migrated_db, "a1")
    assert archived is not None and archived.archived_at == LATER
    repo.insert_agent(migrated_db, make("a2", "Howard"))  # el nombre quedó libre
    with pytest.raises(IntegrityError):  # restaurar el viejo choca con el activo
        repo.restore_agent(migrated_db, "a1", LATER)


def test_update_parcial_de_campos_simples_y_json(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make())
    repo.update_agent(
        migrated_db,
        "howard",
        {
            "role": "Ingeniero",
            "functions": ["Nueva función"],
            "limits": {"maxTokensPerTicket": 1, "maxUsdPerDay": 2.5, "maxRetries": 0},
            "is_cto": True,
            "system_prompt": "otro",
        },
        LATER,
    )
    got = repo.get_agent(migrated_db, "howard")
    assert got is not None
    assert got.role == "Ingeniero"
    assert got.functions == ["Nueva función"]
    assert got.limits.max_usd_per_day == 2.5
    assert got.is_cto is True
    assert got.system_prompt == "otro"
    assert got.rules == ["Un ticket por sesión"]  # lo no enviado no cambia
    assert got.updated_at == LATER


def test_update_rechaza_campos_no_actualizables(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make())
    for bad in ("status", "id", "archived_at", "consecutive_failures", "name; DROP TABLE agents"):
        with pytest.raises(ValueError, match="no actualizables"):
            repo.update_agent(migrated_db, "howard", {bad: "x"}, LATER)


def test_set_status_y_current_task(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make())
    for st in ("WORKING", "REVIEW", "BLOCKED", "SLEEP_QUOTA", "IDLE"):
        repo.set_status(migrated_db, "howard", st, "Tarea" if st == "WORKING" else None, LATER)  # type: ignore[arg-type]
        got = repo.get_agent(migrated_db, "howard")
        assert got is not None and got.status == st
    with pytest.raises(IntegrityError):
        repo.set_status(migrated_db, "howard", "FOO", None, LATER)  # type: ignore[arg-type]


def test_contador_de_fallos(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make())
    repo.set_failures(migrated_db, "howard", 2, LATER)
    got = repo.get_agent(migrated_db, "howard")
    assert got is not None and got.consecutive_failures == 2
    with pytest.raises(IntegrityError):
        repo.set_failures(migrated_db, "howard", -1, LATER)


def test_nombre_unico_entre_activos(migrated_db: Database) -> None:
    repo.insert_agent(migrated_db, make("a1", "Howard"))
    with pytest.raises(IntegrityError):
        repo.insert_agent(migrated_db, make("a2", "Howard"))


def test_inyeccion_sql_en_valores_se_guarda_como_texto(migrated_db: Database) -> None:
    evil = "x'); DROP TABLE agents; --"
    repo.insert_agent(migrated_db, make("a1", evil))
    got = repo.find_active_by_name(migrated_db, evil)
    assert got is not None and got.name == evil
    assert repo.count_active(migrated_db) == 1
