"""Pruebas de /api/health/db sin PostgreSQL: se sustituye check_database.

La conexión real se comprueba a mano con la BD en Docker (ver README).
"""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.main
from app.main import app as fastapi_app

client = TestClient(fastapi_app)


def test_health_db_ok_si_la_bd_responde(monkeypatch):
    monkeypatch.setattr(app.main, "check_database", lambda: None)

    response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_db_503_sin_detalles_si_la_bd_falla(monkeypatch):
    def bd_caida():
        raise OperationalError("SELECT 1", {}, Exception("connection refused password=secreto"))

    monkeypatch.setattr(app.main, "check_database", bd_caida)

    response = client.get("/api/health/db")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert "secreto" not in response.text


def test_health_sigue_ok_aunque_la_bd_falle(monkeypatch):
    def bd_caida():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(app.main, "check_database", bd_caida)

    assert client.get("/api/health").status_code == 200
