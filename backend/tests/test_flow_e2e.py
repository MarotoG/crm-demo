"""El recorrido completo (T27) por la API real, con sesiones reales de cada rol y sin atajos a la BD:
login → lead → cita → seguimiento → asistencia → portal, y el rastro que deja en la auditoría.

Un solo escenario largo a propósito: lo que comprueba es que cada paso deja listo el siguiente. Las
reglas sueltas ya tienen sus pruebas en cada módulo. «Ahora» avanza con la cita.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.appointments_routes import get_now
from app.main import app as fastapi_app
from app.models import Role
from test_follow_ups import PASSWORD, cuenta

LUNES = datetime(2027, 1, 4, 15, 0, tzinfo=UTC)  # lunes 04/01/2027, 10:00 en Nueva York
MARTES_TRAS_LA_CITA = datetime(2027, 1, 5, 16, 5, tzinfo=UTC)  # 11:05: la cita de las 10:00 ya pasó
CONTRASENA_CLIENTA = "contrasena-de-la-clienta-larga"
NOTA = "Prefiere que la llamen por las tardes"


class Reloj:
    ahora = LUNES


@pytest.fixture(autouse=True)
def reloj():
    Reloj.ahora = LUNES
    fastapi_app.dependency_overrides[get_now] = lambda: Reloj.ahora
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


class Sesion:
    """Un navegador con su cookie y su token CSRF."""

    def __init__(self, email: str, password: str = PASSWORD):
        self.client = TestClient(fastapi_app)
        login = self.client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        self.csrf = {"X-CSRF-Token": login.json()["csrf_token"]}

    def get(self, ruta: str, **kwargs):
        return self.client.get(ruta, **kwargs)

    def post(self, ruta: str, cuerpo: dict | None = None):
        return self.client.post(ruta, json=cuerpo, headers=self.csrf)

    def put(self, ruta: str, cuerpo: dict):
        return self.client.put(ruta, json=cuerpo, headers=self.csrf)


def alta(sesion: Sesion, nombre: str, apellido: str, email: str, **campos) -> dict:
    response = sesion.post(
        "/api/contacts",
        {"first_name": nombre, "last_name": apellido, "email": email, "source": "instagram", **campos},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_del_lead_al_portal_con_su_rastro_y_sin_ver_lo_ajeno(db):
    admin = Sesion(cuenta(db, "admin", Role.ADMIN).email)
    recepcion_cuenta = cuenta(db, "recepcion", Role.RECEPTION)
    recepcion = Sesion(recepcion_cuenta.email)
    prof_cuenta = cuenta(db, "prof", Role.PROFESSIONAL)
    prof = Sesion(prof_cuenta.email)
    colega_cuenta = cuenta(db, "colega", Role.PROFESSIONAL)
    colega = Sesion(colega_cuenta.email)

    # 1. Admin prepara un servicio y recepción registra el lead.
    servicio = admin.post(
        "/api/services", {"name": "Limpieza facial", "duration_minutes": 60, "staff_ids": [prof_cuenta.id, colega_cuenta.id]}
    ).json()
    ana = alta(recepcion, "Ana", "Smith", "ana@example.com", phone="(212) 555-0123", note=NOTA)
    assert ana["status"] == "new" and ana["phone"] == "+12125550123"
    assert recepcion.get("/api/contacts", params={"q": "smith"}).json()["total"] == 1

    # El mismo email no entra dos veces: una persona, un contacto.
    assert recepcion.post(
        "/api/contacts", {"first_name": "Ana", "last_name": "Otra", "email": "ana@example.com", "source": "other"}
    ).status_code == 409

    # 2. Recepción la contacta y le da cita: el estado acompaña.
    ficha = recepcion.get(f"/api/contacts/{ana['id']}").json()
    contactada = recepcion.put(f"/api/contacts/{ana['id']}/status", {"status": "contacted", "version": ficha["version"]})
    assert contactada.json()["status"] == "contacted"
    cita = recepcion.post(
        "/api/appointments",
        {"contact_id": ana["id"], "service_id": servicio["id"], "staff_id": prof_cuenta.id, "starts_at": "2027-01-05T10:00"},
    ).json()
    assert cita["status"] == "scheduled"
    assert recepcion.get(f"/api/contacts/{ana['id']}").json()["status"] == "scheduled"

    # La misma franja con la misma persona: 409 aunque sea otro contacto.
    bea = alta(recepcion, "Bea", "Jones", "bea@example.com")
    solapada = recepcion.post(
        "/api/appointments",
        {"contact_id": bea["id"], "service_id": servicio["id"], "staff_id": prof_cuenta.id, "starts_at": "2027-01-05T10:30"},
    )
    assert solapada.status_code == 409
    cita_bea = recepcion.post(
        "/api/appointments",
        {"contact_id": bea["id"], "service_id": servicio["id"], "staff_id": colega_cuenta.id, "starts_at": "2027-01-05T10:30"},
    ).json()

    # 3. Seguimiento para el profesional: lo ve él, no su colega.
    tarea = recepcion.post(
        f"/api/contacts/{ana['id']}/follow-ups",
        {"description": "Confirmar la visita", "due_on": "2027-01-05", "assigned_to_id": prof_cuenta.id},
    ).json()
    assert prof.get("/api/follow-ups/summary").json() == {"overdue": 0, "due_today": 0}
    assert [t["id"] for t in prof.get("/api/follow-ups").json()["items"]] == [tarea["id"]]
    assert colega.get("/api/follow-ups").json()["total"] == 0
    assert colega.post(f"/api/follow-ups/{tarea['id']}/complete", {"version": 1}).status_code == 404

    # 4. El profesional solo alcanza lo suyo.
    assert prof.get(f"/api/contacts/{ana['id']}").status_code == 200
    assert prof.get(f"/api/contacts/{bea['id']}").status_code == 404
    assert colega.get(f"/api/contacts/{ana['id']}").status_code == 404
    assert prof.get("/api/appointments", params={"date": "2027-01-05", "staff_id": colega_cuenta.id}).status_code == 403
    agenda = prof.get("/api/appointments", params={"date": "2027-01-05"}).json()
    assert [c["id"] for c in agenda] == [cita["id"]]
    assert prof.put(f"/api/contacts/{ana['id']}/status", {"status": "lost", "version": 1}).status_code == 403

    # 5. Antes de la hora no se marca asistencia; después, sí, y pasa a Cliente.
    temprano = prof.post(f"/api/appointments/{cita['id']}/attendance", {"status": "completed", "version": cita["version"]})
    assert temprano.status_code == 409
    Reloj.ahora = MARTES_TRAS_LA_CITA
    ajena = colega.post(f"/api/appointments/{cita['id']}/attendance", {"status": "completed", "version": cita["version"]})
    assert ajena.status_code == 404
    marcada = prof.post(f"/api/appointments/{cita['id']}/attendance", {"status": "completed", "version": cita["version"]})
    assert marcada.json()["status"] == "completed"
    assert recepcion.get(f"/api/contacts/{ana['id']}").json()["status"] == "client"

    hecha = prof.post(f"/api/follow-ups/{tarea['id']}/complete", {"version": 1})
    assert hecha.json()["completed_by_email"] == prof_cuenta.email
    assert prof.post(f"/api/follow-ups/{tarea['id']}/complete", {"version": 1}).status_code == 409

    # 6. Recepción invita a las dos, y cada una elige su contraseña con su enlace.
    def portal_de(contacto: dict, contrasena: str) -> Sesion:
        token = recepcion.post(f"/api/contacts/{contacto['id']}/portal-invitation").json()["token"]
        publico = TestClient(fastapi_app)
        assert publico.post("/api/portal-invitations/check", json={"token": token}).json() == {"email": contacto["email"]}
        assert publico.post("/api/portal-invitations/accept", json={"token": token, "password": contrasena}).status_code == 204
        # Un solo uso.
        assert publico.post("/api/portal-invitations/accept", json={"token": token, "password": contrasena}).status_code == 410
        return Sesion(contacto["email"], contrasena)

    portal_ana = portal_de(ana, CONTRASENA_CLIENTA)
    portal_bea = portal_de(bea, CONTRASENA_CLIENTA + "-b")

    # 7. Cada una ve solo lo suyo, sin campos internos; el resto de la API, 403.
    citas_ana = portal_ana.get("/api/portal/appointments").json()
    citas_bea = portal_bea.get("/api/portal/appointments").json()
    assert [c["id"] for c in citas_ana["past"]] == [cita["id"]]
    assert citas_ana["past"][0]["status"] == "completed"
    assert [c["id"] for c in citas_bea["upcoming"] + citas_bea["past"]] == [cita_bea["id"]]
    assert set(citas_ana["past"][0]) == {"id", "service_name", "starts_at", "ends_at", "status"}
    crudo = portal_ana.get("/api/portal/appointments", params={"contact_id": bea["id"]}).text
    assert str(cita_bea["id"]) not in [str(c["id"]) for c in citas_ana["past"]]
    assert NOTA not in crudo and "bea@example.com" not in crudo and prof_cuenta.email not in crudo
    for ruta in (f"/api/contacts/{bea['id']}", f"/api/contacts/{ana['id']}", "/api/contacts", f"/api/contacts/{bea['id']}/follow-ups", "/api/follow-ups", "/api/audit-events"):
        assert portal_ana.get(ruta).status_code == 403, ruta

    # 8. Cerrar sesión corta el acceso aunque se reenvíe la cookie.
    assert portal_ana.post("/api/auth/logout").status_code == 204
    assert portal_ana.get("/api/portal/appointments").status_code == 401

    # 9. Admin reconstruye lo ocurrido con Ana desde la auditoría; nadie más puede.
    assert recepcion.get("/api/audit-events").status_code == 403
    assert prof.get("/api/audit-events").status_code == 403
    eventos = admin.get("/api/audit-events", params={"page": 1}).json()
    # Las más antiguas pueden quedar en otra página: pedir por acción las que importan.
    def por_accion(accion: str) -> list[dict]:
        return admin.get("/api/audit-events", params={"action": accion}).json()["items"]

    assert eventos["total"] > 20
    cambios_ana = [
        (e["from_status"], e["to_status"], e["actor_email"])
        for e in reversed(por_accion("contact_status_changed"))
        if e["target_id"] == ana["id"]
    ]
    assert cambios_ana == [
        ("new", "contacted", recepcion_cuenta.email),
        ("contacted", "scheduled", recepcion_cuenta.email),
        ("scheduled", "client", prof_cuenta.email),
    ]
    assert [e["actor_email"] for e in por_accion("follow_up_completed")] == [prof_cuenta.email]
    aperturas = {(e["actor_email"], e["target_id"]) for e in por_accion("contact_viewed")}
    assert (prof_cuenta.email, ana["id"]) in aperturas
    # Lo que se rechazó no aparece como si hubiera pasado.
    assert (colega_cuenta.email, ana["id"]) not in aperturas
    assert (prof_cuenta.email, bea["id"]) not in aperturas
    assert len(por_accion("invitation_accepted")) == 2
    assert len(por_accion("appointment_attendance_marked")) == 1
    # Y ningún evento copia una nota.
    assert NOTA not in admin.get("/api/audit-events").text


def test_errores_que_ve_el_usuario_son_comprensibles_y_no_filtran_detalles(db):
    recepcion = Sesion(cuenta(db, "recepcion", Role.RECEPTION).email)

    sin_datos = recepcion.post("/api/contacts", {"first_name": "", "last_name": "Smith", "email": "x", "source": "other"})
    assert sin_datos.status_code == 422
    assert {e["loc"][-1] for e in sin_datos.json()["detail"]} == {"first_name", "email"}

    sin_token = recepcion.client.post(
        "/api/contacts", json={"first_name": "Ana", "last_name": "Smith", "email": "ana@example.com", "source": "other"}
    )
    assert sin_token.status_code == 403
    assert sin_token.json() == {"detail": "Token CSRF ausente o no válido"}

    assert recepcion.get("/api/contacts/999999").json() == {"detail": "Contacto no encontrado"}

    sin_sesion = TestClient(fastapi_app).get("/api/contacts")
    assert sin_sesion.status_code == 401
    assert sin_sesion.json() == {"detail": "No autenticado"}

    pasada = recepcion.post(
        "/api/appointments",
        {"contact_id": 1, "service_id": 1, "staff_id": 1, "starts_at": (LUNES - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")},
    )
    assert pasada.status_code == 422
    assert "SELECT" not in pasada.text and "psycopg" not in pasada.text
