"""Purga de sesiones caducadas hace más de 30 días (T09)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import SESSION_DURATION, SESSION_RETENTION, create_session, hash_token, purge_expired_sessions
from app.main import app as fastapi_app
from app.models import Role, User, UserSession
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
AHORA = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def usuario(db) -> User:
    user = User(email="recepcion@prueba.example.com", password_hash=hash_password(PASSWORD), role=Role.RECEPTION)
    db.add(user)
    db.flush()
    return user


def sesion_que_caduco_hace(db, usuario, tiempo: timedelta, revocada: bool = False) -> str:
    """Crea una sesión cuyo expires_at es AHORA - tiempo; devuelve su token_hash."""
    token = create_session(db, usuario, now=AHORA - tiempo - SESSION_DURATION)
    db.flush()
    sesion = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if revocada:
        sesion.revoked_at = sesion.expires_at - SESSION_DURATION
        db.flush()
    return sesion.token_hash


def hashes(db) -> set[str]:
    return set(db.scalars(select(UserSession.token_hash)))


def test_borra_solo_lo_caducado_hace_mas_de_30_dias(db, usuario):
    vieja = sesion_que_caduco_hace(db, usuario, SESSION_RETENTION + timedelta(seconds=1))
    vieja_revocada = sesion_que_caduco_hace(db, usuario, timedelta(days=45), revocada=True)
    limite = sesion_que_caduco_hace(db, usuario, SESSION_RETENTION)  # justo 30 días: se conserva
    reciente = sesion_que_caduco_hace(db, usuario, timedelta(days=2))
    revocada_reciente = sesion_que_caduco_hace(db, usuario, timedelta(days=1), revocada=True)
    vigente = sesion_que_caduco_hace(db, usuario, -timedelta(hours=1))

    assert purge_expired_sessions(db, now=AHORA) == 2

    assert hashes(db) == {limite, reciente, revocada_reciente, vigente}
    assert vieja not in hashes(db) and vieja_revocada not in hashes(db)


def test_sin_nada_que_borrar_devuelve_0(db, usuario):
    sesion_que_caduco_hace(db, usuario, timedelta(days=1))

    assert purge_expired_sessions(db, now=AHORA) == 0


def test_cada_login_purga_automaticamente(db, usuario):
    # Con el reloj real: una sesión que caducó hace 31 días desaparece al hacer login.
    token = create_session(db, usuario, now=datetime.now(UTC) - timedelta(days=31) - SESSION_DURATION)
    db.flush()

    response = TestClient(fastapi_app).post(
        "/api/auth/login", json={"email": "recepcion@prueba.example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert hash_token(token) not in hashes(db)
    assert len(hashes(db)) == 1  # solo la sesión nueva
