import pytest
from pydantic import ValidationError

from app.config import Settings


def test_database_url_escapa_y_oculta_la_contrasena():
    # _env_file=None: la prueba no depende del .env local.
    settings = Settings(_env_file=None, db_password="p@ss:wo/rd")

    url = settings.database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss:wo/rd"
    assert "p%40ss%3Awo%2Frd" in url.render_as_string(hide_password=False)
    assert "p@ss" not in str(url)


def test_zona_de_la_clinica_por_defecto_nueva_york():
    settings = Settings(_env_file=None, db_password="x")

    assert settings.clinic_timezone == "America/New_York"
    assert settings.clinic_zone.key == "America/New_York"


@pytest.mark.parametrize("zona", ["Nueva York", "America/Nowhere", "", "../etc/passwd"])
def test_zona_de_la_clinica_no_valida(zona):
    with pytest.raises(ValidationError, match="CRM_CLINIC_TIMEZONE debe ser una zona IANA"):
        Settings(_env_file=None, db_password="x", clinic_timezone=zona)
