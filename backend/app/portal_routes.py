"""Portal del cliente (T22): sus propias citas, en solo lectura.

La identidad sale de la sesión: la ruta no acepta ningún parámetro, así que no hay id ni filtro que
manipular para pedir las citas de otro. La respuesta se construye campo a campo y no reutiliza la de
la agenda: una columna interna nueva no puede llegar aquí por descuido.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Row, and_, func, not_, select
from sqlalchemy.orm import Session

from app.appointments_routes import get_now
from app.auth import require_roles
from app.config import get_settings
from app.db import get_db
from app.models import Appointment, AppointmentStatus, Role, Service, User

router = APIRouter(prefix="/api/portal", tags=["portal"])

# Las más recientes, como la lista de citas de la ficha (T21).
PAST_LIMIT = 20


class PortalAppointment(BaseModel):
    """Lo que el cliente puede saber de una cita. Sin notas, motivo ni detalle de la cancelación, sin
    quién la realiza (las cuentas internas aún no tienen nombre, solo su email) y sin versión."""

    id: int
    service_name: str
    # En la hora de la clínica, con su desfase: «2027-01-11T09:30:00-05:00».
    starts_at: datetime
    ends_at: datetime
    status: str


class PortalAppointments(BaseModel):
    upcoming: list[PortalAppointment]
    past: list[PortalAppointment]
    # Todas las anteriores, aunque solo vengan las 20 últimas.
    past_total: int


@router.get("/appointments")
def my_appointments(
    user: User = Depends(require_roles(Role.CLIENT)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PortalAppointments:
    """Las citas del contacto vinculado a la sesión. Sin vínculo, ninguna.

    Próximas: las que aún no han terminado y siguen Programadas o se cancelaron, para que el cliente
    vea que ya no tiene esa cita; de la más cercana a la más lejana. Anteriores: todas las demás, de
    la más reciente a la más antigua.
    """
    if user.contact_id is None:
        return PortalAppointments(upcoming=[], past=[], past_total=0)
    zone = get_settings().clinic_zone
    own = Appointment.contact_id == user.contact_id
    is_upcoming = and_(
        Appointment.ends_at > now,
        Appointment.status.in_((AppointmentStatus.SCHEDULED, AppointmentStatus.CANCELLED)),
    )
    query = select(
        Appointment.id, Service.name, Appointment.starts_at, Appointment.ends_at, Appointment.status
    ).join(Service, Service.id == Appointment.service_id)

    def out(row: Row) -> PortalAppointment:
        return PortalAppointment(
            id=row.id,
            service_name=row.name,
            starts_at=row.starts_at.astimezone(zone),
            ends_at=row.ends_at.astimezone(zone),
            status=row.status,
        )

    upcoming = db.execute(query.where(own, is_upcoming).order_by(Appointment.starts_at, Appointment.id))
    past = db.execute(
        query.where(own, not_(is_upcoming))
        .order_by(Appointment.starts_at.desc(), Appointment.id.desc())
        .limit(PAST_LIMIT)
    )
    past_total = db.scalar(select(func.count()).select_from(Appointment).where(own, not_(is_upcoming)))
    return PortalAppointments(upcoming=[out(r) for r in upcoming], past=[out(r) for r in past], past_total=past_total)
