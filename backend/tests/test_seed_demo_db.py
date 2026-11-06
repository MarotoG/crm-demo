"""El comando de cuentas y datos de demo contra PostgreSQL real (antes solo había evidencia manual)."""

import re
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import seed_demo
from app.appointments_routes import get_now
from app.main import app as fastapi_app
from app.models import Appointment, AuditEvent, Contact, FollowUpTask, Role, Service, ServiceStaff, User
from app.security import verify_password
from app.seed_demo import DEMO_APPOINTMENTS, DEMO_CONTACTS, DEMO_EMAILS, DEMO_SERVICES, DEMO_TASKS, DemoPasswords, seed_demo_data, upsert_demo_users

# Lunes 04/01/2027 a las 10:00 en Nueva York.
AHORA = datetime(2027, 1, 4, 15, 0, tzinfo=UTC)


def passwords(sufijo: str) -> DemoPasswords:
    return DemoPasswords(_env_file=None, **{role.value: f"demo-{role.value}-{sufijo}" for role in Role})


def test_crea_cuatro_cuentas_y_es_idempotente(db, monkeypatch):
    for role in Role:
        monkeypatch.delenv(f"CRM_DEMO_PASSWORD_{role.name}", raising=False)

    primera = upsert_demo_users(db, passwords("uno"))
    db.flush()
    segunda = upsert_demo_users(db, passwords("dos"))
    db.flush()

    assert all(linea.startswith("creada") for linea in primera)
    assert all(linea.startswith("actualizada") for linea in segunda)
    assert db.scalar(select(func.count()).select_from(User)) == 4
    for role, email in DEMO_EMAILS.items():
        user = db.scalar(select(User).where(User.email == email))
        assert user.role == role and user.active
        assert verify_password(user.password_hash, f"demo-{role.value}-dos")
        assert not verify_password(user.password_hash, f"demo-{role.value}-uno")


def test_solo_la_cuenta_de_cliente_queda_vinculada_a_un_unico_contacto_ficticio(db):
    upsert_demo_users(db, passwords("uno"))
    db.flush()
    upsert_demo_users(db, passwords("dos"))
    db.flush()

    contacto = db.scalar(select(Contact))
    assert db.scalar(select(func.count()).select_from(Contact)) == 1
    assert contacto.email == DEMO_EMAILS[Role.CLIENT] and contacto.status == "new"
    for role, email in DEMO_EMAILS.items():
        user = db.scalar(select(User).where(User.email == email))
        assert user.contact_id == (contacto.id if role == Role.CLIENT else None)


def test_vincula_la_cuenta_de_cliente_que_ya_existia_sin_contacto(db):
    db.add(User(email=DEMO_EMAILS[Role.CLIENT], password_hash="x", role=Role.CLIENT))
    db.flush()

    upsert_demo_users(db, passwords("uno"))
    db.flush()

    user = db.scalar(select(User).where(User.email == DEMO_EMAILS[Role.CLIENT]))
    assert user.contact_id == db.scalar(select(Contact.id))


# --- Datos de demo (T27) -----------------------------------------------------------------


def sembrar(db, now: datetime = AHORA) -> str:
    upsert_demo_users(db, passwords("uno"))
    db.flush()
    resultado = seed_demo_data(db, now)
    db.flush()
    db.expire_all()
    return resultado


def contar(db, modelo) -> int:
    return db.scalar(select(func.count()).select_from(modelo))


def test_el_comando_crea_las_cuentas_y_los_datos_sin_mostrar_contrasenas(db, monkeypatch, capsys):
    monkeypatch.setattr(seed_demo, "get_engine", db.connection)
    monkeypatch.setattr(seed_demo, "DemoPasswords", lambda: passwords("uno"))

    assert seed_demo.main() == 0

    salida = capsys.readouterr().out
    assert "demo-admin-uno" not in salida
    assert "datos de demo: 5 contactos" in salida
    assert contar(db, User) == 4
    assert contar(db, Appointment) == len(DEMO_APPOINTMENTS)


def test_crea_contactos_en_cada_estado_servicios_citas_y_tareas(db):
    resumen = sembrar(db)

    assert contar(db, Contact) == len(DEMO_CONTACTS) + 1
    assert contar(db, Service) == len(DEMO_SERVICES)
    assert contar(db, Appointment) == len(DEMO_APPOINTMENTS)
    assert contar(db, FollowUpTask) == len(DEMO_TASKS)
    assert set(db.scalars(select(Contact.status))) == {"new", "contacted", "scheduled", "client", "lost"}
    assert set(db.scalars(select(Appointment.status))) == {"scheduled", "completed", "no_show", "cancelled"}
    assert str(len(DEMO_APPOINTMENTS)) in resumen


def test_una_segunda_ejecucion_no_duplica_ni_pisa_nada(db):
    sembrar(db)
    emma = db.scalar(select(Contact).where(Contact.first_name == "Emma"))
    emma.status = "contacted"
    db.flush()

    resumen = sembrar(db, AHORA + timedelta(days=30))

    assert "ya estaban" in resumen
    assert contar(db, Contact) == len(DEMO_CONTACTS) + 1
    assert contar(db, Appointment) == len(DEMO_APPOINTMENTS)
    assert contar(db, FollowUpTask) == len(DEMO_TASKS)
    assert db.get(Contact, emma.id).status == "contacted"


def test_los_datos_son_ficticios(db):
    sembrar(db)

    for email, telefono in db.execute(select(Contact.email, Contact.phone)):
        assert email.endswith("@demo.example.com")
        assert telefono is None or re.fullmatch(r"\+1212555010\d", telefono)


def test_el_estado_de_cada_contacto_cuadra_con_sus_citas(db):
    sembrar(db)

    for contacto in db.scalars(select(Contact)):
        estados = set(db.scalars(select(Appointment.status).where(Appointment.contact_id == contacto.id)))
        if contacto.status == "client":
            assert "completed" in estados, contacto.first_name
        if contacto.status == "scheduled":
            assert "scheduled" in estados, contacto.first_name
        if contacto.status == "new":
            assert not estados, contacto.first_name


def test_las_citas_realizadas_son_pasadas_y_las_programadas_futuras(db):
    sembrar(db)

    for cita in db.scalars(select(Appointment)):
        if cita.status in ("completed", "no_show"):
            assert cita.starts_at < AHORA and cita.attended_at is not None
        else:
            assert cita.starts_at > AHORA and cita.attended_at is None


def test_las_tareas_del_profesional_son_de_contactos_con_cita_con_el(db):
    # La regla de T24: si no, no podría abrir su ficha desde la tarea.
    sembrar(db)
    profesional = db.scalar(select(User).where(User.role == Role.PROFESSIONAL))

    suyas = list(db.scalars(select(FollowUpTask).where(FollowUpTask.assigned_to_id == profesional.id)))

    assert suyas
    for tarea in suyas:
        assert db.scalar(
            select(Appointment.id).where(Appointment.contact_id == tarea.contact_id, Appointment.staff_id == profesional.id)
        )


def test_hay_tareas_vencidas_de_hoy_proximas_y_hechas(db):
    sembrar(db)
    hoy = AHORA.date()

    tareas = list(db.scalars(select(FollowUpTask)))

    assert any(t.completed_at is None and t.due_on < hoy for t in tareas)
    assert any(t.completed_at is None and t.due_on == hoy for t in tareas)
    assert any(t.completed_at is None and t.due_on > hoy for t in tareas)
    assert any(t.completed_at is not None and t.completed_by_id is not None for t in tareas)


def test_el_profesional_realiza_los_servicios_de_demo(db):
    sembrar(db)
    profesional = db.scalar(select(User).where(User.role == Role.PROFESSIONAL))

    assert contar(db, ServiceStaff) == len(DEMO_SERVICES)
    assert set(db.scalars(select(ServiceStaff.user_id))) == {profesional.id}


def test_usa_un_servicio_que_ya_existia_con_ese_nombre(db):
    db.add(Service(name="Limpieza facial", duration_minutes=90))
    db.flush()

    sembrar(db)

    assert contar(db, Service) == len(DEMO_SERVICES)
    assert db.scalar(select(Service.duration_minutes).where(Service.name == "Limpieza facial")) == 90


def test_busca_hueco_si_el_profesional_ya_tiene_una_cita_a_esa_hora(db):
    # Sin hueco, la restricción de solapamientos (T17) haría fallar el comando entero.
    upsert_demo_users(db, passwords("uno"))
    db.flush()
    profesional = db.scalar(select(User).where(User.role == Role.PROFESSIONAL))
    otra = Contact(first_name="Otra", last_name="Persona", email="otra@example.com", source="other")
    servicio = Service(name="Otro", duration_minutes=60)
    db.add_all([otra, servicio])
    db.flush()
    # Mañana a las 12:00 en Nueva York: la hora de la primera cita de Liam.
    ocupada = datetime(2027, 1, 5, 17, 0, tzinfo=UTC)
    db.add(
        Appointment(
            contact_id=otra.id, service_id=servicio.id, staff_id=profesional.id, starts_at=ocupada,
            ends_at=ocupada + timedelta(minutes=60), duration_minutes=60,
        )
    )
    db.flush()

    seed_demo_data(db, AHORA)
    db.flush()

    liam = db.scalar(select(Contact).where(Contact.first_name == "Liam"))
    programada = db.scalar(select(Appointment).where(Appointment.contact_id == liam.id, Appointment.status == "scheduled"))
    assert programada.starts_at == ocupada + timedelta(hours=1)


def test_no_deja_eventos_de_auditoria(db):
    sembrar(db)

    assert contar(db, AuditEvent) == 0


def test_la_cuenta_de_cliente_ve_sus_citas_en_el_portal(db):
    sembrar(db)
    fastapi_app.dependency_overrides[get_now] = lambda: AHORA
    try:
        client = TestClient(fastapi_app)
        login = client.post("/api/auth/login", json={"email": DEMO_EMAILS[Role.CLIENT], "password": "demo-client-uno"})
        assert login.status_code == 200
        citas = client.get("/api/portal/appointments").json()
    finally:
        fastapi_app.dependency_overrides.pop(get_now, None)

    assert [c["service_name"] for c in citas["upcoming"]] == ["Peeling suave"]
    assert [c["service_name"] for c in citas["past"]] == ["Limpieza facial"]
    assert citas["past"][0]["status"] == "completed"
