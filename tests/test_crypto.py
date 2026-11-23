import base64
from dataclasses import replace

import pytest

from app.security.crypto import (
    CryptoError,
    SecretBox,
    decode_master_key,
    generate_master_key,
)

SECRET = "sk-ant-valor-super-secreto-1234"


@pytest.fixture
def box() -> SecretBox:
    return SecretBox.from_base64(generate_master_key())


def test_cifrar_y_descifrar(box: SecretBox) -> None:
    sealed = box.encrypt_text("agent-credentials", SECRET, "a1|anthropic|c1")
    assert SECRET.encode() not in sealed.ciphertext
    assert sealed.key_version == 1
    assert box.decrypt_text("agent-credentials", sealed, "a1|anthropic|c1") == SECRET


def test_la_misma_entrada_da_textos_cifrados_distintos(box: SecretBox) -> None:
    a = box.encrypt_text("vault", SECRET, "db.url")
    b = box.encrypt_text("vault", SECRET, "db.url")
    assert a.nonce != b.nonce
    assert a.ciphertext != b.ciphertext


def test_otra_aad_falla(box: SecretBox) -> None:
    sealed = box.encrypt_text("vault", SECRET, "db.url")
    with pytest.raises(CryptoError):
        box.decrypt_text("vault", sealed, "db.auth_token")


def test_texto_cifrado_o_nonce_alterado_falla(box: SecretBox) -> None:
    sealed = box.encrypt_text("vault", SECRET, "db.url")
    flipped = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]
    with pytest.raises(CryptoError):
        box.decrypt_text("vault", replace(sealed, ciphertext=flipped), "db.url")
    with pytest.raises(CryptoError):
        box.decrypt_text("vault", replace(sealed, nonce=b"\x00" * 12), "db.url")
    with pytest.raises(CryptoError):
        box.decrypt_text("vault", replace(sealed, ciphertext=sealed.ciphertext[:-1]), "db.url")


def test_cada_uso_tiene_su_propia_clave(box: SecretBox) -> None:
    sealed = box.encrypt_text("vault", SECRET, "x")
    with pytest.raises(CryptoError):
        box.decrypt_text("agent-credentials", sealed, "x")
    with pytest.raises(CryptoError):
        box.decrypt_text("mfa", sealed, "x")


def test_otra_clave_maestra_falla(box: SecretBox) -> None:
    sealed = box.encrypt_text("vault", SECRET, "x")
    other = SecretBox.from_base64(generate_master_key())
    with pytest.raises(CryptoError):
        other.decrypt_text("vault", sealed, "x")


def test_la_aad_es_obligatoria(box: SecretBox) -> None:
    with pytest.raises(CryptoError, match="AAD"):
        box.encrypt("vault", b"x", b"")
    sealed = box.encrypt_text("vault", "x", "ctx")
    with pytest.raises(CryptoError, match="AAD"):
        box.decrypt("vault", sealed, b"")


def test_key_version_desconocida_y_rotacion() -> None:
    k1 = base64.b64decode(generate_master_key())
    k2 = base64.b64decode(generate_master_key())
    old = SecretBox({1: k1}, 1)
    sealed_v1 = old.encrypt_text("vault", SECRET, "x")
    rotated = SecretBox({1: k1, 2: k2}, current_version=2)
    assert rotated.decrypt_text("vault", sealed_v1, "x") == SECRET  # lee lo antiguo
    assert rotated.encrypt_text("vault", SECRET, "x").key_version == 2
    with pytest.raises(CryptoError, match="desconocida"):
        old.decrypt_text("vault", replace(sealed_v1, key_version=9), "x")


def test_validacion_de_la_clave_maestra() -> None:
    with pytest.raises(CryptoError):
        decode_master_key("no es base64!!")
    with pytest.raises(CryptoError):
        decode_master_key(base64.b64encode(b"corta").decode())
    assert len(decode_master_key(generate_master_key())) == 32
    with pytest.raises(CryptoError):
        SecretBox({1: b"x" * 31}, 1)
    with pytest.raises(CryptoError):
        SecretBox({2: b"x" * 32}, 1)


def test_el_mensaje_de_error_no_filtra_el_secreto(box: SecretBox) -> None:
    sealed = box.encrypt_text("vault", SECRET, "db.url")
    with pytest.raises(CryptoError) as exc:
        box.decrypt_text("vault", sealed, "otra")
    assert SECRET not in str(exc.value)
