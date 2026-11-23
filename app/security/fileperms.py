"""Permisos de archivos sensibles: solo el usuario propietario (PLAN §16.1)."""

import os
import stat
import subprocess
import sys
from pathlib import Path


def restrict_to_owner(path: Path) -> bool:
    """Deja el archivo accesible solo para el usuario actual. Devuelve True si se aplicó.

    - Linux/macOS: `chmod 0o600`.
    - Windows: `icacls <archivo> /inheritance:r /grant:r "<USUARIO>:F"` (sin shell), porque los
      permisos heredados de la carpeta suelen dar acceso a "Usuarios autenticados".
    """
    if sys.platform == "win32":
        user = os.environ.get("USERNAME")
        if not user:
            return False
        try:
            subprocess.run(  # noqa: S603
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],  # noqa: S607
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


def broader_than_owner(path: Path) -> bool:
    """True si (Linux/macOS) el archivo es accesible por grupo u otros. En Windows no se evalúa."""
    if sys.platform == "win32":
        return False
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
