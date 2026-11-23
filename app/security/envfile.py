"""Importa `TURSO_*` del `.env` a la bóveda cifrada y los elimina del archivo (PLAN §16.4)."""

import logging
import os
import re
import tempfile
from pathlib import Path

from app.security.fileperms import restrict_to_owner
from app.security.vault import SecretName, Vault

log = logging.getLogger("flowclic")

_LINE = re.compile(r"^\s*(TURSO_DATABASE_URL|TURSO_AUTH_TOKEN)\s*=(.*)$")
_KEYS: dict[str, SecretName] = {
    "TURSO_DATABASE_URL": "db.url",
    "TURSO_AUTH_TOKEN": "db.auth_token",
}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def atomic_write(path: Path, data: bytes) -> None:
    """Escritura atómica (temporal + renombrado) dejando el archivo solo para el propietario."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    restrict_to_owner(path)


def import_env_secrets(
    env_path: Path,
    vault: Vault,
    env_url: str | None = None,
    env_token: str | None = None,
) -> bool:
    """Si la bóveda no tiene conexión y el `.env` aún trae `TURSO_*`: los guarda cifrados y los
    elimina del `.env` (sin copia de seguridad: sería otro secreto en claro).

    `env_url`/`env_token` son un respaldo (variables de entorno reales): se importan igualmente,
    aunque en ese caso no hay nada que borrar del archivo. Devuelve True si importó algo.
    Nunca escribe valores en el log.
    """
    raw = env_path.read_bytes() if env_path.exists() else b""
    lines = raw.decode("utf-8").splitlines(keepends=True) if raw else []

    found: dict[SecretName, str] = {}
    keep: list[str] = []
    for line in lines:
        m = _LINE.match(line.rstrip("\r\n"))
        if m:
            raw_value = _unquote(m.group(2))
            if raw_value:
                found[_KEYS[m.group(1)]] = raw_value
        else:
            keep.append(line)
    has_lines = len(keep) != len(lines)

    if vault.has("db.url"):
        if has_lines:
            log.warning(
                "El .env aún tiene TURSO_*, pero la bóveda ya tiene conexión: bórralas del .env."
            )
        return False

    if "db.url" not in found and env_url:
        found["db.url"] = env_url
    if "db.auth_token" not in found and env_token:
        found["db.auth_token"] = env_token
    if "db.url" not in found:
        return False

    names: tuple[SecretName, ...] = ("db.url", "db.auth_token")
    for name in names:
        stored = found.get(name)
        if stored is not None:
            vault.set_secret(name, stored, updated_by="env-import")
    # Solo se borra del .env tras comprobar que la bóveda devuelve lo mismo.
    for name in names:
        expected = found.get(name)
        if expected is not None and vault.get_secret(name) != expected:
            raise RuntimeError("La importación a la bóveda no se pudo verificar")

    if has_lines:
        atomic_write(env_path, "".join(keep).encode("utf-8"))
    log.info("conexión importada a la bóveda")
    return True
