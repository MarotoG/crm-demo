"""Tareas de seguimiento de un contacto: crear, asignar y consultar (T24).

Las crean administración y recepción (decisión T24). Un profesional solo puede ser responsable si
el contacto tiene alguna cita con él: así la tarea no le exige abrir una ficha que no puede ver, y
no cambia quién ve qué. Él solo ve las suyas; el cliente, nada.
"""

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StrictInt, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.appointments_routes import MAX_DAYS_AHEAD, get_now
from app.auth import require_csrf, require_roles
from app.config import get_settings
from app.contacts_routes import has_appointment_with
from app.db import get_db
from app.errors import field_error, user_message
from app.models import Appointment, Contact, FollowUpTask, Role, User
from app.validators import DUE_DATE_FORMAT_MESSAGE, normalize_follow_up_description, parse_due_date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts/{contact_id}", tags=["seguimientos"])

LIST_LIMIT = 20
# Pueden ser responsables de cualquier tarea; el profesional, según sus citas.
ANY_CONTACT_ROLES = (Role.ADMIN, Role.RECEPTION)

NOT_FOUND_MESSAGE = "Contacto no encontrado"
PAST_MESSAGE = "La fecha prevista no puede ser anterior a hoy"
TOO_FAR_MESSAGE = f"La fecha prevista no puede ser para dentro de más de {MAX_DAYS_AHEAD} días"
ASSIGNEE_NOT_VALID_MESSAGE = "Esa persona no existe, no es del personal o su cuenta no está activa"
NO_APPOINTMENT_MESSAGE = "Este profesional no tiene citas con este contacto: asígnala a recepción o administración"


class FollowUpCreate(BaseModel):
    # extra="forbid": el navegador no fija el autor, el contacto ni las fechas de registro.
    model_config = ConfigDict(extra="forbid")

    description: str
    due_on: date
    assigned_to_id: StrictInt

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return user_message(normalize_follow_up_description)(value)

    @field_validator("due_on", mode="before")
    @classmethod
    def _due_on(cls, value: object) -> date:
        # mode="before": Pydantic aceptaría también números y fechas con hora.
        if not isinstance(value, str):
            raise PydanticCustomError("dato_no_valido", DUE_DATE_FORMAT_MESSAGE)
        return user_message(parse_due_date)(value)


class FollowUpOut(BaseModel):
    id: int
    contact_id: int
    description: str
    due_on: date
    assigned_to_id: int
    assigned_to_email: str
    created_by_email: str | None  # None si esa cuenta se borró (ON DELETE SET NULL)
    created_at: datetime


class FollowUpList(BaseModel):
    """`total` cuenta todas las que puede ver quien pregunta, aunque solo vayan LIST_LIMIT."""

    total: int
    items: list[FollowUpOut]


class AssigneeOut(BaseModel):
    id: int
    email: str


def _assignee_condition(contact_id: int):
    """Cuentas activas de administración y recepción, y profesionales con alguna cita con el contacto."""
    has_appointment = exists().where(Appointment.contact_id == contact_id, Appointment.staff_id == User.id)
    return (
        User.active.is_(True),
        or_(User.role.in_(ANY_CONTACT_ROLES), (User.role == Role.PROFESSIONAL) & has_appointment),
    )


def _select_tasks():
    assignee = aliased(User)
    creator = aliased(User)
    return (
        select(FollowUpTask, assignee.email, creator.email)
        .join(assignee, assignee.id == FollowUpTask.assigned_to_id)
        .outerjoin(creator, creator.id == FollowUpTask.created_by_id)
    )


def _out(task: FollowUpTask, assignee_email: str, creator_email: str | None) -> FollowUpOut:
    return FollowUpOut(
        id=task.id,
        contact_id=task.contact_id,
        description=task.description,
        due_on=task.due_on,
        assigned_to_id=task.assigned_to_id,
        assigned_to_email=assignee_email,
        created_by_email=creator_email,
        created_at=task.created_at,
    )


@router.get("/follow-ups", responses={404: {"description": "Contacto no encontrado"}})
def list_follow_ups(
    contact_id: int,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)),
    db: Session = Depends(get_db),
) -> FollowUpList:
    """Las tareas de un contacto, de la fecha más cercana a la más lejana.

    El profesional solo ve las suyas, y sin citas con el contacto, 404 como en la ficha (T20): no
    se revela que existe. El filtro lo pone la API, no el navegador. El cliente, 403.
    """
    if db.get(Contact, contact_id) is None or (
        user.role == Role.PROFESSIONAL and not has_appointment_with(db, contact_id, user.id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    conditions = [FollowUpTask.contact_id == contact_id]
    if user.role == Role.PROFESSIONAL:
        conditions.append(FollowUpTask.assigned_to_id == user.id)
    total = db.scalar(select(func.count()).select_from(FollowUpTask).where(*conditions))
    rows = db.execute(
        _select_tasks().where(*conditions).order_by(FollowUpTask.due_on, FollowUpTask.id).limit(LIST_LIMIT)
    )
    return FollowUpList(total=total, items=[_out(*row) for row in rows])


@router.get("/follow-up-assignees", responses={404: {"description": "Contacto no encontrado"}})
def list_assignees(
    contact_id: int,
    _user: User = Depends(require_roles(*ANY_CONTACT_ROLES)),
    db: Session = Depends(get_db),
) -> list[AssigneeOut]:
    """A quién se le puede asignar una tarea de este contacto, para el desplegable."""
    if db.get(Contact, contact_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    users = db.scalars(select(User).where(*_assignee_condition(contact_id)).order_by(User.email))
    return [AssigneeOut(id=u.id, email=u.email) for u in users]


@router.post(
    "/follow-ups",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={404: {"description": "Contacto no encontrado"}, 422: {"description": "Datos no válidos"}},
)
def create_follow_up(
    contact_id: int,
    body: FollowUpCreate,
    user: User = Depends(require_roles(*ANY_CONTACT_ROLES)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FollowUpOut:
    """Crea una tarea. Vale también para un contacto Perdido: puede querer retomarse más adelante."""
    if db.get(Contact, contact_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    today = now.astimezone(get_settings().clinic_zone).date()
    if body.due_on < today:
        raise field_error("due_on", PAST_MESSAGE)
    if body.due_on > today + timedelta(days=MAX_DAYS_AHEAD):
        raise field_error("due_on", TOO_FAR_MESSAGE)
    assignee = db.get(User, body.assigned_to_id)
    if assignee is None or not assignee.active or assignee.role == Role.CLIENT:
        raise field_error("assigned_to_id", ASSIGNEE_NOT_VALID_MESSAGE)
    if assignee.role == Role.PROFESSIONAL and not has_appointment_with(db, contact_id, assignee.id):
        raise field_error("assigned_to_id", NO_APPOINTMENT_MESSAGE)
    task = FollowUpTask(contact_id=contact_id, created_by_id=user.id, **body.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info("Tarea de seguimiento creada: id=%s contacto=%s por user_id=%s", task.id, contact_id, user.id)
    return _out(task, assignee.email, user.email)
