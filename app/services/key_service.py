"""Bolsa global de claves API por proveedor (KEY01). Sustituye a las credenciales por agente.

- AES-256-GCM (HKDF `provider-keys`), AAD `provider|id`: un texto cifrado copiado a otra fila no
  se descifra.
- La API NUNCA devuelve la clave, ni al ADMIN: solo `last4`. La auditoría, los eventos SSE y los
  errores tampoco la llevan.
- Pendiente de S09: las rutas exigirán ADMIN + MFA reciente.
"""

from datetime import UTC, datetime, timedelta

from app.db.database import Database, IntegrityError
from app.domain.key_schemas import (
    ExhaustedModel,
    KeyCreate,
    KeyOrder,
    KeyRotate,
    KeyUpdate,
    ModelUsage,
    ProviderKey,
    UsageTotals,
)
from app.domain.models_catalog import MODELS_CATALOG
from app.errors import AppError, conflict, not_found, validation_error
from app.events.bus import EventBus
from app.repositories import keys_repo as repo
from app.security import audit
from app.security.crypto import SecretBox
from app.services import quota_time
from app.util import new_id

IN_USE_SECONDS = 60


def aad(provider: str, key_id: str) -> str:
    return f"{provider}|{key_id}"


def box_from_key(master_key: str | None) -> SecretBox:
    if not master_key:
        raise AppError(
            "ENCRYPTION_UNAVAILABLE",
            "Falta APP_MASTER_KEY en el servidor: ejecuta python scripts/setup_env.py",
        )
    return SecretBox.from_base64(master_key)


def clean_secret(secret: str) -> str:
    value = secret.strip()
    if len(value) < 8:
        raise validation_error("La clave es demasiado corta")
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise validation_error("La clave no puede contener espacios ni saltos de línea")
    return value


# ── Vista (metadatos + uso + estado calculado) ───────────────────────────────────────────────
def _totals(rows: list[tuple[int, int, int, float]]) -> UsageTotals:
    return UsageTotals(
        requests=sum(r[0] for r in rows),
        input_tokens=sum(r[1] for r in rows),
        output_tokens=sum(r[2] for r in rows),
        cost_usd=round(sum(r[3] for r in rows), 6),
    )


def limit_hit(row: repo.KeyRow, requests: int, tokens: int) -> bool:
    """¿Se alcanzó hoy un límite diario puesto por el CEO (en un modelo)?"""
    return (row.daily_request_limit is not None and requests >= row.daily_request_limit) or (
        row.daily_token_limit is not None and tokens >= row.daily_token_limit
    )


def _local_hhmm(until: str) -> str:
    return quota_time.parse_iso(until).astimezone().strftime("%H:%M")


def view(db: Database, row: repo.KeyRow, now: datetime | None = None) -> ProviderKey:
    now = now or datetime.now(UTC)
    now_s = quota_time.iso(now)
    today = quota_time.usage_day(row.provider, now)
    by_model: dict[str, list[tuple[str, int, int, int, float, str | None, str | None, str | None]]]
    by_model = {}
    for u in repo.usage_rows(db, row.id):
        by_model.setdefault(str(u["model"]), []).append(
            (
                str(u["day"]),
                int(u["requests"]),
                int(u["input_tokens"]),
                int(u["output_tokens"]),
                float(u["cost_usd"]),
                u["exhausted_until"],
                u["last_error_code"],
                u["last_used_at"],
            )
        )
    reset_at = quota_time.iso(_limit_reset(row.provider, now))
    models: list[ModelUsage] = []
    exhausted: list[ExhaustedModel] = []
    today_all: list[tuple[int, int, int, float]] = []
    total_all: list[tuple[int, int, int, float]] = []
    last_used: str | None = None
    for model in sorted(by_model):
        rows = by_model[model]
        today_rows = [(r[1], r[2], r[3], r[4]) for r in rows if r[0] == today]
        total_rows = [(r[1], r[2], r[3], r[4]) for r in rows]
        today_all += today_rows
        total_all += total_rows
        until = max((r[5] for r in rows if r[5] is not None and r[5] > now_s), default=None)
        t = _totals(today_rows)
        if until is None and limit_hit(row, t.requests, t.input_tokens + t.output_tokens):
            until = reset_at
        if until is not None:
            exhausted.append(ExhaustedModel(model=model, until=until))
        used = max((r[7] for r in rows if r[7] is not None), default=None)
        if used is not None and (last_used is None or used > last_used):
            last_used = used
        errors = sorted((r[7] or "", r[6]) for r in rows if r[6] is not None)
        models.append(
            ModelUsage(
                model=model,
                today=t,
                total=_totals(total_rows),
                exhausted_until=until,
                last_error_code=errors[-1][1] if errors else None,
                last_used_at=used,
            )
        )
    computed, label, key_until = _computed_status(row, exhausted, last_used, now, now_s)
    return ProviderKey(
        id=row.id,
        provider=row.provider,
        label=row.label,
        last4=row.last4,
        position=row.position,
        status=row.status,
        computed_status=computed,
        status_label=label,
        exhausted_until=key_until,
        exhausted_models=exhausted,
        daily_request_limit=row.daily_request_limit,
        daily_token_limit=row.daily_token_limit,
        usage_today=_totals(today_all),
        usage_total=_totals(total_all),
        usage_by_model=models,
        last_used_at=last_used,
        created_at=row.created_at,
        rotated_at=row.rotated_at,
        revoked_at=row.revoked_at,
    )


def _limit_reset(provider: str, now: datetime) -> datetime:
    if provider == "google":
        return quota_time.next_pacific_midnight(now)
    return (now.astimezone(UTC) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _computed_status(
    row: repo.KeyRow,
    exhausted: list[ExhaustedModel],
    last_used: str | None,
    now: datetime,
    now_s: str,
) -> tuple[str, str, str | None]:
    if row.status == "REVOKED":
        return "REVOKED", "Revocada", None
    if row.status == "INVALID":
        return "INVALID", "Inválida", None
    catalog = {m.id for m in MODELS_CATALOG if m.provider == row.provider}
    gone = {e.model for e in exhausted}
    if exhausted and (not catalog or catalog <= gone):
        until = min(e.until for e in exhausted)
        return "EXHAUSTED", f"Agotada hasta {_local_hhmm(until)}", until
    if last_used is not None:
        age = now - quota_time.parse_iso(last_used)
        if age <= timedelta(seconds=IN_USE_SECONDS):
            return "IN_USE", "En uso", None
    return "ACTIVE", "Activa", None


def get_or_404(db: Database, key_id: str) -> repo.KeyRow:
    row = repo.get(db, key_id)
    if row is None:
        raise not_found("Clave no encontrada")
    return row


def get_view(db: Database, key_id: str) -> ProviderKey:
    return view(db, get_or_404(db, key_id))


def list_keys(db: Database) -> list[ProviderKey]:
    now = datetime.now(UTC)
    return [view(db, r, now) for r in repo.list_all(db)]


def payload(key: ProviderKey) -> dict[str, object]:
    return key.model_dump(by_alias=True, mode="json")


def emit_updated(db: Database, bus: EventBus | None, key_id: str) -> None:
    if bus is not None:
        bus.emit("key.updated", payload(get_view(db, key_id)))


# ── Operaciones del CEO ──────────────────────────────────────────────────────────────────────
def _label_conflict(provider: str, label: str) -> AppError:
    return conflict(f"Ya hay una clave activa de {provider} llamada «{label}»")


def create_key(db: Database, box: SecretBox, bus: EventBus | None, body: KeyCreate) -> ProviderKey:
    secret = clean_secret(body.secret)
    label = body.label.strip()
    if not label:
        raise validation_error("La etiqueta no puede estar vacía")
    if repo.find_by_label(db, body.provider, label) is not None:
        raise _label_conflict(body.provider, label)
    key_id = new_id()
    sealed = box.encrypt_text("provider-keys", secret, aad(body.provider, key_id))
    now = quota_time.iso(datetime.now(UTC))
    try:
        with db.transaction() as tx:
            repo.insert(
                tx,
                key_id=key_id,
                provider=body.provider,
                label=label,
                sealed=sealed,
                last4=secret[-4:],
                position=repo.next_position(tx),
                now=now,
            )
            audit.record(
                tx,
                "key.created",
                target_type="provider_key",
                target_id=key_id,
                meta={"provider": body.provider, "label": label},
            )
    except IntegrityError:
        raise _label_conflict(body.provider, label) from None
    emit_updated(db, bus, key_id)
    return get_view(db, key_id)


def update_key(db: Database, bus: EventBus | None, key_id: str, patch: KeyUpdate) -> ProviderKey:
    row = get_or_404(db, key_id)
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        return view(db, row)
    label = row.label
    if "label" in changes:
        if changes["label"] is None:
            raise validation_error("label no puede ser null")
        label = changes["label"].strip()
        if not label:
            raise validation_error("La etiqueta no puede estar vacía")
        other = repo.find_by_label(db, row.provider, label)
        if other is not None and other.id != key_id:
            raise _label_conflict(row.provider, label)
    req = changes.get("daily_request_limit", row.daily_request_limit)
    tok = changes.get("daily_token_limit", row.daily_token_limit)
    try:
        with db.transaction() as tx:
            repo.update_fields(
                tx, key_id, label=label, daily_request_limit=req, daily_token_limit=tok
            )
            audit.record(
                tx,
                "key.updated",
                target_type="provider_key",
                target_id=key_id,
                meta={"provider": row.provider, "changedFields": sorted(changes)},
            )
    except IntegrityError:
        raise _label_conflict(row.provider, label) from None
    emit_updated(db, bus, key_id)
    return get_view(db, key_id)


def reorder(db: Database, bus: EventBus | None, body: KeyOrder) -> list[ProviderKey]:
    live = [r.id for r in repo.list_all(db) if r.status != "REVOKED"]
    if len(set(body.ids)) != len(body.ids) or sorted(body.ids) != sorted(live):
        raise validation_error(
            "ids: debe contener todas las claves no revocadas, sin repetir ni añadir otras"
        )
    with db.transaction() as tx:
        for position, key_id in enumerate(body.ids):
            repo.set_position(tx, key_id, position)
        audit.record(tx, "key.reordered", target_type="provider_key", meta={"count": len(live)})
    for key_id in body.ids:
        emit_updated(db, bus, key_id)
    return list_keys(db)


def rotate_key(
    db: Database, box: SecretBox, bus: EventBus | None, key_id: str, body: KeyRotate
) -> ProviderKey:
    row = get_or_404(db, key_id)
    if row.status == "REVOKED":
        raise conflict("La clave está revocada: crea una nueva")
    secret = clean_secret(body.secret)
    sealed = box.encrypt_text("provider-keys", secret, aad(row.provider, key_id))
    now = quota_time.iso(datetime.now(UTC))
    with db.transaction() as tx:
        repo.replace_secret(tx, key_id, sealed, secret[-4:], now)
        if row.status == "INVALID":  # una clave nueva vuelve a ser candidata
            repo.set_status(tx, key_id, "ACTIVE", None)
            repo.clear_exhausted(tx, key_id)
        audit.record(
            tx,
            "key.rotated",
            target_type="provider_key",
            target_id=key_id,
            meta={"provider": row.provider, "label": row.label},
        )
    emit_updated(db, bus, key_id)
    return get_view(db, key_id)


def revoke_key(db: Database, bus: EventBus | None, key_id: str) -> None:
    """Revoca (borrado lógico, idempotente). El texto cifrado se conserva para auditoría."""
    row = get_or_404(db, key_id)
    if row.status == "REVOKED":
        return
    with db.transaction() as tx:
        repo.set_status(tx, key_id, "REVOKED", quota_time.iso(datetime.now(UTC)))
        audit.record(
            tx,
            "key.revoked",
            target_type="provider_key",
            target_id=key_id,
            meta={"provider": row.provider, "label": row.label},
        )
    emit_updated(db, bus, key_id)


def reactivate_key(db: Database, bus: EventBus | None, key_id: str) -> ProviderKey:
    """Vuelve a ACTIVE una clave revocada o inválida y limpia sus agotamientos."""
    row = get_or_404(db, key_id)
    if row.status != "ACTIVE":
        other = repo.find_by_label(db, row.provider, row.label)
        if other is not None and other.id != key_id:
            raise _label_conflict(row.provider, row.label)
    try:
        with db.transaction() as tx:
            repo.set_status(tx, key_id, "ACTIVE", None)
            repo.clear_exhausted(tx, key_id)
            audit.record(
                tx,
                "key.reactivated",
                target_type="provider_key",
                target_id=key_id,
                meta={"provider": row.provider, "label": row.label, "from": row.status},
            )
    except IntegrityError:
        raise _label_conflict(row.provider, row.label) from None
    emit_updated(db, bus, key_id)
    return get_view(db, key_id)
