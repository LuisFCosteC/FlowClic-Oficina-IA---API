"""Permisos de archivos sensibles: solo el usuario propietario (PLAN §16.1).

Regla: los secretos nunca se escriben en un archivo cuyos permisos no se hayan restringido
ANTES. Si `restrict_to_owner` devuelve False, quien llama debe abortar (fallar en cerrado).
"""

import os
import re
import stat
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache
def _windows_identity() -> tuple[str, str] | None:
    """(`DOMINIO\\usuario`, SID) del usuario actual, vía `whoami /user`. None si no se puede."""
    try:
        out = subprocess.run(  # noqa: S603
            ["whoami", "/user", "/fo", "csv", "/nh"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.match(r'^"([^"]+)","(S-1-[0-9-]+)"$', out)
    return (m.group(1), m.group(2)) if m else None


def restrict_to_owner(path: Path) -> bool:
    """Deja el archivo accesible solo para el usuario actual. True solo si se aplicó de verdad.

    - Linux/macOS: `chmod 0o600`.
    - Windows: `icacls <archivo> /inheritance:r /grant:r *<SID>:F` (sin shell). Se concede al
      **SID** del usuario, no a su nombre, para no depender de `USERNAME` (manipulable) ni de
      nombres ambiguos. Quita la herencia: la carpeta suele dar acceso a "Usuarios autenticados".
    """
    if sys.platform == "win32":
        identity = _windows_identity()
        if identity is None:
            return False
        try:
            subprocess.run(  # noqa: S603
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{identity[1]}:F"],  # noqa: S607
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
        return True
    try:
        os.chmod(path, 0o600)
    except OSError:
        return False
    return True


def _windows_acl_principals(path: Path) -> list[tuple[str, str]] | None:
    """Entradas (principal, derechos) de la ACL según `icacls`. None si no se pudo leer."""
    try:
        out = subprocess.run(  # noqa: S603
            ["icacls", str(path)],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    entries: list[tuple[str, str]] = []
    prefix = str(path)
    for raw_line in out.splitlines():
        # La primera ACE va precedida por la ruta del archivo: se quita.
        line = raw_line[len(prefix) :] if raw_line.startswith(prefix) else raw_line
        # Líneas de ACE: `DOMINIO\usuario:(F)` o `    DOMINIO\usuario:(I)(F)`
        m = re.match(r"^\s*(\S.*?):((?:\([A-Za-z,]+\))+)\s*$", line)
        if m:
            entries.append((m.group(1).strip(), m.group(2)))
    return entries


def broader_than_owner(path: Path) -> bool:
    """True si el archivo es accesible por alguien más que el usuario actual.

    Si no se puede comprobar (p. ej. icacls falla), devuelve True: ante la duda, se avisa.
    """
    if sys.platform == "win32":
        identity = _windows_identity()
        entries = _windows_acl_principals(path)
        if identity is None or not entries:
            return True
        me = identity[0].lower()
        for principal, rights in entries:
            if principal.lower() != me or "(I)" in rights:
                return True
        return False
    return bool(path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
