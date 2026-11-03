"""Servicios contra PostgreSQL real (T15): alta, lista, edición y desactivación, personas que los
realizan y permisos por rol."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.auth import CSRF_HEADER
from app.main import app as fastapi_app
from app.models import Role, Service, ServiceStaff, User
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


def sesion_de(role: Role) -> tuple[TestClient, dict[str, str]]:
    """Cliente con sesión de ese rol y las cabeceras con su token CSRF."""
    client = TestClient(fastapi_app)
    response = client.post("/api/auth/login", json={"email": f"{role.value}@prueba.example.com", "password": PASSWORD})
    assert response.status_code == 200
    return client, {CSRF_HEADER: response.json()["csrf_token"]}


def botox(usuarios, **cambios) -> dict:
    return {"name": "Botox", "duration_minutes": 30, "staff_ids": [usuarios[Role.ADMIN].id], **cambios}


def crear(datos: dict, role: Role = Role.ADMIN):
    client, csrf = sesion_de(role)
    return client.post("/api/services", json=datos, headers=csrf)


def editar(servicio: dict, role: Role = Role.ADMIN, **cambios):
    """PUT con el servicio tal como se leyó (versión incluida) y los cambios indicados."""
    datos = {
        "name": servicio["name"],
        "duration_minutes": servicio["duration_minutes"],
        "staff_ids": [p["id"] for p in servicio["staff"]],
        "active": servicio["active"],
        "version": servicio["version"],
        **cambios,
    }
    client, csrf = sesion_de(role)
    return client.put(f"/api/services/{servicio['id']}", json=datos, headers=csrf)


def listar(role: Role = Role.ADMIN):
    client, _ = sesion_de(role)
    return client.get("/api/services")


def contar(db) -> int:
    return db.scalar(select(func.count()).select_from(Service))


def personas(db, service_id: int) -> set[int]:
    return set(db.scalars(select(ServiceStaff.user_id).where(ServiceStaff.service_id == service_id)))


def error_de(response, campo: str) -> str:
    return next(e["msg"] for e in response.json()["detail"] if e["loc"] == ["body", campo])


def cuenta(db, email: str, role: Role, active: bool = True) -> User:
    user = User(email=email, password_hash=hash_password(PASSWORD), role=role, active=active)
    db.add(user)
    db.flush()
    return user


# --- Alta y permisos --------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_crean_un_servicio_con_varias_personas(usuarios, db, role):
    equipo = [usuarios[Role.PROFESSIONAL].id, usuarios[Role.ADMIN].id, usuarios[Role.RECEPTION].id]

    response = crear(botox(usuarios, name="  Botox   (forehead) ", staff_ids=equipo), role)

    assert response.status_code == 201
    datos = response.json()
    assert datos | {"id": 0} == {
        "id": 0, "name": "Botox (forehead)", "duration_minutes": 30, "active": True, "version": 1,
        # Por email: admin@, professional@, reception@.
        "staff": [
            {"id": usuarios[r].id, "email": f"{r.value}@prueba.example.com", "role": r.value, "active": True}
            for r in (Role.ADMIN, Role.PROFESSIONAL, Role.RECEPTION)
        ],
    }
    assert personas(db, datos["id"]) == set(equipo)


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_crean_servicios(usuarios, db, role):
    response = crear(botox(usuarios), role)

    assert response.status_code == 403
    assert contar(db) == 0


def test_sin_token_csrf_403_y_no_se_guarda(usuarios, db):
    client, _ = sesion_de(Role.ADMIN)

    assert client.post("/api/services", json=botox(usuarios)).status_code == 403
    assert contar(db) == 0


def test_la_misma_persona_dos_veces_cuenta_una(usuarios, db):
    admin = usuarios[Role.ADMIN].id

    response = crear(botox(usuarios, staff_ids=[admin, admin]))

    assert response.status_code == 201
    assert [p["id"] for p in response.json()["staff"]] == [admin]


@pytest.mark.parametrize("minutos", [5, 30, 125, 240])
def test_duraciones_validas(usuarios, db, minutos):
    assert crear(botox(usuarios, duration_minutes=minutos)).status_code == 201


# --- Datos no válidos -------------------------------------------------------------

DURACION_NO_VALIDA = "La duración debe ser un múltiplo de 5 minutos, entre 5 y 240 (4 horas)"
NO_ENTERO = "La duración debe ser un número entero de minutos"


@pytest.mark.parametrize(
    "minutos, mensaje",
    [
        (0, DURACION_NO_VALIDA),
        (-5, DURACION_NO_VALIDA),
        (3, DURACION_NO_VALIDA),
        (62, DURACION_NO_VALIDA),
        (245, DURACION_NO_VALIDA),
        (600, DURACION_NO_VALIDA),
        ("60", NO_ENTERO),
        (60.0, NO_ENTERO),
        (True, NO_ENTERO),
        (None, NO_ENTERO),
    ],
)
def test_duracion_no_valida_422(usuarios, db, minutos, mensaje):
    response = crear(botox(usuarios, duration_minutes=minutos))

    assert response.status_code == 422
    assert error_de(response, "duration_minutes") == mensaje
    assert contar(db) == 0


@pytest.mark.parametrize(
    "nombre, mensaje",
    [
        ("   ", "El nombre del servicio no puede estar vacío"),
        ("Depilación", "No se permiten tildes ni caracteres especiales (á, ñ, ü…)"),
        ("Peel 30%", "El nombre solo puede tener letras, cifras, espacios y . , ' & + / ( ) -, y empezar por letra o cifra"),
        ("-Botox", "El nombre solo puede tener letras, cifras, espacios y . , ' & + / ( ) -, y empezar por letra o cifra"),
        ("B" * 121, "El nombre no puede tener más de 120 caracteres"),
    ],
)
def test_nombre_no_valido_422(usuarios, db, nombre, mensaje):
    response = crear(botox(usuarios, name=nombre))

    assert response.status_code == 422
    assert error_de(response, "name") == mensaje
    assert contar(db) == 0


def test_nombre_con_signos_permitidos(usuarios, db):
    response = crear(botox(usuarios, name="Lips & cheeks 1/2 (Dr. O'Neil) - plus+"))

    assert response.status_code == 201
    assert response.json()["name"] == "Lips & cheeks 1/2 (Dr. O'Neil) - plus+"


def test_sin_personas_422(usuarios, db):
    response = crear(botox(usuarios, staff_ids=[]))

    assert response.status_code == 422
    assert error_de(response, "staff_ids") == "Un servicio activo necesita al menos una persona que lo realice"
    assert contar(db) == 0


def test_cliente_desactivada_o_inexistente_no_se_asignan(usuarios, db):
    baja = cuenta(db, "baja@prueba.example.com", Role.PROFESSIONAL, active=False)
    for persona in (usuarios[Role.CLIENT].id, baja.id, 999_999):
        response = crear(botox(usuarios, staff_ids=[usuarios[Role.ADMIN].id, persona]))

        assert response.status_code == 422, persona
        assert error_de(response, "staff_ids") == (
            "Solo se pueden asignar cuentas internas activas (administración, recepción o profesional)"
        )
    assert contar(db) == 0


@pytest.mark.parametrize(
    "cambio",
    [{"active": False}, {"version": 3}, {"id": 7}, {"staff_ids": ["1"]}, {"staff_ids": None}],
)
def test_campos_de_mas_o_mal_formados_422(usuarios, db, cambio):
    assert crear(botox(usuarios, **cambio)).status_code == 422
    assert contar(db) == 0


def test_sin_personas_falta_el_campo_422(usuarios, db):
    datos = botox(usuarios)
    del datos["staff_ids"]

    assert crear(datos).status_code == 422


def test_mas_de_50_personas_422(usuarios, db):
    assert crear(botox(usuarios, staff_ids=list(range(1, 52)))).status_code == 422


@pytest.mark.parametrize("nombre", ["Botox", "BOTOX", "  botox "])
def test_nombre_repetido_sin_distinguir_mayusculas_409(usuarios, db, nombre):
    assert crear(botox(usuarios)).status_code == 201

    response = crear(botox(usuarios, name=nombre))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Ya existe un servicio con ese nombre (puede estar desactivado: edítalo y reactívalo)"
    }
    assert contar(db) == 1


def test_nombre_de_un_servicio_desactivado_tambien_409(usuarios, db):
    servicio = crear(botox(usuarios)).json()
    assert editar(servicio, active=False).status_code == 200

    assert crear(botox(usuarios)).status_code == 409


@pytest.mark.parametrize(
    "columnas, valores",
    [
        ("name, duration_minutes", "'Botox', 7"),  # duración no múltiplo de 5
        ("name, duration_minutes", "'Botox', 245"),  # más de 4 horas
        ("name, duration_minutes", "'Depilación', 30"),  # tilde
        ("name, duration_minutes", "' Botox', 30"),  # sin normalizar
        ("name, duration_minutes, version", "'Botox', 30, 0"),
    ],
)
def test_la_bd_repite_las_reglas(db, columnas, valores):
    # Aunque alguien escriba directamente en la BD, sin pasar por la API.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text(f"INSERT INTO services ({columnas}) VALUES ({valores})"))


def test_la_bd_no_admite_dos_nombres_iguales(db):
    db.execute(text("INSERT INTO services (name, duration_minutes) VALUES ('Botox', 30)"))
    with pytest.raises(IntegrityError, match="uq_services_name"):
        with db.begin_nested():
            db.execute(text("INSERT INTO services (name, duration_minutes) VALUES ('BOTOX', 60)"))


# --- Lista y personas asignables ---------------------------------------------------


def test_lista_primero_activos_y_por_nombre(usuarios, db):
    for nombre in ("peel", "Facial", "Botox"):
        crear(botox(usuarios, name=nombre))
    facial = next(s for s in listar().json() if s["name"] == "Facial")
    editar(facial, active=False, staff_ids=[])

    for role in (Role.ADMIN, Role.RECEPTION):
        response = listar(role)

        assert response.status_code == 200
        assert [(s["name"], s["active"]) for s in response.json()] == [("Botox", True), ("peel", True), ("Facial", False)]


def test_profesional_ve_solo_sus_servicios_activos(usuarios, db):
    pro = usuarios[Role.PROFESSIONAL].id
    crear(botox(usuarios, name="Suyo", staff_ids=[pro]))
    crear(botox(usuarios, name="Ajeno"))
    desactivado = crear(botox(usuarios, name="Suyo pero desactivado", staff_ids=[pro])).json()
    editar(desactivado, active=False)

    response = listar(Role.PROFESSIONAL)

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Suyo"]


def test_cliente_no_ve_servicios(usuarios, db):
    assert listar(Role.CLIENT).status_code == 403


def test_personas_asignables_cuentas_internas_activas(usuarios, db):
    cuenta(db, "baja@prueba.example.com", Role.ADMIN, active=False)
    client, _ = sesion_de(Role.RECEPTION)

    response = client.get("/api/services/staff")

    assert response.status_code == 200
    assert [p["email"] for p in response.json()] == [
        "admin@prueba.example.com", "professional@prueba.example.com", "reception@prueba.example.com",
    ]


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_personas_asignables_solo_admin_y_recepcion(usuarios, db, role):
    client, _ = sesion_de(role)

    assert client.get("/api/services/staff").status_code == 403


# --- Edición y desactivación -----------------------------------------------------


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_editar_nombre_duracion_y_personas(usuarios, db, role):
    servicio = crear(botox(usuarios)).json()
    pro, rec = usuarios[Role.PROFESSIONAL].id, usuarios[Role.RECEPTION].id

    response = editar(servicio, role, name="Botox forehead", duration_minutes=45, staff_ids=[pro, rec])

    assert response.status_code == 200
    datos = response.json()
    assert (datos["name"], datos["duration_minutes"], datos["version"]) == ("Botox forehead", 45, 2)
    assert {p["id"] for p in datos["staff"]} == {pro, rec}
    assert personas(db, servicio["id"]) == {pro, rec}


def test_version_antigua_409_y_no_cambia_nada(usuarios, db):
    servicio = crear(botox(usuarios)).json()
    assert editar(servicio, duration_minutes=60).status_code == 200

    response = editar(servicio, name="Otro", staff_ids=[usuarios[Role.PROFESSIONAL].id])

    assert response.status_code == 409
    assert response.json() == {"detail": "Otra persona ha cambiado este servicio antes de que guardaras"}
    guardado = db.get(Service, servicio["id"], populate_existing=True)
    assert (guardado.name, guardado.duration_minutes, guardado.version) == ("Botox", 60, 2)
    assert personas(db, servicio["id"]) == {usuarios[Role.ADMIN].id}


def test_desactivar_y_reactivar(usuarios, db):
    servicio = crear(botox(usuarios)).json()

    desactivado = editar(servicio, active=False)
    assert desactivado.status_code == 200
    assert desactivado.json()["active"] is False

    reactivado = editar(desactivado.json(), active=True)
    assert reactivado.status_code == 200
    assert (reactivado.json()["active"], reactivado.json()["version"]) == (True, 3)
    assert contar(db) == 1  # nunca se borra


def test_desactivado_puede_quedarse_sin_personas_pero_activo_no(usuarios, db):
    servicio = crear(botox(usuarios)).json()

    activo_sin_nadie = editar(servicio, staff_ids=[])
    assert activo_sin_nadie.status_code == 422
    assert error_de(activo_sin_nadie, "staff_ids") == "Un servicio activo necesita al menos una persona que lo realice"

    desactivado = editar(servicio, active=False, staff_ids=[])
    assert desactivado.status_code == 200
    assert personas(db, servicio["id"]) == set()

    assert editar(desactivado.json(), active=True).status_code == 422


def test_persona_desactivada_ya_asignada_no_impide_guardar(usuarios, db):
    pro = usuarios[Role.PROFESSIONAL]
    servicio = crear(botox(usuarios, staff_ids=[pro.id, usuarios[Role.ADMIN].id])).json()
    pro.active = False
    db.flush()

    response = editar(servicio, duration_minutes=60)

    assert response.status_code == 200
    # Sigue figurando, marcada como desactivada, hasta que alguien la quite.
    assert {(p["id"], p["active"]) for p in response.json()["staff"]} == {(pro.id, False), (usuarios[Role.ADMIN].id, True)}


def test_anadir_al_editar_una_cuenta_no_valida_422(usuarios, db):
    servicio = crear(botox(usuarios)).json()

    response = editar(servicio, staff_ids=[usuarios[Role.ADMIN].id, usuarios[Role.CLIENT].id])

    assert response.status_code == 422
    assert personas(db, servicio["id"]) == {usuarios[Role.ADMIN].id}


def test_renombrar_como_otro_servicio_409(usuarios, db):
    crear(botox(usuarios, name="Facial"))
    servicio = crear(botox(usuarios)).json()

    response = editar(servicio, name="facial")

    assert response.status_code == 409
    assert db.get(Service, servicio["id"], populate_existing=True).name == "Botox"


def test_editar_servicio_inexistente_404(usuarios, db):
    response = editar({"id": 999_999, "name": "Botox", "duration_minutes": 30, "staff": [], "active": False, "version": 1})

    assert response.status_code == 404
    assert response.json() == {"detail": "Servicio no encontrado"}


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_editan(usuarios, db, role):
    servicio = crear(botox(usuarios, staff_ids=[usuarios[Role.PROFESSIONAL].id])).json()

    assert editar(servicio, role, duration_minutes=60).status_code == 403
    assert db.get(Service, servicio["id"], populate_existing=True).duration_minutes == 30


@pytest.mark.parametrize("falta", ["active", "version", "staff_ids"])
def test_editar_exige_el_servicio_entero(usuarios, db, falta):
    servicio = crear(botox(usuarios)).json()
    datos = {"name": "Botox", "duration_minutes": 30, "staff_ids": [usuarios[Role.ADMIN].id], "active": True,
             "version": 1}
    del datos[falta]
    client, csrf = sesion_de(Role.ADMIN)

    assert client.put(f"/api/services/{servicio['id']}", json=datos, headers=csrf).status_code == 422


def test_activo_debe_ser_booleano(usuarios, db):
    servicio = crear(botox(usuarios)).json()

    assert editar(servicio, active="false").status_code == 422


def test_borrar_la_cuenta_la_quita_del_servicio(usuarios, db):
    pro = usuarios[Role.PROFESSIONAL]
    servicio = crear(botox(usuarios, staff_ids=[pro.id, usuarios[Role.ADMIN].id])).json()

    db.delete(pro)
    db.flush()

    assert personas(db, servicio["id"]) == {usuarios[Role.ADMIN].id}
