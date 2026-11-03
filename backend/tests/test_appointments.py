"""Citas contra PostgreSQL real (T16): crear una cita, la hora en la zona de la clínica, la duración
copiada del servicio, el estado del contacto y los permisos por rol.

«Ahora» es siempre el lunes 04/01/2027 a las 10:00 de Nueva York (15:00 UTC), para que las pruebas
no dependan del día en que se ejecutan y alcancen los dos cambios de horario de 2027.
"""

import itertools
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
        "cancel_reason": None,
        "cancel_note": None,
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


# --- Solapamientos (T17) ----------------------------------------------------------------

CHOQUE = "Esa persona ya tiene una cita de 9:30 a 10:30"


@pytest.fixture
def ocupada(db, escena):
    """La persona de la escena ya tiene una cita de 9:30 a 10:30 el 11/01/2027 (guardada por la API)."""
    response = crear(datos(escena))
    assert response.status_code == 201
    return response.json()


_otros = itertools.count(1)


def para_otro(db, escena, persona: User | None = None, minutos: int = 60, **cambios) -> dict:
    """Otra cita: otro contacto y, si hace falta, otro servicio con la duración indicada."""
    otro = contacto(db, email=f"otro{next(_otros)}@example.com")
    persona = persona or escena[2]
    service = escena[1] if minutos == 60 and persona is escena[2] else servicio(db, [persona], minutos, f"S{minutos} {persona.id}")
    return datos((otro, service, persona), **cambios)


@pytest.mark.parametrize(
    "starts_at, minutos",
    [
        ("2027-01-11T09:30", 60),  # la misma franja
        ("2027-01-11T09:00", 60),  # termina dentro
        ("2027-01-11T10:00", 60),  # empieza dentro
        ("2027-01-11T09:45", 15),  # dentro del todo
        ("2027-01-11T09:00", 120),  # la cubre entera
        ("2027-01-11T10:25", 5),  # los últimos 5 minutos
    ],
)
def test_misma_persona_franja_que_se_pisa_409(db, escena, ocupada, starts_at, minutos):
    cuerpo = para_otro(db, escena, minutos=minutos, starts_at=starts_at)

    response = crear(cuerpo)

    assert response.status_code == 409
    assert response.json() == {"detail": CHOQUE}
    assert contar(db) == 1
    # Nada a medias: el otro contacto no pasa a «Cita agendada».
    otro = db.get(Contact, cuerpo["contact_id"], populate_existing=True)
    assert (otro.status, otro.version) == (ContactStatus.NEW, 1)


@pytest.mark.parametrize("starts_at", ["2027-01-11T08:30", "2027-01-11T10:30"], ids=["acaba justo al empezar", "empieza justo al acabar"])
def test_citas_seguidas_si(db, escena, ocupada, starts_at):
    assert crear(para_otro(db, escena, starts_at=starts_at)).status_code == 201


def test_otra_persona_a_la_misma_hora_si(db, usuarios, escena, ocupada):
    assert crear(para_otro(db, escena, persona=usuarios[Role.ADMIN])).status_code == 201


def test_la_misma_clienta_con_dos_personas_a_la_vez_si(db, usuarios, escena, ocupada):
    # Tinte con una persona y, mientras, pedicura con otra (decisión T17): no hay regla por contacto.
    pedicura = servicio(db, [usuarios[Role.RECEPTION]], 30, "Pedicure")

    response = crear(datos((escena[0], pedicura, usuarios[Role.RECEPTION]), starts_at="2027-01-11T09:45"))

    assert response.status_code == 201


def test_la_cancelada_libera_la_franja(db, escena, ocupada):
    # Marcada en la BD; la ruta para cancelar (T19) tiene sus propias pruebas más abajo.
    db.execute(update(Appointment).where(Appointment.id == ocupada["id"]).values(status="cancelled", cancel_reason="other"))
    db.flush()

    assert crear(para_otro(db, escena)).status_code == 201


@pytest.mark.parametrize("estado", ["completed", "no_show"])
def test_realizada_y_no_presentado_siguen_ocupando(db, escena, ocupada, estado):
    db.execute(update(Appointment).where(Appointment.id == ocupada["id"]).values(status=estado))
    db.commit()

    response = crear(para_otro(db, escena))

    assert response.status_code == 409
    assert response.json() == {"detail": CHOQUE}


def test_el_aviso_lleva_la_fecha_si_la_otra_empieza_otro_dia(db, escena):
    assert crear(datos(escena, starts_at="2027-01-11T23:30")).status_code == 201

    response = crear(para_otro(db, escena, starts_at="2027-01-12T00:00"))

    assert response.status_code == 409
    assert response.json() == {"detail": "Esa persona ya tiene una cita el 11/01/2027 de 23:30 a 0:30"}


def test_el_aviso_va_en_la_hora_de_la_clinica_tambien_en_verano(db, escena):
    assert crear(datos(escena, starts_at="2027-07-01T09:30")).status_code == 201

    response = crear(para_otro(db, escena, starts_at="2027-07-01T10:00"))

    assert response.json() == {"detail": CHOQUE}


def test_tras_un_choque_se_puede_seguir_reservando(db, escena, ocupada):
    assert crear(para_otro(db, escena)).status_code == 409

    response = crear(para_otro(db, escena, starts_at="2027-01-11T11:00"))

    assert response.status_code == 201
    assert contar(db) == 2


def _insertar(db, escena, inicio: str, fin: str, minutos: int = 60, estado: str = "scheduled"):
    contact, service, persona = escena
    db.execute(
        text(
            "INSERT INTO appointments (contact_id, service_id, staff_id, starts_at, ends_at, duration_minutes, status,"
            " cancel_reason) VALUES (:c, :s, :p, :inicio, :fin, :m, :estado, :motivo)"
        ),
        {"c": contact.id, "s": service.id, "p": persona.id, "inicio": inicio, "fin": fin, "m": minutos, "estado": estado,
         "motivo": "other" if estado == "cancelled" else None},
    )


def test_la_bd_impide_el_solapamiento_aunque_se_salte_la_api(db, escena):
    _insertar(db, escena, "2027-01-11 14:30+00", "2027-01-11 15:30+00")
    # Seguidas y canceladas, sí.
    _insertar(db, escena, "2027-01-11 15:30+00", "2027-01-11 16:30+00")
    _insertar(db, escena, "2027-01-11 15:00+00", "2027-01-11 16:00+00", estado="cancelled")

    with pytest.raises(IntegrityError, match="ex_appointments_staff_overlap"):
        with db.begin_nested():
            _insertar(db, escena, "2027-01-11 15:00+00", "2027-01-11 16:00+00")


def test_la_bd_impide_reactivar_una_cancelada_que_se_pisa(db, escena):
    # Importa para T19: deshacer una cancelación también debe respetar la regla.
    _insertar(db, escena, "2027-01-11 14:30+00", "2027-01-11 15:30+00", estado="cancelled")
    _insertar(db, escena, "2027-01-11 15:00+00", "2027-01-11 16:00+00")

    with pytest.raises(IntegrityError, match="ex_appointments_staff_overlap"):
        with db.begin_nested():
            db.execute(
                update(Appointment).where(Appointment.status == "cancelled").values(status="scheduled", cancel_reason=None)
            )


def test_el_aviso_nombra_la_cita_que_de_verdad_choca(db, usuarios, escena):
    # Alrededor de la que choca (9:30-10:30) hay citas que empiezan antes y no cuentan: una
    # cancelada de la misma persona, una de otra persona y una seguida que acaba a las 9:30.
    cancelada = crear(datos(escena, starts_at="2027-01-11T09:00")).json()
    db.execute(update(Appointment).where(Appointment.id == cancelada["id"]).values(status="cancelled", cancel_reason="other"))
    db.commit()
    assert crear(para_otro(db, escena, starts_at="2027-01-11T08:30")).status_code == 201
    assert crear(para_otro(db, escena, starts_at="2027-01-11T09:30")).status_code == 201
    assert crear(para_otro(db, escena, persona=usuarios[Role.ADMIN], starts_at="2027-01-11T09:10")).status_code == 201

    response = crear(para_otro(db, escena, starts_at="2027-01-11T09:30"))

    assert response.status_code == 409
    assert response.json() == {"detail": CHOQUE}


# --- Agenda de un día (T18) ---------------------------------------------------------------


def agenda(role: Role = Role.RECEPTION, **parametros):
    client, _ = sesion_de(role)
    return client.get("/api/appointments", params=parametros)


def test_la_agenda_del_dia_por_hora_con_los_nombres(db, usuarios, escena):
    contact, service, persona = escena
    tarde = crear(datos(escena, starts_at="2027-01-11T16:00")).json()
    manana = crear(para_otro(db, escena, starts_at="2027-01-11T09:30")).json()
    crear(para_otro(db, escena, starts_at="2027-01-12T09:30"))  # otro día: no sale

    response = agenda(date="2027-01-11")

    assert response.status_code == 200
    citas = response.json()
    assert [c["id"] for c in citas] == [manana["id"], tarde["id"]]
    assert citas[1] == tarde | {
        "contact_name": "Ana Lopez",
        "service_name": "Botox",
        "staff_email": "professional@prueba.example.com",
    }
    assert citas[0]["starts_at"] == "2027-01-11T09:30:00-05:00"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_ven_la_agenda(db, escena, role):
    crear(datos(escena))

    assert len(agenda(role, date="2027-01-11").json()) == 1


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_ven_la_agenda_todavia(db, escena, role):
    assert agenda(role, date="2027-01-11").status_code == 403


def test_filtro_por_persona_y_por_contacto(db, usuarios, escena):
    crear(datos(escena))
    de_admin = crear(para_otro(db, escena, persona=usuarios[Role.ADMIN], starts_at="2027-01-11T12:00")).json()

    assert [c["id"] for c in agenda(date="2027-01-11", staff_id=usuarios[Role.ADMIN].id).json()] == [de_admin["id"]]
    assert [c["contact_id"] for c in agenda(date="2027-01-11", contact_id=escena[0].id).json()] == [escena[0].id]
    assert agenda(date="2027-01-11", staff_id=999_999).json() == []


def test_la_cita_que_cruza_la_medianoche_sale_en_los_dos_dias(db, escena):
    cita = crear(datos(escena, starts_at="2027-01-11T23:30")).json()

    for dia in ("2027-01-11", "2027-01-12"):
        assert [c["id"] for c in agenda(date=dia).json()] == [cita["id"]], dia
    # La que acaba justo a medianoche no ocupa el día siguiente: [inicio, fin).
    assert crear(para_otro(db, escena, starts_at="2027-01-12T23:00")).status_code == 201
    assert len(agenda(date="2027-01-13").json()) == 0


def test_el_dia_del_cambio_de_horario_tiene_23_horas(db, escena):
    # 14/03/2027: de 0:00 a 0:00 del día siguiente son 23 horas reales; las dos citas son de ese día.
    primera = crear(datos(escena, starts_at="2027-03-14T00:00")).json()
    ultima = crear(para_otro(db, escena, starts_at="2027-03-14T22:55", minutos=5)).json()
    crear(para_otro(db, escena, starts_at="2027-03-15T00:00"))

    assert [c["id"] for c in agenda(date="2027-03-14").json()] == [primera["id"], ultima["id"]]


@pytest.mark.parametrize("dia", ["2027-02-30", "11/01/2027", "mañana", ""])
def test_dia_no_valido_422(db, escena, dia):
    assert agenda(date=dia).status_code == 422


def test_sin_dia_422(db, escena):
    assert agenda().status_code == 422


# --- Reprogramar (T19) ----------------------------------------------------------------------

CAMBIADA = "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo."


def reprogramar(cita: dict, role: Role = Role.RECEPTION, **cambios):
    """PUT con la persona, la hora y la versión de la cita, cambiando lo que se indique."""
    client, csrf = sesion_de(role)
    cuerpo = {"staff_id": cita["staff_id"], "starts_at": "2027-01-12T09:30", "version": cita["version"], **cambios}
    return client.put(f"/api/appointments/{cita['id']}", json=cuerpo, headers=csrf)


def cancelar(cita: dict, role: Role = Role.RECEPTION, **cambios):
    client, csrf = sesion_de(role)
    cuerpo = {"version": cita["version"], "reason": "client_request", **cambios}
    return client.post(f"/api/appointments/{cita['id']}/cancel", json=cuerpo, headers=csrf)


def en_bd(db, cita: dict) -> Appointment:
    return db.get(Appointment, cita["id"], populate_existing=True)


def marcar(db, cita: dict, **valores):
    """Cambia la cita directamente en la BD (otra persona, o estados que llegarán después)."""
    db.execute(update(Appointment).where(Appointment.id == cita["id"]).values(**valores))
    db.commit()


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_reprograman_una_cita(db, usuarios, escena, ocupada, role):
    response = reprogramar(ocupada, role, starts_at="2027-01-12T16:15")

    assert response.status_code == 200
    assert response.json() | {"created_at": ""} == ocupada | {
        "starts_at": "2027-01-12T16:15:00-05:00",
        "ends_at": "2027-01-12T17:15:00-05:00",
        "version": 2,
        "created_at": "",
    }
    guardada = en_bd(db, ocupada)
    assert guardada.starts_at == datetime(2027, 1, 12, 21, 15, tzinfo=UTC)
    assert guardada.updated_by_id == usuarios[role].id


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_reprograman_ni_cancelan(db, escena, ocupada, role):
    assert reprogramar(ocupada, role).status_code == 403
    assert cancelar(ocupada, role).status_code == 403
    guardada = en_bd(db, ocupada)
    assert (guardada.status, guardada.version, guardada.starts_at.hour) == ("scheduled", 1, 14)


def test_sin_token_csrf_no_se_reprograma_ni_se_cancela(db, escena, ocupada):
    client, _ = sesion_de(Role.RECEPTION)

    put = client.put(f"/api/appointments/{ocupada['id']}", json={"staff_id": ocupada["staff_id"], "starts_at": "2027-01-12T09:30", "version": 1})
    post = client.post(f"/api/appointments/{ocupada['id']}/cancel", json={"version": 1, "reason": "other"})

    assert (put.status_code, post.status_code) == (403, 403)
    assert en_bd(db, ocupada).version == 1


def test_cita_que_no_existe_404(db, escena, ocupada):
    otra = ocupada | {"id": ocupada["id"] + 1000}

    assert reprogramar(otra).status_code == 404
    assert cancelar(otra).json() == {"detail": "Cita no encontrada"}


def test_se_puede_cambiar_a_otra_persona_del_servicio(db, usuarios, escena):
    contact, _, persona = escena
    equipo = servicio(db, [persona, usuarios[Role.ADMIN]], 30, "Peel")
    cita = crear(datos((contact, equipo, persona))).json()

    response = reprogramar(cita, staff_id=usuarios[Role.ADMIN].id, starts_at="2027-01-11T09:30")

    assert response.status_code == 200
    assert response.json()["staff_id"] == usuarios[Role.ADMIN].id
    # La franja que deja la otra persona queda libre.
    assert crear(datos((contacto(db, email="bea@example.com"), equipo, persona))).status_code == 201


@pytest.mark.parametrize("quien", ["no realiza el servicio", "desactivada", "cliente", "no existe"])
def test_persona_no_valida_al_reprogramar_422(db, usuarios, escena, ocupada, quien):
    personas = {
        "no realiza el servicio": lambda: usuarios[Role.ADMIN].id,
        "desactivada": lambda: escena[2].id,
        "cliente": lambda: usuarios[Role.CLIENT].id,
        "no existe": lambda: 999_999,
    }
    if quien == "desactivada":
        db.execute(update(User).where(User.id == escena[2].id).values(active=False))
        db.commit()
    if quien == "cliente":
        db.add(ServiceStaff(service_id=escena[1].id, user_id=usuarios[Role.CLIENT].id))
        db.commit()

    response = reprogramar(ocupada, staff_id=personas[quien]())

    assert response.status_code == 422
    assert error_de(response, "staff_id") == "Esa persona no realiza este servicio o su cuenta no está activa"
    assert en_bd(db, ocupada).version == 1


# Regresión de T17 al editar: la cita no choca consigo misma, pero sí con las demás.


@pytest.mark.parametrize(
    "starts_at", ["2027-01-11T10:00", "2027-01-11T09:00", "2027-01-11T09:30"], ids=["media hora más tarde", "media hora antes", "la misma hora"]
)
def test_moverla_dentro_de_su_propia_franja_si(db, escena, ocupada, starts_at):
    # «Llego tarde, ¿me la pasas a las 10?»: la franja nueva pisa la antigua, que es la misma cita.
    response = reprogramar(ocupada, starts_at=starts_at)

    assert response.status_code == 200
    assert contar(db) == 1


def test_moverla_encima_de_otra_409_y_nombra_la_otra(db, escena, ocupada):
    # Ana 9:30-10:30 y otra de 10:45 a 11:45. A las 10:00, Ana pisa su propia franja (que no
    # cuenta) y la otra (que sí): el aviso debe nombrar la de las 10:45, no la de las 9:30.
    assert crear(para_otro(db, escena, starts_at="2027-01-11T10:45")).status_code == 201

    response = reprogramar(ocupada, starts_at="2027-01-11T10:00")

    assert response.status_code == 409
    assert response.json() == {"detail": "Esa persona ya tiene una cita de 10:45 a 11:45"}
    guardada = en_bd(db, ocupada)
    assert (guardada.starts_at, guardada.version) == (datetime(2027, 1, 11, 14, 30, tzinfo=UTC), 1)


def test_cambiar_a_una_persona_ocupada_409(db, usuarios, escena):
    contact, _, persona = escena
    admin = usuarios[Role.ADMIN]
    equipo = servicio(db, [persona, admin], 60, "Peel")
    cita = crear(datos((contact, equipo, persona))).json()
    assert crear(datos((contacto(db, email="bea@example.com"), equipo, admin), starts_at="2027-01-11T09:00")).status_code == 201

    response = reprogramar(cita, staff_id=admin.id, starts_at="2027-01-11T09:30")

    assert response.status_code == 409
    assert response.json() == {"detail": "Esa persona ya tiene una cita de 9:00 a 10:00"}


def test_moverla_a_la_franja_de_una_cancelada_si(db, escena, ocupada):
    otra = crear(para_otro(db, escena, starts_at="2027-01-11T14:00")).json()
    assert cancelar(otra).status_code == 200

    assert reprogramar(ocupada, starts_at="2027-01-11T14:00").status_code == 200


def test_tras_reprogramar_la_franja_antigua_queda_libre(db, escena, ocupada):
    assert reprogramar(ocupada, starts_at="2027-01-11T15:00").status_code == 200

    assert crear(para_otro(db, escena, starts_at="2027-01-11T09:30")).status_code == 201


def test_conserva_la_duracion_copiada_aunque_cambie_el_servicio(db, escena, ocupada):
    db.execute(update(Service).where(Service.id == escena[1].id).values(duration_minutes=90))
    db.commit()

    response = reprogramar(ocupada, starts_at="2027-01-12T09:00")

    assert (response.json()["duration_minutes"], response.json()["ends_at"]) == (60, "2027-01-12T10:00:00-05:00")


def test_reprogramar_cruzando_el_cambio_de_horario(db, escena, ocupada):
    # 14/03/2027: de la 1:30 a las 3:30 del reloj hay una hora real.
    response = reprogramar(ocupada, starts_at="2027-03-14T01:30")

    assert (response.json()["starts_at"], response.json()["ends_at"]) == ("2027-03-14T01:30:00-05:00", "2027-03-14T03:30:00-04:00")


@pytest.mark.parametrize(
    "starts_at, mensaje",
    [
        ("2027-01-04T09:55", "La cita no puede empezar en el pasado"),
        ("2028-01-05T10:00", "La cita no puede ser para dentro de más de 365 días"),
        ("2027-03-14T02:30", "Esa hora no existe ese día: el reloj se adelanta una hora por el cambio de horario"),
        ("2027-11-07T01:30", "Esa hora se repite ese día por el cambio de horario: elige otra"),
        ("2027-01-12T09:32", "La hora de inicio debe ir en múltiplos de 5 minutos (9:00, 9:05, 9:10…)"),
        ("2027-01-12 09:30", appointments_routes.START_FORMAT_MESSAGE),
    ],
)
def test_la_hora_nueva_cumple_las_reglas_del_alta(db, escena, ocupada, starts_at, mensaje):
    response = reprogramar(ocupada, starts_at=starts_at)

    assert response.status_code == 422
    assert error_de(response, "starts_at") == mensaje
    assert en_bd(db, ocupada).version == 1


def test_contacto_perdido_no_se_reprograma_pero_si_se_cancela(db, escena, ocupada):
    db.execute(update(Contact).where(Contact.id == escena[0].id).values(status=ContactStatus.LOST))
    db.commit()

    response = reprogramar(ocupada)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "El contacto está «Perdido»: reábrelo antes de cambiar la cita, o cancélala"
    assert cancelar(ocupada).status_code == 200
    assert db.get(Contact, escena[0].id, populate_existing=True).status == ContactStatus.LOST


def test_servicio_desactivado_no_se_reprograma_pero_si_se_cancela(db, escena, ocupada):
    db.execute(update(Service).where(Service.id == escena[1].id).values(active=False))
    db.commit()

    response = reprogramar(ocupada)

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"type": "dato_no_valido", "loc": ["body"], "msg": "El servicio está desactivado: cancela la cita y da otra"}
    ]
    assert cancelar(ocupada).status_code == 200


def test_reprogramar_no_cambia_el_contacto(db, escena, ocupada):
    antes = db.get(Contact, escena[0].id, populate_existing=True)
    estado, version = antes.status, antes.version

    assert reprogramar(ocupada).status_code == 200

    despues = db.get(Contact, escena[0].id, populate_existing=True)
    assert (despues.status, despues.version) == (estado, version)


@pytest.mark.parametrize(
    "extra",
    [{"contact_id": 1}, {"service_id": 1}, {"duration_minutes": 30}, {"status": "cancelled"}, {"ends_at": "2027-01-12T09:45"}],
    ids=["contacto", "servicio", "duración", "estado", "fin"],
)
def test_reprogramar_no_admite_otros_campos(db, escena, ocupada, extra):
    assert reprogramar(ocupada, **extra).status_code == 422
    assert en_bd(db, ocupada).version == 1


@pytest.mark.parametrize("version", [0, "1", 1.0, None], ids=["cero", "texto", "decimal", "nula"])
def test_la_version_es_un_entero_positivo(db, escena, ocupada, version):
    assert reprogramar(ocupada, version=version).status_code == 422
    assert cancelar(ocupada, version=version).status_code == 422


# --- Versión y estado de la cita (T19) -----------------------------------------------------


def test_con_la_version_antigua_409_y_no_se_pisa(db, escena, ocupada):
    assert reprogramar(ocupada, starts_at="2027-01-12T09:00").status_code == 200

    # Quien la abrió antes (versión 1) intenta moverla y cancelarla.
    tarde = reprogramar(ocupada, starts_at="2027-01-13T09:00")
    cancelada = cancelar(ocupada)

    assert (tarde.status_code, tarde.json()) == (409, {"detail": CAMBIADA})
    assert (cancelada.status_code, cancelada.json()) == (409, {"detail": CAMBIADA})
    guardada = en_bd(db, ocupada)
    assert (guardada.status, guardada.version, guardada.starts_at.day) == ("scheduled", 2, 12)


@pytest.mark.parametrize(
    "estado, nombre", [("cancelled", "Cancelada"), ("completed", "Realizada"), ("no_show", "No presentado")]
)
def test_solo_se_cambian_las_programadas(db, escena, ocupada, estado, nombre):
    # Con la versión al día: lo que lo impide es el estado.
    marcar(db, ocupada, status=estado, cancel_reason="other" if estado == "cancelled" else None)

    mensaje = {"detail": f"La cita está «{nombre}»: ya no se puede cambiar"}
    assert (reprogramar(ocupada).status_code, reprogramar(ocupada).json()) == (409, mensaje)
    assert (cancelar(ocupada).status_code, cancelar(ocupada).json()) == (409, mensaje)


@pytest.mark.parametrize(
    "inicio, fin",
    [("2027-01-04 15:00+00", "2027-01-04 16:00+00"), ("2027-01-04 14:00+00", "2027-01-04 15:00+00")],
    ids=["empieza justo ahora", "empezó hace una hora"],
)
def test_la_que_ya_ha_empezado_no_se_cambia(db, escena, inicio, fin):
    _insertar(db, escena, inicio, fin)
    db.commit()
    cita = {"id": db.scalar(select(Appointment.id)), "staff_id": escena[2].id, "version": 1}

    for response in (reprogramar(cita), cancelar(cita)):
        assert (response.status_code, response.json()) == (409, {"detail": "La cita ya ha empezado: no se puede cambiar"})


# --- Cancelar (T19) --------------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_cancelan_con_motivo_y_detalle(db, usuarios, escena, ocupada, role):
    response = cancelar(ocupada, role, reason="clinic", note="  La profesional   no viene  ")

    assert response.status_code == 200
    assert response.json() | {"created_at": ""} == ocupada | {
        "status": "cancelled",
        "version": 2,
        "cancel_reason": "clinic",
        "cancel_note": "La profesional no viene",
        "created_at": "",
    }
    assert en_bd(db, ocupada).updated_by_id == usuarios[role].id


@pytest.mark.parametrize("motivo", ["client_request", "clinic", "other"])
def test_los_tres_motivos_valen_y_el_detalle_es_opcional(db, escena, ocupada, motivo):
    response = cancelar(ocupada, reason=motivo)

    assert response.status_code == 200
    assert (response.json()["cancel_reason"], response.json()["cancel_note"]) == (motivo, None)


@pytest.mark.parametrize("cuerpo", [{}, {"reason": "illness"}, {"reason": ""}, {"reason": None}, {"reason": 1}],
                         ids=["sin motivo", "desconocido", "vacío", "nulo", "número"])
def test_el_motivo_es_obligatorio_y_de_la_lista(db, escena, ocupada, cuerpo):
    client, csrf = sesion_de(Role.RECEPTION)

    response = client.post(f"/api/appointments/{ocupada['id']}/cancel", json={"version": 1, **cuerpo}, headers=csrf)

    assert response.status_code == 422
    if cuerpo:
        assert error_de(response, "reason") == "Elige el motivo de la cancelación"
    assert en_bd(db, ocupada).status == "scheduled"


@pytest.mark.parametrize(
    "nota, guardada",
    [("", None), ("   ", None), ("Llamo\nmanana", "Llamo manana"), ("x" * 200, "x" * 200)],
    ids=["vacía", "solo espacios", "salto de línea", "200 caracteres"],
)
def test_el_detalle_se_normaliza(db, escena, ocupada, nota, guardada):
    response = cancelar(ocupada, note=nota)

    assert response.status_code == 200
    assert en_bd(db, ocupada).cancel_note == guardada


@pytest.mark.parametrize(
    "nota, mensaje",
    [
        ("x" * 201, "El detalle no puede tener más de 200 caracteres"),
        ("Llamará mañana", "No se permiten tildes ni caracteres especiales (á, ñ, ü…)"),
        ("Tab​Oculto", "No se permiten tildes ni caracteres especiales (á, ñ, ü…)"),
        (12, "El detalle debe ser texto"),
    ],
    ids=["201 caracteres", "tildes", "invisible", "número"],
)
def test_detalle_no_valido_422(db, escena, ocupada, nota, mensaje):
    response = cancelar(ocupada, note=nota)

    assert response.status_code == 422
    assert error_de(response, "note") == mensaje
    assert en_bd(db, ocupada).status == "scheduled"


def test_cancelar_no_admite_otros_campos(db, escena, ocupada):
    assert cancelar(ocupada, status="scheduled").status_code == 422


def test_cancelar_libera_la_franja(db, escena, ocupada):
    assert crear(para_otro(db, escena)).status_code == 409

    assert cancelar(ocupada).status_code == 200

    assert crear(para_otro(db, escena)).status_code == 201


def test_cancelar_la_ultima_programada_devuelve_el_contacto_a_contactado(db, usuarios, escena, ocupada):
    contact = db.get(Contact, escena[0].id, populate_existing=True)
    assert (contact.status, contact.version) == (ContactStatus.SCHEDULED, 2)

    assert cancelar(ocupada, Role.ADMIN).status_code == 200

    contact = db.get(Contact, escena[0].id, populate_existing=True)
    assert (contact.status, contact.version, contact.updated_by_id) == (ContactStatus.CONTACTED, 3, usuarios[Role.ADMIN].id)


def test_si_le_queda_otra_programada_sigue_en_cita_agendada(db, escena, ocupada):
    otra = crear(datos(escena, starts_at="2027-01-12T09:30")).json()

    assert cancelar(ocupada).status_code == 200
    contact = db.get(Contact, escena[0].id, populate_existing=True)
    assert (contact.status, contact.version) == (ContactStatus.SCHEDULED, 2)

    assert cancelar(otra).status_code == 200
    assert db.get(Contact, escena[0].id, populate_existing=True).status == ContactStatus.CONTACTED


@pytest.mark.parametrize("estado", ["completed", "no_show", "cancelled"])
def test_las_que_no_estan_programadas_no_cuentan_como_pendientes(db, escena, ocupada, estado):
    otra = crear(datos(escena, starts_at="2027-01-12T09:30")).json()
    marcar(db, otra, status=estado, cancel_reason="other" if estado == "cancelled" else None)

    assert cancelar(ocupada).status_code == 200

    assert db.get(Contact, escena[0].id, populate_existing=True).status == ContactStatus.CONTACTED


def test_un_cliente_sigue_siendo_cliente(db, escena, ocupada):
    db.execute(update(Contact).where(Contact.id == escena[0].id).values(status=ContactStatus.CLIENT))
    db.commit()

    assert cancelar(ocupada).status_code == 200

    assert db.get(Contact, escena[0].id, populate_existing=True).status == ContactStatus.CLIENT


def test_quien_editaba_la_ficha_antes_de_cancelar_recibe_409(db, escena, ocupada):
    # Cancelar la última cita cambia el estado del contacto y sube su versión (como el alta, T16).
    assert cancelar(ocupada).status_code == 200
    client, csrf = sesion_de(Role.RECEPTION)

    response = client.put(f"/api/contacts/{escena[0].id}/status", json={"status": "lost", "version": 2}, headers=csrf)

    assert response.status_code == 409


# --- La BD repite las reglas de la cancelación (T19) ----------------------------------------


@pytest.mark.parametrize(
    "estado, motivo, nota",
    [
        ("cancelled", None, None),  # cancelada sin motivo
        ("scheduled", "other", None),  # motivo sin estar cancelada
        ("cancelled", "illness", None),  # motivo fuera de la lista
        ("scheduled", None, "Nota suelta"),  # detalle sin motivo
        ("cancelled", "other", "Llamará"),  # detalle con tilde
        ("cancelled", "other", " Con espacios "),  # detalle sin normalizar
        ("cancelled", "other", ""),  # detalle vacío
        ("cancelled", "other", "x" * 201),  # más de 200
    ],
)
def test_la_bd_repite_las_reglas_de_la_cancelacion(db, escena, estado, motivo, nota):
    contact, service, persona = escena
    with pytest.raises(Exception) as fallo:
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO appointments (contact_id, service_id, staff_id, starts_at, ends_at, duration_minutes,"
                    " status, cancel_reason, cancel_note) VALUES (:c, :s, :p, '2027-01-11 14:30+00',"
                    " '2027-01-11 15:30+00', 60, :estado, :motivo, :nota)"
                ),
                {"c": contact.id, "s": service.id, "p": persona.id, "estado": estado, "motivo": motivo, "nota": nota},
            )
    # 201 caracteres no caben en la columna (varchar(200)); lo demás lo paran las CHECK.
    assert fallo.type.__name__ in {"IntegrityError", "DataError"}


def test_la_bd_admite_una_cancelada_con_motivo_y_detalle(db, escena):
    contact, service, persona = escena
    db.execute(
        text(
            "INSERT INTO appointments (contact_id, service_id, staff_id, starts_at, ends_at, duration_minutes,"
            " status, cancel_reason, cancel_note) VALUES (:c, :s, :p, '2027-01-11 14:30+00',"
            " '2027-01-11 15:30+00', 60, 'cancelled', 'clinic', 'Cierre por nieve')"
        ),
        {"c": contact.id, "s": service.id, "p": persona.id},
    )
    assert contar(db) == 1
