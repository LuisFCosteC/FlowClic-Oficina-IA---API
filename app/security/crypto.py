"""Cifrado de secretos: AES-256-GCM, claves derivadas con HKDF de `APP_MASTER_KEY` (PLAN §16.1).

- Una clave por uso (`info` distinto): lo cifrado para la bóveda no se descifra como
  credencial de agente.
- La AAD (datos asociados) es **obligatoria**: ata el texto cifrado a su contexto (nombre del
  secreto, `agent_id|provider|id`, ...), así que copiarlo a otra fila falla al descifrar.
- Cada cifrado usa un nonce aleatorio de 12 B: la misma entrada da textos cifrados distintos.
- `key_version` permite rotar la clave maestra (`python -m app.security.rotate_key`).
"""

import base64
import binascii
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

Purpose = Literal["vault", "agent-credentials", "provider-keys", "mfa"]

_INFO: dict[str, bytes] = {
    "vault": b"flowclic/vault/v1",
    "agent-credentials": b"flowclic/agent-credentials/v1",
    "provider-keys": b"flowclic/provider-keys/v1",
    "mfa": b"flowclic/mfa/v1",
}
_NONCE_BYTES = 12


class CryptoError(Exception):
    """No se pudo cifrar o descifrar. Los mensajes nunca incluyen datos sensibles."""


@dataclass(frozen=True)
class Sealed:
    """Resultado de cifrar: lo que se guarda en la BD (nunca el texto en claro)."""

    ciphertext: bytes
    nonce: bytes
    key_version: int


def decode_master_key(value: str) -> bytes:
    """Decodifica una `APP_MASTER_KEY` (32 B en base64)."""
    try:
        key = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CryptoError("APP_MASTER_KEY no es base64 válido") from exc
    if len(key) != 32:
        raise CryptoError("APP_MASTER_KEY debe tener 32 bytes")
    return key


def generate_master_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


class SecretBox:
    """Cifra y descifra con claves derivadas de una o varias claves maestras versionadas."""

    def __init__(self, master_keys: Mapping[int, bytes], current_version: int = 1) -> None:
        if current_version not in master_keys:
            raise CryptoError("Falta la clave maestra de la versión actual")
        for key in master_keys.values():
            if len(key) != 32:
                raise CryptoError("Las claves maestras deben tener 32 bytes")
        self._masters = dict(master_keys)
        self.current_version = current_version

    @classmethod
    def from_base64(cls, master_key_b64: str, version: int = 1) -> "SecretBox":
        return cls({version: decode_master_key(master_key_b64)}, version)

    def _key(self, purpose: Purpose, version: int) -> bytes:
        master = self._masters.get(version)
        if master is None:
            raise CryptoError(f"Versión de clave desconocida: {version}")
        info = _INFO.get(purpose)
        if info is None:
            raise CryptoError("Uso de cifrado desconocido")
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(master)

    def encrypt(self, purpose: Purpose, plaintext: bytes, aad: bytes) -> Sealed:
        if not aad:
            raise CryptoError("La AAD es obligatoria")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        key = self._key(purpose, self.current_version)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
        return Sealed(ciphertext, nonce, self.current_version)

    def decrypt(self, purpose: Purpose, sealed: Sealed, aad: bytes) -> bytes:
        if not aad:
            raise CryptoError("La AAD es obligatoria")
        key = self._key(purpose, sealed.key_version)
        try:
            return AESGCM(key).decrypt(sealed.nonce, sealed.ciphertext, aad)
        except InvalidTag as exc:
            raise CryptoError(
                "No se pudo descifrar (clave, contexto o contenido incorrectos)"
            ) from exc

    def encrypt_text(self, purpose: Purpose, text: str, aad: str) -> Sealed:
        return self.encrypt(purpose, text.encode(), aad.encode())

    def decrypt_text(self, purpose: Purpose, sealed: Sealed, aad: str) -> str:
        return self.decrypt(purpose, sealed, aad.encode()).decode()
