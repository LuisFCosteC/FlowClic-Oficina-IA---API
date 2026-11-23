import re
from pathlib import Path

import pytest

from app.db.database import Database
from app.domain.agent_policy import GLOBAL_RESTRICTIONS, check_profile, generate_system_prompt
from app.domain.agent_templates import BASE_TEAM, TEMPLATES, AgentTemplate
from app.events.bus import DomainEvent, EventBus
from app.repositories import agents_repo as repo
from app.services.agents_service import load_base_team

DOC = Path(__file__).resolve().parent.parent / "docs" / "AGENT_PROFILES.md"


def sections() -> dict[str, dict[str, list[str]]]:
    """Parsea AGENT_PROFILES.md: {nombre: {Funciones|Reglas|Restricciones: [bullets]}}."""
    text = DOC.read_text(encoding="utf-8")
    out: dict[str, dict[str, list[str]]] = {}
    for block in re.split(r"\n## ", text)[1:]:
        name = block.split(":", 1)[0].strip()
        if name not in {"Sheldon", "Leonard", "Penny", "Raj"}:
            continue
        data: dict[str, list[str]] = {}
        current: str | None = None
        for line in block.splitlines():
            m = re.match(r"^- \*\*(Funciones|Reglas|Restricciones):\*\*\s*$", line)
            if m:
                current = m.group(1)
                data[current] = []
            elif re.match(r"^- \*\*", line):
                current = None
            elif current and (b := re.match(r"^  - (.+)$", line)):
                data[current].append(b.group(1))
        out[name] = data
    return out


def by_name(name: str) -> AgentTemplate:
    return next(t for t in BASE_TEAM if t.name == name)


@pytest.mark.parametrize("name", ["Sheldon", "Leonard", "Penny", "Raj"])
def test_las_plantillas_reproducen_literalmente_el_texto_del_ceo(name: str) -> None:
    doc = sections()[name]
    t = by_name(name)
    assert t.functions == doc["Funciones"]
    assert t.rules == doc["Reglas"]
    assert t.restrictions == doc["Restricciones"]


def test_roles_modelos_y_limites_del_ceo() -> None:
    t = {x.name: x for x in BASE_TEAM}
    assert [x.role_type for x in BASE_TEAM] == ["CTO", "DEV_BACKEND", "DEV_FRONTEND", "QA"]
    assert (t["Sheldon"].model.primary, t["Sheldon"].model.fallback) == (
        "claude-sonnet-5-5",
        "claude-opus-5-5",
    )
    assert (t["Leonard"].model.primary, t["Leonard"].model.fallback) == (
        "gemini-pro",
        "claude-sonnet-5-5",
    )
    assert (t["Penny"].model.primary, t["Penny"].model.fallback) == ("gemini-pro", "gemini-flash")
    assert (t["Raj"].model.primary, t["Raj"].model.fallback) == ("gemini-flash", "claude-haiku-5-5")
    limits = {n: (x.limits.max_tokens_per_ticket, x.limits.max_usd_per_day) for n, x in t.items()}
    assert limits == {
        "Sheldon": (200_000, 10),
        "Leonard": (150_000, 8),
        "Penny": (150_000, 8),
        "Raj": (80_000, 3),
    }
    assert all(x.limits.max_retries == 3 for x in BASE_TEAM)


def test_permisos_del_ceo() -> None:
    t = {x.name: x.permissions for x in BASE_TEAM}
    assert t["Sheldon"].workspaces == {"api": "read", "front": "read", "docs": "write"}
    assert "approvals.create" in t["Sheldon"].actions
    assert t["Sheldon"].ticket_transitions == [("IN_REVIEW", "DONE"), ("IN_REVIEW", "RETURNED")]
    assert t["Leonard"].workspaces == {"api": "write", "front": "none", "docs": "read"}
    assert t["Penny"].workspaces == {"api": "none", "front": "write", "docs": "read"}
    assert "cmd.dev" in t["Penny"].actions and "cmd.dev" not in t["Leonard"].actions
    assert t["Raj"].workspaces == {"api": "tests", "front": "tests", "docs": "qa_report"}
    assert t["Raj"].ticket_transitions == [("IN_QA", "IN_REVIEW"), ("IN_QA", "RETURNED")]
    assert [x.only_assigned_tickets for x in t.values()] == [False, True, True, False]
    for name in ("Leonard", "Penny", "Raj"):
        assert "approvals.create" not in t[name].actions


def test_todas_las_plantillas_pasan_la_politica_y_generan_prompt_con_las_globales() -> None:
    for t in TEMPLATES:
        check_profile(t.role_type, t.permissions, t.model, t.limits)
        prompt = generate_system_prompt(
            name=t.name or "X",
            role=t.role or "r",
            role_type=t.role_type,
            functions=t.functions,
            rules=t.rules,
            restrictions=t.restrictions,
        )
        assert prompt.endswith(GLOBAL_RESTRICTIONS[4])


def test_cargar_el_equipo_base_dos_veces_deja_4_agentes(migrated_db: Database) -> None:
    bus = EventBus()
    events: list[DomainEvent] = []
    bus.subscribe(events.append)
    created, skipped = load_base_team(migrated_db, bus)
    assert [a.id for a in created] == ["sheldon", "leonard", "penny", "raj"]
    assert skipped == []
    created2, skipped2 = load_base_team(migrated_db, bus)
    assert created2 == []
    assert skipped2 == ["Sheldon", "Leonard", "Penny", "Raj"]
    assert len(repo.list_agents(migrated_db)) == 4
    assert [e.type for e in events] == ["agent.created"] * 4


def test_los_agentes_cargados_tienen_prompt_del_servidor_y_estado_idle(
    migrated_db: Database,
) -> None:
    load_base_team(migrated_db)
    sheldon = repo.get_agent(migrated_db, "sheldon")
    assert sheldon is not None
    assert sheldon.is_cto is True and sheldon.status == "IDLE"
    assert sheldon.role_type == "CTO"
    assert sheldon.system_prompt.endswith(GLOBAL_RESTRICTIONS[4])
    assert "Convertir los pedidos del CEO" in sheldon.system_prompt
    assert repo.get_agent(migrated_db, "raj").is_cto is False  # type: ignore[union-attr]


def test_si_ya_existe_un_agente_con_ese_nombre_se_omite(migrated_db: Database) -> None:
    from app.domain.schemas import AgentCreate
    from app.services.agents_service import create_agent

    create_agent(migrated_db, None, AgentCreate(name="Penny", role="Otra Penny"))
    created, skipped = load_base_team(migrated_db)
    assert "Penny" in skipped
    assert sorted(a.name for a in created) == ["Leonard", "Raj", "Sheldon"]
    # el agente existente no se modifica
    existing = repo.find_active_by_name(migrated_db, "Penny")
    assert existing is not None and existing.role == "Otra Penny"
