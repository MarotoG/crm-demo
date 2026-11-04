"""Protección por defecto: toda ruta de la API exige sesión salvo una lista explícita (T09).

Recorre el OpenAPI, así que una ruta nueva que se quede sin proteger hace fallar
esta prueba aunque nadie se acuerde de escribirle una.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.models import Role, User
from app.security import hash_password

PUBLICAS = {
    ("GET", "/api/health"),
    ("GET", "/api/health/db"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),  # sin sesión válida no hay nada que cerrar (204)
    ("POST", "/api/portal-invitations/check"),  # autoriza el token del enlace (T21)
    ("POST", "/api/portal-invitations/accept"),
}


def rutas_de_la_api() -> set[tuple[str, str]]:
    paths = fastapi_app.openapi()["paths"]
    return {(method.upper(), path) for path, operations in paths.items() for method in operations}


def test_la_lista_de_publicas_existe_y_no_se_queda_vieja():
    assert PUBLICAS <= rutas_de_la_api()


@pytest.mark.parametrize("method, path", sorted(rutas_de_la_api() - PUBLICAS))
def test_toda_ruta_no_publica_responde_401_sin_sesion(db, method, path):
    url = re.sub(r"\{[^}]+\}", "1", path)  # parámetros de ruta futuros, p. ej. /api/contacts/{id}

    response = TestClient(fastapi_app).request(method, url)

    assert response.status_code == 401, f"{method} {path} no exige sesión"


def test_toda_ruta_que_cambia_datos_exige_csrf(db):
    """Con sesión válida pero sin X-CSRF-Token, toda ruta no GET (salvo las públicas) da 403."""
    db.add(User(email="csrf-admin@prueba.example.com", password_hash=hash_password("contraseña-larga"), role=Role.ADMIN))
    db.flush()
    client = TestClient(fastapi_app)
    login = client.post("/api/auth/login", json={"email": "csrf-admin@prueba.example.com", "password": "contraseña-larga"})
    assert login.status_code == 200

    rutas = sorted((m, p) for m, p in rutas_de_la_api() - PUBLICAS if m != "GET")
    assert rutas, "no hay rutas que cambien datos: esta prueba no comprobaría nada"
    for method, path in rutas:
        response = client.request(method, re.sub(r"\{[^}]+\}", "1", path), json={})
        assert response.status_code == 403, f"{method} {path} no exige el token CSRF"
        assert response.json() == {"detail": "Token CSRF ausente o no válido"}
