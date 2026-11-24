"""KEY01: KeyPool (rotación ante 429, por modelo, reinicio, INVALID, SLEEP_QUOTA, concurrencia)."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.errors import AppError
from app.events.bus import DomainEvent, get_bus
from app.security.crypto import SecretBox
from app.services import key_pool, key_service, quota_time
from app.services.key_pool import KeyPool

T0 = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)  # 07:00 PST


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def box(master_key: str) -> SecretBox:
    return SecretBox.from_base64(master_key)


@pytest.fixture
def pool(migrated_db: Database, box: SecretBox, clock: Clock) -> KeyPool:
    return KeyPool(migrated_db, box, get_bus(), clock=clock)


def add(db: Database, box: SecretBox, label: str, secret: str, provider: str = "google") -> str:
    from app.domain.key_schemas import KeyCreate

    created = key_service.create_key(
        db,
        box,
        None,
        KeyCreate(provider=provider, label=label, secret=secret),  # type: ignore[arg-type]
    )
    return created.id


def test_toma_la_primera_por_posicion(migrated_db: Database, box: SecretBox, pool: KeyPool) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    b = add(migrated_db, box, "b", "secret-bbbb-0002")
    got = pool.acquire("google", "gemini-pro")
    assert got.key_id == a and got.secret == "secret-aaaa-0001"
    assert "secret-aaaa" not in repr(got)  # el repr oculta la clave
    from app.domain.key_schemas import KeyOrder

    key_service.reorder(migrated_db, None, KeyOrder(ids=[b, a]))
    assert pool.acquire("google", "gemini-pro").key_id == b


def test_rotacion_ante_429_hacia_la_siguiente(
    migrated_db: Database, box: SecretBox, pool: KeyPool
) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    b = add(migrated_db, box, "b", "secret-bbbb-0002")
    assert pool.acquire("google", "gemini-pro").key_id == a
    pool.report_exhausted(a, "gemini-pro")  # 429
    assert pool.acquire("google", "gemini-pro").key_id == b
    pool.report_exhausted(b, "gemini-pro")
    with pytest.raises(AppError) as exc:
        pool.acquire("google", "gemini-pro")
    assert exc.value.code == "NO_KEY_AVAILABLE" and exc.value.status_code == 503


def test_agotar_en_pro_no_agota_en_flash(
    migrated_db: Database, box: SecretBox, pool: KeyPool
) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    pool.report_exhausted(a, "gemini-pro")
    assert pool.acquire("google", "gemini-flash").key_id == a
    with pytest.raises(AppError):
        pool.acquire("google", "gemini-pro")
    assert key_pool.has_usable_key(migrated_db, "google", "gemini-flash") is True
    assert key_pool.has_usable_key(migrated_db, "google", "gemini-pro") is False
    view = key_service.get_view(migrated_db, a)
    assert view.computed_status == "ACTIVE"  # solo Pro agotada
    assert [e.model for e in view.exhausted_models] == ["gemini-pro"]
    pool.report_exhausted(a, "gemini-flash")
    view = key_service.get_view(migrated_db, a)
    assert view.computed_status == "EXHAUSTED" and view.status_label.startswith("Agotada hasta ")


def test_el_reinicio_la_reactiva(
    migrated_db: Database, box: SecretBox, pool: KeyPool, clock: Clock
) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    pool.report_exhausted(a, "gemini-pro")
    with pytest.raises(AppError):
        pool.acquire("google", "gemini-pro")
    # Google: medianoche del Pacífico. T0 = 07:00 PST → faltan 17 h
    reset = quota_time.next_pacific_midnight(T0)
    assert reset == datetime(2026, 11, 24, 8, 0, tzinfo=UTC)
    clock.now = reset - timedelta(seconds=1)
    with pytest.raises(AppError):
        pool.acquire("google", "gemini-pro")
    clock.now = reset
    assert pool.acquire("google", "gemini-pro").key_id == a


def test_reinicio_de_otros_proveedores_retry_after_o_una_hora(
    migrated_db: Database, box: SecretBox, pool: KeyPool, clock: Clock
) -> None:
    x = add(migrated_db, box, "x", "secret-xxxx-0001", provider="anthropic")
    pool.report_exhausted(x, "claude-opus-5-5", retry_after_seconds=120)
    clock.now = T0 + timedelta(seconds=119)
    with pytest.raises(AppError):
        pool.acquire("anthropic", "claude-opus-5-5")
    clock.now = T0 + timedelta(seconds=121)
    assert pool.acquire("anthropic", "claude-opus-5-5").key_id == x
    pool.report_exhausted(x, "claude-opus-5-5")  # sin Retry-After: 1 h
    clock.now += timedelta(minutes=59)
    with pytest.raises(AppError):
        pool.acquire("anthropic", "claude-opus-5-5")
    clock.now += timedelta(minutes=2)
    assert pool.acquire("anthropic", "claude-opus-5-5").key_id == x


def test_reset_configurable(migrated_db: Database, box: SecretBox, clock: Clock) -> None:
    short = KeyPool(migrated_db, box, clock=clock, default_reset_hours=0.25)
    x = add(migrated_db, box, "x", "secret-xxxx-0001", provider="openai")
    short.report_exhausted(x, "m")
    clock.now += timedelta(minutes=16)
    assert short.acquire("openai", "m").key_id == x
    explicit = clock.now + timedelta(hours=5)
    short.report_exhausted(x, "m", reset_at=explicit)
    clock.now = explicit - timedelta(seconds=1)
    with pytest.raises(AppError):
        short.acquire("openai", "m")


def test_clave_invalida_nunca_se_usa(
    migrated_db: Database, box: SecretBox, pool: KeyPool, clock: Clock
) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    b = add(migrated_db, box, "b", "secret-bbbb-0002")
    pool.report_invalid(a, "401")
    clock.now += timedelta(days=30)
    for _ in range(3):
        assert pool.acquire("google", "gemini-pro").key_id == b
    assert key_service.get_view(migrated_db, a).status_label == "Inválida"
    pool.report_invalid(b, "403")
    with pytest.raises(AppError):
        pool.acquire("google", "gemini-pro")
    assert key_pool.has_usable_key(migrated_db, "google", "gemini-pro") is False
    key_service.reactivate_key(migrated_db, None, a)  # solo el CEO la devuelve al uso
    assert pool.acquire("google", "gemini-pro").key_id == a


def test_revocada_no_se_usa(migrated_db: Database, box: SecretBox, pool: KeyPool) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    key_service.revoke_key(migrated_db, None, a)
    with pytest.raises(AppError):
        pool.acquire("google", "gemini-pro")


def test_uso_acumulado_por_modelo_y_dia(
    migrated_db: Database, box: SecretBox, pool: KeyPool, clock: Clock
) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    pool.report_usage(a, "gemini-pro", 100, 50, 0.01)
    pool.report_usage(a, "gemini-pro", 10, 5, 0.001)
    pool.report_usage(a, "gemini-flash", 1, 1, 0.0001)
    clock.now += timedelta(days=1)
    pool.report_usage(a, "gemini-pro", 7, 3, 0.002)
    view = key_service.view(migrated_db, key_service.get_or_404(migrated_db, a), clock.now)
    by = {m.model: m for m in view.usage_by_model}
    assert by["gemini-pro"].total.requests == 3 and by["gemini-pro"].today.requests == 1
    assert by["gemini-pro"].total.input_tokens == 117
    assert by["gemini-pro"].today.output_tokens == 3
    assert by["gemini-flash"].today.requests == 0 and by["gemini-flash"].total.requests == 1
    assert view.usage_total.requests == 4 and view.usage_today.requests == 1
    assert view.usage_total.cost_usd == pytest.approx(0.0131)


def test_limites_diarios_del_ceo(
    migrated_db: Database, box: SecretBox, pool: KeyPool, clock: Clock
) -> None:
    from app.domain.key_schemas import KeyUpdate

    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    b = add(migrated_db, box, "b", "secret-bbbb-0002")
    key_service.update_key(migrated_db, None, a, KeyUpdate(daily_request_limit=2))
    pool.report_usage(a, "gemini-pro", 1, 1, 0)
    assert pool.acquire("google", "gemini-pro").key_id == a
    pool.report_usage(a, "gemini-pro", 1, 1, 0)  # alcanza el límite del día
    assert pool.acquire("google", "gemini-pro").key_id == b
    assert pool.acquire("google", "gemini-flash").key_id == a  # el límite es por modelo
    clock.now = quota_time.next_pacific_midnight(clock.now)  # día nuevo: se reinicia
    assert pool.acquire("google", "gemini-pro").key_id == a


def test_sin_clave_el_agente_pasa_a_sleep_quota(
    client: TestClient, migrated_db: Database, box: SecretBox, clock: Clock
) -> None:
    agent = client.post("/api/agents", json={"name": "Zed", "role": "Dev"}).json()
    events: list[DomainEvent] = []
    off = get_bus().subscribe(events.append)
    pool = KeyPool(migrated_db, box, get_bus(), clock=clock)
    try:
        with pytest.raises(AppError) as exc:
            pool.acquire_for_agent(agent["id"], "google", "gemini-pro")
        assert exc.value.code == "NO_KEY_AVAILABLE"
    finally:
        off()
    status = client.get(f"/api/agents/{agent['id']}").json()["status"]
    assert status == "SLEEP_QUOTA"
    assert any(e.type == "agent.updated" for e in events)
    # R1: un agente BLOCKED no se toca
    blocked = client.post("/api/agents", json={"name": "Bob", "role": "Dev"}).json()
    client.patch(f"/api/agents/{blocked['id']}/status", json={"status": "BLOCKED"})
    with pytest.raises(AppError):
        pool.acquire_for_agent(blocked["id"], "google", "gemini-pro")
    assert client.get(f"/api/agents/{blocked['id']}").json()["status"] == "BLOCKED"


def test_concurrencia_sin_errores(migrated_db: Database, box: SecretBox, pool: KeyPool) -> None:
    a = add(migrated_db, box, "a", "secret-aaaa-0001")
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(10):
                pool.acquire("google", "gemini-pro")
                pool.report_usage(a, "gemini-pro", 1, 1, 0.001)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert key_service.get_view(migrated_db, a).usage_total.requests == 50


def test_la_clave_no_aparece_en_vistas_ni_eventos(
    migrated_db: Database, box: SecretBox, pool: KeyPool
) -> None:
    secret = "secret-UNICO-0001"
    a = add(migrated_db, box, "a", secret)
    events: list[DomainEvent] = []
    off = get_bus().subscribe(events.append)
    try:
        pool.report_usage(a, "gemini-pro", 1, 1, 0)
        pool.report_exhausted(a, "gemini-pro")
        pool.report_invalid(a)
    finally:
        off()
    assert events and all(secret not in str(e.payload) for e in events)
    assert secret not in key_service.get_view(migrated_db, a).model_dump_json()


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2026, 7, 1, 12, 0, tzinfo=UTC), datetime(2026, 7, 2, 7, 0, tzinfo=UTC)),  # PDT
        (datetime(2026, 12, 1, 12, 0, tzinfo=UTC), datetime(2026, 12, 2, 8, 0, tzinfo=UTC)),  # PST
        (datetime(2026, 3, 7, 12, 0, tzinfo=UTC), datetime(2026, 3, 8, 8, 0, tzinfo=UTC)),
        # el 8-mar-2026 (2.º domingo) cambia a PDT a las 02:00: la medianoche siguiente es PDT
        (datetime(2026, 3, 8, 12, 0, tzinfo=UTC), datetime(2026, 3, 9, 7, 0, tzinfo=UTC)),
        (datetime(2026, 11, 1, 12, 0, tzinfo=UTC), datetime(2026, 11, 2, 8, 0, tzinfo=UTC)),
    ],
)
def test_medianoche_del_pacifico(when: datetime, expected: datetime) -> None:
    assert quota_time.next_pacific_midnight(when) == expected


def test_dia_de_uso_de_google_es_pacifico() -> None:
    t = datetime(2026, 11, 24, 3, 0, tzinfo=UTC)  # 19:00 PST del día 23
    assert quota_time.usage_day("google", t) == "2026-11-23"
    assert quota_time.usage_day("anthropic", t) == "2026-11-24"
