"""Permisos por rol: GET /api/users solo para el administrador (T09)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.models import Role, User
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"


@pytest.fixture
def usuarios(db) -> dict[Role, User]:
    creados = {}
    for role in Role:
        user = User(email=f"{role.value}@prueba.example.com", password_hash=hash_password(PASSWORD), role=role)
        db.add(user)
        creados[role] = user
    db.flush()
    return creados


def cliente_de(role: Role) -> TestClient:
    client = TestClient(fastapi_app)
    response = client.post("/api/auth/login", json={"email": f"{role.value}@prueba.example.com", "password": PASSWORD})
    assert response.status_code == 200
    return client


def test_sin_sesion_401(db):
    assert TestClient(fastapi_app).get("/api/users").status_code == 401


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.PROFESSIONAL, Role.CLIENT])
def test_otros_roles_403_sin_datos(usuarios, role):
    response = cliente_de(role).get("/api/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "Permiso denegado"}
    assert "@prueba.example.com" not in response.text


def test_admin_ve_los_usuarios_sin_hash(usuarios):
    response = cliente_de(Role.ADMIN).get("/api/users")

    assert response.status_code == 200
    datos = response.json()
    assert [u["email"] for u in datos] == [u.email for u in sorted(usuarios.values(), key=lambda u: u.id)]
    assert set(datos[0]) == {"id", "email", "role", "active"}
    assert "argon2" not in response.text


def test_admin_desactivado_tras_el_login_401(usuarios, db):
    client = cliente_de(Role.ADMIN)
    usuarios[Role.ADMIN].active = False
    db.flush()

    assert client.get("/api/users").status_code == 401


def test_cambiar_el_rol_en_bd_tiene_efecto_en_la_siguiente_peticion(usuarios, db):
    # El rol se lee de la BD en cada petición, no se guarda en la cookie.
    client = cliente_de(Role.ADMIN)
    usuarios[Role.ADMIN].role = Role.RECEPTION
    db.flush()

    assert client.get("/api/users").status_code == 403
