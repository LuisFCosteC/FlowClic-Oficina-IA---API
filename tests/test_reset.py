from pathlib import Path

import pytest

from app.config import Settings
from app.db.bootstrap import build_vault
from app.db.database import connect_database
from app.db.reset import ResetRefused, local_path, main, reset_database
from app.security.crypto import generate_master_key


def agent_count(url: str) -> int:
    db = connect_database(url)
    try:
        row = db.fetch_one("SELECT COUNT(*) AS n FROM agents")
        return int(row["n"]) if row else -1
    finally:
        db.close()


def test_reset_deja_la_bd_vacia_por_defecto_y_con_demo_trae_ejemplos(tmp_path: Path) -> None:
    url = "file:" + (tmp_path / "local.db").as_posix()
    reset_database(url)
    assert agent_count(url) == 0
    reset_database(url, demo=True)
    assert agent_count(url) == 4


def test_reset_borra_y_recrea_la_bd_local(tmp_path: Path) -> None:
    url = "file:" + (tmp_path / "local.db").as_posix()
    reset_database(url, demo=True)
    assert agent_count(url) == 4
    db = connect_database(url)
    db.execute("DELETE FROM agents WHERE id = 'raj'")
    db.execute(
        "INSERT INTO project_memory (id, kind, title, created_at, updated_at)"
        " VALUES ('x', 'NOTE', 'extra', 'a', 'a')"
    )
    db.close()
    reset_database(url, demo=True)  # vuelve al estado inicial
    assert agent_count(url) == 4


def test_con_url_remota_se_niega_sin_borrar_nada(tmp_path: Path) -> None:
    for url in ("libsql://x.turso.io", "https://x.turso.io", "postgres://x"):
        with pytest.raises(ResetRefused):
            local_path(url)
        with pytest.raises(ResetRefused):
            reset_database(url)


def test_cli_con_libsql_en_la_boveda_termina_sin_borrar_y_con_mensaje(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key = generate_master_key()
    monkeypatch.setenv("APP_MASTER_KEY", key)
    vault = build_vault(Settings(_env_file=None, app_master_key=key))  # type: ignore[call-arg]
    vault.set_secret("db.url", "libsql://secreta-org.turso.io")
    vault.close()
    sentinel = tmp_path / "local.db"
    sentinel.write_text("no me borres")
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "solo funciona con bases locales" in err
    assert "secreta-org" not in err  # no se imprime la URL
    assert sentinel.read_text() == "no me borres"


def test_cli_con_bd_local_de_la_boveda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = generate_master_key()
    monkeypatch.setenv("APP_MASTER_KEY", key)
    url = "file:" + (tmp_path / "local.db").as_posix()
    vault = build_vault(Settings(_env_file=None, app_master_key=key))  # type: ignore[call-arg]
    vault.set_secret("db.url", url)
    vault.close()
    assert main([]) == 0
    assert agent_count(url) == 0  # vacia por defecto
    assert main(["--demo"]) == 0
    assert agent_count(url) == 4
