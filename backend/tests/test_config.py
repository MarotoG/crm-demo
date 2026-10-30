from app.config import Settings


def test_database_url_escapa_y_oculta_la_contrasena():
    # _env_file=None: la prueba no depende del .env local.
    settings = Settings(_env_file=None, db_password="p@ss:wo/rd")

    url = settings.database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss:wo/rd"
    assert "p%40ss%3Awo%2Frd" in url.render_as_string(hide_password=False)
    assert "p@ss" not in str(url)
