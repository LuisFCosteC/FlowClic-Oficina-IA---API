import subprocess
import sys
from pathlib import Path

import pytest

from app.security import envfile, fileperms, vault
from app.security.crypto import SecretBox, generate_master_key
from app.security.envfile import atomic_write
from app.security.vault import Vault, VaultError

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="icacls solo en Windows")


def no_temporales(folder: Path) -> list[Path]:
    return [p for p in folder.iterdir() if p.name.endswith(".tmp")]


# --- camino de fallo: falla en cerrado --------------------------------------------------------


def test_atomic_write_si_no_se_puede_restringir_no_toca_el_env_ni_deja_temporales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("PORT=4000\n", encoding="utf-8")
    monkeypatch.setattr(envfile, "restrict_to_owner", lambda _p: False)
    with pytest.raises(PermissionError):
        atomic_write(env, b"APP_MASTER_KEY=secreto-que-no-debe-escribirse\n")
    assert env.read_text(encoding="utf-8") == "PORT=4000\n"
    assert no_temporales(tmp_path) == []


def test_atomic_write_no_escribe_datos_antes_de_restringir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, int] = {}

    def spy(p: Path) -> bool:
        seen["size_al_restringir"] = p.stat().st_size
        return True

    monkeypatch.setattr(envfile, "restrict_to_owner", spy)
    atomic_write(tmp_path / ".env", b"APP_MASTER_KEY=abc\n")
    assert seen["size_al_restringir"] == 0  # el temporal estaba vacío al restringirlo
    assert (tmp_path / ".env").read_bytes() == b"APP_MASTER_KEY=abc\n"


def test_atomic_write_ok_deja_solo_el_archivo(tmp_path: Path) -> None:
    atomic_write(tmp_path / ".env", b"X=1\n")
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_boveda_si_no_se_puede_restringir_no_se_crea_el_archivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vault, "restrict_to_owner", lambda _p: False)
    box = SecretBox.from_base64(generate_master_key())
    path = tmp_path / "data" / "vault.db"
    with pytest.raises(VaultError, match="permisos"):
        Vault(path, box)
    assert not path.exists()


def test_boveda_se_restringe_antes_de_guardar_secretos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, int] = {}

    def spy(p: Path) -> bool:
        seen["size"] = p.stat().st_size
        return True

    monkeypatch.setattr(vault, "restrict_to_owner", spy)
    v = Vault(tmp_path / "vault.db", SecretBox.from_base64(generate_master_key()))
    assert seen["size"] == 0
    v.close()


# --- Windows: SID e icacls ---------------------------------------------------------------------


@windows_only
def test_en_windows_se_concede_al_sid_y_no_al_nombre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return real_run(args, **kw)  # type: ignore[call-overload, no-any-return]

    monkeypatch.setattr(fileperms.subprocess, "run", spy)
    fileperms._windows_identity.cache_clear()
    f = tmp_path / "x.txt"
    f.write_text("x")
    assert fileperms.restrict_to_owner(f) is True
    icacls = next(c for c in calls if c[0] == "icacls")
    grant = icacls[icacls.index("/grant:r") + 1]
    assert grant.startswith("*S-1-5-") and grant.endswith(":F")
    assert "/inheritance:r" in icacls


@windows_only
def test_en_windows_restringido_queda_un_unico_permiso_y_no_es_mas_amplio(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    atomic_write(f, b"APP_MASTER_KEY=abc\n")
    out = subprocess.run(  # noqa: S603
        ["icacls", str(f)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert len([ln for ln in out.splitlines() if ":(" in ln]) == 1, out
    assert fileperms.broader_than_owner(f) is False


@windows_only
def test_en_windows_un_archivo_con_permisos_heredados_si_es_mas_amplio(tmp_path: Path) -> None:
    f = tmp_path / "heredado.txt"
    f.write_text("x")  # hereda la ACL de la carpeta (SYSTEM, Administradores, ...)
    assert fileperms.broader_than_owner(f) is True


@windows_only
def test_en_windows_si_icacls_falla_se_considera_amplio_y_no_restringido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x")

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("icacls no disponible")

    monkeypatch.setattr(fileperms.subprocess, "run", boom)
    fileperms._windows_identity.cache_clear()
    assert fileperms.restrict_to_owner(f) is False
    assert fileperms.broader_than_owner(f) is True
    fileperms._windows_identity.cache_clear()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod solo en POSIX")
def test_en_posix_chmod_600(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("x")
    f.chmod(0o644)
    assert fileperms.broader_than_owner(f) is True
    assert fileperms.restrict_to_owner(f) is True
    assert fileperms.broader_than_owner(f) is False
