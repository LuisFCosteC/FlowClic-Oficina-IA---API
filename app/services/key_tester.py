"""Prueba de una clave SIN gastar tokens: lista los modelos del proveedor (KEY01).

Solo se llama a URLs fijas de los proveedores (sin SSRF). Los errores devueltos son genéricos:
nunca incluyen la clave ni el cuerpo de la respuesta del proveedor.
"""

import urllib.error
import urllib.request
from collections.abc import Callable

from app.domain.key_schemas import KeyTestResult

KeyTester = Callable[[str, str], KeyTestResult]  # (provider, secret) -> resultado

_TIMEOUT = 10.0


def _request(provider: str, secret: str) -> urllib.request.Request | None:
    if provider == "google":
        return urllib.request.Request(  # noqa: S310 - URL fija https
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
            headers={"x-goog-api-key": secret},
        )
    if provider == "anthropic":
        return urllib.request.Request(  # noqa: S310
            "https://api.anthropic.com/v1/models?limit=1",
            headers={"x-api-key": secret, "anthropic-version": "2023-06-01"},
        )
    if provider == "openai":
        return urllib.request.Request(  # noqa: S310
            "https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {secret}"}
        )
    return None


def http_key_tester(provider: str, secret: str) -> KeyTestResult:
    req = _request(provider, secret)
    if req is None:
        return KeyTestResult(
            ok=False, status="ERROR", message="Este proveedor no tiene prueba automática"
        )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            if 200 <= resp.status < 300:
                return KeyTestResult(ok=True, status="OK", message="La clave es válida")
            return KeyTestResult(ok=False, status="ERROR", message=f"Respuesta HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):  # Google responde 400 a una clave mal formada
            return KeyTestResult(
                ok=False, status="INVALID_KEY", message="El proveedor rechazó la clave"
            )
        if exc.code == 429:
            return KeyTestResult(
                ok=False, status="RATE_LIMITED", message="El proveedor limitó la petición (429)"
            )
        return KeyTestResult(ok=False, status="ERROR", message=f"Respuesta HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError):
        return KeyTestResult(
            ok=False, status="ERROR", message="No se pudo contactar con el proveedor"
        )
