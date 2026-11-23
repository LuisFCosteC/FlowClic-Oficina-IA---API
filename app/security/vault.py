"""Bóveda local cifrada (`data/vault.db`) para la URL y el token de la BD (PLAN §16.2).

Vive fuera de la BD principal porque la API necesita la URL *antes* de poder conectarse.
Cada secreto se cifra con AES-256-GCM (clave HKDF de `APP_MASTER_KEY`); la AAD es el nombre.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Literal

from app.security.crypto import CryptoError, Sealed, SecretBox
from app.security.fileperms import restrict_to_owner
from app.util import now_iso

SecretName = Literal["db.url", "db.auth_token"]
_NAMES = ("db.url", "db.auth_token")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS secrets (
  name        TEXT PRIMARY KEY CHECK (name IN ('db.url','db.auth_token')),
  ciphertext  BLOB NOT NULL,
  nonce       BLOB NOT NULL,
  key_version INTEGER NOT NULL,
  updated_by  TEXT,
  updated_at  TEXT NOT NULL
)
"""


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, path: Path, box: SecretBox) -> None:
        self._box = box
        self._lock = threading.RLock()
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            # Se crea vacío y se restringe ANTES de guardar ningún secreto (falla en cerrado).
            path.touch()
            if not restrict_to_owner(path):
                path.unlink(missing_ok=True)
                raise VaultError(
                    "No se pudieron restringir los permisos de la bóveda; no se creó el archivo."
                )
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute(_SCHEMA)

    @staticmethod
    def _check(name: str) -> None:
        if name not in _NAMES:
            raise VaultError(f"Secreto desconocido: {name}")

    def has(self, name: SecretName) -> bool:
        self._check(name)
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM secrets WHERE name = ?", (name,)).fetchone()
        return row is not None

    def get_secret(self, name: SecretName) -> str | None:
        """Devuelve el secreto descifrado o None si no existe."""
        self._check(name)
        with self._lock:
            row = self._conn.execute(
                "SELECT ciphertext, nonce, key_version FROM secrets WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            return None
        try:
            sealed = Sealed(bytes(row[0]), bytes(row[1]), int(row[2]))
            return self._box.decrypt_text("vault", sealed, name)
        except CryptoError as exc:
            raise VaultError(
                f"No se pudo descifrar «{name}»: ¿cambió APP_MASTER_KEY o se alteró la bóveda?"
            ) from exc

    def set_secret(self, name: SecretName, value: str, updated_by: str | None = None) -> None:
        self._check(name)
        sealed = self._box.encrypt_text("vault", value, name)
        with self._lock:
            self._conn.execute(
                """INSERT INTO secrets
                     (name, ciphertext, nonce, key_version, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET ciphertext = excluded.ciphertext,
                     nonce = excluded.nonce, key_version = excluded.key_version,
                     updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                (name, sealed.ciphertext, sealed.nonce, sealed.key_version, updated_by, now_iso()),
            )

    def delete_secret(self, name: SecretName) -> None:
        self._check(name)
        with self._lock:
            self._conn.execute("DELETE FROM secrets WHERE name = ?", (name,))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
