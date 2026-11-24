"""Reloj de cuotas (KEY01): día de uso y hora de reinicio por proveedor.

Google reinicia sus cuotas diarias a medianoche de la hora del Pacífico. No usamos `zoneinfo`
(en Windows exige el paquete `tzdata`): la regla de EE. UU. es fija desde 2007 (horario de
verano: segundo domingo de marzo 02:00 → primer domingo de noviembre 02:00).
"""

from datetime import UTC, date, datetime, timedelta


def _nth_sunday(year: int, month: int, n: int) -> int:
    first = date(year, month, 1)
    return 1 + (6 - first.weekday()) % 7 + 7 * (n - 1)


def pacific_offset(at: datetime) -> timedelta:
    """Desfase de la hora del Pacífico respecto a UTC en el instante `at` (UTC)."""
    at = at.astimezone(UTC)
    start = datetime(at.year, 3, _nth_sunday(at.year, 3, 2), 10, 0, tzinfo=UTC)  # 02:00 PST
    end = datetime(at.year, 11, _nth_sunday(at.year, 11, 1), 9, 0, tzinfo=UTC)  # 02:00 PDT
    return timedelta(hours=-7 if start <= at < end else -8)


def next_pacific_midnight(now: datetime) -> datetime:
    """Próxima medianoche del Pacífico, en UTC."""
    local = now.astimezone(UTC) + pacific_offset(now)
    target_local = datetime(local.year, local.month, local.day, tzinfo=UTC) + timedelta(days=1)
    guess = target_local - pacific_offset(target_local + timedelta(hours=8))
    return target_local - pacific_offset(guess)


def usage_day(provider: str, now: datetime) -> str:
    """Día (AAAA-MM-DD) al que se atribuye el uso: Pacífico para Google, UTC para el resto."""
    base = now.astimezone(UTC)
    if provider == "google":
        base = base + pacific_offset(base)
    return base.strftime("%Y-%m-%d")


def iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond // 1000:03d}Z"


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
