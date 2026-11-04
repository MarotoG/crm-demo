"""Invitación al portal y cuenta de cliente contra PostgreSQL real (T21): quién invita, a quién, la
caducidad, el enlace de un solo uso y el vínculo con el contacto. También las citas en la ficha."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.appointments_routes import get_now
from app.auth import CSRF_HEADER, hash_token
from app.main import app as fastapi_app
from app.models import Appointment, Contact, ContactStatus, PortalInvitation, Role, Service, User
from app.security import hash_password, verify_password

PASSWORD = "contraseña-de-prueba-larga"
CLIENTE = {"email": "Ana.Cliente@Example.com", "password": "una-frase-bastante-larga"}
AHORA = datetime(2027, 1, 4, 15, 0, tzinfo=UTC)
ENLACE_NO_VALE = "Este enlace no es válido o ha caducado. Pide uno nuevo a la clínica."


@pytest.fixture(autouse=True)
def reloj_fijo():
    poner_reloj(AHORA)
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


def poner_reloj(momento: datetime) -> None:
    fastapi_app.dependency_overrides[get_now] = lambda: momento


@pytest.fixture
def usuarios(db) -> dict[Role, User]:
    creados = {}
    for role in Role:
        user = User(email=f"{role.value}@prueba.example.com", password_hash=hash_password(PASSWORD), role=role)
        db.add(user)
        creados[role] = user
    db.flush()
    return creados


def contacto(db, status: ContactStatus = ContactStatus.NEW, nombre: str = "Ana") -> Contact:
    contact = Contact(first_name=nombre, last_name="Lopez", phone="+12125550123", source="instagram", status=status)
    db.add(contact)
    db.flush()
    return contact


def sesion_de(role: Role) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(fastapi_app)
    response = client.post("/api/auth/login", json={"email": f"{role.value}@prueba.example.com", "password": PASSWORD})
    assert response.status_code == 200
    return client, {CSRF_HEADER: response.json()["csrf_token"]}


def invitar(contact_id: int, role: Role = Role.RECEPTION):
    client, csrf = sesion_de(role)
    return client.post(f"/api/contacts/{contact_id}/portal-invitation", headers=csrf)


def token_de(contact_id: int) -> str:
    response = invitar(contact_id)
    assert response.status_code == 201
    return response.json()["token"]


def aceptar(token: str, **cambios):
    return TestClient(fastapi_app).post("/api/portal-invitations/accept", json={"token": token, **CLIENTE, **cambios})


def comprobar(token: str):
    return TestClient(fastapi_app).post("/api/portal-invitations/check", json={"token": token})


def estado_portal(contact_id: int, role: Role = Role.RECEPTION):
    client, _ = sesion_de(role)
    return client.get(f"/api/contacts/{contact_id}/portal")


def clientes(db) -> list[User]:
    return list(db.scalars(select(User).where(User.contact_id.is_not(None))))


def error_de(response, campo: str) -> str:
    return next(e["msg"] for e in response.json()["detail"] if e["loc"] == ["body", campo])


# --- Generar el enlace ------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_generan_el_enlace(db, usuarios, role):
    contact = contacto(db)

    response = invitar(contact.id, role)

    assert response.status_code == 201
    cuerpo = response.json()
    assert set(cuerpo) == {"token", "expires_at"}
    assert datetime.fromisoformat(cuerpo["expires_at"]) == AHORA + timedelta(hours=24)
    guardada = db.scalar(select(PortalInvitation))
    assert guardada.contact_id == contact.id and guardada.created_by_id == usuarios[role].id


@pytest.mark.parametrize("role", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_invitan(db, usuarios, role):
    contact = contacto(db)

    assert invitar(contact.id, role).status_code == 403
    assert estado_portal(contact.id, role).status_code == 403
    assert db.scalar(select(func.count()).select_from(PortalInvitation)) == 0


def test_sin_csrf_no_se_genera(db, usuarios):
    contact = contacto(db)
    client, _ = sesion_de(Role.RECEPTION)

    assert client.post(f"/api/contacts/{contact.id}/portal-invitation").status_code == 403


def test_en_la_bd_solo_queda_el_hash_del_token(db, usuarios):
    token = token_de(contacto(db).id)

    guardada = db.scalar(select(PortalInvitation))
    assert guardada.token_hash == hash_token(token) and token not in guardada.token_hash


@pytest.mark.parametrize("estado", [ContactStatus.NEW, ContactStatus.CONTACTED, ContactStatus.SCHEDULED, ContactStatus.CLIENT])
def test_se_invita_a_cualquier_contacto_aunque_no_tenga_citas(db, usuarios, estado):
    assert invitar(contacto(db, estado).id).status_code == 201


def test_a_un_perdido_no_se_le_invita(db, usuarios):
    response = invitar(contacto(db, ContactStatus.LOST).id)

    assert response.status_code == 409
    assert response.json()["detail"] == "El contacto está «Perdido»: reábrelo antes de invitarlo"


def test_contacto_inexistente_da_404(db, usuarios):
    assert invitar(999999).status_code == 404
    assert estado_portal(999999).status_code == 404


def test_invitar_no_cambia_la_ficha(db, usuarios):
    contact = contacto(db)

    token_de(contact.id)

    db.refresh(contact)
    assert contact.status == ContactStatus.NEW and contact.version == 1


def test_generar_otro_anula_el_anterior(db, usuarios):
    contact = contacto(db)
    primero = token_de(contact.id)

    segundo = token_de(contact.id)

    assert primero != segundo
    assert aceptar(primero).status_code == 410
    assert aceptar(segundo).status_code == 204


def test_quien_ya_tiene_cuenta_recibe_un_aviso_y_no_otro_enlace(db, usuarios):
    contact = contacto(db)
    assert aceptar(token_de(contact.id)).status_code == 204

    response = invitar(contact.id)

    assert response.status_code == 409
    assert response.json()["detail"] == "Este contacto ya tiene cuenta en el portal"
    assert len(clientes(db)) == 1


# --- Estado en la ficha -----------------------------------------------------------


def test_estado_del_portal_en_cada_momento(db, usuarios):
    contact = contacto(db)

    assert estado_portal(contact.id).json() == {"has_account": False, "invitation_expires_at": None}
    token = token_de(contact.id)
    abierta = estado_portal(contact.id).json()
    assert abierta["has_account"] is False
    assert datetime.fromisoformat(abierta["invitation_expires_at"]) == AHORA + timedelta(hours=24)

    poner_reloj(AHORA + timedelta(hours=24))
    assert estado_portal(contact.id).json() == {"has_account": False, "invitation_expires_at": None}

    poner_reloj(AHORA)
    assert aceptar(token).status_code == 204
    assert estado_portal(contact.id).json() == {"has_account": True, "invitation_expires_at": None}


# --- Comprobar y aceptar ----------------------------------------------------------


def test_aceptar_crea_una_cuenta_de_cliente_vinculada_y_con_login(db, usuarios):
    contact = contacto(db)

    response = aceptar(token_de(contact.id))

    assert response.status_code == 204 and response.content == b""
    user = db.scalar(select(User).where(User.email == "ana.cliente@example.com"))
    assert user.role == Role.CLIENT and user.active and user.contact_id == contact.id
    assert user.password_hash.startswith("$argon2id$") and verify_password(user.password_hash, CLIENTE["password"])
    login = TestClient(fastapi_app).post("/api/auth/login", json=CLIENTE)
    assert login.status_code == 200 and login.json()["role"] == "client"


def test_aceptar_no_inicia_sesion(db, usuarios):
    response = aceptar(token_de(contacto(db).id))

    assert "set-cookie" not in response.headers


def test_el_enlace_reutilizado_se_rechaza(db, usuarios):
    token = token_de(contacto(db).id)
    assert aceptar(token).status_code == 204

    response = aceptar(token, email="otra@example.com")

    assert response.status_code == 410 and response.json()["detail"] == ENLACE_NO_VALE
    assert comprobar(token).status_code == 410
    assert len(clientes(db)) == 1


def test_caduca_justo_a_las_24_horas(db, usuarios):
    token = token_de(contacto(db).id)

    poner_reloj(AHORA + timedelta(hours=24) - timedelta(seconds=1))
    assert comprobar(token).status_code == 204

    poner_reloj(AHORA + timedelta(hours=24))
    assert comprobar(token).status_code == 410
    assert aceptar(token).status_code == 410
    assert clientes(db) == []


@pytest.mark.parametrize("token", ["inventado", "x" * 128])
def test_un_token_inventado_se_rechaza_con_el_mismo_mensaje(db, usuarios, token):
    for response in (comprobar(token), aceptar(token)):
        assert response.status_code == 410 and response.json()["detail"] == ENLACE_NO_VALE


@pytest.mark.parametrize("cuerpo", [{}, {"token": ""}, {"token": 1}, {"token": "x" * 129}])
def test_un_token_mal_formado_da_422(db, usuarios, cuerpo):
    assert TestClient(fastapi_app).post("/api/portal-invitations/check", json=cuerpo).status_code == 422


def test_marcar_perdido_despues_invalida_el_enlace(db, usuarios):
    contact = contacto(db)
    token = token_de(contact.id)
    contact.status = ContactStatus.LOST
    db.flush()

    assert comprobar(token).status_code == 410
    assert aceptar(token).status_code == 410


@pytest.mark.parametrize(
    "extra", [{"role": "admin"}, {"contact_id": 1}, {"active": False}, {"id": 1}]
)
def test_el_navegador_no_fija_rol_ni_contacto(db, usuarios, extra):
    token = token_de(contacto(db).id)

    assert aceptar(token, **extra).status_code == 422
    assert clientes(db) == []
    assert comprobar(token).status_code == 204  # el enlace sigue valiendo


@pytest.mark.parametrize("email", ["sin-arroba", "", "ana@clinica", "añó@example.com"])
def test_email_no_valido(db, usuarios, email):
    response = aceptar(token_de(contacto(db).id), email=email)

    assert response.status_code == 422
    assert error_de(response, "email")
    assert clientes(db) == []


@pytest.mark.parametrize("password", ["corta", "x" * 11, "x" * 1025])
def test_contrasena_fuera_de_limites(db, usuarios, password):
    response = aceptar(token_de(contacto(db).id), password=password)

    assert response.status_code == 422
    assert error_de(response, "password") == "La contraseña debe tener entre 12 y 1024 caracteres"
    assert clientes(db) == []


def test_contrasena_justo_de_12_vale(db, usuarios):
    assert aceptar(token_de(contacto(db).id), password="x" * 12).status_code == 204


@pytest.mark.parametrize("email", ["reception@prueba.example.com", "RECEPTION@prueba.example.com"])
def test_email_en_uso_avisa_y_el_enlace_sigue_valiendo(db, usuarios, email):
    token = token_de(contacto(db).id)

    response = aceptar(token, email=email)

    assert response.status_code == 409
    assert response.json()["detail"] == "Ese email ya está en uso: escribe otro"
    assert aceptar(token).status_code == 204


def test_un_enlace_no_cambia_la_contrasena_de_una_cuenta_que_ya_existe(db, usuarios):
    token = token_de(contacto(db).id)

    aceptar(token, email="admin@prueba.example.com")

    assert verify_password(db.scalar(select(User).where(User.role == Role.ADMIN)).password_hash, PASSWORD)


def test_dos_contactos_de_una_familia_necesitan_emails_distintos(db, usuarios):
    assert aceptar(token_de(contacto(db).id)).status_code == 204

    response = aceptar(token_de(contacto(db, nombre="Bea").id))

    assert response.status_code == 409


def test_el_enlace_de_un_contacto_vincula_solo_a_ese_contacto(db, usuarios):
    ana, bea = contacto(db), contacto(db, nombre="Bea")
    token_bea = token_de(bea.id)
    token_de(ana.id)

    assert aceptar(token_bea).status_code == 204

    assert [user.contact_id for user in clientes(db)] == [bea.id]


def test_comprobar_no_revela_datos_ni_gasta_el_enlace(db, usuarios):
    token = token_de(contacto(db).id)

    response = comprobar(token)

    assert response.status_code == 204 and response.content == b""
    assert comprobar(token).status_code == 204


# --- Reglas en la propia BD -------------------------------------------------------


def test_la_bd_rechaza_vincular_una_cuenta_interna(db, usuarios):
    usuarios[Role.RECEPTION].contact_id = contacto(db).id

    with pytest.raises(IntegrityError, match="ck_users_contact_only_for_client"), db.begin_nested():
        db.flush()
    db.rollback()


def test_la_bd_rechaza_dos_cuentas_para_el_mismo_contacto(db, usuarios):
    contact = contacto(db)
    usuarios[Role.CLIENT].contact_id = contact.id
    db.flush()
    db.add(User(email="otra@example.com", password_hash="x", role=Role.CLIENT, contact_id=contact.id))

    with pytest.raises(IntegrityError, match="uq_users_contact_id"), db.begin_nested():
        db.flush()
    db.rollback()


def test_la_bd_rechaza_dos_invitaciones_abiertas_para_un_contacto(db, usuarios):
    contact = contacto(db)
    for numero in "ab":
        db.add(PortalInvitation(token_hash=numero * 64, contact_id=contact.id, expires_at=AHORA))

    with pytest.raises(IntegrityError, match="uq_portal_invitations_contact_open"), db.begin_nested():
        db.flush()
    db.rollback()


# --- Citas en la ficha ------------------------------------------------------------


def _cita(db, contact: Contact, persona: User, inicio: datetime, status: str = "scheduled") -> Appointment:
    service = db.scalar(select(Service).where(Service.name == "Botox"))
    if service is None:
        service = Service(name="Botox", duration_minutes=60)
        db.add(service)
        db.flush()
    cita = Appointment(
        contact_id=contact.id,
        service_id=service.id,
        staff_id=persona.id,
        starts_at=inicio,
        ends_at=inicio + timedelta(minutes=60),
        duration_minutes=60,
        status=status,
        cancel_reason="clinic" if status == "cancelled" else None,
    )
    db.add(cita)
    db.flush()
    return cita


def citas_de(contact_id: int, role: Role):
    client, _ = sesion_de(role)
    return client.get(f"/api/appointments/by-contact/{contact_id}")


@pytest.mark.parametrize("role", [Role.ADMIN, Role.RECEPTION])
def test_ficha_lista_todas_las_citas_de_la_mas_reciente_a_la_mas_antigua(db, usuarios, role):
    contact = contacto(db)
    persona = usuarios[Role.PROFESSIONAL]
    antigua = _cita(db, contact, persona, AHORA + timedelta(days=1))
    cancelada = _cita(db, contact, persona, AHORA + timedelta(days=2), status="cancelled")
    nueva = _cita(db, contact, usuarios[Role.ADMIN], AHORA + timedelta(days=3))
    _cita(db, contacto(db, nombre="Bea"), persona, AHORA + timedelta(days=4))

    response = citas_de(contact.id, role)

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["total"] == 3
    assert [c["id"] for c in cuerpo["items"]] == [nueva.id, cancelada.id, antigua.id]
    # En la hora de la clínica y con los nombres de la agenda.
    assert cuerpo["items"][0]["starts_at"].endswith("-05:00")
    assert cuerpo["items"][0]["service_name"] == "Botox"


def test_ficha_sin_citas_es_una_lista_vacia(db, usuarios):
    assert citas_de(contacto(db).id, Role.RECEPTION).json() == {"total": 0, "items": []}


def test_ficha_trae_20_y_cuenta_el_total(db, usuarios):
    contact = contacto(db)
    for dia in range(1, 23):
        _cita(db, contact, usuarios[Role.PROFESSIONAL], AHORA + timedelta(days=dia))

    cuerpo = citas_de(contact.id, Role.RECEPTION).json()

    assert cuerpo["total"] == 22 and len(cuerpo["items"]) == 20
    assert cuerpo["items"][0]["starts_at"].startswith("2027-01-26")


def test_el_profesional_solo_ve_sus_citas_del_contacto(db, usuarios):
    contact = contacto(db)
    suya = _cita(db, contact, usuarios[Role.PROFESSIONAL], AHORA + timedelta(days=1))
    _cita(db, contact, usuarios[Role.ADMIN], AHORA + timedelta(days=2))

    cuerpo = citas_de(contact.id, Role.PROFESSIONAL).json()

    assert cuerpo["total"] == 1 and [c["id"] for c in cuerpo["items"]] == [suya.id]


def test_el_profesional_sin_citas_con_el_contacto_recibe_404_como_si_no_existiera(db, usuarios):
    contact = contacto(db)
    _cita(db, contact, usuarios[Role.ADMIN], AHORA + timedelta(days=1))

    ajeno, inexistente = citas_de(contact.id, Role.PROFESSIONAL), citas_de(999999, Role.PROFESSIONAL)

    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == inexistente.json()


def test_el_cliente_no_ve_las_citas_de_la_ficha(db, usuarios):
    assert citas_de(contacto(db).id, Role.CLIENT).status_code == 403


def test_contacto_inexistente_en_las_citas_de_la_ficha_da_404(db, usuarios):
    assert citas_de(999999, Role.RECEPTION).status_code == 404
