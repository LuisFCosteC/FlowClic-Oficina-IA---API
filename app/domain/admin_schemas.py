"""DTOs de Administración (PLAN §13): proyecto, límites y reglas."""

from typing import Annotated, Any, Literal

from pydantic import Field

from app.domain.schemas import CamelModel, StrictInput

RuleSeverity = Literal["MUST", "SHOULD"]
Limit = Annotated[int, Field(ge=1, le=100)]
Goal = Annotated[str, Field(min_length=1, max_length=200)]
StackItem = Annotated[str, Field(min_length=1, max_length=60)]


class ProjectSettings(StrictInput):
    """Ajustes de la EMPRESA (PRJ01). Los proyectos viven en `/api/admin/projects`.

    Compatibilidad: `projectName`, `description`, `goals` y `stack` se siguen aceptando en el
    PUT y se devuelven vacíos en el GET, pero ya NO se guardan (obsoletos).
    """

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


# ── Auditoría y usuarios (A07) ───────────────────────────────────────────────────────────────
UserRole = Literal["ADMIN", "OPERATOR", "VIEWER"]


class AuditEntry(CamelModel):
    id: str
    user_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    meta: dict[str, Any]
    created_at: str


class AdminUser(CamelModel):
    """Vista pública de un usuario: NUNCA incluye hash de contraseña ni secreto MFA."""

    id: str
    email: str
    display_name: str
    role: UserRole
    mfa_enabled: bool
    last_login_at: str | None
    disabled_at: str | None
    created_at: str
    updated_at: str


class UserCreate(StrictInput):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    role: UserRole
    password: Annotated[str, Field(min_length=1, max_length=256)]


class UserUpdate(StrictInput):
    display_name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    role: UserRole | None = None
    disabled: bool | None = None


# ── Conexión de BD y backup (A05) ────────────────────────────────────────────────────────────
class DbStatus(CamelModel):
    """Estado de la conexión. NUNCA incluye la URL completa ni el token (solo `hasToken`)."""

    mode: Literal["local", "remote"]
    host: str
    connected: bool
    schema_version: int | None
    has_token: bool
    last_backup_at: str | None


class DbTestBody(StrictInput):
    url: Annotated[str, Field(min_length=1, max_length=500)]
    auth_token: Annotated[str, Field(max_length=4000)] | None = None


class DbTestResult(CamelModel):
    ok: bool
    mode: Literal["local", "remote"]
    host: str
    schema_version: int | None
    will_create: bool


class BackupResult(CamelModel):
    folder: str
    tables: dict[str, int]
    created_at: str
