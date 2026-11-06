"""Eventos de auditoría contra PostgreSQL real (T26): qué se registra, qué no se guarda nunca, quién los
consulta y que el evento y su acción van juntos. «Ahora» es el lunes 04/01/2027 a las 10:00 de Nueva York."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import contacts_routes
from app.appointments_routes import get_now
from app.auth import hash_token
from app.main import app as fastapi_app
from app.models import AuditEvent, Contact, PortalInvitation, Role, Service, ServiceStaff, UserSession
from test_follow_ups import AHORA, PASSWORD, cita, contacto, cuenta, sesion, tarea

EVENTOS = "/api/audit-events"
NOTA_SECRETA = "Texto de la nota que no debe copiarse"
NOTA_NUEVA = "Otra nota que tampoco debe copiarse"


@pytest.fixture(autouse=True)
def reloj_fijo():
    fastapi_app.dependency_overrides[get_now] = lambda: AHORA
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


def eventos(db, accion: str | None = None) -> list[AuditEvent]:
    # Deshace lo no confirmado: un evento que la ruta añadió sin hacer commit no debe contar.
    db.rollback()
    query = select(AuditEvent).order_by(AuditEvent.id)
    if accion is not None:
        query = query.where(AuditEvent.action == accion)
    return list(db.scalars(query))


def uno(db, accion: str) -> AuditEvent:
    encontrados = eventos(db, accion)
    assert len(encontrados) == 1, [e.action for e in eventos(db)]
    return encontrados[0]


def ficha_cuerpo(ficha: Contact, **campos) -> dict:
    return {
        "first_name": ficha.first_name,
        "last_name": ficha.last_name,
        "email": ficha.email,
        "phone": ficha.phone,
        "source": ficha.source,
        "note": ficha.note,
        "owner_id": ficha.owner_id,
        "version": ficha.version,
        **campos,
    }


def servicio(db, persona, nombre: str = "Limpieza") -> Service:
    nuevo = Service(name=nombre, duration_minutes=60)
    db.add(nuevo)
    db.flush()
    db.add(ServiceStaff(service_id=nuevo.id, user_id=persona.id))
    db.flush()
    return nuevo


# --- Acceso ---------------------------------------------------------------------------


def test_un_login_correcto_y_el_logout_quedan_a_nombre_de_la_cuenta(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    client, csrf = sesion(recepcion)

    entrada = uno(db, "login_succeeded")
    assert entrada.actor_id == recepcion.id
    assert entrada.target_type is None

    assert client.post("/api/auth/logout", headers=csrf).status_code == 204
    assert uno(db, "logout").actor_id == recepcion.id


def test_un_login_fallido_guarda_la_cuenta_como_objetivo_y_no_como_actor(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)

    response = TestClient(fastapi_app).post("/api/auth/login", json={"email": recepcion.email, "password": "mala"})

    assert response.status_code == 401
    fallo = uno(db, "login_failed")
    assert fallo.actor_id is None
    assert (fallo.target_type, fallo.target_id) == ("user", recepcion.id)


def test_un_login_con_un_email_que_no_existe_no_guarda_lo_tecleado(db):
    tecleado = "mi-contrasena-en-el-campo-equivocado"

    response = TestClient(fastapi_app).post("/api/auth/login", json={"email": tecleado, "password": "mala"})

    assert response.status_code == 401
    fallo = uno(db, "login_failed")
    assert fallo.actor_id is None and fallo.target_type is None and fallo.target_id is None
    assert fallo.changed_fields is None


def test_el_login_fallido_de_una_cuenta_desactivada_tambien_se_registra(db):
    baja = cuenta(db, "baja", Role.RECEPTION, active=False)

    response = TestClient(fastapi_app).post("/api/auth/login", json={"email": baja.email, "password": PASSWORD})

    assert response.status_code == 401
    assert uno(db, "login_failed").target_id == baja.id


def test_con_el_limite_superado_no_se_registran_mas_fallos(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    client = TestClient(fastapi_app)

    codigos = [
        client.post("/api/auth/login", json={"email": recepcion.email, "password": "mala"}).status_code
        for _ in range(7)
    ]

    assert codigos == [401] * 5 + [429] * 2
    assert len(eventos(db, "login_failed")) == 5


def test_los_eventos_no_guardan_contrasenas_ni_tokens(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    client, csrf = sesion(recepcion)
    client.post("/api/auth/login", json={"email": recepcion.email, "password": "contrasena-equivocada"})
    client.post("/api/auth/logout", headers=csrf)
    sesiones = db.scalars(select(UserSession.token_hash)).all()

    filas = db.execute(text("SELECT audit_events::text FROM audit_events")).scalars().all()

    assert len(filas) == 3
    for fila in filas:
        assert "contrasena-equivocada" not in fila
        assert PASSWORD not in fila
        assert csrf["X-CSRF-Token"] not in fila
        assert all(token_hash not in fila for token_hash in sesiones)


# --- Abrir una ficha ------------------------------------------------------------------


def test_abrir_una_ficha_registra_quien_vio_a_quien(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, _ = sesion(recepcion)

    assert client.get(f"/api/contacts/{ficha.id}").status_code == 200

    visto = uno(db, "contact_viewed")
    assert visto.actor_id == recepcion.id
    assert (visto.target_type, visto.target_id) == ("contact", ficha.id)


def test_cada_apertura_es_un_evento(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, _ = sesion(recepcion)

    client.get(f"/api/contacts/{ficha.id}")
    client.get(f"/api/contacts/{ficha.id}")

    assert len(eventos(db, "contact_viewed")) == 2


def test_el_profesional_que_abre_la_ficha_de_su_contacto_queda_registrado(db):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof)
    client, _ = sesion(prof)

    assert client.get(f"/api/contacts/{ficha.id}").status_code == 200

    assert uno(db, "contact_viewed").actor_id == prof.id


def test_un_acceso_denegado_a_una_ficha_no_es_un_evento(db):
    # Decisión T26: los rechazos siguen en el log, no en esta tabla.
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    client, _ = sesion(prof)

    assert client.get(f"/api/contacts/{ficha.id}").status_code == 404

    assert eventos(db, "contact_viewed") == []


def test_las_listas_y_busquedas_no_son_eventos(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    contacto(db)
    client, _ = sesion(recepcion)
    antes = len(eventos(db))

    assert client.get("/api/contacts", params={"q": "ana"}).status_code == 200

    assert len(eventos(db)) == antes


# --- Contactos ------------------------------------------------------------------------


def test_crear_un_contacto_se_registra(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    client, csrf = sesion(recepcion)

    response = client.post(
        "/api/contacts",
        json={"first_name": "Ana", "last_name": "Lopez", "email": "ana@example.com", "source": "other", "note": NOTA_SECRETA},
        headers=csrf,
    )

    assert response.status_code == 201
    creado = uno(db, "contact_created")
    assert creado.actor_id == recepcion.id
    assert (creado.target_type, creado.target_id) == ("contact", response.json()["id"])


def test_un_contacto_duplicado_no_deja_evento(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    contacto(db)
    client, csrf = sesion(recepcion)

    response = client.post(
        "/api/contacts",
        json={"first_name": "Ana", "last_name": "Lopez", "email": "ana@example.com", "source": "other"},
        headers=csrf,
    )

    assert response.status_code == 409
    assert eventos(db, "contact_created") == []


def test_editar_una_ficha_guarda_los_nombres_de_los_campos_y_no_sus_valores(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db, note=NOTA_SECRETA, owner_id=recepcion.id)
    client, csrf = sesion(recepcion)

    response = client.put(
        f"/api/contacts/{ficha.id}",
        json=ficha_cuerpo(ficha, note=NOTA_NUEVA, phone="+12125550123"),
        headers=csrf,
    )

    assert response.status_code == 200, response.text
    editado = uno(db, "contact_updated")
    assert editado.actor_id == recepcion.id
    assert editado.changed_fields == "note, phone"
    fila = db.execute(text("SELECT audit_events::text FROM audit_events WHERE id = :i"), {"i": editado.id}).scalar_one()
    assert NOTA_SECRETA not in fila
    assert NOTA_NUEVA not in fila
    assert "+12125550123" not in fila


def test_guardar_una_ficha_sin_cambios_registra_el_guardado_sin_campos(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db, owner_id=recepcion.id)
    client, csrf = sesion(recepcion)

    assert client.put(f"/api/contacts/{ficha.id}", json=ficha_cuerpo(ficha), headers=csrf).status_code == 200

    assert uno(db, "contact_updated").changed_fields is None


def test_una_edicion_con_version_vieja_no_deja_evento(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db, version=2)
    client, csrf = sesion(recepcion)

    response = client.put(f"/api/contacts/{ficha.id}", json=ficha_cuerpo(ficha, version=1), headers=csrf)

    assert response.status_code == 409
    assert eventos(db, "contact_updated") == []


def test_cambiar_el_estado_a_mano_guarda_el_origen_y_el_destino(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, csrf = sesion(recepcion)

    response = client.put(f"/api/contacts/{ficha.id}/status", json={"status": "lost", "version": 1}, headers=csrf)

    assert response.status_code == 200, response.text
    cambio = uno(db, "contact_status_changed")
    assert cambio.actor_id == recepcion.id
    assert (cambio.from_status, cambio.to_status) == ("new", "lost")


def test_un_cambio_de_estado_no_permitido_no_deja_evento(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db, status="contacted")
    client, csrf = sesion(recepcion)

    response = client.put(f"/api/contacts/{ficha.id}/status", json={"status": "contacted", "version": 1}, headers=csrf)

    assert response.status_code == 422
    assert eventos(db, "contact_status_changed") == []


# --- Servicios ------------------------------------------------------------------------


def test_crear_un_servicio_se_registra(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    client, csrf = sesion(recepcion)

    response = client.post(
        "/api/services", json={"name": "Limpieza", "duration_minutes": 60, "staff_ids": [prof.id]}, headers=csrf
    )

    assert response.status_code == 201, response.text
    creado = uno(db, "service_created")
    assert (creado.target_type, creado.target_id) == ("service", response.json()["id"])


def test_editar_un_servicio_guarda_que_cambio_tambien_las_personas(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    colega = cuenta(db, "colega", Role.PROFESSIONAL)
    existente = servicio(db, prof)
    client, csrf = sesion(recepcion)

    response = client.put(
        f"/api/services/{existente.id}",
        json={"name": "Limpieza", "duration_minutes": 90, "active": True, "staff_ids": [colega.id], "version": 1},
        headers=csrf,
    )

    assert response.status_code == 200, response.text
    assert uno(db, "service_updated").changed_fields == "duration_minutes, staff_ids"


def test_editar_un_servicio_sin_tocar_las_personas_no_las_nombra(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    existente = servicio(db, prof)
    client, csrf = sesion(recepcion)

    response = client.put(
        f"/api/services/{existente.id}",
        json={"name": "Limpieza", "duration_minutes": 60, "active": False, "staff_ids": [prof.id], "version": 1},
        headers=csrf,
    )

    assert response.status_code == 200, response.text
    assert uno(db, "service_updated").changed_fields == "active"


# --- Citas ----------------------------------------------------------------------------


def test_crear_una_cita_registra_la_cita_y_el_cambio_de_estado_del_contacto(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    existente = servicio(db, prof)
    client, csrf = sesion(recepcion)

    response = client.post(
        "/api/appointments",
        json={"contact_id": ficha.id, "service_id": existente.id, "staff_id": prof.id, "starts_at": "2027-01-05T10:00"},
        headers=csrf,
    )

    assert response.status_code == 201, response.text
    creada = uno(db, "appointment_created")
    assert (creada.target_type, creada.target_id) == ("appointment", response.json()["id"])
    cambio = uno(db, "contact_status_changed")
    assert cambio.actor_id == recepcion.id
    assert (cambio.target_type, cambio.target_id) == ("contact", ficha.id)
    assert (cambio.from_status, cambio.to_status) == ("new", "scheduled")


def test_una_segunda_cita_no_registra_un_cambio_de_estado_que_no_hubo(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db, status="scheduled")
    existente = servicio(db, prof)
    client, csrf = sesion(recepcion)

    response = client.post(
        "/api/appointments",
        json={"contact_id": ficha.id, "service_id": existente.id, "staff_id": prof.id, "starts_at": "2027-01-05T10:00"},
        headers=csrf,
    )

    assert response.status_code == 201, response.text
    assert eventos(db, "contact_status_changed") == []


def test_una_cita_que_se_solapa_no_deja_eventos(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    existente = servicio(db, prof)
    cita(db, contacto(db, "bea"), prof, horas=24)  # 05/01 a las 10:00 de Nueva York
    client, csrf = sesion(recepcion)

    response = client.post(
        "/api/appointments",
        json={"contact_id": ficha.id, "service_id": existente.id, "staff_id": prof.id, "starts_at": "2027-01-05T10:00"},
        headers=csrf,
    )

    assert response.status_code == 409, response.text
    assert eventos(db, "appointment_created") == []
    assert eventos(db, "contact_status_changed") == []


def test_reprogramar_guarda_lo_que_cambio(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db, status="scheduled")
    existente = servicio(db, prof)
    original = cita(db, ficha, prof)
    original.service_id = existente.id
    db.flush()
    client, csrf = sesion(recepcion)

    response = client.put(
        f"/api/appointments/{original.id}",
        json={"starts_at": "2027-01-06T10:00", "staff_id": prof.id, "version": 1},
        headers=csrf,
    )

    assert response.status_code == 200, response.text
    assert uno(db, "appointment_rescheduled").changed_fields == "starts_at"


def test_cancelar_la_ultima_cita_registra_los_dos_cambios_de_estado(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db, status="scheduled")
    original = cita(db, ficha, prof)
    client, csrf = sesion(recepcion)

    response = client.post(
        f"/api/appointments/{original.id}/cancel",
        json={"version": 1, "reason": "client_request", "note": NOTA_SECRETA},
        headers=csrf,
    )

    assert response.status_code == 200, response.text
    cancelada = uno(db, "appointment_cancelled")
    assert (cancelada.from_status, cancelada.to_status) == ("scheduled", "cancelled")
    cambio = uno(db, "contact_status_changed")
    assert (cambio.from_status, cambio.to_status) == ("scheduled", "contacted")
    assert NOTA_SECRETA not in db.execute(text("SELECT string_agg(audit_events::text, ' ') FROM audit_events")).scalar_one()


def test_cancelar_con_otras_citas_no_cambia_el_estado_del_contacto(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db, status="scheduled")
    original = cita(db, ficha, prof)
    cita(db, ficha, prof, horas=48)
    client, csrf = sesion(recepcion)

    response = client.post(
        f"/api/appointments/{original.id}/cancel", json={"version": 1, "reason": "clinic"}, headers=csrf
    )

    assert response.status_code == 200, response.text
    assert eventos(db, "contact_status_changed") == []


def test_marcar_la_asistencia_guarda_quien_y_el_paso_a_cliente(db):
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db, status="scheduled")
    original = cita(db, ficha, prof, horas=-2)
    client, csrf = sesion(prof)

    response = client.post(
        f"/api/appointments/{original.id}/attendance", json={"version": 1, "status": "completed"}, headers=csrf
    )

    assert response.status_code == 200, response.text
    marcada = uno(db, "appointment_attendance_marked")
    assert marcada.actor_id == prof.id
    assert (marcada.from_status, marcada.to_status) == ("scheduled", "completed")
    cambio = uno(db, "contact_status_changed")
    assert cambio.actor_id == prof.id
    assert (cambio.from_status, cambio.to_status) == ("scheduled", "client")


def test_corregir_la_asistencia_conserva_las_dos_marcas_en_el_historial(db):
    # Lo que T20b dejó pendiente: la cita solo guarda al último autor.
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db, status="scheduled")
    original = cita(db, ficha, prof, horas=-2)
    client_prof, csrf_prof = sesion(prof)
    client_recepcion, csrf_recepcion = sesion(recepcion)

    primera = client_prof.post(
        f"/api/appointments/{original.id}/attendance", json={"version": 1, "status": "completed"}, headers=csrf_prof
    )
    segunda = client_recepcion.post(
        f"/api/appointments/{original.id}/attendance", json={"version": 2, "status": "no_show"}, headers=csrf_recepcion
    )

    assert primera.status_code == segunda.status_code == 200
    marcas = eventos(db, "appointment_attendance_marked")
    assert [(e.actor_id, e.from_status, e.to_status) for e in marcas] == [
        (prof.id, "scheduled", "completed"),
        (recepcion.id, "completed", "no_show"),
    ]
    assert [(e.from_status, e.to_status) for e in eventos(db, "contact_status_changed")] == [
        ("scheduled", "client"),
        ("client", "contacted"),
    ]


def test_editar_la_nota_de_una_cita_no_copia_el_texto(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    original = cita(db, contacto(db), prof)
    client, csrf = sesion(recepcion)

    response = client.put(f"/api/appointments/{original.id}/note", json={"version": 1, "note": NOTA_SECRETA}, headers=csrf)

    assert response.status_code == 200, response.text
    editada = uno(db, "appointment_note_edited")
    assert editada.changed_fields == "note"
    assert NOTA_SECRETA not in db.execute(text("SELECT audit_events::text FROM audit_events WHERE id = :i"), {"i": editada.id}).scalar_one()


# --- Invitaciones ---------------------------------------------------------------------


def test_invitar_y_aceptar_se_registran_sin_el_token(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, csrf = sesion(recepcion)

    invitacion = client.post(f"/api/contacts/{ficha.id}/portal-invitation", headers=csrf)
    assert invitacion.status_code == 201, invitacion.text
    token = invitacion.json()["token"]
    aceptada = TestClient(fastapi_app).post(
        "/api/portal-invitations/accept", json={"token": token, "password": PASSWORD}
    )

    assert aceptada.status_code == 204, aceptada.text
    creada = uno(db, "invitation_created")
    assert creada.actor_id == recepcion.id
    assert (creada.target_type, creada.target_id) == ("contact", ficha.id)
    aceptacion = uno(db, "invitation_accepted")
    # El cliente es el actor: lo prueba tener el enlace, y la cuenta nace en la misma transacción.
    assert aceptacion.actor_id is not None and aceptacion.actor_id != recepcion.id
    assert (aceptacion.target_type, aceptacion.target_id) == ("contact", ficha.id)
    filas = " ".join(db.execute(text("SELECT audit_events::text FROM audit_events")).scalars())
    assert token not in filas
    assert hash_token(token) not in filas


def test_una_invitacion_rechazada_no_deja_evento(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db, status="lost")
    client, csrf = sesion(recepcion)

    assert client.post(f"/api/contacts/{ficha.id}/portal-invitation", headers=csrf).status_code == 409

    assert eventos(db, "invitation_created") == []


def test_aceptar_con_un_email_ya_ocupado_no_deja_evento_ni_gasta_el_enlace(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, csrf = sesion(recepcion)
    token = client.post(f"/api/contacts/{ficha.id}/portal-invitation", headers=csrf).json()["token"]
    # Una cuenta nace con ese email después de invitar: lo que protege la restricción única.
    cuenta(db, "ana-ocupa", Role.RECEPTION)
    db.execute(text("UPDATE users SET email = :e WHERE email = :o"), {"e": ficha.email, "o": "ana-ocupa@prueba.example.com"})

    response = TestClient(fastapi_app).post("/api/portal-invitations/accept", json={"token": token, "password": PASSWORD})

    assert response.status_code == 409, response.text
    assert eventos(db, "invitation_accepted") == []
    assert db.scalar(select(PortalInvitation.used_at)) is None


# --- Tareas ---------------------------------------------------------------------------


def test_el_ciclo_de_una_tarea_deja_un_evento_por_paso(db):
    # Lo que T25 dejó pendiente: la tarea solo guarda quién la marcó por última vez.
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    ficha = contacto(db)
    cita(db, ficha, prof)
    client, csrf = sesion(recepcion)

    creada = client.post(
        f"/api/contacts/{ficha.id}/follow-ups",
        json={"description": NOTA_SECRETA, "due_on": "2027-01-11", "assigned_to_id": recepcion.id},
        headers=csrf,
    )
    assert creada.status_code == 201, creada.text
    id_tarea = creada.json()["id"]
    editada = client.put(
        f"/api/follow-ups/{id_tarea}",
        json={"description": NOTA_NUEVA, "due_on": "2027-01-11", "assigned_to_id": prof.id, "version": 1},
        headers=csrf,
    )
    assert editada.status_code == 200, editada.text
    client_prof, csrf_prof = sesion(prof)
    assert client_prof.post(f"/api/follow-ups/{id_tarea}/complete", json={"version": 2}, headers=csrf_prof).status_code == 200
    assert client.post(f"/api/follow-ups/{id_tarea}/reopen", json={"version": 3}, headers=csrf).status_code == 200

    assert uno(db, "follow_up_created").actor_id == recepcion.id
    edicion = uno(db, "follow_up_updated")
    assert edicion.changed_fields == "assigned_to_id, description"
    assert uno(db, "follow_up_completed").actor_id == prof.id
    reapertura = uno(db, "follow_up_reopened")
    assert reapertura.actor_id == recepcion.id
    assert (reapertura.target_type, reapertura.target_id) == ("follow_up", id_tarea)
    filas = " ".join(db.execute(text("SELECT audit_events::text FROM audit_events")).scalars())
    assert NOTA_SECRETA not in filas
    assert NOTA_NUEVA not in filas


def test_completar_con_version_vieja_no_deja_evento(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    pendiente = tarea(db, contacto(db), recepcion, version=2)
    client, csrf = sesion(recepcion)

    response = client.post(f"/api/follow-ups/{pendiente.id}/complete", json={"version": 1}, headers=csrf)

    assert response.status_code == 409
    assert eventos(db, "follow_up_completed") == []


# --- El evento y la acción van juntos ---------------------------------------------------


def test_si_el_evento_falla_la_accion_no_se_guarda(db, monkeypatch):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, csrf = sesion(recepcion)

    def falla(*_args, **_kwargs):
        raise RuntimeError("fallo al registrar")

    monkeypatch.setattr(contacts_routes, "record", falla)
    with pytest.raises(RuntimeError):
        client.put(f"/api/contacts/{ficha.id}/status", json={"status": "lost", "version": 1}, headers=csrf)

    db.rollback()
    db.expire_all()
    guardada = db.get(Contact, ficha.id)
    assert guardada.status == "new"
    assert guardada.version == 1


def test_si_el_commit_falla_no_queda_ni_la_accion_ni_el_evento(db, monkeypatch):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client, csrf = sesion(recepcion)

    def falla():
        raise RuntimeError("fallo al confirmar")

    monkeypatch.setattr(db, "commit", falla)
    with pytest.raises(RuntimeError):
        client.put(f"/api/contacts/{ficha.id}/status", json={"status": "lost", "version": 1}, headers=csrf)

    monkeypatch.undo()
    db.rollback()
    assert eventos(db, "contact_status_changed") == []
    assert db.get(Contact, ficha.id).status == "new"


# --- La BD no admite cualquier cosa -----------------------------------------------------


@pytest.mark.parametrize(
    "columnas, valores",
    [
        ("action", "'inventada'"),
        ("action, target_type, target_id", "'contact_viewed', 'inventado', 1"),
        ("action, target_type", "'contact_viewed', 'contact'"),
        ("action, target_id", "'contact_viewed', 1"),
        ("action, changed_fields", "'contact_updated', 'Tiene alergia a la penicilina'"),
        ("action, changed_fields", "'contact_updated', ''"),
        ("action, from_status", "'contact_updated', 'Texto libre'"),
        ("action, to_status", "'contact_updated', 'Texto libre'"),
    ],
)
def test_la_bd_rechaza_eventos_no_validos(db, columnas, valores):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(f"INSERT INTO audit_events ({columnas}) VALUES ({valores})"))


def test_la_bd_no_deja_borrar_una_cuenta_con_eventos(db):
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    sesion(recepcion)

    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("DELETE FROM users WHERE id = :i"), {"i": recepcion.id})


# --- Consulta -------------------------------------------------------------------------


@pytest.mark.parametrize("rol", [Role.RECEPTION, Role.PROFESSIONAL, Role.CLIENT])
def test_solo_administracion_consulta_los_eventos(db, rol):
    otro = cuenta(db, "otro", rol)
    client, _ = sesion(otro)

    assert client.get(EVENTOS).status_code == 403


def test_sin_sesion_no_se_consultan(db):
    assert TestClient(fastapi_app).get(EVENTOS).status_code == 401


def test_admin_ve_los_eventos_del_mas_reciente_al_mas_antiguo_con_el_email_de_quien_actuo(db):
    admin = cuenta(db, "admin", Role.ADMIN)
    ficha = contacto(db)
    client, _ = sesion(admin)
    client.get(f"/api/contacts/{ficha.id}")

    cuerpo = client.get(EVENTOS).json()

    assert cuerpo["total"] == 2
    assert cuerpo["page_size"] == 50
    primero, segundo = cuerpo["items"]
    assert primero["action"] == "contact_viewed"
    assert primero["actor_email"] == admin.email
    assert (primero["target_type"], primero["target_id"]) == ("contact", ficha.id)
    assert primero["target_email"] is None
    assert primero["changed_fields"] == []
    assert primero["occurred_at"]
    assert segundo["action"] == "login_succeeded"


def test_un_login_fallido_muestra_la_cuenta_intentada_sin_actor(db):
    admin = cuenta(db, "admin", Role.ADMIN)
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    TestClient(fastapi_app).post("/api/auth/login", json={"email": recepcion.email, "password": "mala"})
    client, _ = sesion(admin)

    cuerpo = client.get(EVENTOS, params={"action": "login_failed"}).json()

    assert cuerpo["total"] == 1
    item = cuerpo["items"][0]
    assert item["actor_email"] is None
    assert item["target_email"] == recepcion.email


def test_el_id_de_un_contacto_no_se_confunde_con_el_de_una_cuenta(db):
    # target_email solo si el objetivo es una cuenta, aunque coincida el número.
    admin = cuenta(db, "admin", Role.ADMIN)
    db.add(AuditEvent(action="contact_viewed", actor_id=admin.id, target_type="contact", target_id=admin.id))
    db.flush()
    client, _ = sesion(admin)

    cuerpo = client.get(EVENTOS, params={"action": "contact_viewed"}).json()

    assert cuerpo["items"][0]["target_email"] is None


def test_devuelve_la_lista_de_campos_que_cambiaron(db):
    admin = cuenta(db, "admin", Role.ADMIN)
    db.add(AuditEvent(action="contact_updated", actor_id=admin.id, changed_fields="note, phone"))
    db.flush()
    client, _ = sesion(admin)

    cuerpo = client.get(EVENTOS, params={"action": "contact_updated"}).json()

    assert cuerpo["items"][0]["changed_fields"] == ["note", "phone"]


def test_filtra_por_persona_y_por_accion(db):
    admin = cuenta(db, "admin", Role.ADMIN)
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    ficha = contacto(db)
    client_recepcion, _ = sesion(recepcion)
    client_recepcion.get(f"/api/contacts/{ficha.id}")
    client, _ = sesion(admin)
    client.get(f"/api/contacts/{ficha.id}")

    de_recepcion = client.get(EVENTOS, params={"actor_id": recepcion.id}).json()
    aperturas = client.get(EVENTOS, params={"action": "contact_viewed"}).json()
    las_dos = client.get(EVENTOS, params={"actor_id": recepcion.id, "action": "contact_viewed"}).json()

    assert de_recepcion["total"] == 2
    assert {i["actor_email"] for i in de_recepcion["items"]} == {recepcion.email}
    assert aperturas["total"] == 2
    assert {i["action"] for i in aperturas["items"]} == {"contact_viewed"}
    assert las_dos["total"] == 1
    assert las_dos["items"][0]["actor_email"] == recepcion.email


def test_pagina_de_cincuenta_en_cincuenta(db):
    admin = cuenta(db, "admin", Role.ADMIN)
    for _ in range(55):
        db.add(AuditEvent(action="logout", actor_id=admin.id))
    db.flush()
    client, _ = sesion(admin)

    primera = client.get(EVENTOS, params={"action": "logout"}).json()
    segunda = client.get(EVENTOS, params={"action": "logout", "page": 2}).json()

    assert primera["total"] == segunda["total"] == 55
    assert len(primera["items"]) == 50
    assert len(segunda["items"]) == 5
    assert not {i["id"] for i in primera["items"]} & {i["id"] for i in segunda["items"]}
    assert primera["items"][0]["id"] > segunda["items"][0]["id"]


@pytest.mark.parametrize("parametros", [{"page": 0}, {"page": -1}, {"action": "inventada"}, {"actor_id": "uno"}])
def test_parametros_no_validos_dan_422(db, parametros):
    admin = cuenta(db, "admin", Role.ADMIN)
    client, _ = sesion(admin)

    assert client.get(EVENTOS, params=parametros).status_code == 422


def test_consultar_los_eventos_no_crea_eventos(db):
    admin = cuenta(db, "admin", Role.ADMIN)
    client, _ = sesion(admin)
    antes = len(eventos(db))

    assert client.get(EVENTOS).status_code == 200

    assert len(eventos(db)) == antes


def test_la_api_no_ofrece_cambiar_ni_borrar_eventos():
    rutas = fastapi_app.openapi()["paths"]
    de_auditoria = {path: set(ops) for path, ops in rutas.items() if path.startswith(EVENTOS)}
    assert de_auditoria == {EVENTOS: {"get"}}


def test_las_sesiones_caducadas_no_se_llevan_los_eventos(db):
    # Los eventos cuelgan de la cuenta, no de la sesión: la purga de T09 no los toca.
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    sesion(recepcion)
    db.execute(
        text("UPDATE sessions SET expires_at = :v WHERE user_id = :u"),
        {"v": AHORA - timedelta(days=400), "u": recepcion.id},
    )
    otra = cuenta(db, "otra", Role.RECEPTION)
    sesion(otra)  # este login purga

    assert db.scalar(select(AuditEvent.id).where(AuditEvent.actor_id == recepcion.id)) is not None
    assert db.scalar(select(UserSession.id).where(UserSession.user_id == recepcion.id)) is None
