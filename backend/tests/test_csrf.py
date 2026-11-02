"""Token CSRF y CRM_SECRET_KEY sin BD (T09)."""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

import app.auth
from app.auth import csrf_matches, csrf_token_for, hash_token
from app.config import SECRET_KEY_PLACEHOLDER, Settings

CLAVE = b"k" * 32


def test_el_token_depende_de_la_sesion_y_de_la_clave():
    token = csrf_token_for("sesion-a", CLAVE)

    assert token == csrf_token_for("sesion-a", CLAVE)  # se puede recalcular sin guardarlo
    assert token != csrf_token_for("sesion-b", CLAVE)
    assert token != csrf_token_for("sesion-a", b"otra" * 8)
    assert len(token) == 64


def test_el_token_no_es_el_hash_guardado_en_bd():
    # Quien lea la tabla sessions ve hash_token(...): no debe servirle como token CSRF.
    assert csrf_token_for("sesion-a", CLAVE) != hash_token("sesion-a")


@pytest.fixture
def clave_configurada(monkeypatch):
    monkeypatch.setattr(app.auth, "get_settings", lambda: SimpleNamespace(secret_key=SecretStr(CLAVE.decode())))


@pytest.mark.parametrize("enviado", [None, "", "x" * 64, "ñandú", csrf_token_for("otra-sesion", CLAVE)])
def test_csrf_matches_rechaza_tokens_ausentes_o_ajenos(clave_configurada, enviado):
    assert csrf_matches("sesion-a", enviado) is False


def test_csrf_matches_acepta_el_token_de_su_sesion(clave_configurada):
    assert csrf_matches("sesion-a", csrf_token_for("sesion-a", CLAVE)) is True


def test_sin_clave_falla_con_mensaje_claro(monkeypatch):
    monkeypatch.setattr(app.auth, "get_settings", lambda: SimpleNamespace(secret_key=None))

    with pytest.raises(RuntimeError, match="CRM_SECRET_KEY"):
        csrf_token_for("sesion-a")


@pytest.mark.parametrize(
    "valor, motivo",
    [(SECRET_KEY_PLACEHOLDER, "valor de ejemplo"), ("corta-de-31-caracteres-xxxxxxxx", "al menos 32")],
)
def test_la_clave_de_ejemplo_o_corta_se_rechaza_sin_mostrarla(valor, motivo):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, db_password="x", secret_key=valor)

    assert motivo in str(error.value)
    assert valor not in str(error.value)


def test_una_clave_de_32_caracteres_se_acepta():
    settings = Settings(_env_file=None, db_password="x", secret_key="a" * 32)

    assert settings.secret_key.get_secret_value() == "a" * 32
    assert "a" * 32 not in repr(settings)
