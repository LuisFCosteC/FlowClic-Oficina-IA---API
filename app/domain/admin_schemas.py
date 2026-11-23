"""DTOs de Administración (PLAN §13): proyecto, límites y reglas."""

from typing import Annotated, Literal

from pydantic import Field

from app.domain.schemas import CamelModel, StrictInput

RuleSeverity = Literal["MUST", "SHOULD"]
Limit = Annotated[int, Field(ge=1, le=100)]
Goal = Annotated[str, Field(min_length=1, max_length=200)]
StackItem = Annotated[str, Field(min_length=1, max_length=60)]


class ProjectSettings(StrictInput):
    company_name: Annotated[str, Field(max_length=120)] = ""
    project_name: Annotated[str, Field(max_length=120)] = ""
    description: Annotated[str, Field(max_length=2000)] = ""
    goals: Annotated[list[Goal], Field(max_length=20)] = []
    stack: Annotated[list[StackItem], Field(max_length=30)] = []


class LimitsSettings(StrictInput):
    max_agents: Limit
    max_active_tickets_per_agent: Limit
    require_approval_for_done: bool


class Rule(CamelModel):
    id: str
    title: str
    description: str
    severity: RuleSeverity
    enabled: bool
    position: int
    created_at: str
    updated_at: str


class RuleCreate(StrictInput):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=2000)] = ""
    severity: RuleSeverity = "MUST"
    enabled: bool = True


class RuleUpdate(StrictInput):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    severity: RuleSeverity | None = None
    enabled: bool | None = None


class RuleOrder(StrictInput):
    ids: Annotated[list[Annotated[str, Field(min_length=1, max_length=64)]], Field(max_length=500)]
