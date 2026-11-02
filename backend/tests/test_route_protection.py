"""Protección por defecto: toda ruta de la API exige sesión salvo una lista explícita (T09).

Recorre el OpenAPI, así que una ruta nueva que se quede sin proteger hace fallar
esta prueba aunque nadie se acuerde de escribirle una.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app

PUBLICAS = {
    ("GET", "/api/health"),
    ("GET", "/api/health/db"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),  # sin sesión válida no hay nada que cerrar (204)
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
