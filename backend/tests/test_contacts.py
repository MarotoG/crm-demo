"""Alta de contactos contra PostgreSQL real (T11, ver conftest.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.auth import CSRF_HEADER
from app.main import app as fastapi_app
from app.models import Contact, Role, User
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
ANA = {"first_name": "Ana", "last_name": "Smith", "email": "ana@clinica.example.com", "source": "instagram"}


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


def crear(datos: dict, role: Role = Role.RECEPTION):
    client, csrf = sesion_de(role)
    return client.post("/api/contacts", json=datos, headers=csrf)


def contar(db) -> int:
    return db.scalar(select(func.count()).select_from(Contact))


def mensajes(response) -> list[str]:
    return [error["msg"] for error in response.json()["detail"]]


# --- Alta correcta y permisos ----------------------------------------------------


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ADMIN])
def test_recepcion_y_admin_crean_un_contacto(usuarios, db, role):
    response = crear({**ANA, "first_name": "  Ana  ", "email": " Ana@Clinica.Example.COM ", "phone": "(212) 555-0123"}, role)

    assert response.status_code == 201
    datos = response.json()
    assert datos | {"id": 0, "created_at": ""} == {
        "id": 0, "first_name": "Ana", "last_name": "Smith", "email": "ana@clinica.example.com",
        "phone": "+12125550123", "source": "instagram", "status": "new", "created_at": "",
    }
    contacto = db.get(Contact, datos["id"])
    assert contacto.created_by_id == usuarios[role].id
    assert contacto.status == "new"


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_crean_contactos(usuarios, db, role):
    response = crear(ANA, role)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permiso denegado"}
    assert contar(db) == 0


def test_sin_token_csrf_403_y_no_se_guarda(usuarios, db):
    client, _ = sesion_de(Role.RECEPTION)

    assert client.post("/api/contacts", json=ANA).status_code == 403
    assert contar(db) == 0


def test_sin_sesion_401_aunque_los_datos_sean_invalidos(db):
    # Quien no ha entrado no recibe pistas sobre la validación.
    response = TestClient(fastapi_app).post("/api/contacts", json={"first_name": ""})

    assert response.status_code == 401


# --- Datos no válidos -------------------------------------------------------------


def test_sin_email_ni_telefono_422(usuarios, db):
    response = crear({**ANA, "email": "  ", "phone": ""})

    assert response.status_code == 422
    assert "Indica al menos un email o un teléfono" in mensajes(response)
    assert contar(db) == 0


def test_basta_con_el_telefono(usuarios, db):
    response = crear({"first_name": "Ana", "last_name": "Smith", "phone": "+34 612 345 678", "source": "referral"})

    assert response.status_code == 201
    assert response.json()["email"] is None


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        ({"email": "ana@clinica"}, "El dominio del email no es válido (por ejemplo: nombre@clinica.com)"),
        ({"phone": "(123) 555-0123"}, "El teléfono de EE. UU. no es válido (p. ej. (212) 555-0123)"),
        ({"first_name": "   "}, "El nombre no puede estar vacío"),
        ({"last_name": "Smi​th"}, "El apellido contiene caracteres no permitidos"),
    ],
)
def test_datos_no_validos_422_con_mensaje_claro(usuarios, db, cambio, mensaje):
    response = crear({**ANA, **cambio})

    assert response.status_code == 422
    assert mensaje in mensajes(response)
    assert contar(db) == 0


@pytest.mark.parametrize(
    "cambio",
    [{"source": "tiktok"}, {"source": None}, {"status": "client"}, {"created_by_id": 1}, {"id": 99}],
    ids=["origen fuera de la lista", "sin origen", "fijar estado", "fijar autor", "fijar id"],
)
def test_origen_invalido_o_campos_que_no_decide_el_navegador_422(usuarios, db, cambio):
    assert crear({**ANA, **cambio}).status_code == 422
    assert contar(db) == 0


# --- Duplicados (decisión T11) ------------------------------------------------------


def test_mismo_nombre_y_email_409_aunque_cambien_mayusculas_y_espacios(usuarios, db):
    assert crear(ANA).status_code == 201

    response = crear({**ANA, "first_name": " ANA ", "last_name": "smith", "email": "ANA@clinica.example.com"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Ya existe un contacto con ese nombre, apellidos y email"}
    assert contar(db) == 1


def test_mismo_nombre_y_telefono_409(usuarios, db):
    base = {"first_name": "Ana", "last_name": "Smith", "phone": "(212) 555-0123", "source": "google"}
    assert crear(base).status_code == 201

    response = crear({**base, "phone": "+1 212-555-0123", "email": "otra@clinica.example.com"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Ya existe un contacto con ese nombre, apellidos y teléfono"}


def test_mismo_nombre_con_la_tilde_escrita_de_otra_forma_409(usuarios, db):
    base = {"first_name": "José", "last_name": "Pérez", "email": "jose@clinica.example.com", "source": "google"}
    assert crear(base).status_code == 201

    # Se ve igual, pero llega como «e» + tilde suelta (p. ej., pegado desde otra aplicación).
    response = crear({**base, "first_name": "José", "last_name": "Pérez"})

    assert response.status_code == 409
    assert contar(db) == 1
    assert db.scalar(select(Contact.first_name)) == "José"


def test_una_familia_puede_compartir_email_y_telefono(usuarios, db):
    familia = {"last_name": "Smith", "email": "familia@clinica.example.com", "phone": "(212) 555-0123", "source": "referral"}

    assert crear({**familia, "first_name": "Ana"}).status_code == 201
    assert crear({**familia, "first_name": "Laura"}).status_code == 201
    assert crear({**ANA, "email": "ana.otra@clinica.example.com"}).status_code == 201  # misma persona, otro email
    assert contar(db) == 3


def test_tras_un_409_se_puede_seguir_creando(usuarios, db):
    crear(ANA)
    assert crear(ANA).status_code == 409

    assert crear({**ANA, "first_name": "Laura"}).status_code == 201


# --- La BD repite las reglas aunque alguien salte la API ----------------------------


@pytest.mark.parametrize(
    "columnas, valores",
    [
        ("first_name, last_name, source", "'Ana', 'Smith', 'google'"),  # sin email ni teléfono
        ("first_name, last_name, email, source", "'Ana', 'Smith', 'Ana@X.com', 'google'"),
        ("first_name, last_name, phone, source", "'Ana', 'Smith', '2125550123', 'google'"),
        ("first_name, last_name, email, source", "' Ana', 'Smith', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'Ana  María', 'Smith', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'', 'Smith', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'Ana', 'Smith', 'a@x.com', 'tiktok'"),
        ("first_name, last_name, email, source, status", "'Ana', 'Smith', 'a@x.com', 'google', 'vip'"),
    ],
    ids=["sin contacto", "email sin normalizar", "teléfono sin +", "espacio inicial", "espacio doble",
         "nombre vacío", "origen inválido", "estado inválido"],
)
def test_la_bd_rechaza_datos_que_salten_la_api(db, columnas, valores):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(f"INSERT INTO contacts ({columnas}) VALUES ({valores})"))


def test_la_bd_rechaza_el_duplicado_aunque_salte_la_api(db):
    db.execute(text("INSERT INTO contacts (first_name, last_name, email, source) VALUES ('Ana', 'Smith', 'a@x.com', 'google')"))

    with pytest.raises(IntegrityError, match="uq_contacts_name_email"), db.begin_nested():
        db.execute(text("INSERT INTO contacts (first_name, last_name, email, source) VALUES ('ANA', 'smith', 'a@x.com', 'other')"))


def test_borrar_al_autor_conserva_el_contacto(usuarios, db):
    contacto_id = crear(ANA).json()["id"]

    db.delete(usuarios[Role.RECEPTION])
    db.flush()
    db.expire_all()

    contacto = db.get(Contact, contacto_id)
    assert contacto is not None and contacto.created_by_id is None


# --- Lista y búsqueda (T12) ----------------------------------------------------------


def guardar(db, *contactos: tuple[str, str, str | None, str | None]) -> list[int]:
    """Inserta contactos directamente (nombre, apellidos, email, teléfono) y devuelve sus id en orden."""
    filas = [Contact(first_name=n, last_name=a, email=e, phone=t, source="other") for n, a, e, t in contactos]
    db.add_all(filas)
    db.flush()
    return [f.id for f in filas]


def listar(q: str | None = None, role: Role = Role.RECEPTION):
    client, _ = sesion_de(role)
    return client.get("/api/contacts", params=None if q is None else {"q": q})


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ADMIN])
def test_recepcion_y_admin_ven_la_lista_del_mas_reciente_al_mas_antiguo(usuarios, db, role):
    ids = guardar(db, ("Ana", "Smith", "ana@x.com", None), ("Luis", "Pérez", None, "+12125550123"))

    response = listar(role=role)

    assert response.status_code == 200
    datos = response.json()
    assert datos["total"] == 2
    assert [c["id"] for c in datos["items"]] == ids[::-1]
    assert set(datos["items"][0]) == {"id", "first_name", "last_name", "email", "phone", "source", "status", "created_at"}


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_ven_la_lista(usuarios, db, role):
    guardar(db, ("Ana", "Smith", "ana@x.com", None))

    response = listar(role=role)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permiso denegado"}


def test_la_lista_trae_20_y_el_total_real(usuarios, db):
    ids = guardar(db, *[(f"Ana{i}", "Smith", f"a{i}@x.com", None) for i in range(25)])

    datos = listar().json()

    assert datos["total"] == 25
    assert [c["id"] for c in datos["items"]] == ids[::-1][:20]


def test_el_total_cuenta_todos_los_que_cumplen_la_busqueda(usuarios, db):
    guardar(db, *[(f"Ana{i}", "Smith", f"a{i}@x.com", None) for i in range(22)], ("Luis", "Pérez", "l@x.com", None))

    datos = listar("ana").json()

    assert datos["total"] == 22
    assert len(datos["items"]) == 20


@pytest.mark.parametrize(
    "q",
    ["jose", "JOSÉ", "José", "perez", "José Pérez", "  perez   jose ", "jose.p@clin", "(212) 555-01", "+1 212", "5550123"],
    ids=["sin tilde", "mayúsculas", "tilde suelta", "apellido", "nombre completo", "al revés y con espacios",
         "parte del email", "teléfono con formato", "teléfono con prefijo", "final del teléfono"],
)
def test_la_busqueda_encuentra_por_nombre_email_o_telefono(usuarios, db, q):
    jose, _ = guardar(db, ("José", "Pérez", "jose.p@clinica.example.com", "+12125550123"), ("Ana", "Smith", "ana@x.com", "+34612345678"))

    datos = listar(q).json()

    assert [c["id"] for c in datos["items"]] == [jose]
    assert datos["total"] == 1


@pytest.mark.parametrize(
    "q",
    ["%", "_", "\\", "nadie", "21"],
    ids=["% literal", "_ literal", "barra invertida", "sin coincidencias", "menos de 3 cifras"],
)
def test_la_busqueda_no_devuelve_de_mas(usuarios, db, q):
    guardar(db, ("José", "Pérez", "jose@x.com", "+12125550123"), ("Ana", "Smith", "ana@x.com", None))

    datos = listar(q).json()

    assert datos == {"total": 0, "items": []}


def test_busqueda_vacia_o_solo_espacios_devuelve_todos(usuarios, db):
    guardar(db, ("José", "Pérez", "jose@x.com", None), ("Ana", "Smith", "ana@x.com", None))

    assert listar("   ").json()["total"] == 2


def test_busqueda_demasiado_larga_422(usuarios, db):
    assert listar("a" * 101).status_code == 422
    assert listar("a" * 100).status_code == 200


def test_lo_creado_por_la_api_aparece_el_primero_en_la_lista(usuarios, db):
    guardar(db, ("Luis", "Pérez", "l@x.com", None))
    creado = crear(ANA).json()

    assert listar().json()["items"][0] == creado
