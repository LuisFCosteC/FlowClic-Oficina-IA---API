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
    """Escritura atómica (temporal + renombrado) que falla en cerrado.

    El temporal se restringe al propietario ANTES de escribir ningún dato; si no se puede
    restringir, se borra el temporal y se lanza `PermissionError` sin tocar el archivo destino.
    El renombrado conserva los permisos del temporal.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        os.close(fd)  # vacío todavía: se restringe antes de escribir el contenido
        if not restrict_to_owner(tmp_path):
            raise PermissionError(
                f"No se pudieron restringir los permisos de {path.name}; no se escribió nada."
            )
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


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
