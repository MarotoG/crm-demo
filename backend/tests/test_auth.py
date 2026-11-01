"""Login y sesión (T08) contra PostgreSQL real (crm_demo_test, ver conftest.py)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.auth_routes
from app.auth import SESSION_COOKIE, SESSION_DURATION, create_session, hash_token
from app.main import app as fastapi_app
from app.models import Role, User, UserSession
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
MENSAJE_GENERICO = {"detail": "Email o contraseña incorrectos"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


@pytest.fixture
def usuario(db) -> User:
    user = User(email="recepcion@prueba.example.com", password_hash=hash_password(PASSWORD), role=Role.RECEPTION)
    db.add(user)
    db.flush()
    return user


def login(client, email="recepcion@prueba.example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- Login -----------------------------------------------------------------


def test_login_correcto_devuelve_usuario_sin_hash_y_cookie_segura(client, usuario):
    response = login(client)

    assert response.status_code == 200
    assert response.json() == {"id": usuario.id, "email": usuario.email, "role": "reception"}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert f"Max-Age={int(SESSION_DURATION.total_seconds())}" in cookie
    assert "Secure" not in cookie  # el .env de desarrollo usa CRM_ENV=development


def test_cookie_secure_fuera_de_desarrollo(client, usuario, monkeypatch):
    monkeypatch.setattr(app.auth_routes, "get_settings", lambda: SimpleNamespace(env="production"))

    assert "Secure" in login(client).headers["set-cookie"]


def test_login_normaliza_el_email(client, usuario):
    assert login(client, email="  RECEPCION@Prueba.Example.com ").status_code == 200


@pytest.mark.parametrize(
    "email, password",
    [
        ("recepcion@prueba.example.com", "otra-contraseña-larga"),  # contraseña errónea
        ("nadie@prueba.example.com", PASSWORD),  # email inexistente
        ("recepcion@prueba.example.com", PASSWORD.upper()),  # distingue mayúsculas
    ],
)
def test_login_fallido_mismo_mensaje_y_sin_cookie(client, usuario, email, password):
    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert response.json() == MENSAJE_GENERICO
    assert "set-cookie" not in response.headers


def test_cuenta_desactivada_no_entra_y_no_se_distingue(client, usuario, db):
    usuario.active = False
    db.flush()

    response = login(client)

    assert response.status_code == 401
    assert response.json() == MENSAJE_GENERICO


@pytest.mark.parametrize(
    "body",
    [
        {"email": "", "password": PASSWORD},
        {"email": "a@b.example.com", "password": ""},
        {"email": "a@b.example.com", "password": "x" * 1025},  # no se calcula Argon2id sobre textos enormes
        {"email": "a@b.example.com"},
    ],
)
def test_datos_de_login_invalidos_422(client, db, body):
    assert client.post("/api/auth/login", json=body).status_code == 422


def test_el_token_no_se_guarda_en_claro(client, usuario, db):
    token = login(client).cookies[SESSION_COOKIE]

    sesion = db.scalar(select(UserSession).where(UserSession.user_id == usuario.id))
    assert sesion.token_hash == hash_token(token)
    assert token not in sesion.token_hash
    assert sesion.revoked_at is None
    assert sesion.expires_at - sesion.created_at == pytest.approx(SESSION_DURATION, abs=timedelta(seconds=5))


def test_cada_login_crea_una_sesion_distinta(client, usuario, db):
    token_1 = login(client).cookies[SESSION_COOKIE]
    token_2 = login(client).cookies[SESSION_COOKIE]

    assert token_1 != token_2
    assert db.scalar(select(func.count()).select_from(UserSession)) == 2


# --- /api/auth/me ----------------------------------------------------------


def test_me_sin_cookie_401(client, db):
    assert client.get("/api/auth/me").status_code == 401


def test_me_con_sesion_valida(client, usuario):
    login(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == usuario.email


def test_me_con_token_inventado_401(client, usuario):
    login(client)
    client.cookies.set(SESSION_COOKIE, "token-inventado")

    assert client.get("/api/auth/me").status_code == 401


def test_me_con_el_hash_como_token_401(client, usuario, db):
    # Quien robe la tabla sessions obtiene hashes; usarlos como cookie no sirve.
    token = login(client).cookies[SESSION_COOKIE]
    client.cookies.set(SESSION_COOKIE, hash_token(token))

    assert client.get("/api/auth/me").status_code == 401


def test_me_con_sesion_caducada_401(client, usuario, db):
    token = create_session(db, usuario, now=datetime.now(UTC) - SESSION_DURATION - timedelta(seconds=1))
    db.flush()
    client.cookies.set(SESSION_COOKIE, token)

    assert client.get("/api/auth/me").status_code == 401


def test_me_con_sesion_revocada_401(client, usuario, db):
    token = login(client).cookies[SESSION_COOKIE]
    db.scalar(select(UserSession)).revoked_at = datetime.now(UTC)
    db.flush()
    client.cookies.set(SESSION_COOKIE, token)

    assert client.get("/api/auth/me").status_code == 401


def test_me_si_desactivan_la_cuenta_tras_el_login_401(client, usuario, db):
    login(client)
    usuario.active = False
    db.flush()

    assert client.get("/api/auth/me").status_code == 401


def test_borrar_el_usuario_borra_sus_sesiones(client, usuario, db):
    login(client)
    db.delete(usuario)
    db.flush()

    assert db.scalar(select(func.count()).select_from(UserSession)) == 0


# --- Límite de intentos ----------------------------------------------------


def test_tras_5_fallos_responde_429_incluso_con_la_contraseña_correcta(client, usuario):
    for _ in range(5):
        assert login(client, password="mal-mal-mal-mal").status_code == 401

    response = login(client)

    assert response.status_code == 429
    assert "set-cookie" not in response.headers


def test_el_bloqueo_no_afecta_a_otro_email(client, usuario, db):
    db.add(User(email="otro@prueba.example.com", password_hash=hash_password(PASSWORD), role=Role.PROFESSIONAL))
    db.flush()
    for _ in range(5):
        login(client, password="mal-mal-mal-mal")

    assert login(client, email="otro@prueba.example.com").status_code == 200


def test_el_bloqueo_cuenta_el_email_normalizado(client, usuario):
    # Cambiar mayúsculas o añadir espacios no da 5 intentos más.
    for variante in ["recepcion@prueba.example.com", "RECEPCION@prueba.example.com", " recepcion@prueba.example.com",
                     "Recepcion@Prueba.example.com", "recepcion@PRUEBA.example.com"]:
        login(client, email=variante, password="mal-mal-mal-mal")

    assert login(client).status_code == 429


def test_un_login_correcto_pone_el_contador_a_cero(client, usuario):
    for _ in range(4):
        login(client, password="mal-mal-mal-mal")
    assert login(client).status_code == 200
    for _ in range(4):
        login(client, password="mal-mal-mal-mal")

    assert login(client).status_code == 200
