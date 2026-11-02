"""Contactos contra PostgreSQL real: alta (T11), lista y búsqueda (T12), sin tildes (T12b), ficha y edición (T13)."""

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
        ({"last_name": "Smi\u200bth"}, "No se permiten tildes ni caracteres especiales (á, ñ, ü…)"),
        ({"last_name": "Smith2"}, "El apellido solo puede tener letras, espacios, guiones, apóstrofos y puntos, y empezar por letra"),
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


@pytest.mark.parametrize(
    "cambio",
    [{"first_name": "Jos\u00e9"}, {"last_name": "Mu\u00f1oz"}, {"email": "jos\u00e9@clinica.example.com"}],
    ids=["nombre con tilde", "apellido con eñe", "email con tilde"],
)
def test_con_tildes_422_con_el_aviso_y_no_se_guarda(usuarios, db, cambio):
    response = crear({**ANA, **cambio})

    assert response.status_code == 422
    assert "No se permiten tildes ni caracteres especiales (á, ñ, ü…)" in mensajes(response)
    assert contar(db) == 0


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
        ("first_name, last_name, email, source", "'Ana  Maria', 'Smith', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'', 'Smith', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'Ana', 'Smith', 'a@x.com', 'tiktok'"),
        ("first_name, last_name, email, source, status", "'Ana', 'Smith', 'a@x.com', 'google', 'vip'"),
        ("first_name, last_name, email, source", "'Jos\u00e9', 'Smith', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'Ana', 'Mu\u00f1oz', 'a@x.com', 'google'"),
        ("first_name, last_name, email, source", "'Ana', 'Smith', 'jos\u00e9@x.com', 'google'"),
        ("first_name, last_name, email, source", "'Ana2', 'Smith', 'a@x.com', 'google'"),
    ],
    ids=["sin contacto", "email sin normalizar", "teléfono sin +", "espacio inicial", "espacio doble",
         "nombre vacío", "origen inválido", "estado inválido", "nombre con tilde", "apellido con eñe",
         "email con tilde", "nombre con cifra"],
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
    ids = guardar(db, ("Ana", "Smith", "ana@x.com", None), ("Luis", "Perez", None, "+12125550123"))

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
    ids = guardar(db, *[(f"Ana{chr(65 + i)}", "Smith", f"a{i}@x.com", None) for i in range(25)])

    datos = listar().json()

    assert datos["total"] == 25
    assert [c["id"] for c in datos["items"]] == ids[::-1][:20]


def test_el_total_cuenta_todos_los_que_cumplen_la_busqueda(usuarios, db):
    guardar(db, *[(f"Ana{chr(65 + i)}", "Smith", f"a{i}@x.com", None) for i in range(22)], ("Luis", "Perez", "l@x.com", None))

    datos = listar("ana").json()

    assert datos["total"] == 22
    assert len(datos["items"]) == 20


@pytest.mark.parametrize(
    "q",
    ["jose", "JOSE", "perez", "Jose Perez", "  perez   jose ", "jose.p@clin", "(212) 555-01", "+1 212", "5550123"],
    ids=["nombre", "mayúsculas", "apellido", "nombre completo", "al revés y con espacios",
         "parte del email", "teléfono con formato", "teléfono con prefijo", "final del teléfono"],
)
def test_la_busqueda_encuentra_por_nombre_email_o_telefono(usuarios, db, q):
    jose, _ = guardar(db, ("Jose", "Perez", "jose.p@clinica.example.com", "+12125550123"), ("Ana", "Smith", "ana@x.com", "+34612345678"))

    datos = listar(q).json()

    assert [c["id"] for c in datos["items"]] == [jose]
    assert datos["total"] == 1


@pytest.mark.parametrize(
    "q",
    ["%", "_", "\\", "nadie", "21", "Jos\u00e9"],
    ids=["% literal", "_ literal", "barra invertida", "sin coincidencias", "menos de 3 cifras", "con tilde"],
)
def test_la_busqueda_no_devuelve_de_mas(usuarios, db, q):
    guardar(db, ("Jose", "Perez", "jose@x.com", "+12125550123"), ("Ana", "Smith", "ana@x.com", None))

    datos = listar(q).json()

    assert datos == {"total": 0, "items": []}


def test_busqueda_vacia_o_solo_espacios_devuelve_todos(usuarios, db):
    guardar(db, ("Jose", "Perez", "jose@x.com", None), ("Ana", "Smith", "ana@x.com", None))

    assert listar("   ").json()["total"] == 2


def test_busqueda_demasiado_larga_422(usuarios, db):
    assert listar("a" * 101).status_code == 422
    assert listar("a" * 100).status_code == 200


def test_lo_creado_por_la_api_aparece_el_primero_en_la_lista(usuarios, db):
    guardar(db, ("Luis", "Perez", "l@x.com", None))
    creado = crear(ANA).json()

    assert listar().json()["items"][0] == creado


# --- Ficha y edición (T13) -------------------------------------------------------------

VERSION_CONFLICT = {"detail": "Otra persona ha cambiado esta ficha mientras la editabas"}


def ver(contact_id: int, role: Role = Role.RECEPTION):
    client, _ = sesion_de(role)
    return client.get(f"/api/contacts/{contact_id}")


def editar(contact_id: int, datos: dict, role: Role = Role.RECEPTION):
    client, csrf = sesion_de(role)
    return client.put(f"/api/contacts/{contact_id}", json=datos, headers=csrf)


def ficha_de_ana(**cambios) -> dict:
    """Lo que enviaría el formulario de edición: la ficha entera y la versión leída."""
    return {**ANA, "phone": None, "version": 1, **cambios}


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ADMIN])
def test_recepcion_y_admin_ven_la_ficha(usuarios, db, role):
    creado = crear(ANA).json()

    response = ver(creado["id"], role)

    assert response.status_code == 200
    assert response.json() | {"created_at": "", "updated_at": ""} == {
        **creado, "created_at": "", "updated_at": "", "version": 1,
        "created_by_email": "reception@prueba.example.com", "updated_by_email": None,
    }


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_ven_ni_editan_la_ficha(usuarios, db, role):
    contacto_id = crear(ANA).json()["id"]

    assert ver(contacto_id, role).status_code == 403
    assert editar(contacto_id, ficha_de_ana(first_name="Eva"), role).status_code == 403
    assert db.get(Contact, contacto_id).first_name == "Ana"


def test_ficha_que_no_existe_404(usuarios, db):
    assert ver(999999).json() == {"detail": "Contacto no encontrado"}
    assert ver(999999).status_code == 404
    assert editar(999999, ficha_de_ana()).status_code == 404


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ADMIN])
def test_editar_conserva_el_id_normaliza_y_sube_la_version(usuarios, db, role):
    creado = crear(ANA).json()

    response = editar(creado["id"], ficha_de_ana(first_name="  Anna ", email=None, phone="(212) 555-0123", source="google"), role)

    assert response.status_code == 200
    datos = response.json()
    assert (datos["id"], datos["first_name"], datos["email"], datos["phone"], datos["source"]) == (
        creado["id"], "Anna", None, "+12125550123", "google",
    )
    assert datos["version"] == 2
    assert datos["status"] == "new"  # el estado no se toca (T14)
    assert datos["created_by_email"] == "reception@prueba.example.com"
    assert datos["updated_by_email"] == f"{role.value}@prueba.example.com"
    lista = listar().json()
    assert lista["total"] == 1 and lista["items"][0]["id"] == creado["id"]  # misma ficha, no otra


def test_dos_ediciones_con_la_misma_version_la_segunda_409(usuarios, db):
    contacto_id = crear(ANA).json()["id"]

    primera = editar(contacto_id, ficha_de_ana(first_name="Anna"))
    segunda = editar(contacto_id, ficha_de_ana(last_name="Smyth"), Role.ADMIN)  # leyó la versión 1

    assert primera.status_code == 200
    assert segunda.status_code == 409
    assert segunda.json() == VERSION_CONFLICT
    contacto = db.get(Contact, contacto_id, populate_existing=True)
    assert (contacto.first_name, contacto.last_name, contacto.version) == ("Anna", "Smith", 2)


def test_con_la_version_nueva_se_puede_volver_a_editar(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    editar(contacto_id, ficha_de_ana(first_name="Anna"))

    response = editar(contacto_id, ficha_de_ana(first_name="Anna", last_name="Smyth", version=2))

    assert response.status_code == 200
    assert response.json()["version"] == 3


def test_guardar_sin_cambios_no_choca_consigo_misma(usuarios, db):
    contacto_id = crear(ANA).json()["id"]

    assert editar(contacto_id, ficha_de_ana()).status_code == 200


def test_la_edicion_que_crea_un_duplicado_409_y_no_cambia_nada(usuarios, db):
    crear({**ANA, "first_name": "Laura"})
    ana_id = crear(ANA).json()["id"]

    response = editar(ana_id, ficha_de_ana(first_name="LAURA"))

    assert response.status_code == 409
    assert response.json() == {"detail": "Ya existe un contacto con ese nombre, apellidos y email"}
    contacto = db.get(Contact, ana_id, populate_existing=True)
    assert (contacto.first_name, contacto.version) == ("Ana", 1)


@pytest.mark.parametrize(
    "cambio",
    [
        {"first_name": "Jos\u00e9"},
        {"email": None, "phone": None},
        {"status": "client"},
        {"created_by_id": 1},
        {"version": 0},
        {"version": None},
    ],
    ids=["con tilde", "sin email ni teléfono", "fijar estado", "fijar autor", "versión 0", "sin versión"],
)
def test_edicion_no_valida_422_y_no_cambia_nada(usuarios, db, cambio):
    contacto_id = crear(ANA).json()["id"]

    response = editar(contacto_id, {**ficha_de_ana(), **cambio})

    assert response.status_code == 422
    assert db.get(Contact, contacto_id, populate_existing=True).version == 1


def test_editar_sin_token_csrf_403(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    client, _ = sesion_de(Role.RECEPTION)

    assert client.put(f"/api/contacts/{contacto_id}", json=ficha_de_ana(first_name="Eva")).status_code == 403
    assert db.get(Contact, contacto_id, populate_existing=True).first_name == "Ana"


def test_la_bd_rechaza_una_version_menor_que_1(db):
    db.execute(text("INSERT INTO contacts (first_name, last_name, email, source) VALUES ('Ana', 'Smith', 'a@x.com', 'google')"))

    with pytest.raises(IntegrityError, match="ck_contacts_version_positive"), db.begin_nested():
        db.execute(text("UPDATE contacts SET version = 0"))
