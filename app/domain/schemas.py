"""DTOs de la API (PLAN §6): la API responde y acepta camelCase.

- Salida: modelos `CamelModel` (alias camelCase al serializar, que es lo que hace FastAPI).
- Entrada: `StrictInput` rechaza campos desconocidos (equivale al `.strict()` de PLAN §12.1 #8) y
  todos los textos tienen longitud máxima.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

AgentStatus = Literal["IDLE", "WORKING", "REVIEW", "BLOCKED", "SLEEP_QUOTA"]
TicketStatus = Literal["PENDING", "IN_PROGRESS", "IN_QA", "IN_REVIEW", "DONE", "RETURNED"]
Gate = Literal[1, 2, 3, 4]  # 1 Alcance · 2 Arquitectura · 3 Merge · 4 Producción
Priority = Literal["HIGH", "MEDIUM", "LOW"]
ModelTier = Literal["opus_pro", "sonnet_pro", "haiku_flash"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
ApprovalCategory = Literal["Arquitectura", "Despliegue", "Seguridad", "Datos"]
MemoryKind = Literal["NOTE", "DECISION"]
HairStyle = Literal["short", "long", "curly", "bun", "parted"]
TicketEventType = Literal[
    "CREATED",
    "UPDATED",
    "STATUS_CHANGED",
    "ASSIGNED",
    "CONTINUED",
    "APPROVAL_REQUESTED",
    "APPROVAL_DECIDED",
    "APPROVAL_CANCELLED",
    "DELETED",
]

# Límites de longitud (entrada)
Name = Annotated[str, Field(min_length=1, max_length=80)]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
LongText = Annotated[str, Field(max_length=5000)]
Prompt = Annotated[str, Field(max_length=20000)]
Ref = Annotated[str, Field(min_length=1, max_length=64)]
ProjectName = Annotated[str, Field(max_length=120)]
Money = Annotated[float, Field(ge=0, le=1_000_000)]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StrictInput(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ── Agentes ──────────────────────────────────────────────────────────────────────────────────
class AgentAvatar(StrictInput):
    color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{3,8}$")]
    glasses: bool | None = None
    hair_style: HairStyle | None = None


RoleType = Literal["CTO", "DEV_BACKEND", "DEV_FRONTEND", "QA", "CUSTOM"]
WorkspaceLevel = Literal["none", "read", "tests", "qa_report", "write"]


class Permissions(CamelModel):
    """Permisos DUROS (los aplica la API). PLAN §19.3."""

    workspaces: dict[str, WorkspaceLevel] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)
    ticket_transitions: list[tuple[TicketStatus, TicketStatus]] = Field(default_factory=list)
    only_assigned_tickets: bool = True


class ModelConfig(CamelModel):
    primary: str
    fallback: str | None = None
    fallback_condition: str | None = None


class Limits(CamelModel):
    max_tokens_per_ticket: Annotated[int, Field(ge=1, le=10_000_000)]
    max_usd_per_day: Annotated[float, Field(ge=0, le=100_000)]
    max_retries: Annotated[int, Field(ge=0, le=20)]


class Agent(CamelModel):
    id: str
    name: str
    character: str
    role: str
    role_type: RoleType
    status: AgentStatus
    avatar: AgentAvatar
    functions: list[str]
    rules: list[str]
    restrictions: list[str]
    permissions: Permissions
    model: ModelConfig
    limits: Limits
    system_prompt: str
    is_cto: bool
    current_task: str | None
    project: str | None
    consecutive_failures: int
    created_at: str
    updated_at: str
    archived_at: str | None


ListItem = Annotated[str, Field(min_length=1, max_length=500)]
ProfileList = Annotated[list[ListItem], Field(max_length=40)]


class AgentCreate(StrictInput):
    """Perfil de un agente nuevo. El prompt y `is_cto` los genera el servidor (G02)."""

    name: Name
    role: ShortText
    role_type: RoleType = "CUSTOM"
    character: Name | None = None
    avatar: AgentAvatar | None = None
    functions: ProfileList = Field(default_factory=list)
    rules: ProfileList = Field(default_factory=list)
    restrictions: ProfileList = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)
    model: ModelConfig = Field(default_factory=lambda: ModelConfig(primary="claude-sonnet-5-5"))
    limits: Limits = Field(
        default_factory=lambda: Limits(
            max_tokens_per_ticket=150_000, max_usd_per_day=8, max_retries=3
        )
    )
    project: ProjectName | None = None


class AgentUpdate(StrictInput):
    """Parcial. No admite `status` (endpoint propio) ni `system_prompt` (lo genera el servidor)."""

    name: Name | None = None
    role: ShortText | None = None
    role_type: RoleType | None = None
    character: Name | None = None
    avatar: AgentAvatar | None = None
    functions: ProfileList | None = None
    rules: ProfileList | None = None
    restrictions: ProfileList | None = None
    permissions: Permissions | None = None
    model: ModelConfig | None = None
    limits: Limits | None = None
    project: ProjectName | None = None


class AgentStatusBody(StrictInput):
    status: AgentStatus
    current_task: Annotated[str, Field(max_length=500)] | None = None


# ── Tickets ──────────────────────────────────────────────────────────────────────────────────
class Ticket(CamelModel):
    id: str
    title: str
    description: str
    status: TicketStatus
    priority: Priority
    assigned_agent_id: str | None
    project: str | None
    model_tier: ModelTier
    estimated_cost_usd: float
    position: int
    created_at: str
    updated_at: str


class TicketCreate(StrictInput):
    title: Title
    description: LongText | None = None
    status: TicketStatus | None = None
    priority: Priority | None = None
    assigned_agent_id: Ref | None = None
    project: ProjectName | None = None
    model_tier: ModelTier | None = None
    estimated_cost_usd: Money | None = None


class TicketUpdate(StrictInput):
    title: Title | None = None
    description: LongText | None = None
    priority: Priority | None = None
    project: ProjectName | None = None
    model_tier: ModelTier | None = None
    estimated_cost_usd: Money | None = None
    position: Annotated[int, Field(ge=0, le=100_000)] | None = None


class TicketStatusBody(StrictInput):
    status: TicketStatus


class TicketAssignBody(StrictInput):
    agent_id: Ref | None


class TicketContinueBody(StrictInput):
    note: Annotated[str, Field(max_length=1000)] | None = None


class TicketEvent(CamelModel):
    id: str
    ticket_id: str
    type: TicketEventType
    from_value: str | None
    to_value: str | None
    actor: str
    payload: dict[str, object]
    created_at: str


# ── Aprobaciones ─────────────────────────────────────────────────────────────────────────────
class Approval(CamelModel):
    id: str
    ticket_id: str | None
    agent_id: str | None
    gate: Gate
    title: str
    category: ApprovalCategory
    summary: str
    reviewer_note: str
    estimated_tokens: int
    status: ApprovalStatus
    decision_note: str | None
    decided_by: str | None
    requested_at: str
    decided_at: str | None


class ApprovalCreate(StrictInput):
    gate: Gate
    title: Title
    ticket_id: Ref | None = None
    agent_id: Ref | None = None
    category: ApprovalCategory | None = None
    summary: LongText | None = None
    reviewer_note: LongText | None = None
    estimated_tokens: Annotated[int, Field(ge=0, le=100_000_000)] | None = None


class ApprovalUpdate(StrictInput):
    title: Title | None = None
    summary: LongText | None = None
    reviewer_note: LongText | None = None
    category: ApprovalCategory | None = None


class ApprovalDecision(StrictInput):
    decision: Literal["APPROVED", "REJECTED"]
    note: Annotated[str, Field(max_length=1000)] | None = None


# ── Memoria del proyecto ─────────────────────────────────────────────────────────────────────
class MemoryEntry(CamelModel):
    id: str
    kind: MemoryKind
    title: str
    content: str
    project: str | None
    ticket_id: str | None
    author: str
    created_at: str
    updated_at: str


class MemoryCreate(StrictInput):
    kind: MemoryKind
    title: Title
    content: Annotated[str, Field(max_length=20000)] | None = None
    project: ProjectName | None = None
    ticket_id: Ref | None = None


class MemoryUpdate(StrictInput):
    kind: MemoryKind | None = None
    title: Title | None = None
    content: Annotated[str, Field(max_length=20000)] | None = None
    project: ProjectName | None = None
    ticket_id: Ref | None = None
