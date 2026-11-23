import sqlite3
from pathlib import Path

import pytest

from app.config import Settings
from app.db.bootstrap import build_vault, open_database_from_vault
from app.db.migrate import migrate
from app.security.crypto import SecretBox, generate_master_key
from app.security.vault import Vault, VaultError

URL = "libsql://mi-bd-secreta-org.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSJ9.token-super-secreto"


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path / "data" / "vault.db", SecretBox.from_base64(generate_master_key()))


def test_set_get_has(vault: Vault) -> None:
    assert not vault.has("db.url")
    assert vault.get_secret("db.url") is None
    vault.set_secret("db.url", URL, updated_by="u1")
    vault.set_secret("db.auth_token", TOKEN)
    assert vault.has("db.url")
    assert vault.get_secret("db.url") == URL
    assert vault.get_secret("db.auth_token") == TOKEN
    vault.set_secret("db.url", "file:otra.db")  # reemplaza
    assert vault.get_secret("db.url") == "file:otra.db"


def test_en_claro_no_aparece_en_el_archivo_ni_en_sqlite(vault: Vault) -> None:
    vault.set_secret("db.url", URL)
    vault.set_secret("db.auth_token", TOKEN)
    vault.close()
    raw = vault.path.read_bytes()
    assert URL.encode() not in raw
    assert TOKEN.encode() not in raw
    assert b"turso.io" not in raw
    conn = sqlite3.connect(vault.path)
    dump = "\n".join(conn.iterdump())
    rows = conn.execute("SELECT name, ciphertext, nonce FROM secrets").fetchall()
    conn.close()
    assert "turso.io" not in dump
    assert TOKEN not in dump
    assert {r[0] for r in rows} == {"db.url", "db.auth_token"}
    assert all(isinstance(r[1], bytes) and r[1] != URL.encode() for r in rows)


def test_nombres_no_permitidos(vault: Vault) -> None:
    with pytest.raises(VaultError):
        vault.set_secret("otro", "x")  # type: ignore[arg-type]
    with pytest.raises(VaultError):
        vault.get_secret("otro")  # type: ignore[arg-type]


def test_copiar_el_cifrado_de_un_secreto_a_otro_falla(vault: Vault) -> None:
    vault.set_secret("db.url", URL)
    vault.set_secret("db.auth_token", TOKEN)
    conn = sqlite3.connect(vault.path)
    conn.execute(
        "UPDATE secrets SET ciphertext = (SELECT ciphertext FROM secrets WHERE name='db.url'),"
        " nonce = (SELECT nonce FROM secrets WHERE name='db.url') WHERE name='db.auth_token'"
    )
    conn.commit()
    conn.close()
    with pytest.raises(VaultError, match="descifrar"):
        vault.get_secret("db.auth_token")


def test_con_otra_clave_maestra_no_se_abre(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    Vault(path, SecretBox.from_base64(generate_master_key())).set_secret("db.url", URL)
    other = Vault(path, SecretBox.from_base64(generate_master_key()))
    with pytest.raises(VaultError):
        other.get_secret("db.url")


def test_la_api_se_conecta_con_los_datos_de_la_boveda(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_master_key=generate_master_key(),
        vault_path=str(tmp_path / "d" / "vault.db"),
    )  # type: ignore[call-arg]
    vault = build_vault(settings)
    assert open_database_from_vault(vault) is None  # sin URL: modo SETUP
    vault.set_secret("db.url", "file:" + (tmp_path / "main.db").as_posix())
    db = open_database_from_vault(vault)
    assert db is not None
    assert migrate(db).applied
    assert db.fetch_one("SELECT COUNT(*) AS n FROM agents") == {"n": 0}
    db.close()


def test_sin_clave_maestra_el_error_es_claro() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    with pytest.raises(VaultError, match="APP_MASTER_KEY"):
        build_vault(settings)
