"""Pruebas de /api/health/db sin PostgreSQL: se inyecta otra comprobación con Depends.

La conexión real se comprueba a mano con la BD en Docker (ver README).
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_database_check, get_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def comprobacion() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_database_check, None)


def usar_comprobacion(funcion) -> None:
    app.dependency_overrides[get_database_check] = lambda: funcion


def bd_caida():
    raise OperationalError("SELECT 1", {}, Exception("connection refused password=secreto"))


def test_health_db_ok_si_la_bd_responde(comprobacion):
    usar_comprobacion(lambda: None)

    response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_db_503_sin_detalles_si_la_bd_falla(comprobacion):
    usar_comprobacion(bd_caida)

    response = client.get("/api/health/db")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert "secreto" not in response.text


def test_health_db_503_tambien_si_falta_la_configuracion(comprobacion):
    # Sin .env, leer la configuración falla dentro de la comprobación: debe ser 503, no 500.
    def sin_configuracion():
        raise ValueError("db_password Field required")

    usar_comprobacion(sin_configuracion)

    assert client.get("/api/health/db").status_code == 503


def test_health_no_usa_la_comprobacion_de_bd(comprobacion):
    llamadas = []
    usar_comprobacion(lambda: llamadas.append(1) or bd_caida())

    assert client.get("/api/health").status_code == 200
    assert llamadas == []


def test_rutas_con_bd_responden_503_sin_detalles_si_la_bd_cae():
    class SesionCaida:
        def scalar(self, *args, **kwargs):
            bd_caida()

    app.dependency_overrides[get_db] = lambda: SesionCaida()
    try:
        response = TestClient(app).post("/api/auth/login", json={"email": "a@b.example.com", "password": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Servicio no disponible"}
    assert "secreto" not in response.text
