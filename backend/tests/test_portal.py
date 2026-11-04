"""Portal del cliente contra PostgreSQL real (T22): cada cliente solo obtiene sus citas y sin campos
internos, se manipule lo que se manipule. «Ahora» es el lunes 04/01/2027 a las 10:00 de Nueva York."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.appointments_routes import get_now
from app.main import app as fastapi_app
from app.models import Appointment, Contact, ContactStatus, Role, Service, User
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
AHORA = datetime(2027, 1, 4, 15, 0, tzinfo=UTC)
RUTA = "/api/portal/appointments"
CAMPOS = {"id", "service_name", "starts_at", "ends_at", "status"}


@pytest.fixture(autouse=True)
def reloj_fijo():
    fastapi_app.dependency_overrides[get_now] = lambda: AHORA
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def escena(db):
    """Dos clientes con cuenta, una persona que realiza el servicio y el servicio."""
    persona = User(email="prof@prueba.example.com", password_hash=hash_password(PASSWORD), role=Role.PROFESSIONAL)
    servicio = Service(name="Botox", duration_minutes=60)
    db.add_all([persona, servicio])
    db.flush()
    return cliente(db, "ana"), cliente(db, "bea"), persona, servicio


def cliente(db, nombre: str, status: ContactStatus = ContactStatus.NEW) -> User:
    contact = Contact(first_name=nombre.title(), last_name="Lopez", email=f"{nombre}@example.com", source="other", status=status)
    db.add(contact)
    db.flush()
    user = User(email=contact.email, password_hash=hash_password(PASSWORD), role=Role.CLIENT, contact_id=contact.id)
    db.add(user)
    db.flush()
    return user


def cita(db, user: User, persona: User, servicio: Service, horas: float, status: str = "scheduled", **campos) -> Appointment:
    inicio = AHORA + timedelta(hours=horas)
    if status == "cancelled":
        campos.setdefault("cancel_reason", "clinic")
    if status in ("completed", "no_show"):
        campos.setdefault("attended_at", inicio)
    nueva = Appointment(
        contact_id=user.contact_id, service_id=servicio.id, staff_id=persona.id, starts_at=inicio,
        ends_at=inicio + timedelta(minutes=60), duration_minutes=60, status=status, **campos,
    )
    db.add(nueva)
    db.flush()
    return nueva


def sesion(user_email: str) -> TestClient:
    client = TestClient(fastapi_app)
    assert client.post("/api/auth/login", json={"email": user_email, "password": PASSWORD}).status_code == 200
    return client


def ids(citas: list[dict]) -> list[int]:
    return [c["id"] for c in citas]


# --- Aislamiento --------------------------------------------------------------------


def test_cada_cliente_solo_recibe_sus_citas(db, escena):
    ana, bea, persona, servicio = escena
    de_ana = cita(db, ana, persona, servicio, 24)
    de_bea = cita(db, bea, persona, servicio, 48)

    assert ids(sesion(ana.email).get(RUTA).json()["upcoming"]) == [de_ana.id]
    assert ids(sesion(bea.email).get(RUTA).json()["upcoming"]) == [de_bea.id]


@pytest.mark.parametrize("nombre", ["contact_id", "user_id", "staff_id", "id", "email"])
def test_ningun_parametro_cambia_de_quien_son_las_citas(db, escena, nombre):
    ana, bea, persona, servicio = escena
    de_ana = cita(db, ana, persona, servicio, 24)
    cita(db, bea, persona, servicio, 48)
    valor = bea.email if nombre == "email" else bea.contact_id

    response = sesion(ana.email).get(RUTA, params={nombre: valor})

    assert response.status_code == 200
    assert ids(response.json()["upcoming"]) == [de_ana.id]


def test_la_ruta_no_declara_ningun_parametro_salvo_la_cookie_de_sesion():
    operacion = fastapi_app.openapi()["paths"][RUTA]["get"]

    assert {p["in"] for p in operacion.get("parameters", [])} <= {"cookie"}
    assert "requestBody" not in operacion


def test_no_hay_ruta_para_pedir_una_cita_por_su_id(db, escena):
    ana, bea, persona, servicio = escena
    ajena = cita(db, bea, persona, servicio, 48)

    assert sesion(ana.email).get(f"{RUTA}/{ajena.id}").status_code == 404


@pytest.mark.parametrize(
    "metodo, ruta",
    [
        ("GET", "/api/appointments?date=2027-01-05"),
        ("GET", "/api/contacts"),
        ("GET", "/api/services"),
        ("GET", "/api/users"),
    ],
)
def test_el_cliente_no_llega_a_las_rutas_internas(db, escena, metodo, ruta):
    ana, *_ = escena

    assert sesion(ana.email).request(metodo, ruta).status_code == 403


def test_tampoco_a_la_ficha_ni_a_las_citas_de_otro_contacto(db, escena):
    ana, bea, *_ = escena
    client = sesion(ana.email)

    assert client.get(f"/api/contacts/{bea.contact_id}").status_code == 403
    assert client.get(f"/api/appointments/by-contact/{bea.contact_id}").status_code == 403


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL])
def test_el_personal_no_usa_esta_ruta(db, role):
    db.add(User(email="interno@prueba.example.com", password_hash=hash_password(PASSWORD), role=role))
    db.flush()

    assert sesion("interno@prueba.example.com").get(RUTA).status_code == 403


def test_sin_sesion_401(db):
    assert TestClient(fastapi_app).get(RUTA).status_code == 401


def test_una_cuenta_de_cliente_sin_vinculo_no_ve_nada(db, escena):
    ana, _, persona, servicio = escena
    cita(db, ana, persona, servicio, 24)
    db.add(User(email="suelta@prueba.example.com", password_hash=hash_password(PASSWORD), role=Role.CLIENT))
    db.flush()

    assert sesion("suelta@prueba.example.com").get(RUTA).json() == {"upcoming": [], "past": [], "past_total": 0}


# --- Sin campos internos ------------------------------------------------------------


def test_solo_los_campos_permitidos_sin_rastro_de_los_internos(db, escena):
    ana, _, persona, servicio = escena
    cita(db, ana, persona, servicio, 24, note="NOTA-INTERNA")
    cita(db, ana, persona, servicio, 48, status="cancelled", cancel_note="DETALLE-INTERNO", note="OTRA-NOTA")
    cita(db, ana, persona, servicio, -48, status="completed", note="NOTA-PASADA")

    response = sesion(ana.email).get(RUTA)

    cuerpo = response.json()
    for c in cuerpo["upcoming"] + cuerpo["past"]:
        assert set(c) == CAMPOS
    for secreto in ("NOTA-INTERNA", "DETALLE-INTERNO", "OTRA-NOTA", "NOTA-PASADA", "clinic", persona.email):
        assert secreto not in response.text


def test_la_hora_viene_en_la_de_la_clinica_y_el_servicio_con_su_nombre(db, escena):
    ana, _, persona, servicio = escena
    cita(db, ana, persona, servicio, 24)

    c = sesion(ana.email).get(RUTA).json()["upcoming"][0]

    assert c["starts_at"] == "2027-01-05T10:00:00-05:00" and c["ends_at"] == "2027-01-05T11:00:00-05:00"
    assert c["service_name"] == "Botox" and c["status"] == "scheduled"


# --- Próximas y anteriores ----------------------------------------------------------


def test_sin_citas_las_dos_listas_vacias(db, escena):
    ana, *_ = escena

    assert sesion(ana.email).get(RUTA).json() == {"upcoming": [], "past": [], "past_total": 0}


def test_proximas_de_la_mas_cercana_y_anteriores_de_la_mas_reciente(db, escena):
    ana, _, persona, servicio = escena
    lejana = cita(db, ana, persona, servicio, 72)
    cercana = cita(db, ana, persona, servicio, 24)
    antigua = cita(db, ana, persona, servicio, -72, status="completed")
    reciente = cita(db, ana, persona, servicio, -24, status="no_show")

    cuerpo = sesion(ana.email).get(RUTA).json()

    assert ids(cuerpo["upcoming"]) == [cercana.id, lejana.id]
    assert ids(cuerpo["past"]) == [reciente.id, antigua.id]
    assert [c["status"] for c in cuerpo["past"]] == ["no_show", "completed"]  # decisión T22: su estado real


def test_una_cancelada_futura_sale_en_proximas_y_una_pasada_en_anteriores(db, escena):
    ana, _, persona, servicio = escena
    futura = cita(db, ana, persona, servicio, 24, status="cancelled")
    pasada = cita(db, ana, persona, servicio, -24, status="cancelled")

    cuerpo = sesion(ana.email).get(RUTA).json()

    assert ids(cuerpo["upcoming"]) == [futura.id] and cuerpo["upcoming"][0]["status"] == "cancelled"
    assert ids(cuerpo["past"]) == [pasada.id]


def test_una_cita_en_curso_sigue_en_proximas_hasta_que_termina(db, escena):
    ana, _, persona, servicio = escena
    en_curso = cita(db, ana, persona, servicio, -0.5)
    otra = User(email="otra@prueba.example.com", password_hash=hash_password(PASSWORD), role=Role.PROFESSIONAL)
    db.add(otra)
    db.flush()
    recien_terminada = cita(db, ana, otra, servicio, -1)  # con otra persona: las dos se pisan

    cuerpo = sesion(ana.email).get(RUTA).json()

    assert ids(cuerpo["upcoming"]) == [en_curso.id]
    assert ids(cuerpo["past"]) == [recien_terminada.id]


def test_una_ya_marcada_aunque_no_haya_terminado_pasa_a_anteriores(db, escena):
    ana, _, persona, servicio = escena
    marcada = cita(db, ana, persona, servicio, -0.5, status="completed")

    cuerpo = sesion(ana.email).get(RUTA).json()

    assert cuerpo["upcoming"] == [] and ids(cuerpo["past"]) == [marcada.id]


def test_de_las_anteriores_trae_20_y_cuenta_el_total(db, escena):
    ana, _, persona, servicio = escena
    for dias in range(1, 23):
        cita(db, ana, persona, servicio, -24 * dias, status="completed")

    cuerpo = sesion(ana.email).get(RUTA).json()

    assert cuerpo["past_total"] == 22 and len(cuerpo["past"]) == 20
    assert cuerpo["past"][0]["starts_at"].startswith("2027-01-03")


# --- Contacto Perdido (decisión T22) ------------------------------------------------


def test_un_contacto_perdido_sigue_entrando_y_viendo_sus_citas(db, escena):
    _, _, persona, servicio = escena
    lia = cliente(db, "lia", ContactStatus.LOST)
    suya = cita(db, lia, persona, servicio, -24, status="completed")

    response = sesion(lia.email).get(RUTA)

    assert response.status_code == 200
    assert ids(response.json()["past"]) == [suya.id]
    assert "lost" not in response.text
