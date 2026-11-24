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

# Prohibidas para cualquier agente (restricciones globales 1, 2 y 3): 422 GLOBAL_RESTRICTION.
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "git.merge_main",
        "deploy.production",
        "secrets.read",
        "env.read",
        "email.send",
        "client.contact",
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
