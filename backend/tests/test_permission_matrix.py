"""Revisión de permisos (T27): qué rol puede usar cada ruta de la API, escrito en una sola tabla.

Es la matriz de las especificaciones (sección 5) llevada a rutas. Recorre el OpenAPI: una ruta nueva
sin fila aquí hace fallar la prueba, así que nadie añade una sin decidir quién la usa.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.models import Role
from test_follow_ups import PASSWORD, cuenta
from test_route_protection import PUBLICAS, rutas_de_la_api

A, R, P, C = Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL, Role.CLIENT
PERSONAL = {A, R, P}
OFICINA = {A, R}

MATRIZ: dict[tuple[str, str], set[Role]] = {
    ("GET", "/api/auth/me"): {A, R, P, C},
    ("GET", "/api/users"): {A},
    ("GET", "/api/audit-events"): {A},
    ("GET", "/api/contacts"): OFICINA,
    ("POST", "/api/contacts"): OFICINA,
    ("GET", "/api/contacts/owners"): OFICINA,
    ("GET", "/api/contacts/{contact_id}"): PERSONAL,
    ("PUT", "/api/contacts/{contact_id}"): OFICINA,
    ("PUT", "/api/contacts/{contact_id}/status"): OFICINA,
    ("GET", "/api/contacts/{contact_id}/portal"): OFICINA,
    ("POST", "/api/contacts/{contact_id}/portal-invitation"): OFICINA,
    ("GET", "/api/contacts/{contact_id}/follow-ups"): PERSONAL,
    ("POST", "/api/contacts/{contact_id}/follow-ups"): OFICINA,
    ("GET", "/api/contacts/{contact_id}/follow-up-assignees"): OFICINA,
    ("GET", "/api/services"): PERSONAL,
    ("POST", "/api/services"): OFICINA,
    ("GET", "/api/services/staff"): OFICINA,
    ("PUT", "/api/services/{service_id}"): OFICINA,
    ("GET", "/api/appointments"): PERSONAL,
    ("POST", "/api/appointments"): OFICINA,
    ("GET", "/api/appointments/by-contact/{contact_id}"): PERSONAL,
    ("PUT", "/api/appointments/{appointment_id}"): OFICINA,
    ("POST", "/api/appointments/{appointment_id}/cancel"): OFICINA,
    ("POST", "/api/appointments/{appointment_id}/attendance"): PERSONAL,
    ("PUT", "/api/appointments/{appointment_id}/note"): OFICINA,
    ("GET", "/api/follow-ups"): PERSONAL,
    ("GET", "/api/follow-ups/summary"): PERSONAL,
    ("POST", "/api/follow-ups/{task_id}/complete"): PERSONAL,
    ("POST", "/api/follow-ups/{task_id}/reopen"): PERSONAL,
    ("PUT", "/api/follow-ups/{task_id}"): OFICINA,
    ("GET", "/api/portal/appointments"): {C},
}


def test_toda_ruta_tiene_su_fila_en_la_matriz():
    assert set(MATRIZ) == rutas_de_la_api() - PUBLICAS


CASOS = [
    pytest.param(method, path, rol, rol in permitidos, id=f"{method} {path} {rol.value}")
    for (method, path), permitidos in sorted(MATRIZ.items(), key=lambda item: item[0])
    for rol in Role
]


@pytest.mark.parametrize("method, path, rol, permitido", CASOS)
def test_cada_rol_solo_entra_en_sus_rutas(db, method, path, rol, permitido):
    usuario = cuenta(db, "matriz", rol)
    client = TestClient(fastapi_app)
    login = client.post("/api/auth/login", json={"email": usuario.email, "password": PASSWORD})
    assert login.status_code == 200
    # Con token CSRF: lo que se prueba es el rol. El id no existe y el cuerpo va vacío, así que
    # quien pasa el permiso recibe 200, 404 o 422, pero nunca cambia datos.
    url = re.sub(r"\{[^}]+\}", "999999", path)

    response = client.request(method, url, json={}, headers={"X-CSRF-Token": login.json()["csrf_token"]})

    if permitido:
        assert response.status_code not in (401, 403), f"{rol.value} debería poder usar {method} {path}"
    else:
        assert response.status_code == 403, f"{rol.value} no debería poder usar {method} {path}"
        assert response.json() == {"detail": "Permiso denegado"}
