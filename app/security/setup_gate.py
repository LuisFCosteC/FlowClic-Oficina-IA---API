"""Código de configuración de un solo uso para el modo SETUP (PLAN §16.3).

Se imprime en la consola del servidor (nunca en el log ni en una respuesta), caduca a los
30 min y se invalida tras 5 intentos fallidos (se emite uno nuevo). Quien no ve la consola
del servidor no puede completar el asistente.
"""

import hmac
import secrets
import threading
import time
from collections.abc import Callable

from app.errors import AppError

# Sin caracteres ambiguos (I, O, 0, 1).
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GROUPS = 3
GROUP_LEN = 4
TTL_SECONDS = 30 * 60
MAX_ATTEMPTS = 5


def _console(code: str) -> None:
    print(
        f"\n[SETUP] Código de configuración: {code}  "
        f"(caduca en {TTL_SECONDS // 60} min; solo desde localhost)\n",
        flush=True,
    )


class SetupGate:
    def __init__(
        self,
        ttl_seconds: int = TTL_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        clock: Callable[[], float] = time.monotonic,
        announce: Callable[[str], None] = _console,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._clock = clock
        self._announce = announce
        self._lock = threading.Lock()
        # Serializa toda la secuencia comprobación + escritura de un paso del asistente.
        self.operation = threading.Lock()
        self._code: str | None = None
        self._expires = 0.0
        self._attempts = 0

    @staticmethod
    def _new_code() -> str:
        return "-".join(
            "".join(secrets.choice(ALPHABET) for _ in range(GROUP_LEN)) for _ in range(GROUPS)
        )

    def issue(self) -> str:
        """Genera un código nuevo (invalida el anterior) y lo muestra en la consola."""
        with self._lock:
            return self._issue_locked()

    def _issue_locked(self) -> str:
        self._code = self._new_code()
        self._expires = self._clock() + self._ttl
        self._attempts = 0
        self._announce(self._code)
        return self._code

    @property
    def code(self) -> str | None:
        """Solo para pruebas internas: nunca se expone por la API."""
        return self._code

    def close(self) -> None:
        with self._lock:
            self._code = None

    def verify(self, supplied: str) -> None:
        """Lanza 403 si el código no es válido. Mensaje idéntico en todos los casos de fallo."""
        denied = AppError("FORBIDDEN", "Código de configuración inválido o caducado")
        with self._lock:
            if self._code is None:
                raise denied
            if self._clock() >= self._expires:
                self._issue_locked()  # caducado: se emite otro (solo visible en la consola)
                raise denied
            candidate = supplied.strip().upper().encode()
            if hmac.compare_digest(candidate, self._code.encode()):
                return
            self._attempts += 1
            if self._attempts >= self._max_attempts:
                self._issue_locked()  # demasiados fallos: el código anterior queda quemado
            raise denied
