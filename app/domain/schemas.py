"""DTOs de la API (PLAN §6): la API responde y acepta camelCase.

- Salida: modelos `CamelModel` (alias camelCase al serializar, que es lo que hace FastAPI).
- Entrada: `StrictInput` rechaza campos desconocidos (equivale al `.strict()` de PLAN §12.1 #8) y
  todos los textos tienen longitud máxima.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_serializer
from pydantic.alias_generators import to_camel

AgentStatus = Literal["IDLE", "WORKING", "REVIEW", "BLOCKED", "SLEEP_QUOTA"]
TicketStatus = Literal[
    "PENDING", "IN_PROGRESS", "IN_QA", "IN_SENIOR_REVIEW", "IN_REVIEW", "DONE", "RETURNED"
]
Gate = Literal[1, 2, 3, 4]  # 1 Alcance · 2 Arquitectura · 3 Merge · 4 Producción
Priority = Literal["HIGH", "MEDIUM", "LOW"]
ModelTier = Literal["opus_pro", "sonnet_pro", "haiku_flash"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
ApprovalCategory = Literal["Arquitectura", "Despliegue", "Seguridad", "Datos"]
MemoryKind = Literal["NOTE", "DECISION"]
HairStyle = Literal["short", "long", "curly", "bun", "parted", "ponytail", "spiky", "bob", "bald"]
Gender = Literal["male", "female", "neutral"]
FaceStyle = Literal["neutral", "smile", "serious", "worried"]
TopStyle = Literal["tshirt", "jacket", "hoodie", "suit", "dress"]
PantsStyle = Literal["pants", "shorts", "skirt"]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{3,8}$")]
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
# Campos de apariencia completa (opcionales): si no se definen, no aparecen en la salida.
_LOOK_KEYS = (
    "gender",
    "skin_tone",
    "hair_color",
    "face",
    "top_style",
    "top_color",
    "inner_color",
    "pants_style",
    "pants_color",
    "shoe_color",
)


class AgentAvatar(StrictInput):
    color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{3,8}$")]
    glasses: bool | None = None
    hair_style: HairStyle | None = None
    gender: Gender | None = None
    skin_tone: HexColor | None = None
    hair_color: HexColor | None = None
    face: FaceStyle | None = None
    top_style: TopStyle | None = None
    top_color: HexColor | None = None
    inner_color: HexColor | None = None
    pants_style: PantsStyle | None = None
    pants_color: HexColor | None = None
    shoe_color: HexColor | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_look(self, handler: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in _LOOK_KEYS:
            camel = to_camel(key)
            for k in (key, camel):
                if k in data and data[k] is None:
                    del data[k]
        return data


ProjectId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
RoleType = Literal["CTO", "DEV_BACKEND", "DEV_FRONTEND", "QA", "CUSTOM"]
WorkspaceLevel = Literal["none", "read", "tests", "qa_report", "write"]


class FolderAccess(StrictInput):
    """Nivel de acceso por TIPO de carpeta (PERM01); lo que no se indica es `none`."""

    api: WorkspaceLevel = "none"
    front: WorkspaceLevel = "none"
    docs: WorkspaceLevel = "none"
    mobile: WorkspaceLevel = "none"
    other: WorkspaceLevel = "none"


class Permissions(StrictInput):
    """Permisos DUROS (los aplica la API). PLAN §19.3 + PERM01.

    Acceso efectivo a un workspace W = `folder_access[W.kind]`, solo si `W.project_id` está en
    `project_scope` ("ALL" incluye los proyectos futuros). Un workspace sin proyecto solo lo ven
    los agentes con alcance "ALL".
    """

    folder_access: FolderAccess = Field(default_factory=FolderAccess)
    project_scope: Literal["ALL"] | Annotated[list[ProjectId], Field(max_length=200)] = Field(
        default_factory=list
    )
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
    reports_to: str | None = None  # id del agente al que reporta; null = el CEO
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
    reports_to: Ref | None = None


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
    reports_to: Ref | None = None


class AgentStatusBody(StrictInput):
    status: AgentStatus
    current_task: Annotated[str, Field(max_length=500)] | None = None


# ── Tickets ──────────────────────────────────────────────────────────────────────────────────
TicketKind = Literal["REQUEST", "TASK"]
UNDEFINED_LABEL = "Por definir"


class Ticket(CamelModel):
    id: str
    title: str
    description: str
    status: TicketStatus
    priority: Priority | None = None  # null = "Por definir" (lo decide el CTO)
    assigned_agent_id: str | None
    project_id: str | None = None
    project: str | None = None  # nombre del proyecto (solo lectura, derivado de project_id)
    model_tier: ModelTier
    estimated_cost_usd: float
    position: int
    created_at: str
    updated_at: str
    objective: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    model: str | None = None  # null = "Por definir"
    kind: TicketKind = "TASK"
    parent_ticket_id: str | None = None
    requirement: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def priority_label(self) -> str:
        return UNDEFINED_LABEL if self.priority is None else self.priority

    @computed_field  # type: ignore[prop-decorator]
    @property
    def model_label(self) -> str:
        return UNDEFINED_LABEL if self.model is None else self.model


class RequestCreate(StrictInput):
    """Pedido del CEO (REQ01): lo recibe el CTO; prioridad y modelo los decide él."""

    title: Title
    requirement: Annotated[str, Field(min_length=1, max_length=5000)]
    project_id: ProjectId


class TaskCreate(StrictInput):
    """Subtarea (kind TASK) de un pedido: la crean el CTO o Leonard (REQ01)."""

    parent_ticket_id: Ref
    title: Title
    objective: Annotated[str, Field(min_length=1, max_length=5000)]
    acceptance_criteria: Annotated[list[ListItem], Field(min_length=1, max_length=40)]
    actions: ProfileList = Field(default_factory=list)
    restrictions: ProfileList = Field(default_factory=list)
    dependencies: ProfileList = Field(default_factory=list)
    assigned_agent_id: Ref
    model: Ref
    priority: Priority
    acting_agent_id: Ref | None = None


class TicketUpdate(StrictInput):
    title: Title | None = None
    description: LongText | None = None
    priority: Priority | None = None
    project_id: Ref | None = None
    model_tier: ModelTier | None = None
    estimated_cost_usd: Money | None = None
    position: Annotated[int, Field(ge=0, le=100_000)] | None = None


class TicketStatusBody(StrictInput):
    status: TicketStatus


class TicketTransitionBody(StrictInput):
    """`POST /api/tickets/{id}/transition`; `actingAgentId` simula a un agente (GM02)."""

    to: TicketStatus
    note: Annotated[str, Field(max_length=1000)] | None = None
    acting_agent_id: Ref | None = None


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


# ── Credenciales API de agentes (PLAN §16) ───────────────────────────────────────────────────
CredentialProvider = Literal["anthropic", "openai", "google", "other"]
SecretText = Annotated[str, Field(min_length=8, max_length=4096)]


class AgentCredential(CamelModel):
    """Metadatos de una conexión. La clave NUNCA sale de la API: solo `last4`."""

    id: str
    agent_id: str
    provider: CredentialProvider
    label: str
    last4: str
    key_version: int
    created_by: str
    created_at: str
    rotated_at: str | None
    revoked_at: str | None


class CredentialCreate(StrictInput):
    provider: CredentialProvider
    label: Annotated[str, Field(min_length=1, max_length=80)]
    secret: SecretText


class CredentialRotate(StrictInput):
    secret: SecretText


# ── Mensajes (chat de mando) y resumen de estado ─────────────────────────────────────────────
MessageScope = Literal["GLOBAL", "AGENT"]
MessageKind = Literal["ORDER", "QUESTION", "NOTE", "STATUS", "REPLY"]
HumanMessageKind = Literal["ORDER", "QUESTION", "NOTE"]  # STATUS y REPLY: solo sistema/agentes
MessageStatus = Literal["PENDING", "ACK", "DONE", "REJECTED"]
AuthorType = Literal["HUMAN", "AGENT", "SYSTEM"]


class Message(CamelModel):
    id: str
    scope: MessageScope
    agent_id: str | None
    author_type: AuthorType
    author_id: str
    kind: MessageKind
    body: str
    status: MessageStatus
    ticket_id: str | None
    created_at: str


class MessageCreate(StrictInput):
    scope: MessageScope
    agent_id: Ref | None = None
    kind: HumanMessageKind = "ORDER"
    body: Annotated[str, Field(min_length=1, max_length=2000)]
    ticket_id: Ref | None = None


class ThreadEntry(CamelModel):
    """Una línea del hilo: un mensaje o un evento de ticket, ordenados por fecha."""

    id: str
    entry_type: Literal["MESSAGE", "TICKET_EVENT"]
    kind: str
    scope: MessageScope | None
    agent_id: str | None
    author_type: AuthorType | None
    author_id: str | None
    body: str
    status: MessageStatus | None
    ticket_id: str | None
    created_at: str


class TicketBrief(CamelModel):
    id: str
    title: str
    status: TicketStatus
    priority: Priority | None
    description: str
    since_seconds: int


class PendingApprovalBrief(CamelModel):
    id: str
    title: str
    gate: Gate


class StatusSummary(CamelModel):
    """Tarjeta "qué está haciendo / qué le falta" de un agente."""

    agent_id: str
    name: str
    status: AgentStatus
    current_task: str | None
    ticket: TicketBrief | None
    open_tickets: dict[str, int]
    blocked_reason: str | None
    pending_approvals: list[PendingApprovalBrief]
    next_step: str
    summary: str


# ── Espacios de trabajo (J03) ────────────────────────────────────────────────────────────────
WorkspaceKind = Literal["api", "front", "docs", "mobile", "other"]
WORKSPACE_KINDS: tuple[WorkspaceKind, ...] = ("api", "front", "docs", "mobile", "other")
ProjectStatus = Literal["ACTIVE", "ARCHIVED"]


class Workspace(CamelModel):
    id: str
    name: str
    path: str
    project_id: str | None = None
    kind: WorkspaceKind = "other"
    created_at: str
    updated_at: str


class WorkspaceBody(StrictInput):
    """`projectId` y `kind` opcionales: al editar, lo que no se envía se conserva."""

    name: Name
    path: Annotated[str, Field(min_length=1, max_length=500)]
    project_id: ProjectId | None = None
    kind: WorkspaceKind | None = None


class AgentWorkspaceView(CamelModel):
    """Vista de un workspace para un agente: sin ruta local."""

    id: str
    name: str
    kind: WorkspaceKind
    project_id: str | None
    access: WorkspaceLevel


# ── Proyectos (PRJ01) ────────────────────────────────────────────────────────────────────────
_Goal = Annotated[str, Field(min_length=1, max_length=200)]
_StackItem = Annotated[str, Field(min_length=1, max_length=60)]


class Project(CamelModel):
    id: str
    name: str
    description: str
    goals: list[str]
    stack: list[str]
    status: ProjectStatus
    created_at: str
    updated_at: str


class ProjectCreate(StrictInput):
    id: ProjectId
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=2000)] = ""
    goals: Annotated[list[_Goal], Field(max_length=20)] = Field(default_factory=list)
    stack: Annotated[list[_StackItem], Field(max_length=30)] = Field(default_factory=list)


class ProjectUpdate(StrictInput):
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    goals: Annotated[list[_Goal], Field(max_length=20)] | None = None
    stack: Annotated[list[_StackItem], Field(max_length=30)] | None = None


class WorkspaceCheck(CamelModel):
    """Resultado de comprobar la carpeta. Nunca lista su contenido."""

    exists: bool
    is_dir: bool
    writable: bool
