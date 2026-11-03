"""Citas contra PostgreSQL real (T16): crear una cita, la hora en la zona de la clínica, la duración
copiada del servicio, el estado del contacto y los permisos por rol.

«Ahora» es siempre el lunes 04/01/2027 a las 10:00 de Nueva York (15:00 UTC), para que las pruebas
no dependan del día en que se ejecutan y alcancen los dos cambios de horario de 2027.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError

from app import appointments_routes
from app.appointments_routes import get_now
from app.auth import CSRF_HEADER
from app.config import get_settings
from app.main import app as fastapi_app
from app.models import Appointment, Contact, ContactStatus, Role, Service, ServiceStaff, User
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
AHORA = datetime(2027, 1, 4, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def reloj_fijo():
    fastapi_app.dependency_overrides[get_now] = lambda: AHORA
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def usuarios(db) -> dict[Role, User]:
    creados = {}
    for role in Role:
        user = User(email=f"{role.value}@prueba.example.com", password_hash=hash_password(PASSWORD), role=role)
        db.add(user)
        creados[role] = user
    db.flush()
    return creados


def cuenta(db, email: str, role: Role, active: bool = True) -> User:
    user = User(email=email, password_hash=hash_password(PASSWORD), role=role, active=active)
    db.add(user)
    db.flush()
    return user


def contacto(db, status: ContactStatus = ContactStatus.NEW, email: str = "ana@example.com") -> Contact:
    contact = Contact(first_name="Ana", last_name="Lopez", email=email, source="instagram", status=status)
    db.add(contact)
    db.flush()
    return contact


def servicio(db, personas: list[User], minutos: int = 60, nombre: str = "Botox", active: bool = True) -> Service:
    service = Service(name=nombre, duration_minutes=minutos, active=active)
    db.add(service)
    db.flush()
    db.add_all(ServiceStaff(service_id=service.id, user_id=p.id) for p in personas)
    db.flush()
    return service


@pytest.fixture
def escena(db, usuarios):
    """Un contacto nuevo y un servicio de 60 minutos que realiza el profesional."""
    return contacto(db), servicio(db, [usuarios[Role.PROFESSIONAL]]), usuarios[Role.PROFESSIONAL]


def datos(escena, starts_at: str = "2027-01-11T09:30", **cambios) -> dict:
    contact, service, persona = escena
    return {"contact_id": contact.id, "service_id": service.id, "staff_id": persona.id, "starts_at": starts_at, **cambios}


def sesion_de(role: Role) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(fastapi_app)
    response = client.post("/api/auth/login", json={"email": f"{role.value}@prueba.example.com", "password": PASSWORD})
    assert response.status_code == 200
    return client, {CSRF_HEADER: response.json()["csrf_token"]}


def crear(cuerpo: dict, role: Role = Role.RECEPTION):
    client, csrf = sesion_de(role)
    return client.post("/api/appointments", json=cuerpo, headers=csrf)


def contar(db) -> int:
    return db.scalar(select(func.count()).select_from(Appointment))


def error_de(response, campo: str) -> str:
    return next(e["msg"] for e in response.json()["detail"] if e["loc"] == ["body", campo])


# --- Alta y permisos --------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_crean_una_cita(db, usuarios, escena, role):
    contact, service, persona = escena

    response = crear(datos(escena), role)

    assert response.status_code == 201
    cita = response.json()
    assert cita | {"id": 0, "created_at": ""} == {
        "id": 0,
        "contact_id": contact.id,
        "service_id": service.id,
        "staff_id": persona.id,
        # En la hora de la clínica, con su desfase (invierno: −5 h).
        "starts_at": "2027-01-11T09:30:00-05:00",
        "ends_at": "2027-01-11T10:30:00-05:00",
        "duration_minutes": 60,
        "status": "scheduled",
        "version": 1,
        "created_at": "",
    }
    guardada = db.get(Appointment, cita["id"])
    # En la BD, el instante: 9:30 en Nueva York son las 14:30 UTC.
    assert guardada.starts_at == datetime(2027, 1, 11, 14, 30, tzinfo=UTC)
    assert guardada.ends_at == datetime(2027, 1, 11, 15, 30, tzinfo=UTC)
    assert guardada.created_by_id == usuarios[role].id


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_crean_citas(db, escena, role):
    response = crear(datos(escena), role)

    assert response.status_code == 403
    assert contar(db) == 0
    assert escena[0].status == ContactStatus.NEW


def test_sin_token_csrf_403_y_no_se_guarda(db, escena):
    client, _ = sesion_de(Role.RECEPTION)

    assert client.post("/api/appointments", json=datos(escena)).status_code == 403
    assert contar(db) == 0


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL])
def test_la_realiza_cualquier_persona_del_servicio(db, usuarios, role):
    # El jefe o la recepcionista también pueden realizar servicios (T15).
    escena = contacto(db), servicio(db, [usuarios[role]]), usuarios[role]

    response = crear(datos(escena))

    assert response.status_code == 201
    assert response.json()["staff_id"] == usuarios[role].id


def test_con_varias_personas_se_elige_una(db, usuarios):
    equipo = [usuarios[Role.ADMIN], usuarios[Role.PROFESSIONAL]]
    contact, service = contacto(db), servicio(db, equipo)

    response = crear(datos((contact, service, usuarios[Role.ADMIN])))

    assert response.status_code == 201
    assert response.json()["staff_id"] == usuarios[Role.ADMIN].id


# --- Duración copiada del servicio -------------------------------------------------


def test_la_duracion_se_copia_y_no_cambia_con_el_servicio(db, escena):
    contact, service, persona = escena
    cita = crear(datos(escena)).json()

    db.execute(update(Service).where(Service.id == service.id).values(duration_minutes=90))
    db.flush()

    guardada = db.get(Appointment, cita["id"], populate_existing=True)
    assert guardada.duration_minutes == 60
    assert guardada.ends_at - guardada.starts_at == timedelta(minutes=60)
    # Las citas nuevas sí toman la duración nueva.
    otra = crear(datos(escena, starts_at="2027-01-12T09:30")).json()
    assert otra["duration_minutes"] == 90
    assert otra["ends_at"] == "2027-01-12T11:00:00-05:00"


# --- Estado del contacto ------------------------------------------------------------


@pytest.mark.parametrize("origen", [ContactStatus.NEW, ContactStatus.CONTACTED])
def test_nuevo_y_contactado_pasan_a_cita_agendada(db, usuarios, origen):
    contact = contacto(db, origen)
    escena = contact, servicio(db, [usuarios[Role.PROFESSIONAL]]), usuarios[Role.PROFESSIONAL]

    assert crear(datos(escena)).status_code == 201

    db.refresh(contact)
    assert contact.status == ContactStatus.SCHEDULED
    # Cambiar el estado es cambiar la ficha (T13/T14): sube la versión y consta quién lo hizo.
    assert contact.version == 2
    assert contact.updated_by_id == usuarios[Role.RECEPTION].id


@pytest.mark.parametrize("origen", [ContactStatus.SCHEDULED, ContactStatus.CLIENT])
def test_cita_agendada_y_cliente_se_quedan_igual(db, usuarios, origen):
    contact = contacto(db, origen)
    escena = contact, servicio(db, [usuarios[Role.PROFESSIONAL]]), usuarios[Role.PROFESSIONAL]

    assert crear(datos(escena)).status_code == 201

    db.refresh(contact)
    assert contact.status == origen
    assert contact.version == 1
    assert contact.updated_by_id is None


def test_segunda_cita_del_mismo_contacto(db, escena):
    contact = escena[0]
    assert crear(datos(escena)).status_code == 201
    assert crear(datos(escena, starts_at="2027-01-12T09:30")).status_code == 201

    db.refresh(contact)
    assert contact.status == ContactStatus.SCHEDULED
    assert contact.version == 2  # solo la primera cambió el estado
    assert contar(db) == 2


def test_contacto_perdido_422_hay_que_reabrirlo(db, usuarios):
    contact = contacto(db, ContactStatus.LOST)
    escena = contact, servicio(db, [usuarios[Role.PROFESSIONAL]]), usuarios[Role.PROFESSIONAL]

    response = crear(datos(escena))

    assert response.status_code == 422
    assert error_de(response, "contact_id") == "El contacto está «Perdido»: reábrelo antes de darle una cita"
    assert contar(db) == 0
    db.refresh(contact)
    assert (contact.status, contact.version) == (ContactStatus.LOST, 1)


def test_quien_editaba_la_ficha_antes_de_la_cita_recibe_409(db, escena):
    # La cita sube la versión del contacto: un cambio con la versión leída antes no lo pisa.
    contact = escena[0]
    assert crear(datos(escena)).status_code == 201

    client, csrf = sesion_de(Role.RECEPTION)
    response = client.put(f"/api/contacts/{contact.id}/status", json={"status": "lost", "version": 1}, headers=csrf)

    assert response.status_code == 409
    db.refresh(contact)
    assert contact.status == ContactStatus.SCHEDULED


# --- Contacto, servicio y persona no válidos ----------------------------------------


def test_contacto_inexistente_422(db, escena):
    response = crear(datos(escena, contact_id=999_999))

    assert response.status_code == 422
    assert error_de(response, "contact_id") == "El contacto no existe"
    assert contar(db) == 0


def test_servicio_desactivado_o_inexistente_422(db, usuarios, escena):
    desactivado = servicio(db, [usuarios[Role.PROFESSIONAL]], nombre="Peel", active=False)
    for service_id in (desactivado.id, 999_999):
        response = crear(datos(escena, service_id=service_id))

        assert response.status_code == 422
        assert error_de(response, "service_id") == "El servicio no existe o está desactivado"
    assert contar(db) == 0
    assert escena[0].status == ContactStatus.NEW


def test_persona_que_no_realiza_el_servicio_422(db, usuarios, escena):
    # Una cuenta interna activa que realiza otro servicio, pero no este.
    servicio(db, [usuarios[Role.ADMIN]], nombre="Peel")
    baja = cuenta(db, "baja@prueba.example.com", Role.PROFESSIONAL, active=False)
    # Asignada a este servicio, pero desactivada después.
    db.add(ServiceStaff(service_id=escena[1].id, user_id=baja.id))
    db.flush()
    for staff_id in (usuarios[Role.ADMIN].id, baja.id, usuarios[Role.CLIENT].id, 999_999):
        response = crear(datos(escena, staff_id=staff_id))

        assert response.status_code == 422, staff_id
        assert error_de(response, "staff_id") == "Esa persona no realiza este servicio o su cuenta no está activa"
    assert contar(db) == 0


def test_un_cliente_asignado_a_mano_en_la_bd_tampoco_vale(db, usuarios, escena):
    # La API de servicios no deja asignar clientes; si alguien lo hiciera en la BD, la cita lo frena.
    db.add(ServiceStaff(service_id=escena[1].id, user_id=usuarios[Role.CLIENT].id))
    db.flush()

    response = crear(datos(escena, staff_id=usuarios[Role.CLIENT].id))

    assert response.status_code == 422
    assert contar(db) == 0


# --- La hora de inicio ----------------------------------------------------------------

FORMATO = "Indica la fecha y la hora de inicio como AAAA-MM-DDTHH:MM, en hora de la clínica"


@pytest.mark.parametrize(
    "starts_at, mensaje",
    [
        ("2027-01-11T09:30:00", FORMATO),
        ("2027-01-11T09:30-05:00", FORMATO),
        ("2027-01-11T14:30Z", FORMATO),
        ("2027-01-11", FORMATO),
        ("", FORMATO),
        (1_800_000_000, FORMATO),
        (None, FORMATO),
        ("2027-02-30T09:30", "Esa fecha u hora no existe"),
        ("2027-01-11T09:32", "La hora de inicio debe ir en múltiplos de 5 minutos (9:00, 9:05, 9:10…)"),
        ("2027-01-04T09:55", "La cita no puede empezar en el pasado"),
        ("2028-01-04T10:05", "La cita no puede ser para dentro de más de 365 días"),
        ("2027-03-14T02:30", "Esa hora no existe ese día: el reloj se adelanta una hora por el cambio de horario"),
        ("2027-11-07T01:30", "Esa hora se repite ese día por el cambio de horario: elige otra"),
    ],
)
def test_hora_no_valida_422(db, escena, starts_at, mensaje):
    response = crear(datos(escena, starts_at=starts_at))

    assert response.status_code == 422
    assert error_de(response, "starts_at") == mensaje
    assert contar(db) == 0
    assert escena[0].status == ContactStatus.NEW


@pytest.mark.parametrize("starts_at", ["2027-01-04T10:00", "2028-01-04T10:00"], ids=["ahora mismo", "dentro de 365 días"])
def test_limites_de_la_hora_incluidos(db, escena, starts_at):
    assert crear(datos(escena, starts_at=starts_at)).status_code == 201


@pytest.mark.parametrize(
    "starts_at, minutos, inicio, fin, utc",
    [
        # Verano: −4 h.
        ("2027-07-01T09:30", 60, "2027-07-01T09:30:00-04:00", "2027-07-01T10:30:00-04:00", datetime(2027, 7, 1, 13, 30, tzinfo=UTC)),
        # Cruza el adelanto de primavera: 60 minutos reales, el reloj marca dos horas más.
        ("2027-03-14T01:30", 60, "2027-03-14T01:30:00-05:00", "2027-03-14T03:30:00-04:00", datetime(2027, 3, 14, 6, 30, tzinfo=UTC)),
        # Cruza el retraso de otoño: 90 minutos reales y termina a la segunda 1:00.
        ("2027-11-07T00:30", 90, "2027-11-07T00:30:00-04:00", "2027-11-07T01:00:00-05:00", datetime(2027, 11, 7, 4, 30, tzinfo=UTC)),
        # Cruza la medianoche.
        ("2027-01-11T23:30", 60, "2027-01-11T23:30:00-05:00", "2027-01-12T00:30:00-05:00", datetime(2027, 1, 12, 4, 30, tzinfo=UTC)),
    ],
)
def test_hora_local_y_cambios_de_horario(db, usuarios, starts_at, minutos, inicio, fin, utc):
    escena = contacto(db), servicio(db, [usuarios[Role.PROFESSIONAL]], minutos=minutos), usuarios[Role.PROFESSIONAL]

    response = crear(datos(escena, starts_at=starts_at))

    assert response.status_code == 201
    assert (response.json()["starts_at"], response.json()["ends_at"]) == (inicio, fin)
    guardada = db.get(Appointment, response.json()["id"])
    assert guardada.starts_at == utc
    assert guardada.ends_at - guardada.starts_at == timedelta(minutes=minutos)


def test_la_zona_sale_de_la_configuracion(db, escena, monkeypatch):
    otra = get_settings().model_copy(update={"clinic_timezone": "America/Los_Angeles"})
    monkeypatch.setattr(appointments_routes, "get_settings", lambda: otra)

    response = crear(datos(escena))

    assert response.status_code == 201
    assert response.json()["starts_at"] == "2027-01-11T09:30:00-08:00"
    assert db.get(Appointment, response.json()["id"]).starts_at == datetime(2027, 1, 11, 17, 30, tzinfo=UTC)


# --- Forma de la petición -------------------------------------------------------------


@pytest.mark.parametrize(
    "extra", [{"duration_minutes": 5}, {"ends_at": "2027-01-11T09:35"}, {"status": "completed"}, {"version": 7}, {"notes": "x"}]
)
def test_campos_de_mas_422(db, escena, extra):
    assert crear(datos(escena, **extra)).status_code == 422
    assert contar(db) == 0


@pytest.mark.parametrize("campo", ["contact_id", "service_id", "staff_id"])
@pytest.mark.parametrize("forma", ["texto", "decimal", "booleano", "nulo"])
def test_los_ids_son_enteros_de_verdad(db, escena, campo, forma):
    # Con el id real escrito de otra forma: si la API lo convirtiera, la cita sí se crearía.
    real = datos(escena)[campo]
    valor = {"texto": str(real), "decimal": real + 0.0, "booleano": True, "nulo": None}[forma]

    response = crear(datos(escena, **{campo: valor}))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", campo]
    assert contar(db) == 0


@pytest.mark.parametrize("campo", ["contact_id", "service_id", "staff_id", "starts_at"])
def test_falta_un_campo_422(db, escena, campo):
    cuerpo = datos(escena)
    del cuerpo[campo]

    assert crear(cuerpo).status_code == 422
    assert contar(db) == 0


# --- La BD repite las reglas ------------------------------------------------------------


@pytest.mark.parametrize(
    "inicio, fin, minutos, estado, version",
    [
        ("2027-01-11 14:30+00", "2027-01-11 15:00+00", 60, "scheduled", 1),  # el fin no cuadra con la duración
        ("2027-01-11 14:30+00", "2027-01-11 14:37+00", 7, "scheduled", 1),  # duración no múltiplo de 5
        ("2027-01-11 14:30+00", "2027-01-11 18:35+00", 245, "scheduled", 1),  # más de 4 horas
        ("2027-01-11 14:30+00", "2027-01-11 15:30+00", 60, "pending", 1),  # estado desconocido
        ("2027-01-11 14:30+00", "2027-01-11 15:30+00", 60, "scheduled", 0),
    ],
)
def test_la_bd_repite_las_reglas(db, escena, inicio, fin, minutos, estado, version):
    contact, service, persona = escena
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO appointments (contact_id, service_id, staff_id, starts_at, ends_at, duration_minutes,"
                    " status, version) VALUES (:c, :s, :p, :inicio, :fin, :m, :estado, :v)"
                ),
                {"c": contact.id, "s": service.id, "p": persona.id, "inicio": inicio, "fin": fin, "m": minutos,
                 "estado": estado, "v": version},
            )


@pytest.mark.parametrize("tabla", [Contact, Service, User])
def test_no_se_borra_nada_con_citas(db, escena, tabla):
    # Contactos, servicios y cuentas no se borran (se desactivan); con citas, la BD lo impide.
    contact, service, persona = escena
    assert crear(datos(escena)).status_code == 201
    objetivo = {Contact: contact.id, Service: service.id, User: persona.id}[tabla]

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(delete(tabla).where(tabla.id == objetivo))
    assert contar(db) == 1
