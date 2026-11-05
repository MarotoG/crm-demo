"""Panel de pendientes, contador, completar, reabrir y editar tareas contra PostgreSQL real (T25).
«Ahora» es el lunes 04/01/2027 a las 10:00 de Nueva York."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.appointments_routes import get_now
from app.main import app as fastapi_app
from app.models import FollowUpTask, Role
from test_follow_ups import AHORA, HOY, TAREA, cita, contacto, cuenta, error_de, sesion, tarea

PANEL = "/api/follow-ups"
RESUMEN = "/api/follow-ups/summary"
AYER = HOY - timedelta(days=1)
MANANA = HOY + timedelta(days=1)


@pytest.fixture(autouse=True)
def reloj_fijo():
    fastapi_app.dependency_overrides[get_now] = lambda: AHORA
    yield
    fastapi_app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def escena(db):
    """Recepción, un profesional con cita con Ana y otro con cita con Bea."""
    recepcion = cuenta(db, "recepcion", Role.RECEPTION)
    prof = cuenta(db, "prof", Role.PROFESSIONAL)
    colega = cuenta(db, "colega", Role.PROFESSIONAL)
    ana = contacto(db, "ana")
    bea = contacto(db, "bea")
    cita(db, ana, prof)
    cita(db, bea, colega)
    return recepcion, prof, colega, ana, bea


def hecha(db, ficha, responsable, autor=None, cuando=AHORA, **campos) -> FollowUpTask:
    return tarea(db, ficha, responsable, completed_at=cuando, completed_by_id=(autor or responsable).id, **campos)


def ids(cuerpo: dict) -> list[int]:
    return [t["id"] for t in cuerpo["items"]]


def post(user, ruta: str, cuerpo: dict):
    client, csrf = sesion(user)
    return client.post(ruta, json=cuerpo, headers=csrf)


def completar(user, t: FollowUpTask, version: int | None = None):
    return post(user, f"{PANEL}/{t.id}/complete", {"version": t.version if version is None else version})


def reabrir(user, t: FollowUpTask, version: int | None = None):
    return post(user, f"{PANEL}/{t.id}/reopen", {"version": t.version if version is None else version})


def editar(user, t: FollowUpTask, **campos):
    client, csrf = sesion(user)
    cuerpo = {
        "description": t.description,
        "due_on": t.due_on.isoformat(),
        "assigned_to_id": t.assigned_to_id,
        "version": t.version,
        **campos,
    }
    return client.put(f"{PANEL}/{t.id}", json=cuerpo, headers=csrf)


# --- Panel ----------------------------------------------------------------------------


def test_recepcion_ve_las_pendientes_de_toda_la_clinica_por_fecha(db, escena):
    recepcion, prof, colega, ana, bea = escena
    lejana = tarea(db, ana, prof, due_on=MANANA)
    vencida = tarea(db, bea, colega, due_on=AYER)
    de_hoy = tarea(db, ana, recepcion, due_on=HOY)
    hecha(db, ana, prof)
    client, _ = sesion(recepcion)

    cuerpo = client.get(PANEL).json()

    assert ids(cuerpo) == [vencida.id, de_hoy.id, lejana.id]
    assert cuerpo["total"] == 3
    assert cuerpo["today"] == "2027-01-04"


def test_cada_tarea_lleva_el_contacto_y_su_estado(db, escena):
    recepcion, _, _, _, _ = escena
    perdida = contacto(db, "lara", status="lost")
    tarea(db, perdida, recepcion)
    client, _ = sesion(recepcion)

    item = client.get(PANEL).json()["items"][0]

    assert item["contact_id"] == perdida.id
    assert item["contact_name"] == "Lara Lopez"
    assert item["contact_status"] == "lost"
    assert item["completed_at"] is None
    assert item["version"] == 1


def test_hechas_de_la_mas_reciente_a_la_mas_antigua_con_quien_las_marco(db, escena):
    recepcion, prof, _, ana, _ = escena
    antigua = hecha(db, ana, prof, autor=recepcion, cuando=AHORA - timedelta(days=3))
    reciente = hecha(db, ana, prof, cuando=AHORA - timedelta(hours=1))
    tarea(db, ana, prof)
    client, _ = sesion(recepcion)

    cuerpo = client.get(PANEL, params={"state": "done"}).json()

    assert ids(cuerpo) == [reciente.id, antigua.id]
    assert cuerpo["items"][0]["completed_by_email"] == prof.email
    assert cuerpo["items"][1]["completed_by_email"] == recepcion.email


def test_filtro_por_responsable(db, escena):
    recepcion, prof, colega, ana, bea = escena
    suya = tarea(db, ana, prof)
    tarea(db, bea, colega)
    client, _ = sesion(recepcion)

    assert ids(client.get(PANEL, params={"assigned_to_id": prof.id}).json()) == [suya.id]


def test_el_filtro_tambien_vale_para_las_hechas(db, escena):
    recepcion, prof, colega, ana, bea = escena
    suya = hecha(db, ana, prof)
    hecha(db, bea, colega)
    client, _ = sesion(recepcion)

    assert ids(client.get(PANEL, params={"state": "done", "assigned_to_id": prof.id}).json()) == [suya.id]


def test_las_50_mas_cercanas_con_el_total(db, escena):
    recepcion, _, _, ana, _ = escena
    for n in range(53):
        tarea(db, ana, recepcion, due_on=HOY + timedelta(days=n))
    client, _ = sesion(recepcion)

    cuerpo = client.get(PANEL).json()

    assert cuerpo["total"] == 53
    assert len(cuerpo["items"]) == 50
    assert cuerpo["items"][-1]["due_on"] == (HOY + timedelta(days=49)).isoformat()


def test_el_profesional_solo_ve_las_suyas_pendientes_y_hechas(db, escena):
    recepcion, prof, colega, ana, bea = escena
    suya = tarea(db, ana, prof)
    suya_hecha = hecha(db, ana, prof)
    tarea(db, ana, recepcion)
    tarea(db, bea, colega)
    hecha(db, bea, colega)
    client, _ = sesion(prof)

    assert ids(client.get(PANEL).json()) == [suya.id]
    assert ids(client.get(PANEL, params={"state": "done"}).json()) == [suya_hecha.id]


def test_el_profesional_recibe_403_al_pedir_las_de_otro_y_no_al_pedir_las_suyas(db, escena):
    _, prof, colega, ana, bea = escena
    suya = tarea(db, ana, prof)
    tarea(db, bea, colega)
    client, _ = sesion(prof)

    assert client.get(PANEL, params={"assigned_to_id": colega.id}).status_code == 403
    assert ids(client.get(PANEL, params={"assigned_to_id": prof.id}).json()) == [suya.id]


def test_el_cliente_no_entra_en_el_panel_ni_en_el_contador(db, escena):
    _, _, _, ana, _ = escena
    client, _ = sesion(cuenta(db, "cliente", Role.CLIENT, contact_id=ana.id))

    assert client.get(PANEL).status_code == 403
    assert client.get(RESUMEN).status_code == 403


def test_un_estado_que_no_existe_da_422(db, escena):
    client, _ = sesion(escena[0])

    assert client.get(PANEL, params={"state": "cualquiera"}).status_code == 422


# --- Contador -------------------------------------------------------------------------


def test_cuenta_vencidas_y_de_hoy_sin_las_hechas_ni_las_futuras(db, escena):
    recepcion, prof, colega, ana, bea = escena
    tarea(db, ana, prof, due_on=AYER)
    tarea(db, bea, colega, due_on=AYER - timedelta(days=9))
    tarea(db, ana, recepcion, due_on=HOY)
    tarea(db, ana, recepcion, due_on=MANANA)
    hecha(db, ana, recepcion, due_on=AYER)
    hecha(db, ana, recepcion, due_on=HOY)
    client, _ = sesion(recepcion)

    assert client.get(RESUMEN).json() == {"overdue": 2, "due_today": 1}


def test_el_contador_del_profesional_solo_cuenta_las_suyas(db, escena):
    recepcion, prof, colega, ana, bea = escena
    tarea(db, ana, prof, due_on=HOY)
    tarea(db, bea, colega, due_on=AYER)
    tarea(db, ana, recepcion, due_on=AYER)
    client, _ = sesion(prof)

    assert client.get(RESUMEN).json() == {"overdue": 0, "due_today": 1}


def test_vencida_y_hoy_son_del_dia_de_la_clinica_y_no_de_utc(db, escena):
    recepcion, _, _, ana, _ = escena
    # El 05/01 a las 2:00 en UTC, en Nueva York siguen siendo las 21:00 del día 4.
    fastapi_app.dependency_overrides[get_now] = lambda: datetime(2027, 1, 5, 2, 0, tzinfo=UTC)
    tarea(db, ana, recepcion, due_on=date(2027, 1, 4))
    client, _ = sesion(recepcion)

    assert client.get(RESUMEN).json() == {"overdue": 0, "due_today": 1}
    assert client.get(PANEL).json()["today"] == "2027-01-04"


# --- Completar ------------------------------------------------------------------------


@pytest.mark.parametrize("rol", [Role.ADMIN, Role.RECEPTION])
def test_admin_y_recepcion_completan_cualquiera(db, escena, rol):
    _, prof, _, ana, _ = escena
    autor = cuenta(db, "autor", rol)
    t = tarea(db, ana, prof)

    response = completar(autor, t)

    assert response.status_code == 200, response.text
    cuerpo = response.json()
    assert cuerpo["completed_by_email"] == autor.email
    assert datetime.fromisoformat(cuerpo["completed_at"]) == AHORA
    assert cuerpo["version"] == 2
    db.refresh(t)
    assert t.completed_by_id == autor.id


def test_el_profesional_completa_la_suya(db, escena):
    _, prof, _, ana, _ = escena

    assert completar(prof, tarea(db, ana, prof)).json()["completed_by_email"] == prof.email


def test_el_profesional_recibe_404_con_la_de_otro_y_no_la_cambia(db, escena):
    recepcion, prof, _, ana, _ = escena
    ajena = tarea(db, ana, recepcion)

    response = completar(prof, ajena)

    assert response.status_code == 404
    assert response.json() == post(prof, f"{PANEL}/999999/complete", {"version": 1}).json()
    db.refresh(ajena)
    assert ajena.completed_at is None


def test_el_cliente_no_completa(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion)

    assert completar(cuenta(db, "cliente", Role.CLIENT, contact_id=ana.id), t).status_code == 403


def test_completar_dos_veces_da_409_con_el_motivo(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion)
    completar(recepcion, t)

    response = completar(recepcion, t, version=1)

    assert response.status_code == 409
    assert response.json()["detail"] == "Esta tarea ya está hecha"


def test_completar_una_ya_hecha_con_su_version_actual_da_409_y_conserva_quien_la_marco(db, escena):
    recepcion, prof, _, ana, _ = escena
    t = hecha(db, ana, prof, version=2)

    response = completar(recepcion, t)

    assert response.status_code == 409
    db.refresh(t)
    assert t.completed_by_id == prof.id


def test_completar_con_una_version_antigua_da_409_sin_cambiarla(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion, version=3)

    response = completar(recepcion, t, version=2)

    assert response.status_code == 409
    assert "Otra persona" in response.json()["detail"]
    db.refresh(t)
    assert t.completed_at is None


def test_completar_no_toca_la_ficha_y_vale_en_un_perdido(db, escena):
    recepcion, _, _, _, _ = escena
    perdida = contacto(db, "lara", status="lost")

    assert completar(recepcion, tarea(db, perdida, recepcion)).status_code == 200
    db.refresh(perdida)
    assert (perdida.status, perdida.version) == ("lost", 1)


@pytest.mark.parametrize("cuerpo", [{}, {"version": 0}, {"version": "1"}, {"version": 1, "completed_by_id": 1}, {"version": 1, "completed_at": "2020-01-01T00:00:00Z"}])
def test_el_navegador_solo_envia_la_version(db, escena, cuerpo):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion)

    assert post(recepcion, f"{PANEL}/{t.id}/complete", cuerpo).status_code == 422
    db.refresh(t)
    assert t.completed_at is None


# --- Reabrir --------------------------------------------------------------------------


def test_reabrir_borra_quien_y_cuando_y_sube_la_version(db, escena):
    recepcion, _, _, ana, _ = escena
    t = hecha(db, ana, recepcion)

    response = reabrir(recepcion, t)

    assert response.status_code == 200, response.text
    cuerpo = response.json()
    assert cuerpo["completed_at"] is None
    assert cuerpo["completed_by_email"] is None
    assert cuerpo["version"] == 2


def test_reabrir_no_tiene_limite_de_tiempo_y_una_fecha_pasada_vuelve_vencida(db, escena):
    recepcion, _, _, ana, _ = escena
    t = hecha(db, ana, recepcion, cuando=AHORA - timedelta(days=400), due_on=AYER)
    client, _ = sesion(recepcion)

    assert reabrir(recepcion, t).status_code == 200
    assert client.get(RESUMEN).json()["overdue"] == 1


def test_el_profesional_reabre_la_suya_y_no_la_de_otro(db, escena):
    recepcion, prof, _, ana, _ = escena

    assert reabrir(prof, hecha(db, ana, prof, autor=recepcion)).status_code == 200
    ajena = hecha(db, ana, recepcion)
    assert reabrir(prof, ajena).status_code == 404
    db.refresh(ajena)
    assert ajena.completed_at is not None


def test_reabrir_una_pendiente_da_409_con_el_motivo(db, escena):
    recepcion, _, _, ana, _ = escena

    response = reabrir(recepcion, tarea(db, ana, recepcion))

    assert response.status_code == 409
    assert response.json()["detail"] == "Esta tarea ya está pendiente"


def test_reabrir_con_una_version_antigua_da_409(db, escena):
    recepcion, _, _, ana, _ = escena
    t = hecha(db, ana, recepcion, version=2)

    assert reabrir(recepcion, t, version=1).status_code == 409
    db.refresh(t)
    assert t.completed_at is not None


def test_reabrir_una_que_no_existe_da_404_y_el_cliente_403(db, escena):
    recepcion, _, _, ana, _ = escena
    t = hecha(db, ana, recepcion)

    assert post(recepcion, f"{PANEL}/999999/reopen", {"version": 1}).status_code == 404
    assert reabrir(cuenta(db, "cliente", Role.CLIENT, contact_id=ana.id), t).status_code == 403


# --- Editar y reasignar ---------------------------------------------------------------


def test_editar_cambia_texto_fecha_y_responsable_y_sube_la_version(db, escena):
    recepcion, prof, _, ana, _ = escena
    t = tarea(db, ana, recepcion)

    response = editar(recepcion, t, description="  Otro   texto ", due_on="2027-02-01", assigned_to_id=prof.id)

    assert response.status_code == 200, response.text
    cuerpo = response.json()
    assert cuerpo["description"] == "Otro texto"
    assert cuerpo["due_on"] == "2027-02-01"
    assert cuerpo["assigned_to_email"] == prof.email
    assert cuerpo["version"] == 2
    assert cuerpo["contact_id"] == ana.id


@pytest.mark.parametrize("rol", [Role.PROFESSIONAL, Role.CLIENT])
def test_profesional_y_cliente_no_editan_ni_la_suya(db, escena, rol):
    recepcion, prof, _, ana, _ = escena
    t = tarea(db, ana, prof)
    otro = prof if rol == Role.PROFESSIONAL else cuenta(db, "cliente", Role.CLIENT, contact_id=ana.id)

    assert editar(otro, t, description="Cambiado").status_code == 403
    db.refresh(t)
    assert t.description == TAREA


def test_editar_una_que_no_existe_da_404(db, escena):
    client, csrf = sesion(escena[0])
    cuerpo = {"description": "x", "due_on": "2027-02-01", "assigned_to_id": escena[0].id, "version": 1}

    assert client.put(f"{PANEL}/999999", json=cuerpo, headers=csrf).status_code == 404


def test_editar_con_una_version_antigua_da_409_sin_cambiarla(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion, version=2)

    response = editar(recepcion, t, description="Cambiado", version=1)

    assert response.status_code == 409
    assert "Otra persona" in response.json()["detail"]
    db.refresh(t)
    assert t.description == TAREA


def test_una_hecha_no_se_edita_hasta_reabrirla(db, escena):
    recepcion, _, _, ana, _ = escena
    t = hecha(db, ana, recepcion)

    response = editar(recepcion, t, description="Cambiado")

    assert response.status_code == 409
    assert "reábrela" in response.json()["detail"]


def test_reasignar_cumple_la_misma_regla_que_crear(db, escena):
    recepcion, prof, colega, ana, _ = escena
    t = tarea(db, ana, recepcion)
    baja = cuenta(db, "baja", Role.RECEPTION, active=False)
    cliente = cuenta(db, "cliente", Role.CLIENT, contact_id=ana.id)

    assert "no tiene citas" in error_de(editar(recepcion, t, assigned_to_id=colega.id), "assigned_to_id")
    assert "no está activa" in error_de(editar(recepcion, t, assigned_to_id=baja.id), "assigned_to_id")
    assert "no está activa" in error_de(editar(recepcion, t, assigned_to_id=cliente.id), "assigned_to_id")
    assert "no está activa" in error_de(editar(recepcion, t, assigned_to_id=999999), "assigned_to_id")
    assert editar(recepcion, t, assigned_to_id=prof.id).status_code == 200


def test_reasignar_mueve_quien_la_ve_y_quien_la_completa(db, escena):
    recepcion, prof, _, ana, _ = escena
    t = tarea(db, ana, prof)
    antes, _ = sesion(prof)
    assert ids(antes.get(PANEL).json()) == [t.id]

    editada = editar(recepcion, t, assigned_to_id=recepcion.id).json()

    assert antes.get(PANEL).json()["total"] == 0
    assert post(prof, f"{PANEL}/{t.id}/complete", {"version": editada["version"]}).status_code == 404


def test_una_vencida_se_reasigna_sin_moverle_la_fecha(db, escena):
    recepcion, prof, _, ana, _ = escena
    t = tarea(db, ana, recepcion, due_on=AYER)

    response = editar(recepcion, t, assigned_to_id=prof.id)

    assert response.status_code == 200, response.text
    assert response.json()["due_on"] == AYER.isoformat()


def test_cambiar_la_fecha_si_se_comprueba(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion, due_on=MANANA)

    assert "anterior a hoy" in error_de(editar(recepcion, t, due_on=AYER.isoformat()), "due_on")
    assert "365" in error_de(editar(recepcion, t, due_on=(HOY + timedelta(days=366)).isoformat()), "due_on")


def test_corregir_una_errata_no_falla_si_el_responsable_ya_no_podria_asignarse(db, escena):
    recepcion, _, _, ana, _ = escena
    baja = cuenta(db, "baja", Role.RECEPTION, active=False)
    t = tarea(db, ana, baja)

    assert editar(recepcion, t, description="Corregida").status_code == 200


def test_las_validaciones_del_texto_tambien_valen_al_editar(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion)

    assert "qué hay que hacer" in error_de(editar(recepcion, t, description=" "), "description")
    assert "tildes" in error_de(editar(recepcion, t, description="mañana"), "description")


@pytest.mark.parametrize("campos", [{"contact_id": 1}, {"completed_at": "2027-01-01T00:00:00Z"}, {"created_by_id": 1}, {"version": None}, {"version": 0}])
def test_al_editar_el_navegador_no_fija_nada_mas(db, escena, campos):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion)

    assert editar(recepcion, t, **campos).status_code == 422


# --- La ficha -------------------------------------------------------------------------


def test_la_ficha_muestra_primero_las_pendientes_y_despues_las_hechas(db, escena):
    recepcion, _, _, ana, _ = escena
    hecha_pronto = hecha(db, ana, recepcion, due_on=AYER)
    pendiente_lejana = tarea(db, ana, recepcion, due_on=date(2027, 6, 1))
    pendiente_cercana = tarea(db, ana, recepcion, due_on=MANANA)
    client, _ = sesion(recepcion)

    cuerpo = client.get(f"/api/contacts/{ana.id}/follow-ups").json()

    assert ids(cuerpo) == [pendiente_cercana.id, pendiente_lejana.id, hecha_pronto.id]


# --- Base de datos --------------------------------------------------------------------


def test_la_bd_no_admite_autor_sin_hora_ni_version_cero(db, escena):
    recepcion, _, _, ana, _ = escena
    t = tarea(db, ana, recepcion)

    for sql in ("completed_by_id = :a", "version = 0"):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(f"UPDATE follow_up_tasks SET {sql} WHERE id = :i"), {"a": recepcion.id, "i": t.id})
