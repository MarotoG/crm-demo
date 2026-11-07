"""Citas (T16): crear una cita para un contacto, un servicio y una de las personas que lo realizan.
La agenda de un día (T18) o de un mes (T20), con filtros por persona y contacto.

Las crean administración y recepción; el profesional y el cliente reciben 403. El profesional
consulta solo las suyas (T20); el cliente, más adelante en el portal. La hora se escribe en la hora local de la clínica, sin zona (decisión T16), y
la API la convierte a un instante. La duración se copia del servicio.

Solapamientos (T17): la misma persona no puede tener dos citas que se pisen (409). Lo decide una
restricción de exclusión de PostgreSQL (app/models.py). Una clienta sí puede tener dos citas a la
vez con dos personas distintas (tinte y pedicura, decisión T17).

Reprogramar y cancelar (T19): solo una cita Programada que no ha empezado, con la versión leída
(409 si otra persona la cambió antes). Reprogramar cambia el día, la hora y la persona, con las
mismas reglas que al crearla; el contacto y el servicio no cambian (para eso se cancela y se da
otra). Cancelar exige un motivo de la lista y libera la franja.

Asistencia (T20b): Realizada o No presentado desde la hora de inicio, por admin y recepción en
cualquier cita y por el profesional en las suyas; se corrige durante 7 días y el estado del
contacto se recalcula (la primera Realizada lo hace Cliente).
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import changed_fields, record, record_contact_status
from app.auth import require_csrf, require_roles
from app.config import get_settings
from app.db import get_db
from app.errors import body_error, field_error, user_message
from app.models import (
    STAFF_OVERLAP_CONSTRAINT,
    Appointment,
    AppointmentStatus,
    AuditAction,
    AuditTarget,
    CancelReason,
    Contact,
    ContactStatus,
    Role,
    Service,
    ServiceStaff,
    User,
)
from app.services_routes import STAFF_ROLES
from app.validators import (
    START_FORMAT_MESSAGE,
    clinic_instant,
    normalize_cancel_note,
    normalize_note,
    parse_local_start,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/appointments", tags=["citas"])

# Como mucho dentro de un año (decisión T16). Sin horario de apertura por ahora.
MAX_DAYS_AHEAD = 365

# Estado del contacto al darle una cita (decisión T16): Nuevo y Contactado pasan a «Cita agendada»;
# Cita agendada y Cliente se quedan como están; un Perdido se rechaza: hay que reabrirlo antes (T14).
PROMOTED_TO_SCHEDULED = frozenset({ContactStatus.NEW, ContactStatus.CONTACTED})

PAST_MESSAGE = "La cita no puede empezar en el pasado"
TOO_FAR_MESSAGE = f"La cita no puede ser para dentro de más de {MAX_DAYS_AHEAD} días"
CONTACT_NOT_FOUND_MESSAGE = "El contacto no existe"
CONTACT_LOST_MESSAGE = "El contacto está «Perdido»: reábrelo antes de darle una cita"
SERVICE_NOT_VALID_MESSAGE = "El servicio no existe o está desactivado"
STAFF_NOT_VALID_MESSAGE = "Esa persona no realiza este servicio o su cuenta no está activa"
OVERLAP_FALLBACK_MESSAGE = "Esa persona ya tiene otra cita a esa hora"
# Reprogramar y cancelar (T19). Texto general (decisión T19): vale también si se pulsó un botón.
NOT_FOUND_MESSAGE = "Cita no encontrada"
VERSION_CONFLICT_MESSAGE = "Esta cita ha cambiado desde que la abriste. Revisa los datos y vuelve a intentarlo."
ALREADY_STARTED_MESSAGE = "La cita ya ha empezado: no se puede cambiar"
CONTACT_LOST_RESCHEDULE_MESSAGE = "El contacto está «Perdido»: reábrelo antes de cambiar la cita, o cancélala"
SERVICE_INACTIVE_RESCHEDULE_MESSAGE = "El servicio está desactivado: cancela la cita y da otra"
CANCEL_REASON_MESSAGE = "Elige el motivo de la cancelación"
# Agenda de un intervalo (T20): un mes como mucho, para la vista mensual.
MAX_RANGE_DAYS = 31
RANGE_MISSING_MESSAGE = "Indica un día (date) o un intervalo (from y to)"
RANGE_ORDER_MESSAGE = "El último día no puede ser anterior al primero"
RANGE_TOO_LONG_MESSAGE = f"El intervalo no puede pasar de {MAX_RANGE_DAYS} días"
OWN_AGENDA_MESSAGE = "Solo puedes ver tus citas"
# Citas en la ficha del contacto (T21): las más recientes, como la lista de contactos (T12).
CONTACT_LIST_LIMIT = 20
CONTACT_NOT_FOUND_LIST_MESSAGE = "Contacto no encontrado"
# Asistencia (T20b): desde que empieza la cita; se corrige durante 7 días desde que se marcó.
ATTENDANCE_STATUSES = frozenset({AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW})
CORRECTION_DAYS = 7
ATTENDANCE_STATUS_MESSAGE = "Elige «Realizada» o «No presentado»"
NOT_STARTED_MESSAGE = "La cita aún no ha empezado: la asistencia se marca desde su hora de inicio"
CANCELLED_ATTENDANCE_MESSAGE = "La cita está «Cancelada»: no se marca la asistencia"
CORRECTION_EXPIRED_MESSAGE = f"Han pasado más de {CORRECTION_DAYS} días desde que se marcó: ya no se puede corregir"
STATUS_NAMES = {
    AppointmentStatus.COMPLETED: "Realizada",
    AppointmentStatus.NO_SHOW: "No presentado",
    AppointmentStatus.CANCELLED: "Cancelada",
}


class _WithStart(BaseModel):
    # extra="forbid": el navegador no fija la duración, el fin, el estado ni la versión.
    model_config = ConfigDict(extra="forbid")

    # Hora local de la clínica, sin zona: «2027-01-11T09:30».
    starts_at: datetime

    @field_validator("starts_at", mode="before")
    @classmethod
    def _starts_at(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise PydanticCustomError("dato_no_valido", START_FORMAT_MESSAGE)
        return user_message(parse_local_start)(value)


def _clean_note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PydanticCustomError("dato_no_valido", "La nota debe ser texto")
    return user_message(normalize_note)(value)


class AppointmentCreate(_WithStart):
    contact_id: StrictInt
    service_id: StrictInt
    staff_id: StrictInt
    note: str | None = None

    @field_validator("note", mode="before")
    @classmethod
    def _note(cls, value: object) -> str | None:
        return _clean_note(value)


class AppointmentNote(BaseModel):
    """Editar la nota (T21b), sin reprogramar: la nota, o null para quitarla, y la versión leída."""

    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(ge=1)
    note: str | None

    @field_validator("note", mode="before")
    @classmethod
    def _note(cls, value: object) -> str | None:
        return _clean_note(value)


class AppointmentReschedule(_WithStart):
    """Reprogramar (T19): el día, la hora y la persona; el contacto y el servicio no cambian."""

    staff_id: StrictInt
    version: StrictInt = Field(ge=1)


class AppointmentCancel(BaseModel):
    """Cancelar (T19): el motivo de la lista y, si se quiere, un detalle corto sin datos clínicos."""

    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(ge=1)
    reason: CancelReason
    note: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def _reason(cls, value: object) -> object:
        if value not in {reason.value for reason in CancelReason}:
            raise PydanticCustomError("dato_no_valido", CANCEL_REASON_MESSAGE)
        return value

    @field_validator("note", mode="before")
    @classmethod
    def _note(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise PydanticCustomError("dato_no_valido", "El detalle debe ser texto")
        return user_message(normalize_cancel_note)(value)


class AppointmentAttendance(BaseModel):
    """Asistencia (T20b): Realizada o No presentado, con la versión leída."""

    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(ge=1)
    status: Literal["completed", "no_show"]

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: object) -> object:
        if value not in ATTENDANCE_STATUSES:
            raise PydanticCustomError("dato_no_valido", ATTENDANCE_STATUS_MESSAGE)
        return value


class AppointmentOut(BaseModel):
    id: int
    contact_id: int
    service_id: int
    staff_id: int
    # En la hora de la clínica, con su desfase: «2027-01-11T09:30:00-05:00».
    starts_at: datetime
    ends_at: datetime
    duration_minutes: int
    status: str
    version: int
    created_at: datetime
    # Solo en las canceladas (T19).
    cancel_reason: str | None
    cancel_note: str | None
    # Cuándo se marcó la asistencia la primera vez (T20b), en la hora de la clínica.
    attended_at: datetime | None
    # Nota interna (T21b): el portal del cliente no debe devolverla.
    note: str | None


class AgendaItem(AppointmentOut):
    """Una cita de la agenda (T18): además, los nombres que se leen en la lista."""

    contact_name: str
    service_name: str
    staff_email: str


class ContactAppointments(BaseModel):
    """Las citas de la ficha (T21): `total` las cuenta todas, aunque solo vengan las 20 últimas."""

    total: int
    items: list[AgendaItem]


# Cada cita con los nombres que se leen en la lista (agenda y ficha).
_AGENDA_SELECT = (
    select(Appointment, Contact.first_name, Contact.last_name, Service.name, User.email)
    .join(Contact, Contact.id == Appointment.contact_id)
    .join(Service, Service.id == Appointment.service_id)
    .join(User, User.id == Appointment.staff_id)
)


def _agenda_items(db: Session, query: Select, zone: ZoneInfo) -> list[AgendaItem]:
    return [
        AgendaItem(
            **_out(appointment, zone).model_dump(),
            contact_name=f"{first_name} {last_name}",
            service_name=service_name,
            staff_email=staff_email,
        )
        for appointment, first_name, last_name, service_name, staff_email in db.execute(query)
    ]


def _days_bounds(first: date, last: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Los días de la clínica de `first` a `last` (incluido) como instantes [00:00 de `first`, 00:00
    del día siguiente a `last`). Un día con cambio de horario dura 23 o 25 horas: por eso se
    calcula cada medianoche en la zona y no se suman 24 h."""
    start = datetime.combine(first, time(0), tzinfo=zone)
    end = datetime.combine(last + timedelta(days=1), time(0), tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def _query_error(param: str, message: str) -> HTTPException:
    """422 con la forma de los de Pydantic, en un parámetro de la dirección."""
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"type": "dato_no_valido", "loc": ["query", param], "msg": message}],
    )


def _clock(moment: datetime) -> str:
    return f"{moment.hour}:{moment.minute:02d}"


def _overlap_or_raise(
    error: IntegrityError,
    db: Session,
    staff_id: int,
    starts_at: datetime,
    ends_at: datetime,
    zone: ZoneInfo,
    moved_id: int | None = None,
) -> HTTPException:
    """409 con la hora de la cita que choca, si ha saltado la regla de solapamientos.

    Sin el nombre del contacto (decisión T17). Cualquier otro error de integridad sigue su curso.
    Al reprogramar (T19), `moved_id` es la cita que se mueve: tras el rollback sigue en su hora
    antigua, que puede pisarse con la nueva, pero nunca choca consigo misma.
    """
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint != STAFF_OVERLAP_CONSTRAINT:
        raise error
    # La que choca ya está guardada: la restricción solo falla frente a citas confirmadas.
    query = (
        select(Appointment)
        .where(
            Appointment.staff_id == staff_id,
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        .order_by(Appointment.starts_at)
        .limit(1)
    )
    if moved_id is not None:
        query = query.where(Appointment.id != moved_id)
    other = db.scalars(query).first()
    if other is None:  # la cancelaron justo ahora: basta con volver a intentarlo
        return HTTPException(status.HTTP_409_CONFLICT, OVERLAP_FALLBACK_MESSAGE)
    start, end = other.starts_at.astimezone(zone), other.ends_at.astimezone(zone)
    span = f"de {_clock(start)} a {_clock(end)}"
    if start.date() != starts_at.astimezone(zone).date():
        span = f"el {start:%d/%m/%Y} {span}"
    return HTTPException(status.HTTP_409_CONFLICT, f"Esa persona ya tiene una cita {span}")


def get_now() -> datetime:
    """La hora actual; las pruebas la sustituyen para no depender del día en que se ejecutan."""
    return datetime.now(UTC)


@router.get("", responses={403: {"description": "El profesional solo ve sus citas"}})
def list_appointments(
    day: Annotated[date | None, Query(alias="date", description="Día en la hora de la clínica: AAAA-MM-DD")] = None,
    first: Annotated[date | None, Query(alias="from", description="Primer día del intervalo (con `to`)")] = None,
    last: Annotated[date | None, Query(alias="to", description="Último día del intervalo, incluido")] = None,
    staff_id: int | None = None,
    contact_id: int | None = None,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)),
    db: Session = Depends(get_db),
) -> list[AgendaItem]:
    """Agenda de un día (T18) o de un intervalo de hasta 31 días (T20, la vista del mes), por hora
    de inicio; filtros opcionales por persona y por contacto.

    Incluye las citas que ocupan parte del periodo aunque empiecen antes (23:30-0:30). El
    profesional (T20) solo ve las suyas: el filtro por persona lo pone la API, no el navegador, y
    pedir las de otra persona es 403. El cliente, 403 (verá las suyas en el portal).
    """
    if day is not None and first is None and last is None:
        first = last = day
    elif day is not None or first is None or last is None:
        raise _query_error("date", RANGE_MISSING_MESSAGE)
    elif last < first:
        raise _query_error("to", RANGE_ORDER_MESSAGE)
    elif (last - first).days >= MAX_RANGE_DAYS:
        raise _query_error("to", RANGE_TOO_LONG_MESSAGE)
    if user.role == Role.PROFESSIONAL:
        if staff_id is not None and staff_id != user.id:
            logger.warning("Agenda ajena denegada: user_id=%s pidió staff_id=%s", user.id, staff_id)
            raise HTTPException(status.HTTP_403_FORBIDDEN, OWN_AGENDA_MESSAGE)
        staff_id = user.id
    zone = get_settings().clinic_zone
    start, end = _days_bounds(first, last, zone)
    query = (
        _AGENDA_SELECT.where(Appointment.starts_at < end, Appointment.ends_at > start)
        .order_by(Appointment.starts_at, Appointment.id)
    )
    if staff_id is not None:
        query = query.where(Appointment.staff_id == staff_id)
    if contact_id is not None:
        query = query.where(Appointment.contact_id == contact_id)
    return _agenda_items(db, query, zone)


@router.get("/by-contact/{contact_id}", responses={404: {"description": "Contacto no encontrado"}})
def list_contact_appointments(
    contact_id: int,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)),
    db: Session = Depends(get_db),
) -> ContactAppointments:
    """Las citas de un contacto para su ficha (T21): las 20 de fecha más reciente, también
    canceladas, y el total.

    El profesional solo ve las suyas; sin ninguna, 404 como en la ficha (T20): no se revela que el
    contacto existe. El cliente, 403.
    """
    conditions = [Appointment.contact_id == contact_id]
    if user.role == Role.PROFESSIONAL:
        conditions.append(Appointment.staff_id == user.id)
    total = db.scalar(select(func.count()).select_from(Appointment).where(*conditions))
    if db.get(Contact, contact_id) is None or (user.role == Role.PROFESSIONAL and total == 0):
        raise HTTPException(status.HTTP_404_NOT_FOUND, CONTACT_NOT_FOUND_LIST_MESSAGE)
    query = (
        _AGENDA_SELECT.where(*conditions)
        .order_by(Appointment.starts_at.desc(), Appointment.id.desc())
        .limit(CONTACT_LIST_LIMIT)
    )
    return ContactAppointments(total=total, items=_agenda_items(db, query, get_settings().clinic_zone))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        409: {"description": "Esa persona ya tiene una cita que se solapa"},
        422: {"description": "Hora, contacto, servicio o persona no válidos"},
    },
)
def create_appointment(
    body: AppointmentCreate,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AppointmentOut:
    zone = get_settings().clinic_zone
    starts_at = _start_instant(body.starts_at, zone, now)

    # Se leen con bloqueo, siempre en este orden (contacto, servicio, persona), hasta el commit:
    # - el contacto, en exclusiva: si a la vez alguien lo marca Perdido, uno de los dos espera y
    #   ve el resultado del otro (no puede quedar una cita nueva con un contacto Perdido);
    # - el servicio, compartido: varias citas a la vez no se esperan entre sí, pero desactivarlo o
    #   cambiar sus personas (T15) sí espera, y al revés;
    # - la persona, en exclusiva: sus citas van de una en una (ver _lock_staff).
    contact = _lock_contact(db, body.contact_id)
    if contact is None:
        raise field_error("contact_id", CONTACT_NOT_FOUND_MESSAGE)
    if contact.status == ContactStatus.LOST:
        raise field_error("contact_id", CONTACT_LOST_MESSAGE)
    service = _lock_active_service(db, body.service_id)
    if service is None:
        raise field_error("service_id", SERVICE_NOT_VALID_MESSAGE)
    staff = _lock_staff(db, service.id, body.staff_id)
    if staff is None:
        raise field_error("staff_id", STAFF_NOT_VALID_MESSAGE)

    # La duración se copia: si el servicio cambia después, la cita conserva la suya. El fin se
    # calcula en UTC, así que una cita que cruza el cambio de horario dura lo que debe.
    staff_id = staff.id
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    appointment = Appointment(
        contact_id=contact.id,
        service_id=service.id,
        staff_id=staff_id,
        starts_at=starts_at,
        ends_at=ends_at,
        duration_minutes=service.duration_minutes,
        created_by_id=user.id,
        note=body.note,
    )
    db.add(appointment)
    try:
        # Solapamientos (T17): decide la restricción de exclusión de PostgreSQL, no una consulta
        # previa. Con dos peticiones a la vez para la misma persona, la segunda espera en _lock_staff
        # a que la primera termine y, si se pisan, falla aquí.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise _overlap_or_raise(error, db, staff_id, starts_at, ends_at, zone) from None
    # El estado del contacto, en la misma transacción: o se guardan los dos cambios o ninguno. Sube
    # su versión (T13): quien editaba la ficha con la anterior recibirá 409 y verá el estado nuevo.
    status_before = contact.status
    if contact.status in PROMOTED_TO_SCHEDULED:
        contact.status = ContactStatus.SCHEDULED
        contact.version += 1
        contact.updated_by_id = user.id
    record(db, AuditAction.APPOINTMENT_CREATED, user, (AuditTarget.APPOINTMENT, appointment.id))
    record_contact_status(db, user, contact, status_before)
    db.commit()
    db.refresh(appointment)
    logger.info("Cita creada: id=%s contacto=%s por user_id=%s", appointment.id, contact.id, user.id)
    return _out(appointment, zone)


@router.put(
    "/{appointment_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "La cita no existe"},
        409: {"description": "Otra persona la cambió antes, ya no está programada o se solapa"},
        422: {"description": "Hora o persona no válidas, servicio desactivado o contacto Perdido"},
    },
)
def reschedule_appointment(
    appointment_id: int,
    body: AppointmentReschedule,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AppointmentOut:
    """Reprogramar (T19): otro día, otra hora u otra persona del servicio, con las reglas del alta.

    Conserva la duración copiada al crearla (T16), aunque el servicio haya cambiado después.
    """
    zone = get_settings().clinic_zone
    starts_at = _start_instant(body.starts_at, zone, now)
    appointment, contact = _lock_for_change(db, appointment_id, body.version, now)
    # Las mismas reglas que al crearla, aunque algo haya cambiado desde entonces (decisión T19).
    if contact.status == ContactStatus.LOST:
        raise body_error(CONTACT_LOST_RESCHEDULE_MESSAGE)
    service = _lock_active_service(db, appointment.service_id)
    if service is None:
        raise body_error(SERVICE_INACTIVE_RESCHEDULE_MESSAGE)
    staff = _lock_staff(db, service.id, body.staff_id)
    if staff is None:
        raise field_error("staff_id", STAFF_NOT_VALID_MESSAGE)

    staff_id = staff.id
    ends_at = starts_at + timedelta(minutes=appointment.duration_minutes)
    fields = changed_fields(appointment, {"staff_id": staff_id, "starts_at": starts_at})
    appointment.staff_id = staff_id
    appointment.starts_at = starts_at
    appointment.ends_at = ends_at
    appointment.version += 1
    appointment.updated_by_id = user.id
    try:
        # La misma restricción que al crearla (T17). Se cambia la fila, no se crea otra: la cita
        # no choca consigo misma aunque la hora nueva se pise con la antigua (9:00 → 9:30).
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise _overlap_or_raise(error, db, staff_id, starts_at, ends_at, zone, moved_id=appointment_id) from None
    record(db, AuditAction.APPOINTMENT_RESCHEDULED, user, (AuditTarget.APPOINTMENT, appointment_id), fields=fields)
    db.commit()
    db.refresh(appointment)
    logger.info("Cita reprogramada: id=%s por user_id=%s, versión %s", appointment.id, user.id, appointment.version)
    return _out(appointment, zone)


@router.post(
    "/{appointment_id}/cancel",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "La cita no existe"},
        409: {"description": "Otra persona la cambió antes o ya no está programada"},
        422: {"description": "Falta el motivo o el detalle no es válido"},
    },
)
def cancel_appointment(
    appointment_id: int,
    body: AppointmentCancel,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AppointmentOut:
    """Cancelar (T19): con motivo; libera la franja (T17). Se permite aunque el contacto esté
    Perdido o el servicio desactivado: si no, quedarían citas que no se pueden quitar.

    Si el contacto estaba en «Cita agendada» y no le queda ninguna Programada, vuelve a
    Contactado (decisión T19), en la misma transacción y subiendo su versión.
    """
    zone = get_settings().clinic_zone
    appointment, contact = _lock_for_change(db, appointment_id, body.version, now)
    status_before = contact.status
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancel_reason = body.reason
    appointment.cancel_note = body.note
    appointment.version += 1
    appointment.updated_by_id = user.id
    db.flush()
    if contact.status == ContactStatus.SCHEDULED:
        # El contacto está bloqueado: nadie le da otra cita mientras se cuenta.
        remaining = db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(Appointment.contact_id == contact.id, Appointment.status == AppointmentStatus.SCHEDULED)
        )
        if remaining == 0:
            contact.status = ContactStatus.CONTACTED
            contact.version += 1
            contact.updated_by_id = user.id
    record(
        db,
        AuditAction.APPOINTMENT_CANCELLED,
        user,
        (AuditTarget.APPOINTMENT, appointment_id),
        from_status=AppointmentStatus.SCHEDULED,
        to_status=AppointmentStatus.CANCELLED,
    )
    record_contact_status(db, user, contact, status_before)
    db.commit()
    db.refresh(appointment)
    logger.info("Cita cancelada: id=%s por user_id=%s, motivo %s", appointment.id, user.id, appointment.cancel_reason)
    return _out(appointment, zone)


@router.post(
    "/{appointment_id}/attendance",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "La cita no existe (o, para el profesional, no es suya)"},
        409: {"description": "Otra persona la cambió antes, no ha empezado, está cancelada o el plazo de corrección pasó"},
        422: {"description": "El estado no es Realizada ni No presentado"},
    },
)
def mark_attendance(
    appointment_id: int,
    body: AppointmentAttendance,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AppointmentOut:
    """Asistencia (T20b): Realizada o No presentado, desde la hora de inicio de la cita.

    Admin y recepción, cualquier cita; el profesional, solo las suyas (las de otra persona, 404
    como si no existieran). Se puede corregir de una a otra durante 7 días desde que se marcó.
    El estado del contacto se recalcula en la misma transacción (`_recompute_contact`).
    """
    zone = get_settings().clinic_zone
    appointment, contact = _lock_for_attendance(db, appointment_id, body, now, user)
    appointment_before = appointment.status
    contact_before = contact.status
    if appointment.attended_at is None:
        appointment.attended_at = now
    appointment.status = body.status
    appointment.version += 1
    appointment.updated_by_id = user.id
    db.flush()
    _recompute_contact(db, contact, user)
    record(
        db,
        AuditAction.APPOINTMENT_ATTENDANCE_MARKED,
        user,
        (AuditTarget.APPOINTMENT, appointment_id),
        from_status=appointment_before,
        to_status=body.status,
    )
    record_contact_status(db, user, contact, contact_before)
    db.commit()
    db.refresh(appointment)
    logger.info("Asistencia: cita id=%s %s por user_id=%s", appointment.id, appointment.status, user.id)
    return _out(appointment, zone)


@router.put(
    "/{appointment_id}/note",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "La cita no existe"},
        409: {"description": "Otra persona la cambió antes"},
        422: {"description": "Nota no válida"},
    },
)
def edit_note(
    appointment_id: int,
    body: AppointmentNote,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> AppointmentOut:
    """Editar la nota (T21b), en cualquier estado de la cita: no cambia nada más. Una sola sentencia
    con la versión, como la edición de un contacto (T13); el texto no se registra en el log."""
    statement = (
        update(Appointment)
        .where(Appointment.id == appointment_id, Appointment.version == body.version)
        .values(note=body.note, version=Appointment.version + 1, updated_by_id=user.id, updated_at=func.now())
        .returning(Appointment.id)
    )
    if db.execute(statement).scalar_one_or_none() is None:
        db.rollback()
        if db.get(Appointment, appointment_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
        raise HTTPException(status.HTTP_409_CONFLICT, VERSION_CONFLICT_MESSAGE)
    record(db, AuditAction.APPOINTMENT_NOTE_EDITED, user, (AuditTarget.APPOINTMENT, appointment_id), fields=["note"])
    db.commit()
    appointment = db.get(Appointment, appointment_id, populate_existing=True)
    logger.info("Nota de la cita: id=%s por user_id=%s", appointment.id, user.id)
    return _out(appointment, get_settings().clinic_zone)


def _lock_for_attendance(
    db: Session, appointment_id: int, body: AppointmentAttendance, now: datetime, user: User
) -> tuple[Appointment, Contact]:
    """La cita y su contacto, bloqueados en el orden de siempre (contacto y después cita, T19)."""
    row = db.execute(
        select(Appointment.contact_id, Appointment.staff_id).where(Appointment.id == appointment_id)
    ).one_or_none()
    if row is None or (user.role == Role.PROFESSIONAL and row.staff_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    contact = _lock_contact(db, row.contact_id)
    appointment = db.scalars(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if appointment.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, VERSION_CONFLICT_MESSAGE)
    if appointment.status == AppointmentStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, CANCELLED_ATTENDANCE_MESSAGE)
    if appointment.starts_at > now:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_STARTED_MESSAGE)
    if appointment.status == body.status:
        name = STATUS_NAMES[AppointmentStatus(appointment.status)]
        raise HTTPException(status.HTTP_409_CONFLICT, f"La cita ya está «{name}»")
    if appointment.attended_at is not None and now > appointment.attended_at + timedelta(days=CORRECTION_DAYS):
        raise HTTPException(status.HTTP_409_CONFLICT, CORRECTION_EXPIRED_MESSAGE)
    return appointment, contact


def _recompute_contact(db: Session, contact: Contact, user: User) -> None:
    """El estado del contacto tras marcar o corregir la asistencia (decisiones T20b).

    - Con alguna Realizada es Cliente (la primera lo convierte; un Perdido que viene, también).
    - Si era Cliente y ya no le queda ninguna Realizada (se corrigió a No presentado): vuelve a
      «Cita agendada» si le queda alguna Programada, o a Contactado si no.
    - Si estaba en «Cita agendada» y no le queda ninguna Programada (No presentado en la
      última): Contactado, como al cancelar (T19).
    El contacto está bloqueado: nadie le da otra cita ni marca otra mientras se cuenta.
    """

    def count(state: AppointmentStatus) -> int:
        return db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(Appointment.contact_id == contact.id, Appointment.status == state)
        )

    if count(AppointmentStatus.COMPLETED):
        target = ContactStatus.CLIENT
    elif contact.status in (ContactStatus.CLIENT, ContactStatus.SCHEDULED):
        target = ContactStatus.SCHEDULED if count(AppointmentStatus.SCHEDULED) else ContactStatus.CONTACTED
    else:
        return  # Nuevo, Contactado o Perdido con un No presentado: no cambia
    if contact.status != target:
        contact.status = target
        contact.version += 1
        contact.updated_by_id = user.id


def _start_instant(local: datetime, zone: ZoneInfo, now: datetime) -> datetime:
    """La hora local de inicio como instante, desde ahora y como mucho dentro de 365 días (T16)."""
    try:
        starts_at = clinic_instant(local, zone)
    except ValueError as error:
        raise field_error("starts_at", str(error)) from None
    if starts_at < now:
        raise field_error("starts_at", PAST_MESSAGE)
    if starts_at > now + timedelta(days=MAX_DAYS_AHEAD):
        raise field_error("starts_at", TOO_FAR_MESSAGE)
    return starts_at


def _lock_contact(db: Session, contact_id: int) -> Contact | None:
    return db.scalars(
        select(Contact).where(Contact.id == contact_id).with_for_update().execution_options(populate_existing=True)
    ).one_or_none()


def _lock_active_service(db: Session, service_id: int) -> Service | None:
    return db.scalars(
        select(Service)
        .where(Service.id == service_id, Service.active.is_(True))
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).one_or_none()


def _lock_staff(db: Session, service_id: int, staff_id: int) -> User | None:
    """Una de las personas del servicio, con su cuenta interna activa, bloqueada hasta el commit.

    Las citas de una misma persona se hacen de una en una. La restricción de exclusión escribe la
    fila y luego busca choques: dos a la vez se verían y esperarían la una a la otra, y PostgreSQL
    cortaría una como interbloqueo (503 en vez de 409; T28). FOR NO KEY UPDATE no frena las claves
    ajenas a esta cuenta (key_share), y personas distintas no se esperan.
    """
    return db.scalars(
        select(User)
        .join(ServiceStaff, ServiceStaff.user_id == User.id)
        .where(
            ServiceStaff.service_id == service_id,
            User.id == staff_id,
            User.active.is_(True),
            User.role.in_(STAFF_ROLES),
        )
        .with_for_update(key_share=True, of=User)
        .execution_options(populate_existing=True)
    ).one_or_none()


def _lock_for_change(db: Session, appointment_id: int, version: int, now: datetime) -> tuple[Appointment, Contact]:
    """La cita que se va a reprogramar o cancelar y su contacto, bloqueados hasta el commit.

    Primero el contacto y después la cita, el mismo orden que el alta: dos operaciones sobre
    citas del mismo contacto se esperan en vez de bloquearse mutuamente. Solo una cita
    Programada que no ha empezado y con la versión que se leyó (decisión T19).
    """
    contact_id = db.scalar(select(Appointment.contact_id).where(Appointment.id == appointment_id))
    if contact_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    contact = _lock_contact(db, contact_id)
    # El contacto de una cita no cambia ni se borra (T16): con el bloqueo, la cita sigue siendo suya.
    appointment = db.scalars(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if appointment.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT, VERSION_CONFLICT_MESSAGE)
    if appointment.status != AppointmentStatus.SCHEDULED:
        name = STATUS_NAMES[AppointmentStatus(appointment.status)]
        raise HTTPException(status.HTTP_409_CONFLICT, f"La cita está «{name}»: ya no se puede cambiar")
    if appointment.starts_at <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_STARTED_MESSAGE)
    return appointment, contact


def _out(appointment: Appointment, zone: ZoneInfo) -> AppointmentOut:
    """La cita con sus horas en la de la clínica."""
    return AppointmentOut(
        id=appointment.id,
        contact_id=appointment.contact_id,
        service_id=appointment.service_id,
        staff_id=appointment.staff_id,
        starts_at=appointment.starts_at.astimezone(zone),
        ends_at=appointment.ends_at.astimezone(zone),
        duration_minutes=appointment.duration_minutes,
        status=appointment.status,
        version=appointment.version,
        created_at=appointment.created_at.astimezone(zone),
        cancel_reason=appointment.cancel_reason,
        cancel_note=appointment.cancel_note,
        attended_at=appointment.attended_at.astimezone(zone) if appointment.attended_at else None,
        note=appointment.note,
    )
