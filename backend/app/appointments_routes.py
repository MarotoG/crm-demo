"""Citas (T16): crear una cita para un contacto, un servicio y una de las personas que lo realizan.

Las crean administración y recepción; el profesional y el cliente reciben 403 (consultarán las
suyas más adelante). La hora se escribe en la hora local de la clínica, sin zona (decisión T16), y
la API la convierte a un instante. La duración se copia del servicio.

Solapamientos (T17): la misma persona no puede tener dos citas que se pisen (409). Lo decide una
restricción de exclusión de PostgreSQL (app/models.py). Una clienta sí puede tener dos citas a la
vez con dos personas distintas (tinte y pedicura, decisión T17).
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StrictInt, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_csrf, require_roles
from app.config import get_settings
from app.db import get_db
from app.errors import field_error, user_message
from app.models import (
    STAFF_OVERLAP_CONSTRAINT,
    Appointment,
    AppointmentStatus,
    Contact,
    ContactStatus,
    Role,
    Service,
    ServiceStaff,
    User,
)
from app.services_routes import STAFF_ROLES
from app.validators import START_FORMAT_MESSAGE, clinic_instant, parse_local_start

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


class AppointmentCreate(BaseModel):
    # extra="forbid": el navegador no fija la duración, el fin, el estado ni la versión.
    model_config = ConfigDict(extra="forbid")

    contact_id: StrictInt
    service_id: StrictInt
    staff_id: StrictInt
    # Hora local de la clínica, sin zona: «2027-01-11T09:30».
    starts_at: datetime

    @field_validator("starts_at", mode="before")
    @classmethod
    def _starts_at(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise PydanticCustomError("dato_no_valido", START_FORMAT_MESSAGE)
        return user_message(parse_local_start)(value)


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


def _clock(moment: datetime) -> str:
    return f"{moment.hour}:{moment.minute:02d}"


def _overlap_or_raise(
    error: IntegrityError, db: Session, staff_id: int, starts_at: datetime, ends_at: datetime, zone: ZoneInfo
) -> HTTPException:
    """409 con la hora de la cita que choca, si ha saltado la regla de solapamientos.

    Sin el nombre del contacto (decisión T17). Cualquier otro error de integridad sigue su curso.
    """
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint != STAFF_OVERLAP_CONSTRAINT:
        raise error
    # La que choca ya está guardada: la restricción solo falla frente a citas confirmadas.
    other = db.scalars(
        select(Appointment)
        .where(
            Appointment.staff_id == staff_id,
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        .order_by(Appointment.starts_at)
        .limit(1)
    ).first()
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
    try:
        starts_at = clinic_instant(body.starts_at, zone)
    except ValueError as error:
        raise field_error("starts_at", str(error)) from None
    if starts_at < now:
        raise field_error("starts_at", PAST_MESSAGE)
    if starts_at > now + timedelta(days=MAX_DAYS_AHEAD):
        raise field_error("starts_at", TOO_FAR_MESSAGE)

    # Se leen con bloqueo, siempre en este orden (contacto, servicio, persona), hasta el commit:
    # - el contacto, en exclusiva: si a la vez alguien lo marca Perdido, uno de los dos espera y
    #   ve el resultado del otro (no puede quedar una cita nueva con un contacto Perdido);
    # - el servicio y la persona, compartidos: varias citas a la vez no se esperan entre sí, pero
    #   desactivar el servicio o cambiar sus personas (T15) sí espera, y al revés.
    contact = db.scalars(
        select(Contact).where(Contact.id == body.contact_id).with_for_update().execution_options(populate_existing=True)
    ).one_or_none()
    if contact is None:
        raise field_error("contact_id", CONTACT_NOT_FOUND_MESSAGE)
    if contact.status == ContactStatus.LOST:
        raise field_error("contact_id", CONTACT_LOST_MESSAGE)
    service = db.scalars(
        select(Service)
        .where(Service.id == body.service_id, Service.active.is_(True))
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if service is None:
        raise field_error("service_id", SERVICE_NOT_VALID_MESSAGE)
    # Una de las personas del servicio, con su cuenta interna activa.
    staff = db.scalars(
        select(User)
        .join(ServiceStaff, ServiceStaff.user_id == User.id)
        .where(
            ServiceStaff.service_id == service.id,
            User.id == body.staff_id,
            User.active.is_(True),
            User.role.in_(STAFF_ROLES),
        )
        .with_for_update(read=True, of=User)
        .execution_options(populate_existing=True)
    ).one_or_none()
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
    )
    db.add(appointment)
    try:
        # Solapamientos (T17): decide la restricción de exclusión de PostgreSQL, no una consulta
        # previa. Con dos peticiones a la vez para la misma persona, la segunda espera a que la
        # primera termine y, si se pisan, falla aquí.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise _overlap_or_raise(error, db, staff_id, starts_at, ends_at, zone) from None
    # El estado del contacto, en la misma transacción: o se guardan los dos cambios o ninguno. Sube
    # su versión (T13): quien editaba la ficha con la anterior recibirá 409 y verá el estado nuevo.
    if contact.status in PROMOTED_TO_SCHEDULED:
        contact.status = ContactStatus.SCHEDULED
        contact.version += 1
        contact.updated_by_id = user.id
    db.commit()
    db.refresh(appointment)
    logger.info("Cita creada: id=%s contacto=%s por user_id=%s", appointment.id, contact.id, user.id)
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
    )
