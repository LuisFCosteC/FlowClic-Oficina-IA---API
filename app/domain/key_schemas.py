"""DTOs de la bolsa global de claves API (KEY01). La clave NUNCA sale: solo `last4`."""

from typing import Annotated, Literal

from pydantic import Field

from app.domain.schemas import CamelModel, StrictInput

KeyProvider = Literal["google", "anthropic", "openai", "other"]
KeyStatus = Literal["ACTIVE", "REVOKED", "INVALID"]
ComputedKeyStatus = Literal["ACTIVE", "IN_USE", "EXHAUSTED", "INVALID", "REVOKED"]
KeySecret = Annotated[str, Field(min_length=8, max_length=4096)]
KeyLabel = Annotated[str, Field(min_length=1, max_length=80)]
DailyLimit = Annotated[int, Field(ge=1, le=1_000_000_000)]


class UsageTotals(CamelModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ModelUsage(CamelModel):
    model: str
    today: UsageTotals
    total: UsageTotals
    exhausted_until: str | None
    last_error_code: str | None
    last_used_at: str | None


class ExhaustedModel(CamelModel):
    model: str
    until: str


class ProviderKey(CamelModel):
    """Metadatos de una clave + uso + estado calculado. Sin el valor de la clave."""

    id: str
    provider: KeyProvider
    label: str
    last4: str
    position: int
    status: KeyStatus
    computed_status: ComputedKeyStatus
    status_label: str
    exhausted_until: str | None
    exhausted_models: list[ExhaustedModel]
    daily_request_limit: int | None
    daily_token_limit: int | None
    usage_today: UsageTotals
    usage_total: UsageTotals
    usage_by_model: list[ModelUsage]
    last_used_at: str | None
    created_at: str
    rotated_at: str | None
    revoked_at: str | None


class KeyCreate(StrictInput):
    provider: KeyProvider
    label: KeyLabel
    secret: KeySecret


class KeyUpdate(StrictInput):
    """Parcial. Un límite en `null` lo quita."""

    label: KeyLabel | None = None
    daily_request_limit: DailyLimit | None = None
    daily_token_limit: DailyLimit | None = None


class KeyRotate(StrictInput):
    secret: KeySecret


class KeyOrder(StrictInput):
    ids: Annotated[list[Annotated[str, Field(min_length=1, max_length=64)]], Field(max_length=500)]


class KeyTestResult(CamelModel):
    ok: bool
    status: Literal["OK", "INVALID_KEY", "RATE_LIMITED", "ERROR"]
    message: str
