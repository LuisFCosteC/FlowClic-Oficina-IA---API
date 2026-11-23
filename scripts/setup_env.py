"""Crea o completa el `.env` con claves aleatorias (no sobrescribe nada existente).

Uso: `python scripts/setup_env.py`
- Si no hay `.env`: lo crea desde `.env.example` con APP_MASTER_KEY y SESSION_SECRET.
- Si ya existe: solo añade las claves que falten o estén vacías; el resto no se toca.
- El archivo queda accesible solo para el usuario (icacls en Windows, chmod 600 en POSIX).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.security.crypto import generate_master_key  # noqa: E402
from app.security.envfile import atomic_write  # noqa: E402
from app.security.fileperms import broader_than_owner  # noqa: E402

SECRET_KEYS = ("APP_MASTER_KEY", "SESSION_SECRET")


def fill_missing(text: str, keys: tuple[str, ...] = SECRET_KEYS) -> tuple[str, list[str]]:
    """Rellena `CLAVE=` vacías o añade las claves ausentes. Devuelve (texto, claves añadidas)."""
    added: list[str] = []
    for key in keys:
        pattern = re.compile(rf"^{key}=[ \t]*(\r?)$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(rf"{key}={generate_master_key()}\g<1>", text, count=1)
            added.append(key)
        elif not re.search(rf"^{key}=\S", text, re.MULTILINE):
            if text and not text.endswith("\n"):
                text += "\n"
            text += f"{key}={generate_master_key()}\n"
            added.append(key)
    return text, added


def setup(root: Path) -> tuple[str, list[str]]:
    """Devuelve ('created'|'updated'|'unchanged', claves añadidas)."""
    env_path = root / ".env"
    if not env_path.exists():
        template = (root / ".env.example").read_text(encoding="utf-8")
        text, added = fill_missing(template)
        atomic_write(env_path, text.encode("utf-8"))
        return "created", added
    text = env_path.read_text(encoding="utf-8")
    new_text, added = fill_missing(text)
    if added:
        atomic_write(env_path, new_text.encode("utf-8"))
        return "updated", added
    if broader_than_owner(env_path):
        print("AVISO: el .env es accesible por otros usuarios; ejecuta: chmod 600 .env")
    return "unchanged", []


def main() -> int:
    result, added = setup(ROOT)
    if result == "created":
        print(".env creado con claves aleatorias. Guárdalo en un gestor de contraseñas.")
    elif result == "updated":
        print(f".env existente: se añadieron {', '.join(added)}. El resto no se modificó.")
    else:
        print(".env ya tiene todas las claves: no se modificó nada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
