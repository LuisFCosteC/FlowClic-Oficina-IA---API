"""Validación de las carpetas de los espacios de trabajo (J03).

Reglas (400 con mensaje claro): ruta absoluta, sin segmentos «..», sin rutas UNC ni de
dispositivo, que exista y sea una carpeta, que no sea la raíz de una unidad ni esté dentro de
zonas del sistema (Windows, Program Files...) ni sea la carpeta del perfil del usuario.
La comprobación se repite sobre la ruta real (tras resolver enlaces simbólicos).
"""

import os
import re
import sys
from pathlib import Path

from app.errors import validation_error

WORKSPACE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_PATH_LEN = 500
_WIN_LONG = chr(92) * 2 + "?" + chr(92)  # prefijo de ruta larga de Windows
_WIN_UNC_LONG = _WIN_LONG + "UNC" + chr(92)


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/" + chr(92)) + os.sep)


def _protected_roots() -> list[str]:
    """Carpetas del sistema: nada dentro de ellas (incluida ella misma)."""
    if sys.platform == "win32":
        roots = [
            os.environ.get("SystemRoot", r"C:\Windows"),
            r"C:\Windows",
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            r"C:\Program Files",
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            r"C:\Program Files (x86)",
            os.environ.get("ProgramData", r"C:\ProgramData"),
        ]
    else:
        roots = [
            "/bin",
            "/boot",
            "/dev",
            "/etc",
            "/lib",
            "/lib64",
            "/proc",
            "/root",
            "/sbin",
            "/sys",
            "/usr",
        ]
    return sorted({_norm(r) for r in roots})


def _profile_root() -> str | None:
    home = os.environ.get("USERPROFILE") if sys.platform == "win32" else os.environ.get("HOME")
    return _norm(home) if home else None


def _is_unc_or_device(raw: str) -> bool:
    return raw.startswith(("\\\\", "//"))


def _check_policy(path: str, label: str) -> None:
    """Reglas que no dependen de que la carpeta exista."""
    if Path(path).parent == Path(path):
        raise validation_error(f"{label}: no puede ser la raíz de una unidad")
    norm = _norm(path)
    for root in _protected_roots():
        if _inside(norm, root):
            raise validation_error(f"{label}: es una carpeta del sistema y no se permite")
    if norm == _profile_root():
        raise validation_error(f"{label}: no puede ser la carpeta de perfil del usuario completa")


def validate_workspace_path(raw: str, *, must_exist: bool = True) -> str:
    """Devuelve la ruta normalizada o lanza 400. No lista el contenido de la carpeta."""
    label = "path"
    if not raw or not raw.strip():
        raise validation_error(f"{label}: la ruta no puede estar vacía")
    raw = raw.strip()
    if len(raw) > MAX_PATH_LEN or "\x00" in raw or any(ord(c) < 32 for c in raw):
        raise validation_error(f"{label}: ruta no válida")
    if _is_unc_or_device(raw):
        raise validation_error(f"{label}: no se permiten rutas de red (UNC) ni de dispositivo")
    if not os.path.isabs(raw) or (
        sys.platform == "win32" and not re.match(r"^[A-Za-z]:[/\\]", raw)
    ):
        raise validation_error(f"{label}: la ruta debe ser absoluta")
    if ".." in re.split(r"[/\\]+", raw):
        raise validation_error(f"{label}: no se permite «..» en la ruta")
    path = os.path.normpath(raw)
    _check_policy(path, label)
    if must_exist:
        if not os.path.exists(path):
            raise validation_error(f"{label}: la carpeta no existe")
        if not os.path.isdir(path):
            raise validation_error(f"{label}: la ruta no es una carpeta")
        real = os.path.realpath(path)  # un enlace simbólico no puede sacar de lo permitido
        if real.startswith(_WIN_UNC_LONG):
            raise validation_error(f"{label}: no se permiten rutas de red (UNC)")
        real = real.removeprefix(_WIN_LONG)
        if _is_unc_or_device(real):
            raise validation_error(f"{label}: no se permiten rutas de red (UNC)")
        _check_policy(real, label)
    return path
