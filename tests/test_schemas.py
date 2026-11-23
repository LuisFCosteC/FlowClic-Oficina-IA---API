import enum
import inspect
import pkgutil

import pytest
from pydantic import ValidationError

import app
from app.domain import schemas
from app.domain.schemas import (
    Agent,
    AgentAvatar,
    AgentCreate,
    AgentStatusBody,
    AgentUpdate,
    Limits,
    ModelConfig,
    Permissions,
    TicketAssignBody,
    TicketCreate,
    TicketUpdate,
)


def make_agent() -> Agent:
    return Agent(
        id="a1",
        name="Howard",
        character="Howard",
        role="Hardware",
        role_type="CUSTOM",
        status="IDLE",
        avatar=AgentAvatar(color="#10B981", hair_style="bun"),
        functions=[],
        rules=[],
        restrictions=[],
        permissions=Permissions(),
        model=ModelConfig(primary="claude-sonnet-5-5"),
        limits=Limits(max_tokens_per_ticket=1000, max_usd_per_day=1, max_retries=3),
        system_prompt="",
        is_cto=False,
        current_task=None,
        project=None,
        consecutive_failures=0,
        created_at="2026-11-22T10:00:00.000Z",
        updated_at="2026-11-22T10:00:00.000Z",
        archived_at=None,
    )


def test_la_salida_es_camel_case() -> None:
    data = make_agent().model_dump(by_alias=True)
    assert {
        "systemPrompt",
        "roleType",
        "isCto",
        "currentTask",
        "consecutiveFailures",
        "archivedAt",
    } <= set(data)
    assert data["avatar"] == {"color": "#10B981", "glasses": None, "hairStyle": "bun"}
    assert "system_prompt" not in data


def test_la_entrada_acepta_camel_case() -> None:
    m = AgentCreate.model_validate(
        {"name": "A", "role": "r", "roleType": "QA", "model": {"primary": "gemini-pro"}}
    )
    assert m.role_type == "QA"
    assert m.model.primary == "gemini-pro"
    assert m.limits.max_retries == 3


def test_la_entrada_rechaza_campos_desconocidos() -> None:
    with pytest.raises(ValidationError):
        AgentCreate.model_validate({"name": "A", "role": "r", "isAdmin": True})
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({"title": "T", "id": "x"})


def test_agent_update_no_admite_status() -> None:
    with pytest.raises(ValidationError):
        AgentUpdate.model_validate({"status": "IDLE"})
    with pytest.raises(ValidationError):
        AgentUpdate.model_validate({"systemPrompt": "hackeado"})
    with pytest.raises(ValidationError):
        AgentCreate.model_validate({"name": "A", "role": "r", "isCto": True})
    assert AgentUpdate.model_validate({"role": "QA"}).model_dump(exclude_unset=True) == {
        "role": "QA"
    }


@pytest.mark.parametrize("bad", ["FOO", "idle", ""])
def test_estados_invalidos_se_rechazan(bad: str) -> None:
    with pytest.raises(ValidationError):
        AgentStatusBody.model_validate({"status": bad})
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({"title": "T", "status": bad})


def test_los_cinco_estados_de_agente_son_validos() -> None:
    for st in ["IDLE", "WORKING", "REVIEW", "BLOCKED", "SLEEP_QUOTA"]:
        assert AgentStatusBody.model_validate({"status": st}).status == st


def test_limites_de_longitud_y_rangos() -> None:
    with pytest.raises(ValidationError):
        AgentCreate.model_validate({"name": "x" * 81, "role": "r"})
    with pytest.raises(ValidationError):
        AgentCreate.model_validate({"name": "", "role": "r"})
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({"title": "T", "estimatedCostUsd": -1})
    with pytest.raises(ValidationError):
        TicketUpdate.model_validate({"position": -1})
    with pytest.raises(ValidationError):
        AgentAvatar.model_validate({"color": "rojo"})


def test_assign_acepta_null_para_desasignar() -> None:
    assert TicketAssignBody.model_validate({"agentId": None}).agent_id is None
    with pytest.raises(ValidationError):
        TicketAssignBody.model_validate({})


def test_no_se_usa_enum_de_python_en_la_app() -> None:
    # Los enumerados son Literal (PLAN §0.4): ninguna clase hereda de enum.Enum.
    for info in pkgutil.walk_packages(app.__path__, prefix="app."):
        module = __import__(info.name, fromlist=["_"])
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__:
                assert not issubclass(obj, enum.Enum), f"{info.name}.{obj.__name__}"
    assert schemas.AgentStatus is not None


def test_avatar_apariencia_completa_opcional():
    """Los campos de apariencia completa son opcionales y no aparecen si no se definen."""
    from app.domain.schemas import AgentAvatar

    basico = AgentAvatar(color="#10B981", hair_style="bun").model_dump(by_alias=True)
    assert basico == {"color": "#10B981", "glasses": None, "hairStyle": "bun"}

    completo = AgentAvatar(
        color="#10B981",
        gender="female",
        hair_style="ponytail",
        hair_color="#2C1B12",
        skin_tone="#F4C29F",
        face="smile",
        top_style="jacket",
        top_color="#2D5A27",
        inner_color="#7A7D80",
        pants_style="skirt",
        pants_color="#4A453E",
        shoe_color="#222222",
    ).model_dump(by_alias=True)
    assert completo["topStyle"] == "jacket" and completo["pantsStyle"] == "skirt"
    assert completo["skinTone"] == "#F4C29F" and completo["shoeColor"] == "#222222"
