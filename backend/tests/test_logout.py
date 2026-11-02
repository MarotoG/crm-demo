"""Logout y protección CSRF contra PostgreSQL real (T09, ver conftest.py)."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import CSRF_HEADER, SESSION_COOKIE, csrf_token_for, hash_token, require_csrf
from app.db import get_db
from app.main import app as fastapi_app
from app.models import Role, User, UserSession
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
EMAIL = "recepcion@prueba.example.com"


@pytest.fixture
def usuario(db) -> User:
    user = User(email=EMAIL, password_hash=hash_password(PASSWORD), role=Role.RECEPTION)
    db.add(user)
    db.flush()
    return user


def nuevo_cliente_con_sesion() -> tuple[TestClient, str]:
    """Un navegador distinto con su propia sesión; devuelve el cliente y su token CSRF."""
    client = TestClient(fastapi_app)
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def logout(client, csrf=None):
    headers = {} if csrf is None else {CSRF_HEADER: csrf}
    return client.post("/api/auth/logout", headers=headers)


def test_logout_revoca_la_sesion_y_borra_la_cookie(usuario, db):
    client, csrf = nuevo_cliente_con_sesion()
    token = client.cookies[SESSION_COOKIE]

    response = logout(client, csrf)

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert SESSION_COOKIE not in client.cookies
    assert db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token))).revoked_at is not None
    assert client.get("/api/auth/me").status_code == 401


def test_la_cookie_antigua_no_vuelve_a_valer_tras_el_logout(usuario):
    client, csrf = nuevo_cliente_con_sesion()
    token = client.cookies[SESSION_COOKIE]
    logout(client, csrf)

    client.cookies.set(SESSION_COOKIE, token)  # quien la hubiera copiado antes

    assert client.get("/api/auth/me").status_code == 401


def test_logout_solo_cierra_la_sesion_de_ese_dispositivo(usuario):
    pc, csrf_pc = nuevo_cliente_con_sesion()
    movil, _ = nuevo_cliente_con_sesion()

    assert logout(pc, csrf_pc).status_code == 204

    assert movil.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("motivo", ["sin cabecera", "vacío", "de otra sesión", "hash de la BD", "no ASCII"])
def test_logout_sin_token_csrf_valido_403_y_la_sesion_sigue(usuario, motivo):
    client, _ = nuevo_cliente_con_sesion()
    _, csrf_de_otra = nuevo_cliente_con_sesion()
    token = client.cookies[SESSION_COOKIE]
    enviado = {
        "sin cabecera": None,
        "vacío": "",
        "de otra sesión": csrf_de_otra,
        "hash de la BD": hash_token(token),
        "no ASCII": "ñandú".encode("latin-1"),  # no debe provocar un 500
    }[motivo]

    response = logout(client, enviado)

    assert response.status_code == 403
    assert response.json() == {"detail": "Token CSRF ausente o no válido"}
    assert "set-cookie" not in response.headers
    assert client.get("/api/auth/me").status_code == 200


def test_logout_sin_cookie_204(db):
    response = TestClient(fastapi_app).post("/api/auth/logout")

    assert response.status_code == 204


def test_logout_con_sesion_que_ya_no_vale_204_y_borra_la_cookie(db):
    client = TestClient(fastapi_app)
    client.cookies.set(SESSION_COOKIE, "token-inventado")

    response = logout(client)

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_me_devuelve_el_mismo_token_csrf_que_el_login(usuario):
    client, csrf = nuevo_cliente_con_sesion()

    datos = client.get("/api/auth/me").json()

    assert datos["csrf_token"] == csrf == csrf_token_for(client.cookies[SESSION_COOKIE])
    assert "password_hash" not in datos


# --- require_csrf en una ruta cualquiera que cambie datos ----------------------


@pytest.fixture
def app_con_ruta_de_cambio(db):
    mini = FastAPI()

    @mini.post("/cambio")
    def cambio(user: User = Depends(require_csrf)) -> dict[str, int]:
        return {"user_id": user.id}

    mini.dependency_overrides[get_db] = fastapi_app.dependency_overrides[get_db]  # la BD de pruebas
    return mini


def test_require_csrf_401_sin_sesion(app_con_ruta_de_cambio):
    assert TestClient(app_con_ruta_de_cambio).post("/cambio").status_code == 401


def test_require_csrf_403_sin_token_y_200_con_token(app_con_ruta_de_cambio, usuario):
    navegador, csrf = nuevo_cliente_con_sesion()
    client = TestClient(app_con_ruta_de_cambio)
    client.cookies.set(SESSION_COOKIE, navegador.cookies[SESSION_COOKIE])

    assert client.post("/cambio").status_code == 403
    assert client.post("/cambio", headers={CSRF_HEADER: "falso"}).status_code == 403
    response = client.post("/cambio", headers={CSRF_HEADER: csrf})
    assert response.status_code == 200
    assert response.json() == {"user_id": usuario.id}
