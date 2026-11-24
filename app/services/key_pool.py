"""KeyPool: elige y contabiliza las claves de la bolsa global para el orquestador (KEY01).

- `acquire(provider, model)`: la PRIMERA clave por `position` que esté ACTIVE y no agotada para
  ESE modelo (agotar una clave en Pro no la agota en Flash).
- `report_usage`, `report_exhausted` (429 / cuota), `report_invalid` (401/403: no se vuelve a usar).
- Sin clave usable → `NO_KEY_AVAILABLE` y, con `acquire_for_agent`, el agente pasa a SLEEP_QUOTA.
- Un lock de proceso serializa las operaciones contra la concurrencia.
- El secreto solo existe en memoria dentro de `AcquiredKey` (su repr lo oculta): nunca se
  registra en logs, errores ni eventos.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.db.database import Database
from app.errors import AppError
from app.events.bus import EventBus
from app.repositories import agents_repo
from app.repositories import keys_repo as repo
from app.security.crypto import CryptoError, SecretBox
from app.services import key_service, quota_time
from app.services.agents_service import agent_payload
from app.util import now_iso

log = logging.getLogger("flowclic")
_LOCK = threading.RLock()  # compartido por todas las instancias del proceso
DEFAULT_RESET_HOURS = 1.0  # proveedores sin regla propia y sin Retry-After


@dataclass(frozen=True)
class AcquiredKey:
    key_id: str
    provider: str
    label: str
    model: str
    secret: str = field(repr=False)


def no_key_available(provider: str, model: str) -> AppError:
    return AppError(
        "NO_KEY_AVAILABLE",
        f"No hay ninguna clave de {provider} disponible para el modelo «{model}»",
    )


def is_usable(db: Database, row: repo.KeyRow, model: str, now: datetime | None = None) -> bool:
    """ACTIVE, sin agotamiento vigente para el modelo y sin límite diario alcanzado hoy."""
    now = now or datetime.now(UTC)
    if row.status != "ACTIVE":
        return False
    if repo.is_model_exhausted(db, row.id, model, quota_time.iso(now)):
        return False
    today = repo.day_row(db, row.id, model, quota_time.usage_day(row.provider, now))
    if today is not None:
        tokens = int(today["input_tokens"]) + int(today["output_tokens"])
        if key_service.limit_hit(row, int(today["requests"]), tokens):
            return False
    return True


def usable_models(db: Database, models: list[tuple[str, str]]) -> dict[str, bool]:
    """`hasConnection` de varios modelos [(id, proveedor)] con solo 2 consultas a la BD."""
    now = datetime.now(UTC)
    now_s = quota_time.iso(now)
    keys = repo.list_active_all(db)
    usage = repo.usage_rows_all(db)
    result: dict[str, bool] = {}
    for model_id, provider in models:
        usable = False
        for key in (k for k in keys if k.provider == provider):
            day = quota_time.usage_day(provider, now)
            rows = [u for u in usage if u["key_id"] == key.id and u["model"] == model_id]
            if any(u["exhausted_until"] is not None and u["exhausted_until"] > now_s for u in rows):
                continue
            today = next((u for u in rows if u["day"] == day), None)
            if today is not None:
                tokens = int(today["input_tokens"]) + int(today["output_tokens"])
                if key_service.limit_hit(key, int(today["requests"]), tokens):
                    continue
            usable = True
            break
        result[model_id] = usable
    return result


def has_usable_key(db: Database, provider: str, model: str) -> bool:
    """`hasConnection` de GET /api/models: existe una clave usable del proveedor para el modelo."""
    now = datetime.now(UTC)
    return any(is_usable(db, r, model, now) for r in repo.list_for_provider(db, provider))


class KeyPool:
    def __init__(
        self,
        db: Database,
        box: SecretBox,
        bus: EventBus | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        default_reset_hours: float = DEFAULT_RESET_HOURS,
    ) -> None:
        self._db = db
        self._box = box
        self._bus = bus
        self._clock = clock or (lambda: datetime.now(UTC))
        self._default_reset_hours = default_reset_hours

    # ── elegir ───────────────────────────────────────────────────────────────────────────────
    def acquire(self, provider: str, model: str) -> AcquiredKey:
        with _LOCK:
            now = self._clock()
            for row in repo.list_for_provider(self._db, provider):
                if not is_usable(self._db, row, model, now):
                    continue
                sealed = repo.get_sealed(self._db, row.id)
                if sealed is None:
                    continue
                try:
                    secret = self._box.decrypt_text(
                        "provider-keys", sealed, key_service.aad(row.provider, row.id)
                    )
                except CryptoError:
                    log.warning("No se pudo descifrar la clave %s: se omite", row.id)
                    continue
                return AcquiredKey(row.id, row.provider, row.label, model, secret)
            raise no_key_available(provider, model)

    def acquire_for_agent(self, agent_id: str, provider: str, model: str) -> AcquiredKey:
        """Como `acquire`; sin clave usable el agente pasa a SLEEP_QUOTA (no toca BLOCKED)."""
        try:
            return self.acquire(provider, model)
        except AppError as exc:
            if exc.code == "NO_KEY_AVAILABLE":
                self._sleep_agent(agent_id)
            raise

    def _sleep_agent(self, agent_id: str) -> None:
        with _LOCK:
            agent = agents_repo.get_agent(self._db, agent_id)
            if agent is None or agent.archived_at is not None or agent.status == "BLOCKED":
                return
            if agent.status == "SLEEP_QUOTA":
                return
            agents_repo.set_status(self._db, agent_id, "SLEEP_QUOTA", agent.current_task, now_iso())
            updated = agents_repo.get_agent(self._db, agent_id)
        if self._bus is not None and updated is not None:
            self._bus.emit("agent.updated", agent_payload(updated))

    # ── informar ─────────────────────────────────────────────────────────────────────────────
    def report_usage(
        self, key_id: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float
    ) -> None:
        with _LOCK:
            row = key_service.get_or_404(self._db, key_id)
            now = self._clock()
            with self._db.transaction() as tx:
                repo.add_usage(
                    tx,
                    key_id,
                    model,
                    quota_time.usage_day(row.provider, now),
                    input_tokens=max(0, input_tokens),
                    output_tokens=max(0, output_tokens),
                    cost_usd=max(0.0, cost_usd),
                    now=quota_time.iso(now),
                )
        key_service.emit_updated(self._db, self._bus, key_id)

    def default_reset_at(self, provider: str, retry_after_seconds: float | None = None) -> datetime:
        """Google: medianoche del Pacífico. El resto: Retry-After o `default_reset_hours`."""
        now = self._clock()
        if provider == "google":
            return quota_time.next_pacific_midnight(now)
        seconds = (
            retry_after_seconds
            if retry_after_seconds is not None and retry_after_seconds > 0
            else self._default_reset_hours * 3600
        )
        return now + timedelta(seconds=seconds)

    def report_exhausted(
        self,
        key_id: str,
        model: str,
        reset_at: datetime | None = None,
        *,
        retry_after_seconds: float | None = None,
        error_code: str | None = "429",
    ) -> None:
        """429 o cuota agotada: la clave deja de ofrecerse PARA ESE MODELO hasta `reset_at`."""
        with _LOCK:
            row = key_service.get_or_404(self._db, key_id)
            until = reset_at or self.default_reset_at(row.provider, retry_after_seconds)
            now = self._clock()
            with self._db.transaction() as tx:
                repo.mark_exhausted(
                    tx,
                    key_id,
                    model,
                    quota_time.usage_day(row.provider, now),
                    quota_time.iso(until),
                    error_code,
                    quota_time.iso(now),
                )
        key_service.emit_updated(self._db, self._bus, key_id)

    def report_invalid(self, key_id: str, error_code: str | None = "401") -> None:
        """401/403: la clave pasa a INVALID y no se vuelve a usar (hasta rotarla o reactivarla)."""
        with _LOCK:
            row = key_service.get_or_404(self._db, key_id)
            if row.status == "REVOKED":
                return
            with self._db.transaction() as tx:
                repo.set_status(tx, key_id, "INVALID", None)
                if error_code:
                    repo.set_error(
                        tx,
                        key_id,
                        "*",
                        quota_time.usage_day(row.provider, self._clock()),
                        error_code,
                        quota_time.iso(self._clock()),
                    )
        key_service.emit_updated(self._db, self._bus, key_id)
