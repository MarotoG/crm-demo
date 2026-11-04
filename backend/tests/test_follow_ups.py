"""Tareas de seguimiento contra PostgreSQL real (T24): quién crea, a quién se asigna y quién ve qué.
«Ahora» es el lunes 04/01/2027 a las 10:00 de Nueva York."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DataError, IntegrityError

from app.appointments_routes import get_now
from app.main import app as fastapi_app
from app.models import Appointment, Contact, FollowUpTask, Role, Service, User
from app.security import hash_password

PASSWORD = "contraseña-de-prueba-larga"
AHORA = datetime(2027, 1, 4, 15, 0, tzinfo=UTC)
HOY = date(2027, 1, 4)
TAREA = "Llamar para confirmar la visita"


@pytest.fixture(autouse=True)
def reloj_fijo():
    fastapi_app.dependency_overrides[get_now] = lambda: AHORA
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


def cuenta(db, nombre: str, role: Role, **campos) -> User:
    user = User(email=f"{nombre}@prueba.example.com", password_hash=hash_password(PASSWORD), role=role, **campos)
    db.add(user)
    db.flush()
    return user


def contacto(db, nombre: str = "ana", **campos) -> Contact:
    nuevo = Contact(first_name=nombre.title(), last_name="Lopez", email=f"{nombre}@example.com", source="other", **campos)
    db.add(nuevo)
    db.flush()
    return nuevo


def cita(db, ficha: Contact, persona: User, horas: int = 24, **campos) -> Appointment:
    servicio = Service(name=f"Servicio {ficha.id} {persona.id} {horas}", duration_minutes=60)
    db.add(servicio)
    db.flush()
    inicio = AHORA + timedelta(hours=horas)
    nueva = Appointment(
        contact_id=ficha.id, service_id=servicio.id, staff_id=persona.id, starts_at=inicio,
        ends_at=inicio + timedelta(minutes=60), duration_minutes=60, **campos,
    )
    db.add(nueva)
    db.flush()
    return nueva


def tarea(db, ficha: Contact, responsable: User, **campos) -> FollowUpTask:
    nueva = FollowUpTask(contact_id=ficha.id, assigned_to_id=responsable.id, **{"due_on": HOY, "description": TAREA, **campos})
    db.add(nueva)
    db.flush()
    return nueva


def sesion(user: User) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(fastapi_app)
    login = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200
    return client, {"X-CSRF-Token": login.json()["csrf_token"]}


def crear(user: User, ficha_id: int, responsable_id: int, **campos):
    client, csrf = sesion(user)
    cuerpo = {"description": TAREA, "due_on": "2027-01-11", "assigned_to_id": responsable_id, **campos}
    return client.post(f"/api/contacts/{ficha_id}/follow-ups", json=cuerpo, headers=csrf)


def error_de(response, campo: str) -> str:
    assert response.status_code == 422, response.text
    errores = {e["loc"][-1]: e["msg"] for e in response.json()["detail"]}
    return errores[campo]


@pytest.fixture
def recepcion(db) -> User:
    return cuenta(db, "recepcion", Role.RECEPTION)


# --- Crear --------------------------------------------------------------------------


@pytest.mark.parametrize("rol", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_crean_una_tarea_con_todos_sus_datos(db, rol):
    autor = cuenta(db, "autor", rol)
    responsable = cuenta(db, "responsable", Role.RECEPTION)
    ficha = contacto(db)

    response = crear(autor, ficha.id, responsable.id)

    assert response.status_code == 201, response.text
    cuerpo = response.json()
    assert cuerpo["contact_id"] == ficha.id
    assert cuerpo["description"] == TAREA
    assert cuerpo["due_on"] == "2027-01-11"
    assert cuerpo["assigned_to_id"] == responsable.id
    assert cuerpo["assigned_to_email"] == responsable.email
    assert cuerpo["created_by_email"] == autor.email
    guardada = db.get(FollowUpTask, cuerpo["id"])
    assert guardada.created_by_id == autor.id
    assert guardada.due_on == date(2027, 1, 11)


@pytest.mark.parametrize("rol", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_crean_tareas(db, rol):
    # Aun siendo el profesional responsable y con cita: decisión T24.
    otro = cuenta(db, "otro", rol)
    ficha = contacto(db)
    if rol == Role.PROFESSIONAL:
        cita(db, ficha, otro)

    response = crear(otro, ficha.id, otro.id)

    assert response.status_code == 403
    assert db.scalar(select(FollowUpTask)) is None


def test_crear_en_un_contacto_que_no_existe_da_404(db, recepcion):
    assert crear(recepcion, 999999, recepcion.id).status_code == 404


def test_un_contacto_perdido_tambien_admite_tareas(db, recepcion):
    assert crear(recepcion, contacto(db, status="lost").id, recepcion.id).status_code == 201


def test_crear_una_tarea_no_toca_la_ficha(db, recepcion):
    ficha = contacto(db)

    crear(recepcion, ficha.id, recepcion.id)

    db.refresh(ficha)
    assert (ficha.status, ficha.version) == ("new", 1)


@pytest.mark.parametrize("campo", ["created_by_id", "contact_id", "created_at", "id"])
def test_el_navegador_no_fija_campos_de_mas(db, recepcion, campo):
    ficha = contacto(db)

    response = crear(recepcion, ficha.id, recepcion.id, **{campo: 1})

    assert response.status_code == 422
    assert db.scalar(select(FollowUpTask)) is None


# --- A quién se asigna ----------------------------------------------------------------


def test_se_asigna_a_un_profesional_con_cita_con_el_contacto(db, recepcion):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof)

    assert crear(recepcion, ficha.id, prof.id).status_code == 201


def test_una_cita_cancelada_tambien_cuenta_como_en_la_ficha(db, recepcion):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof, status="cancelled", cancel_reason="clinic")

    assert crear(recepcion, ficha.id, prof.id).status_code == 201


def test_no_se_asigna_a_un_profesional_sin_citas_con_el_contacto(db, recepcion):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, contacto(db, "bea"), prof)  # tiene citas, pero con otra persona

    response = crear(recepcion, ficha.id, prof.id)

    assert "no tiene citas" in error_de(response, "assigned_to_id")
    assert db.scalar(select(FollowUpTask)) is None


def test_un_lead_sin_citas_se_asigna_a_recepcion_o_admin(db, recepcion):
    ficha = contacto(db)

    assert crear(recepcion, ficha.id, cuenta(db, "jefa", Role.ADMIN).id).status_code == 201
    assert crear(recepcion, ficha.id, recepcion.id).status_code == 201


def test_no_se_asigna_a_un_cliente_ni_a_quien_no_existe_ni_a_una_cuenta_de_baja(db, recepcion):
    ficha = contacto(db)
    cliente = cuenta(db, "cliente", Role.CLIENT, contact_id=ficha.id)
    baja = cuenta(db, "baja", Role.RECEPTION, active=False)

    for responsable_id in (cliente.id, baja.id, 999999):
        assert "no está activa" in error_de(crear(recepcion, ficha.id, responsable_id), "assigned_to_id")


@pytest.mark.parametrize("valor", [None, 1.5, True])
def test_el_responsable_debe_ser_un_entero(db, recepcion, valor):
    response = crear(recepcion, contacto(db).id, recepcion.id, assigned_to_id=valor)

    assert response.status_code == 422


def test_el_id_del_responsable_en_texto_tampoco_vale_aunque_exista(db, recepcion):
    response = crear(recepcion, contacto(db).id, recepcion.id, assigned_to_id=str(recepcion.id))

    assert response.status_code == 422
    assert db.scalar(select(FollowUpTask)) is None


def test_la_lista_de_asignables_sigue_la_misma_regla(db, recepcion):
    jefa = cuenta(db, "jefa", Role.ADMIN)
    con_cita = cuenta(db, "con-cita", Role.PROFESSIONAL)
    sin_cita = cuenta(db, "sin-cita", Role.PROFESSIONAL)
    cuenta(db, "baja", Role.RECEPTION, active=False)
    baja_prof = cuenta(db, "baja-prof", Role.PROFESSIONAL, active=False)
    ficha = contacto(db)
    cuenta(db, "cliente", Role.CLIENT, contact_id=ficha.id)
    cita(db, ficha, con_cita)
    cita(db, ficha, baja_prof, horas=48)
    cita(db, contacto(db, "bea"), sin_cita)
    client, _ = sesion(recepcion)

    response = client.get(f"/api/contacts/{ficha.id}/follow-up-assignees")

    assert response.status_code == 200
    assert response.json() == [
        {"id": con_cita.id, "email": con_cita.email},
        {"id": jefa.id, "email": jefa.email},
        {"id": recepcion.id, "email": recepcion.email},
    ]


@pytest.mark.parametrize("rol", [Role.PROFESSIONAL, Role.CLIENT])
def test_la_lista_de_asignables_no_es_para_profesional_ni_cliente(db, rol):
    ficha = contacto(db)
    otro = cuenta(db, "otro", rol)
    if rol == Role.PROFESSIONAL:
        cita(db, ficha, otro)
    client, _ = sesion(otro)

    assert client.get(f"/api/contacts/{ficha.id}/follow-up-assignees").status_code == 403


def test_la_lista_de_asignables_de_un_contacto_que_no_existe_da_404(db, recepcion):
    client, _ = sesion(recepcion)

    assert client.get("/api/contacts/999999/follow-up-assignees").status_code == 404


# --- Fecha prevista -------------------------------------------------------------------


def test_vale_hoy_en_la_hora_de_la_clinica_y_no_ayer(db, recepcion):
    ficha = contacto(db)

    assert crear(recepcion, ficha.id, recepcion.id, due_on="2027-01-04").status_code == 201
    assert "anterior a hoy" in error_de(crear(recepcion, ficha.id, recepcion.id, due_on="2027-01-03"), "due_on")


def test_hoy_es_el_de_la_clinica_y_no_el_de_utc(db, recepcion):
    # El 05/01 a las 2:00 en UTC, en Nueva York todavía son las 21:00 del día 4.
    fastapi_app.dependency_overrides[get_now] = lambda: datetime(2027, 1, 5, 2, 0, tzinfo=UTC)

    assert crear(recepcion, contacto(db).id, recepcion.id, due_on="2027-01-04").status_code == 201


def test_como_mucho_dentro_de_365_dias(db, recepcion):
    ficha = contacto(db)
    limite = HOY + timedelta(days=365)

    assert crear(recepcion, ficha.id, recepcion.id, due_on=limite.isoformat()).status_code == 201
    response = crear(recepcion, ficha.id, recepcion.id, due_on=(limite + timedelta(days=1)).isoformat())
    assert "365" in error_de(response, "due_on")


@pytest.mark.parametrize(
    "valor, mensaje",
    [
        ("", "AAAA-MM-DD"),
        ("11/01/2027", "AAAA-MM-DD"),
        ("2027-01-11T10:00", "AAAA-MM-DD"),
        ("2027-01-11\n", "AAAA-MM-DD"),
        ("２０２７-01-11", "AAAA-MM-DD"),
        (1799625600, "AAAA-MM-DD"),
        (None, "AAAA-MM-DD"),
        ("2027-02-30", "no existe"),
    ],
)
def test_fechas_no_validas(db, recepcion, valor, mensaje):
    assert mensaje in error_de(crear(recepcion, contacto(db).id, recepcion.id, due_on=valor), "due_on")


# --- Descripción ----------------------------------------------------------------------


def test_la_descripcion_se_guarda_sin_espacios_de_mas(db, recepcion):
    response = crear(recepcion, contacto(db).id, recepcion.id, description="  Llamar   a  Ana ")

    assert response.json()["description"] == "Llamar a Ana"


@pytest.mark.parametrize(
    "valor, mensaje",
    [
        ("", "qué hay que hacer"),
        ("   ", "qué hay que hacer"),
        ("x" * 201, "200"),
        ("Llamar mañana", "tildes"),
    ],
)
def test_descripciones_no_validas(db, recepcion, valor, mensaje):
    assert mensaje in error_de(crear(recepcion, contacto(db).id, recepcion.id, description=valor), "description")


def test_admite_justo_200_caracteres(db, recepcion):
    assert crear(recepcion, contacto(db).id, recepcion.id, description="x" * 200).status_code == 201


@pytest.mark.parametrize("valor", ["  con espacios ", "dos  espacios", "", "mañana", "x" * 201, "linea\nnueva"])
def test_la_bd_tambien_rechaza_una_descripcion_no_valida(db, recepcion, valor):
    ficha = contacto(db)

    with pytest.raises((IntegrityError, DataError)):
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO follow_up_tasks (contact_id, assigned_to_id, due_on, description) "
                    "VALUES (:c, :a, '2027-01-11', :d)"
                ),
                {"c": ficha.id, "a": recepcion.id, "d": valor},
            )


# --- Consultar ------------------------------------------------------------------------


def test_admin_y_recepcion_ven_todas_las_del_contacto_por_fecha(db, recepcion):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof)
    tarde = tarea(db, ficha, prof, due_on=date(2027, 3, 1))
    pronto = tarea(db, ficha, recepcion, due_on=date(2027, 1, 5))
    mismo_dia = tarea(db, ficha, recepcion, due_on=date(2027, 3, 1))
    tarea(db, contacto(db, "bea"), recepcion)  # de otro contacto
    client, _ = sesion(recepcion)

    cuerpo = client.get(f"/api/contacts/{ficha.id}/follow-ups").json()

    assert cuerpo["total"] == 3
    assert [t["id"] for t in cuerpo["items"]] == [pronto.id, tarde.id, mismo_dia.id]
    assert cuerpo["items"][1]["assigned_to_email"] == prof.email


def test_autor_de_una_cuenta_borrada_sale_vacio(db, recepcion):
    ficha = contacto(db)
    tarea(db, ficha, recepcion, created_by_id=None)
    client, _ = sesion(recepcion)

    assert client.get(f"/api/contacts/{ficha.id}/follow-ups").json()["items"][0]["created_by_email"] is None


def test_se_ven_las_20_mas_cercanas_con_el_total(db, recepcion):
    ficha = contacto(db)
    for dia in range(1, 24):
        tarea(db, ficha, recepcion, due_on=date(2027, 2, dia))
    client, _ = sesion(recepcion)

    cuerpo = client.get(f"/api/contacts/{ficha.id}/follow-ups").json()

    assert cuerpo["total"] == 23
    assert [t["due_on"] for t in cuerpo["items"]] == [f"2027-02-{dia:02}" for dia in range(1, 21)]


def test_contacto_sin_tareas_da_lista_vacia(db, recepcion):
    client, _ = sesion(recepcion)

    assert client.get(f"/api/contacts/{contacto(db).id}/follow-ups").json() == {"total": 0, "items": []}


def test_contacto_que_no_existe_da_404(db, recepcion):
    client, _ = sesion(recepcion)

    assert client.get("/api/contacts/999999/follow-ups").status_code == 404


def test_el_profesional_solo_ve_las_suyas(db, recepcion):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    colega = cuenta(db, "colega", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof)
    cita(db, ficha, colega)
    suya = tarea(db, ficha, prof)
    tarea(db, ficha, colega)
    tarea(db, ficha, recepcion)
    client, _ = sesion(prof)

    cuerpo = client.get(f"/api/contacts/{ficha.id}/follow-ups").json()

    assert cuerpo["total"] == 1
    assert [t["id"] for t in cuerpo["items"]] == [suya.id]


@pytest.mark.parametrize("nombre", ["assigned_to_id", "user_id", "staff_id"])
def test_un_parametro_no_le_ensena_las_de_otro(db, recepcion, nombre):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof)
    tarea(db, ficha, recepcion)
    client, _ = sesion(prof)

    assert client.get(f"/api/contacts/{ficha.id}/follow-ups", params={nombre: recepcion.id}).json()["total"] == 0


def test_el_profesional_sin_citas_con_el_contacto_recibe_404(db, recepcion):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    tarea(db, ficha, recepcion)
    client, _ = sesion(prof)

    response = client.get(f"/api/contacts/{ficha.id}/follow-ups")

    # La misma respuesta que si no existiera: no se revela que existe.
    assert response.status_code == 404
    assert response.json() == client.get("/api/contacts/999999/follow-ups").json()


def test_el_cliente_no_ve_tareas_ni_siquiera_de_su_contacto(db, recepcion):
    ficha = contacto(db)
    tarea(db, ficha, recepcion)
    client, _ = sesion(cuenta(db, "cliente", Role.CLIENT, contact_id=ficha.id))

    assert client.get(f"/api/contacts/{ficha.id}/follow-ups").status_code == 403


def test_el_portal_no_cambia_con_las_tareas(db, recepcion):
    ficha = contacto(db)
    tarea(db, ficha, recepcion)
    client, _ = sesion(cuenta(db, "cliente", Role.CLIENT, contact_id=ficha.id))

    assert TAREA not in client.get("/api/portal/appointments").text
