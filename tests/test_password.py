import pytest

from app.security.password import (
    DEFAULT_N,
    PasswordPolicyError,
    check_policy,
    hash_password,
    verify_password,
)

PASSWORD = "una-clave-larga-y-segura-1"
FAST = {"n": 2**12}  # parámetros rápidos para tests; el formato guarda los usados


def test_el_hash_no_es_la_contrasena_y_tiene_el_formato_esperado() -> None:
    h = hash_password(PASSWORD, **FAST)
    assert PASSWORD not in h
    prefix, n, r, p, salt, digest = h.split("$")
    assert (prefix, n, r, p) == ("scrypt", "4096", "8", "1")
    assert salt and digest


def test_dos_hashes_de_la_misma_clave_son_distintos() -> None:
    assert hash_password(PASSWORD, **FAST) != hash_password(PASSWORD, **FAST)


def test_verificar_la_buena_y_la_mala() -> None:
    h = hash_password(PASSWORD, **FAST)
    assert verify_password(PASSWORD, h) is True
    assert verify_password(PASSWORD + "x", h) is False
    assert verify_password("", h) is False


def test_parametros_por_defecto_son_los_del_plan() -> None:
    assert DEFAULT_N == 2**17
    h = hash_password(PASSWORD)  # N=2^17, r=8, p=1 reales
    assert h.startswith("scrypt$131072$8$1$")
    assert verify_password(PASSWORD, h) is True


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "basura",
        "scrypt$1$2$3$x",
        "bcrypt$1$8$1$AAAA$AAAA",
        "scrypt$x$8$1$AAAA$AAAA",
        "scrypt$4096$8$1$!!!$AAAA",
    ],
)
def test_un_hash_mal_formado_devuelve_false_sin_lanzar(stored: str) -> None:
    assert verify_password(PASSWORD, stored) is False


def test_politica_minimo_12_y_maximo() -> None:
    with pytest.raises(PasswordPolicyError, match="12"):
        hash_password("corta", **FAST)
    with pytest.raises(PasswordPolicyError):
        check_policy("x" * 129)
    check_policy("x" * 12)
    check_policy("x" * 128)


def test_admite_unicode() -> None:
    h = hash_password("contraseña-ñandú-€-segura", **FAST)
    assert verify_password("contraseña-ñandú-€-segura", h) is True
    assert verify_password("contrasena-nandu-eur-segura", h) is False
