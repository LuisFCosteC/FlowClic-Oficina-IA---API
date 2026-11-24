"""GM04: las 6 restricciones globales aplicadas en código (creación, ejecución y transiciones)."""

from typing import Any

import pytest
from conftest import make_ticket
from fastapi.testclient import TestClient

from app.domain.agent_policy import (
    FORBIDDEN_ACTIONS,
    GLOBAL_RESTRICTIONS,
    enforce_action,
    enforce_can_message_ceo,
    enforce_path_allowed,
    generate_system_prompt,
)
from app.domain.schemas import Permissions
from app.errors import AppError


def perms(**kw: Any) -> Permissions:
    return Permissions.model_validate(kw)


def code(fn: Any, *args: Any) -> str | None:
    try:
        fn(*args)
    except AppError as exc:
        return exc.code
    return None


def test_son_seis_y_el_prompt_las_lleva_todas_al_final() -> None:
    assert len(GLOBAL_RESTRICTIONS) == 6
    prompt = generate_system_prompt(
        name="A", role="r", role_type="CUSTOM", functions=[], rules=[], restrictions=[]
    )
    for i, g in enumerate(GLOBAL_RESTRICTIONS, start=1):
        assert f"{i}. {g}" in prompt
    assert prompt.endswith(GLOBAL_RESTRICTIONS[5])


# 1 · merge a main y despliegue
@pytest.mark.parametrize("action", ["git.merge_main", "deploy.production"])
def test_r1_merge_y_despliegue(client: TestClient, action: str) -> None:
    assert code(enforce_action, "CTO", perms(actions=[]), action) == "GLOBAL_RESTRICTION"
    r = client.post(
        "/api/agents", json={"name": "X", "role": "R", "permissions": {"actions": [action]}}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "GLOBAL_RESTRICTION"


# 2 · llaves de producción y .env
@pytest.mark.parametrize("action", ["secrets.read", "env.read"])
def test_r2_acciones_de_secretos(action: str) -> None:
    assert code(enforce_action, "CTO", perms(), action) == "GLOBAL_RESTRICTION"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "api/.env",
        "api\\.env.production",
        "./app/.ENV",
        "prod.env",
        "data/vault.db",
        "certs/server.pem",
        "keys/id_rsa",
        "home/.ssh/config",
        "x/.aws/credentials",
        "credentials.json",
        "secrets/token.key",
    ],
)
def test_r2_rutas_sensibles_se_rechazan(path: str) -> None:
    assert code(enforce_path_allowed, path) == "GLOBAL_RESTRICTION"


@pytest.mark.parametrize(
    "path", [".env.example", "src/app.py", "docs/README.md", "environment.md", "keyboard.txt"]
)
def test_r2_rutas_normales_se_permiten(path: str) -> None:
    assert code(enforce_path_allowed, path) is None


# 3 · clientes y correos
@pytest.mark.parametrize("action", ["email.send", "client.contact"])
def test_r3_clientes_y_correos(action: str) -> None:
    assert code(enforce_action, "CTO", perms(actions=[action]), action) == "GLOBAL_RESTRICTION"


# 4 · solo el CTO habla con el CEO y crea aprobaciones
def test_r4_solo_el_cto() -> None:
    assert code(enforce_can_message_ceo, "CTO") is None
    for role in ("DEV_BACKEND", "DEV_FRONTEND", "QA", "CUSTOM"):
        assert code(enforce_can_message_ceo, role) == "GLOBAL_RESTRICTION"
        assert (
            code(enforce_action, role, perms(actions=["approvals.create"]), "approvals.create")
            == "GLOBAL_RESTRICTION"
        )
    assert (
        code(enforce_action, "CTO", perms(actions=["approvals.create"]), "approvals.create") is None
    )


def test_r4_no_se_crea_un_agente_no_cto_con_approvals(client: TestClient) -> None:
    r = client.post(
        "/api/agents",
        json={"name": "X", "role": "R", "permissions": {"actions": ["approvals.create"]}},
    )
    assert r.status_code == 422


# 5 · BLOCKED a los 3 fallos seguidos (AgentGuard, ver tests/test_agent_guard.py)
def test_r5_tres_fallos_bloquean(client: TestClient) -> None:
    a = client.post("/api/agents", json={"name": "X", "role": "R"}).json()
    for _ in range(3):
        client.post(f"/api/agents/{a['id']}/failures", json={"outcome": "failure"})
    assert client.get(f"/api/agents/{a['id']}").json()["status"] == "BLOCKED"


# 6 · nadie autoaprueba ni se salta las restricciones
@pytest.mark.parametrize("action", ["approvals.decide", "security.bypass"])
def test_r6_acciones_prohibidas(client: TestClient, action: str) -> None:
    assert action in FORBIDDEN_ACTIONS
    assert code(enforce_action, "CTO", perms(actions=[action]), action) == "GLOBAL_RESTRICTION"
    r = client.post(
        "/api/agents", json={"name": "X", "role": "R", "permissions": {"actions": [action]}}
    )
    assert r.status_code == 422


def test_r6_un_agente_no_aprueba_su_propio_trabajo(client: TestClient) -> None:
    reviewer = client.post(
        "/api/agents",
        json={
            "name": "Leonard",
            "role": "R",
            "permissions": {
                "ticketTransitions": [
                    ["PENDING", "IN_PROGRESS"],
                    ["IN_PROGRESS", "IN_QA"],
                    ["IN_QA", "IN_SENIOR_REVIEW"],
                    ["IN_SENIOR_REVIEW", "IN_REVIEW"],
                ],
                "onlyAssignedTickets": False,
            },
        },
    ).json()
    mine = str(make_ticket(assigned_agent_id=reviewer["id"])["id"])
    theirs = str(make_ticket(assigned_agent_id=None)["id"])

    def move(tid: str, to: str) -> Any:
        return client.post(
            f"/api/tickets/{tid}/transition", json={"to": to, "actingAgentId": reviewer["id"]}
        )

    for tid in (mine, theirs):
        assert move(tid, "IN_PROGRESS").status_code == 200
        assert move(tid, "IN_QA").status_code == 200
    # su propio ticket: no puede pasarlo de EN QA a la revisión senior
    r = move(mine, "IN_SENIOR_REVIEW")
    assert r.status_code == 403 and "autoaprueba" in r.json()["error"]["message"]
    assert client.get(f"/api/tickets/{mine}").json()["status"] == "IN_QA"
    # el de otro sí
    assert move(theirs, "IN_SENIOR_REVIEW").status_code == 200
    # el humano (CEO) sí puede mover cualquiera
    assert (
        client.post(f"/api/tickets/{mine}/transition", json={"to": "IN_SENIOR_REVIEW"}).status_code
        == 200
    )


def test_las_restricciones_de_un_ticket_no_pueden_quitar_las_globales(client: TestClient) -> None:
    from app.services.tickets_service import _task_restrictions

    assert _task_restrictions([GLOBAL_RESTRICTIONS[5], "Mía"]) == ["Mía"]
