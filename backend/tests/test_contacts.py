"""Contactos contra PostgreSQL real: alta (T11), lista y búsqueda (T12), sin tildes (T12b), ficha y edición (T13), estado y responsable (T14)."""

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
        "owner_id": usuarios[role].id, "owner_email": f"{role.value}@prueba.example.com",  # responsable: quien lo crea (T14)
    }
    contacto = db.get(Contact, datos["id"])
    assert contacto.created_by_id == contacto.owner_id == usuarios[role].id
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
    assert contacto is not None and contacto.created_by_id is None and contacto.owner_id is None


# --- Lista y búsqueda (T12) ----------------------------------------------------------


def guardar(db, *contactos: tuple[str, str, str | None, str | None]) -> list[int]:
    """Inserta contactos directamente (nombre, apellidos, email, teléfono) y devuelve sus id en orden."""
    filas = [Contact(first_name=n, last_name=a, email=e, phone=t, source="other") for n, a, e, t in contactos]
    db.add_all(filas)
    db.flush()
    return [f.id for f in filas]


def listar(q: str | None = None, role: Role = Role.RECEPTION, **filtros):
    client, _ = sesion_de(role)
    params = ({} if q is None else {"q": q}) | filtros
    return client.get("/api/contacts", params=params or None)


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ADMIN])
def test_recepcion_y_admin_ven_la_lista_del_mas_reciente_al_mas_antiguo(usuarios, db, role):
    ids = guardar(db, ("Ana", "Smith", "ana@x.com", None), ("Luis", "Perez", None, "+12125550123"))

    response = listar(role=role)

    assert response.status_code == 200
    datos = response.json()
    assert datos["total"] == 2
    assert [c["id"] for c in datos["items"]] == ids[::-1]
    assert set(datos["items"][0]) == {
        "id", "first_name", "last_name", "email", "phone", "source", "status", "created_at", "owner_id", "owner_email",
    }


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
    """Lo que enviaría el formulario de edición: la ficha entera y la versión leída.

    Sin responsable salvo que se indique (`owner_id`): es lo único que no sabe sin la BD.
    """
    return {**ANA, "phone": None, "owner_id": None, "version": 1, **cambios}


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


# --- Estado comercial y responsable (T14) -------------------------------------------------


def cambiar_estado(contact_id: int, estado: str, version: int = 1, role: Role = Role.RECEPTION):
    client, csrf = sesion_de(role)
    return client.put(f"/api/contacts/{contact_id}/status", json={"status": estado, "version": version}, headers=csrf)


def en_estado(db, estado: str, nombre: str = "Ana") -> int:
    """Crea el contacto por la API y lo deja en ese estado directamente en la BD (las citas aún no existen)."""
    contacto_id = crear({**ANA, "first_name": nombre}).json()["id"]
    db.execute(text("UPDATE contacts SET status = :s WHERE id = :id"), {"s": estado, "id": contacto_id})
    return contacto_id


def recargar(db, contact_id: int) -> Contact:
    return db.get(Contact, contact_id, populate_existing=True)


@pytest.mark.parametrize(
    "origen, destino",
    [
        ("new", "contacted"),
        ("new", "lost"),
        ("contacted", "lost"),
        ("scheduled", "lost"),
        ("client", "lost"),
        ("lost", "contacted"),
    ],
    ids=["avanzar", "perder un nuevo", "perder un contactado", "perder con cita", "perder un cliente", "reabrir"],
)
@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ADMIN])
def test_cambios_de_estado_permitidos(usuarios, db, origen, destino, role):
    contacto_id = en_estado(db, origen)

    response = cambiar_estado(contacto_id, destino, role=role)

    assert response.status_code == 200
    datos = response.json()
    assert (datos["id"], datos["status"], datos["version"]) == (contacto_id, destino, 2)  # la misma ficha
    assert datos["updated_by_email"] == f"{role.value}@prueba.example.com"
    assert listar().json()["total"] == 1


@pytest.mark.parametrize(
    "origen, destino, mensaje",
    [
        ("contacted", "contacted", "No se puede pasar de «Contactado» a «Contactado»"),
        ("lost", "lost", "No se puede pasar de «Perdido» a «Perdido»"),
        ("scheduled", "contacted", "No se puede pasar de «Cita agendada» a «Contactado»"),
        ("client", "contacted", "No se puede pasar de «Cliente» a «Contactado»"),
        ("contacted", "new", "Un contacto no vuelve a «Nuevo»"),
        ("lost", "new", "Un contacto no vuelve a «Nuevo»"),
        ("contacted", "scheduled", "«Cita agendada» no se pone a mano: lo pondrán las citas"),
        ("new", "client", "«Cliente» no se pone a mano: lo pondrán las citas"),
    ],
    ids=["repetir", "perder dos veces", "retroceder", "cliente atras", "volver a nuevo", "reabrir como nuevo",
         "cita a mano", "cliente a mano"],
)
def test_cambios_de_estado_no_permitidos_422_y_no_cambia_nada(usuarios, db, origen, destino, mensaje):
    contacto_id = en_estado(db, origen)

    response = cambiar_estado(contacto_id, destino)

    assert response.status_code == 422
    assert mensajes(response) == [mensaje]
    assert response.json()["detail"][0]["loc"] == ["body", "status"]
    contacto = recargar(db, contacto_id)
    assert (contacto.status, contacto.version, contacto.updated_by_id) == (origen, 1, None)


def test_cambio_de_estado_con_version_antigua_409(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    assert cambiar_estado(contacto_id, "contacted").status_code == 200

    response = cambiar_estado(contacto_id, "lost", version=1, role=Role.ADMIN)  # leyó la versión 1

    assert response.status_code == 409
    assert response.json() == VERSION_CONFLICT
    contacto = recargar(db, contacto_id)
    assert (contacto.status, contacto.version) == ("contacted", 2)


def test_estado_y_edicion_comparten_la_version(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    assert cambiar_estado(contacto_id, "contacted").status_code == 200

    # Quien abrió la ficha antes del cambio de estado no lo pisa al guardar.
    assert editar(contacto_id, ficha_de_ana(first_name="Anna")).status_code == 409
    # Y al revés: una edición deja antigua la versión con la que se iba a cambiar el estado.
    assert editar(contacto_id, ficha_de_ana(first_name="Anna", version=2)).status_code == 200
    assert cambiar_estado(contacto_id, "lost", version=2).status_code == 409
    contacto = recargar(db, contacto_id)
    assert (contacto.first_name, contacto.status, contacto.version) == ("Anna", "contacted", 3)


def test_editar_la_ficha_no_cambia_el_estado(usuarios, db):
    contacto_id = en_estado(db, "lost")

    assert editar(contacto_id, ficha_de_ana(first_name="Anna")).json()["status"] == "lost"


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_cambian_el_estado(usuarios, db, role):
    contacto_id = crear(ANA).json()["id"]

    assert cambiar_estado(contacto_id, "contacted", role=role).status_code == 403
    assert recargar(db, contacto_id).status == "new"


def test_cambiar_estado_sin_csrf_403_y_de_uno_que_no_existe_404(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    client, _ = sesion_de(Role.RECEPTION)

    assert client.put(f"/api/contacts/{contacto_id}/status", json={"status": "contacted", "version": 1}).status_code == 403
    assert recargar(db, contacto_id).status == "new"
    assert cambiar_estado(999999, "contacted").status_code == 404


@pytest.mark.parametrize(
    "cuerpo",
    [{"status": "ganado", "version": 1}, {"status": "contacted"}, {"status": "contacted", "version": 1, "owner_id": 1}],
    ids=["estado inexistente", "sin version", "campo de mas"],
)
def test_cambio_de_estado_mal_formado_422(usuarios, db, cuerpo):
    contacto_id = crear(ANA).json()["id"]
    client, csrf = sesion_de(Role.RECEPTION)

    assert client.put(f"/api/contacts/{contacto_id}/status", json=cuerpo, headers=csrf).status_code == 422
    assert recargar(db, contacto_id).version == 1


# Responsable


def cuenta_de_baja(db, role: Role = Role.RECEPTION) -> User:
    user = User(email="baja@prueba.example.com", password_hash=hash_password(PASSWORD), role=role, active=False)
    db.add(user)
    db.flush()
    return user


def test_posibles_responsables_solo_recepcion_y_admin_activos(usuarios, db):
    cuenta_de_baja(db)
    client, _ = sesion_de(Role.RECEPTION)

    response = client.get("/api/contacts/owners")

    assert response.status_code == 200
    assert response.json() == [
        {"id": usuarios[Role.ADMIN].id, "email": "admin@prueba.example.com"},
        {"id": usuarios[Role.RECEPTION].id, "email": "reception@prueba.example.com"},
    ]


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_ven_los_responsables(usuarios, db, role):
    client, _ = sesion_de(role)

    assert client.get("/api/contacts/owners").status_code == 403


def test_reasignar_el_responsable_y_dejarlo_sin_responsable(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    admin = usuarios[Role.ADMIN]

    reasignado = editar(contacto_id, ficha_de_ana(owner_id=admin.id)).json()
    assert (reasignado["owner_id"], reasignado["owner_email"]) == (admin.id, "admin@prueba.example.com")
    assert listar().json()["items"][0]["owner_email"] == "admin@prueba.example.com"

    sin_responsable = editar(contacto_id, ficha_de_ana(owner_id=None, version=2)).json()
    assert (sin_responsable["owner_id"], sin_responsable["owner_email"]) == (None, None)


@pytest.mark.parametrize("quien", ["profesional", "cliente", "de baja", "inexistente"])
def test_responsable_no_valido_422_y_no_cambia_nada(usuarios, db, quien):
    baja = cuenta_de_baja(db, Role.ADMIN)
    owner_id = {
        "profesional": usuarios[Role.PROFESSIONAL].id,
        "cliente": usuarios[Role.CLIENT].id,
        "de baja": baja.id,
        "inexistente": 999999,
    }[quien]
    contacto_id = crear(ANA).json()["id"]

    response = editar(contacto_id, ficha_de_ana(owner_id=owner_id))

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"type": "dato_no_valido", "loc": ["body", "owner_id"],
         "msg": "El responsable debe ser una cuenta activa de recepción o administración"},
    ]
    contacto = recargar(db, contacto_id)
    assert (contacto.owner_id, contacto.version) == (usuarios[Role.RECEPTION].id, 1)


def test_guardar_sin_tocar_un_responsable_dado_de_baja_no_falla(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    recepcion = usuarios[Role.RECEPTION]
    recepcion.active = False
    db.flush()

    response = editar(contacto_id, ficha_de_ana(first_name="Anna", owner_id=recepcion.id), Role.ADMIN)

    assert response.status_code == 200
    assert response.json()["owner_id"] == recepcion.id


def test_editar_sin_indicar_el_responsable_422(usuarios, db):
    contacto_id = crear(ANA).json()["id"]
    ficha = ficha_de_ana()
    del ficha["owner_id"]  # PUT es la ficha entera: no darlo no significa «sin responsable»

    assert editar(contacto_id, ficha).status_code == 422
    assert recargar(db, contacto_id).owner_id == usuarios[Role.RECEPTION].id


# Filtros de la lista


def test_filtrar_por_un_estado_o_varios(usuarios, db):
    ids = {estado: en_estado(db, estado, nombre) for estado, nombre in [("new", "Ana"), ("contacted", "Eva"), ("lost", "Luz")]}

    perdidos = listar(status="lost").json()
    activos = listar(status=["new", "contacted", "scheduled", "client"]).json()

    assert [c["id"] for c in perdidos["items"]] == [ids["lost"]] and perdidos["total"] == 1
    assert {c["id"] for c in activos["items"]} == {ids["new"], ids["contacted"]} and activos["total"] == 2
    assert listar().json()["total"] == 3  # sin filtro, todos


def test_filtrar_por_responsable_mios_y_sin_asignar(usuarios, db):
    mio = crear(ANA).json()["id"]
    de_admin = crear({**ANA, "first_name": "Eva"}, Role.ADMIN).json()["id"]
    sin_nadie = crear({**ANA, "first_name": "Luz"}).json()["id"]
    assert editar(sin_nadie, ficha_de_ana(first_name="Luz", owner_id=None)).status_code == 200

    assert [c["id"] for c in listar(owner="me").json()["items"]] == [mio]
    assert [c["id"] for c in listar(owner="me", role=Role.ADMIN).json()["items"]] == [de_admin]
    assert [c["id"] for c in listar(owner="none").json()["items"]] == [sin_nadie]


def test_los_filtros_se_combinan_con_la_busqueda(usuarios, db):
    ana = crear(ANA).json()["id"]
    crear({**ANA, "first_name": "Eva"})
    assert cambiar_estado(ana, "contacted").status_code == 200

    assert [c["id"] for c in listar("ana", status="contacted", owner="me").json()["items"]] == [ana]
    assert listar("eva", status="contacted").json() == {"total": 0, "items": []}


@pytest.mark.parametrize("filtro", [{"status": "ganado"}, {"owner": "otro"}, {"owner": "1"}])
def test_filtro_no_valido_422(usuarios, db, filtro):
    assert listar(**filtro).status_code == 422
