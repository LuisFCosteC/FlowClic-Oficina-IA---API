"""Contraseñas: scrypt con sal aleatoria (PLAN §12.1 #11).

Formato almacenado: `scrypt$N$r$p$salt$hash` (salt y hash en base64) para poder subir los
parámetros más adelante: `verify_password` usa los parámetros guardados en cada hash.
"""

import base64
import hashlib
import hmac
import secrets

MIN_LENGTH = 12
MAX_LENGTH = 128  # evita usar scrypt como vector de denegación de servicio con claves enormes

# Parámetros por defecto: N=2^17, r=8, p=1 (~128 MiB y ~0,3 s por hash).
DEFAULT_N = 2**17
DEFAULT_R = 8
DEFAULT_P = 1
SALT_BYTES = 16
HASH_BYTES = 32
_PREFIX = "scrypt"


class PasswordPolicyError(ValueError):
    """La contraseña no cumple la política (el mensaje se puede mostrar al usuario)."""


def check_policy(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(f"La contraseña debe tener al menos {MIN_LENGTH} caracteres")
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(f"La contraseña no puede superar los {MAX_LENGTH} caracteres")


def _maxmem(n: int, r: int) -> int:
    # scrypt necesita ~128*N*r bytes; margen para el resto de estructuras.
    return 128 * n * r * 2 + 1024 * 1024


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_maxmem(n, r), dklen=HASH_BYTES
    )


def hash_password(
    password: str, *, n: int = DEFAULT_N, r: int = DEFAULT_R, p: int = DEFAULT_P
) -> str:
    """Devuelve `scrypt$N$r$p$salt$hash`. Aplica la política de longitud."""
    check_policy(password)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, n, r, p)
    b64 = base64.b64encode
    return f"{_PREFIX}${n}${r}${p}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Compara en tiempo constante. Un hash mal formado devuelve False (nunca lanza)."""
    try:
        prefix, n_s, r_s, p_s, salt_b64, hash_b64 = stored.split("$")
        if prefix != _PREFIX:
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        actual = _derive(password, salt, n, r, p)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Hash ficticio para igualar el tiempo de respuesta cuando el usuario no existe (S07).
DUMMY_HASH = hash_password("contraseña-ficticia-no-valida", n=2**14)
