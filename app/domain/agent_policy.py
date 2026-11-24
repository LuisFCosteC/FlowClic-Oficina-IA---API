"""Política de agentes (PLAN §19): restricciones globales, acciones y validación de permisos.

Distinción clave: reglas y funciones son BLANDAS (van al prompt); restricciones y permisos son
DURAS: los aplica la API con código, aunque el modelo "quiera" otra cosa.
"""

from collections.abc import Sequence

from app.domain.models_catalog import validate_model_ids
from app.domain.schemas import (
    Limits,
    ModelConfig,
    Permissions,
    RoleType,
    TicketStatus,
    WorkspaceLevel,
)
from app.errors import AppError, validation_error

# ── Restricciones globales: en código, NO editables desde la app (PLAN §19.2) ─────────────────
GLOBAL_RESTRICTIONS: tuple[str, ...] = (
    "Ningún agente hace merge a `main` ni despliega a producción. Eso lo hace solo el CEO.",
    "Ningún agente ve llaves de producción ni archivos `.env`.",
    "Ningún agente contacta clientes ni envía correos.",
    "Solo Sheldon puede hablar con el CEO y crear aprobaciones.",
    "Todo agente se detiene (BLOCKED) tras 3 fallos seguidos o al llegar a su tope de costo.",
    "Ningún agente puede autoaprobar compuertas ni saltarse las restricciones de seguridad.",
)

# ── Acciones: lista cerrada ───────────────────────────────────────────────────────────────────
VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "repo.read",
        "tickets.create",
        "tickets.assign",
        "tickets.close",
        "approvals.create",
        "memory.write",
        "cmd.install_approved",
        "cmd.dev",
        "cmd.build",
        "cmd.test",
        "cmd.lint",
        "cmd.audit",
        "git.commit_dev",
        "git.push_dev",
    }
)

# Prohibidas para cualquier agente (restricciones globales 1, 2, 3 y 6): 422 GLOBAL_RESTRICTION.
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "git.merge_main",
        "deploy.production",
        "secrets.read",
        "env.read",
        "email.send",
        "client.contact",
        "approvals.decide",  # restricción 6: solo el humano decide compuertas
        "security.bypass",  # restricción 6: nadie se salta las restricciones
    }
)

# Acciones que solo admite un role_type concreto (restricción global 4).
ACTIONS_ONLY_FOR: dict[str, RoleType] = {"approvals.create": "CTO"}

# Grafo válido de tickets (PLAN §19.4).
VALID_TRANSITIONS: frozenset[tuple[TicketStatus, TicketStatus]] = frozenset(
    {
        ("PENDING", "IN_PROGRESS"),
        ("IN_PROGRESS", "IN_QA"),
        ("IN_QA", "IN_SENIOR_REVIEW"),
        ("IN_QA", "RETURNED"),
        ("IN_SENIOR_REVIEW", "IN_REVIEW"),
        ("IN_SENIOR_REVIEW", "RETURNED"),
        ("IN_REVIEW", "DONE"),
        ("IN_REVIEW", "RETURNED"),
        ("RETURNED", "IN_PROGRESS"),
    }
)


def check_permissions(role_type: RoleType, permissions: Permissions) -> None:
    """Valida los permisos de un agente. Lanza AppError si no son aceptables.

    - acción prohibida → 422 GLOBAL_RESTRICTION
    - `approvals.create` fuera de un CTO → 422 GLOBAL_RESTRICTION
    - acción desconocida / transición fuera del grafo → 400
    """
    for action in permissions.actions:
        if action in FORBIDDEN_ACTIONS:
            raise AppError(
                "GLOBAL_RESTRICTION",
                f"La acción «{action}» está prohibida por las restricciones globales",
                [{"path": "permissions.actions", "message": f"prohibida: {action}"}],
            )
    unknown = [a for a in permissions.actions if a not in VALID_ACTIONS]
    if unknown:
        raise validation_error(
            f"permissions.actions: acción desconocida «{unknown[0]}»",
            [{"path": "permissions.actions", "message": f"desconocida: {a}"} for a in unknown],
        )
    for action in permissions.actions:
        only = ACTIONS_ONLY_FOR.get(action)
        if only is not None and role_type != only:
            raise AppError(
                "GLOBAL_RESTRICTION",
                f"«{action}» solo puede tenerla un agente con role_type={only}",
                [{"path": "permissions.actions", "message": f"solo {only}: {action}"}],
            )
    bad_tr = [t for t in permissions.ticket_transitions if t not in VALID_TRANSITIONS]
    if bad_tr:
        raise validation_error(
            f"permissions.ticketTransitions: transición fuera del grafo {bad_tr[0]}",
            [
                {"path": "permissions.ticketTransitions", "message": f"inválida: {t}"}
                for t in bad_tr
            ],
        )


def check_profile(
    role_type: RoleType, permissions: Permissions, model: ModelConfig, limits: Limits
) -> None:
    """Validación completa del perfil duro de un agente (crear y editar)."""
    check_permissions(role_type, permissions)
    validate_model_ids(model.primary, model.fallback)
    if limits.max_tokens_per_ticket < 1:
        raise validation_error("limits.maxTokensPerTicket debe ser >= 1")


def _bullets(items: Sequence[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- (ninguna)"


def generate_system_prompt(
    *,
    name: str,
    role: str,
    role_type: RoleType,
    functions: Sequence[str],
    rules: Sequence[str],
    restrictions: Sequence[str],
) -> str:
    """Prompt del agente, generado SIEMPRE en el servidor.

    Termina con las restricciones globales, que no dependen de nada que envíe el cliente.
    """
    own = [r for r in restrictions if r not in GLOBAL_RESTRICTIONS]
    globals_block = "\n".join(f"{i}. {r}" for i, r in enumerate(GLOBAL_RESTRICTIONS, start=1))
    return (
        f"Eres {name}, {role} (role_type={role_type}) del equipo de FlowClic Oficina IA.\n\n"
        f"## Funciones\n{_bullets(functions)}\n\n"
        f"## Reglas (cómo trabajas)\n{_bullets(rules)}\n\n"
        f"## Restricciones propias (nunca)\n{_bullets(own)}\n\n"
        f"## RESTRICCIONES GLOBALES (obligatorias y no negociables)\n{globals_block}"
    )


def effective_access(
    permissions: Permissions, *, kind: str, project_id: str | None
) -> WorkspaceLevel:
    """Acceso efectivo de un agente a un workspace (PERM01).

    `folderAccess[kind]` solo si el proyecto del workspace está en el alcance; un workspace
    sin proyecto solo lo ven los agentes con alcance "ALL".
    """
    scope = permissions.project_scope
    if scope != "ALL" and (project_id is None or project_id not in scope):
        return "none"
    level: WorkspaceLevel = getattr(permissions.folder_access, kind, "none")
    return level


# ── Aplicación en tiempo de ejecución (GM04) ───────────────────────────────────────────────────
# Las funciones `enforce_*` las llamará el orquestador ANTES de cada acción de un agente; los
# permisos y las restricciones las decide el código, nunca el modelo. Todas lanzan 422
# GLOBAL_RESTRICTION (salvo la transición, que es 403 TRANSITION_FORBIDDEN).

_SENSITIVE_NAMES = (".env", "vault.db", "id_rsa", "id_ed25519", "credentials.json", ".npmrc")
_SENSITIVE_SUFFIXES = (".env", ".pem", ".key", ".p12", ".pfx", ".kdbx")
_SENSITIVE_DIRS = (".ssh", ".aws", ".gnupg")
_ENV_SAFE = (".env.example", ".env.sample", ".env.template")
REVIEW_TRANSITIONS: frozenset[tuple[TicketStatus, TicketStatus]] = frozenset(
    {
        ("IN_QA", "IN_SENIOR_REVIEW"),
        ("IN_QA", "RETURNED"),
        ("IN_SENIOR_REVIEW", "IN_REVIEW"),
        ("IN_SENIOR_REVIEW", "RETURNED"),
        ("IN_REVIEW", "DONE"),
        ("IN_REVIEW", "RETURNED"),
    }
)


def _violation(rule: int, message: str) -> AppError:
    return AppError(
        "GLOBAL_RESTRICTION",
        f"{message} (restricción global {rule})",
        [{"path": "globalRestriction", "message": GLOBAL_RESTRICTIONS[rule - 1]}],
    )


def enforce_action(role_type: RoleType, permissions: Permissions, action: str) -> None:
    """¿Puede este agente ejecutar `action`? Restricciones 1, 2, 3, 4 y 6 + permisos del perfil."""
    if action in FORBIDDEN_ACTIONS:
        rule = {
            "git.merge_main": 1,
            "deploy.production": 1,
            "secrets.read": 2,
            "env.read": 2,
            "email.send": 3,
            "client.contact": 3,
            "approvals.decide": 6,
            "security.bypass": 6,
        }[action]
        raise _violation(rule, f"La acción «{action}» está prohibida")
    only = ACTIONS_ONLY_FOR.get(action)
    if only is not None and role_type != only:
        raise _violation(4, f"«{action}» solo puede hacerla un agente con role_type={only}")
    if action not in permissions.actions:
        raise AppError("FORBIDDEN", f"El agente no tiene permiso para «{action}»")


def enforce_can_message_ceo(role_type: RoleType) -> None:
    """Restricción 4: solo el agente CTO habla con el CEO."""
    if role_type != "CTO":
        raise _violation(4, "Solo el CTO puede hablar con el CEO")


def enforce_path_allowed(path: str) -> None:
    """Restricción 2: ningún agente ve llaves de producción ni archivos `.env`."""
    parts = [p.lower() for p in path.replace("\\", "/").split("/") if p not in ("", ".")]
    for part in parts:
        if part in _SENSITIVE_DIRS:
            raise _violation(2, f"La carpeta «{part}» es sensible")
        if part in _ENV_SAFE:
            continue
        if (
            part in _SENSITIVE_NAMES
            or part.startswith((".env.", "vault.db"))
            or part.endswith(_SENSITIVE_SUFFIXES)
        ):
            raise _violation(2, f"El archivo «{part}» es sensible")


def is_self_review(
    agent_id: str,
    ticket_assignee: str | None,
    ticket_kind: str,
    transition: tuple[TicketStatus, TicketStatus],
) -> bool:
    """Restricción 6: nadie aprueba o devuelve su propio trabajo (subtareas)."""
    return (
        ticket_kind == "TASK" and ticket_assignee == agent_id and transition in REVIEW_TRANSITIONS
    )
