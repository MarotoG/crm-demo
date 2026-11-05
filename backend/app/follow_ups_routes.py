"""Tareas de seguimiento: crear, asignar y consultar en la ficha (T24); panel de pendientes,
completar, reabrir y editar (T25).

Las crean y editan administración y recepción (decisión T24). Un profesional solo puede ser
responsable si el contacto tiene alguna cita con él: así la tarea no le exige abrir una ficha que no
puede ver, y no cambia quién ve qué. Él solo ve las suyas y solo completa o reabre las suyas; el
cliente, nada. Sin push: el aviso es el contador y el panel dentro del CRM.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import ColumnElement, exists, func, or_, select, update
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

router = APIRouter(prefix="/api", tags=["seguimientos"])

LIST_LIMIT = 20
PANEL_LIMIT = 50
# Pueden ser responsables de cualquier tarea; el profesional, según sus citas.
ANY_CONTACT_ROLES = (Role.ADMIN, Role.RECEPTION)
STAFF = (Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)

NOT_FOUND_MESSAGE = "Contacto no encontrado"
TASK_NOT_FOUND_MESSAGE = "Tarea no encontrada"
OWN_TASKS_MESSAGE = "Solo puedes ver tus tareas"
PAST_MESSAGE = "La fecha prevista no puede ser anterior a hoy"
TOO_FAR_MESSAGE = f"La fecha prevista no puede ser para dentro de más de {MAX_DAYS_AHEAD} días"
ASSIGNEE_NOT_VALID_MESSAGE = "Esa persona no existe, no es del personal o su cuenta no está activa"
NO_APPOINTMENT_MESSAGE = "Este profesional no tiene citas con este contacto: asígnala a recepción o administración"
VERSION_CONFLICT_MESSAGE = "Otra persona ha cambiado esta tarea. Revisa los datos actuales y vuelve a intentarlo."
ALREADY_DONE_MESSAGE = "Esta tarea ya está hecha"
NOT_DONE_MESSAGE = "Esta tarea ya está pendiente"
EDIT_DONE_MESSAGE = "Esta tarea ya está hecha: reábrela para editarla"


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


class FollowUpUpdate(FollowUpCreate):
    """Edición (T25): la tarea entera, más la versión que se leyó."""

    version: StrictInt = Field(ge=1)


class VersionOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(ge=1)


class FollowUpOut(BaseModel):
    id: int
    contact_id: int
    contact_name: str
    contact_status: str
    description: str
    due_on: date
    assigned_to_id: int
    assigned_to_email: str
    created_by_email: str | None  # None si esa cuenta se borró (ON DELETE SET NULL)
    created_at: datetime
    completed_at: datetime | None
    completed_by_email: str | None
    version: int


class FollowUpList(BaseModel):
    """`total` cuenta todas las que puede ver quien pregunta, aunque no vayan todas. `today` es el día
    de la clínica: con él la interfaz sabe cuáles están vencidas sin fiarse del reloj del navegador."""

    today: date
    total: int
    items: list[FollowUpOut]


class FollowUpSummary(BaseModel):
    """Para el contador de la barra: las pendientes vencidas y las de hoy."""

    overdue: int
    due_today: int


class AssigneeOut(BaseModel):
    id: int
    email: str


def _today(now: datetime) -> date:
    return now.astimezone(get_settings().clinic_zone).date()


def _assignee_condition(contact_id: int):
    """Cuentas activas de administración y recepción, y profesionales con alguna cita con el contacto."""
    has_appointment = exists().where(Appointment.contact_id == contact_id, Appointment.staff_id == User.id)
    return (
        User.active.is_(True),
        or_(User.role.in_(ANY_CONTACT_ROLES), (User.role == Role.PROFESSIONAL) & has_appointment),
    )


def _visible_to(user: User) -> list[ColumnElement[bool]]:
    """El profesional solo alcanza sus tareas; lo pone la API, no el navegador."""
    return [FollowUpTask.assigned_to_id == user.id] if user.role == Role.PROFESSIONAL else []


def _check_due_on(due_on: date, today: date) -> None:
    if due_on < today:
        raise field_error("due_on", PAST_MESSAGE)
    if due_on > today + timedelta(days=MAX_DAYS_AHEAD):
        raise field_error("due_on", TOO_FAR_MESSAGE)


def _check_assignee(db: Session, contact_id: int, assignee_id: int) -> None:
    assignee = db.get(User, assignee_id)
    if assignee is None or not assignee.active or assignee.role == Role.CLIENT:
        raise field_error("assigned_to_id", ASSIGNEE_NOT_VALID_MESSAGE)
    if assignee.role == Role.PROFESSIONAL and not has_appointment_with(db, contact_id, assignee.id):
        raise field_error("assigned_to_id", NO_APPOINTMENT_MESSAGE)


def _select_tasks():
    assignee = aliased(User)
    creator = aliased(User)
    completer = aliased(User)
    return (
        select(FollowUpTask, Contact, assignee.email, creator.email, completer.email)
        .join(Contact, Contact.id == FollowUpTask.contact_id)
        .join(assignee, assignee.id == FollowUpTask.assigned_to_id)
        .outerjoin(creator, creator.id == FollowUpTask.created_by_id)
        .outerjoin(completer, completer.id == FollowUpTask.completed_by_id)
    )


def _out(
    task: FollowUpTask, contact: Contact, assignee_email: str, creator_email: str | None, completer_email: str | None
) -> FollowUpOut:
    return FollowUpOut(
        id=task.id,
        contact_id=task.contact_id,
        contact_name=f"{contact.first_name} {contact.last_name}",
        contact_status=contact.status,
        description=task.description,
        due_on=task.due_on,
        assigned_to_id=task.assigned_to_id,
        assigned_to_email=assignee_email,
        created_by_email=creator_email,
        created_at=task.created_at,
        completed_at=task.completed_at,
        completed_by_email=completer_email,
        version=task.version,
    )


def _read_one(db: Session, task_id: int) -> FollowUpOut:
    row = db.execute(
        _select_tasks().where(FollowUpTask.id == task_id).execution_options(populate_existing=True)
    ).one()
    return _out(*row)


@router.get("/follow-ups", responses={403: {"description": "El profesional solo ve sus tareas"}})
def list_panel(
    state: Literal["pending", "done"] = "pending",
    assigned_to_id: int | None = None,
    user: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FollowUpList:
    """Panel de pendientes (T25). Pendientes: las 50 de fecha más cercana, así las vencidas salen
    siempre primero. Hechas: las 50 marcadas más recientemente. Filtro opcional por responsable.

    Como en la agenda (T20), el filtro del profesional lo pone la API, y pedir las de otra persona
    es 403. El cliente, 403.
    """
    if user.role == Role.PROFESSIONAL and assigned_to_id not in (None, user.id):
        logger.warning("Tareas ajenas denegadas: user_id=%s pidió assigned_to_id=%s", user.id, assigned_to_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, OWN_TASKS_MESSAGE)
    pending = state == "pending"
    conditions = [FollowUpTask.completed_at.is_(None) if pending else FollowUpTask.completed_at.is_not(None)]
    conditions += _visible_to(user)
    if assigned_to_id is not None:
        conditions.append(FollowUpTask.assigned_to_id == assigned_to_id)
    order = (FollowUpTask.due_on, FollowUpTask.id) if pending else (FollowUpTask.completed_at.desc(), FollowUpTask.id.desc())
    total = db.scalar(select(func.count()).select_from(FollowUpTask).where(*conditions))
    rows = db.execute(_select_tasks().where(*conditions).order_by(*order).limit(PANEL_LIMIT))
    return FollowUpList(today=_today(now), total=total, items=[_out(*row) for row in rows])


@router.get("/follow-ups/summary")
def panel_summary(
    user: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FollowUpSummary:
    """Cuántas pendientes están vencidas y cuántas son de hoy, de las que abre el panel: todas para
    administración y recepción; las suyas para el profesional."""
    today = _today(now)
    overdue, due_today = db.execute(
        select(
            func.count().filter(FollowUpTask.due_on < today),
            func.count().filter(FollowUpTask.due_on == today),
        ).where(FollowUpTask.completed_at.is_(None), *_visible_to(user))
    ).one()
    return FollowUpSummary(overdue=overdue, due_today=due_today)


def _conflict_or_missing(db: Session, task_id: int, user: User, done_message: str | None, pending_message: str | None) -> HTTPException:
    """Por qué no se actualizó nada: no existe (o no es suya: mismo 404, no se revela) o ya cambió."""
    db.rollback()
    task = db.get(FollowUpTask, task_id, populate_existing=True)
    if task is None or (user.role == Role.PROFESSIONAL and task.assigned_to_id != user.id):
        return HTTPException(status.HTTP_404_NOT_FOUND, TASK_NOT_FOUND_MESSAGE)
    if done_message and task.completed_at is not None:
        return HTTPException(status.HTTP_409_CONFLICT, done_message)
    if pending_message and task.completed_at is None:
        return HTTPException(status.HTTP_409_CONFLICT, pending_message)
    return HTTPException(status.HTTP_409_CONFLICT, VERSION_CONFLICT_MESSAGE)


@router.post(
    "/follow-ups/{task_id}/complete",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "No existe o no es del profesional"},
        409: {"description": "Ya está hecha o cambió antes (versión distinta)"},
    },
)
def complete_follow_up(
    task_id: int,
    body: VersionOnly,
    user: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FollowUpOut:
    """Marca la tarea como hecha y guarda quién y cuándo. Versión, estado y dueño se comprueban en el
    mismo UPDATE: con dos clics simultáneos, PostgreSQL deja pasar uno y el otro recibe 409."""
    done = db.execute(
        update(FollowUpTask)
        .where(
            FollowUpTask.id == task_id,
            FollowUpTask.version == body.version,
            FollowUpTask.completed_at.is_(None),
            *_visible_to(user),
        )
        .values(completed_at=now, completed_by_id=user.id, version=FollowUpTask.version + 1)
        .returning(FollowUpTask.id)
    ).scalar_one_or_none()
    if done is None:
        raise _conflict_or_missing(db, task_id, user, ALREADY_DONE_MESSAGE, None)
    db.commit()
    logger.info("Tarea de seguimiento hecha: id=%s por user_id=%s", task_id, user.id)
    return _read_one(db, task_id)


@router.post(
    "/follow-ups/{task_id}/reopen",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "No existe o no es del profesional"},
        409: {"description": "Ya está pendiente o cambió antes (versión distinta)"},
    },
)
def reopen_follow_up(
    task_id: int,
    body: VersionOnly,
    user: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
) -> FollowUpOut:
    """La devuelve a pendiente, sin límite de tiempo (decisión T25): no cambia nada más en el CRM.
    Conserva su fecha: si ya pasó, vuelve como vencida."""
    reopened = db.execute(
        update(FollowUpTask)
        .where(
            FollowUpTask.id == task_id,
            FollowUpTask.version == body.version,
            FollowUpTask.completed_at.is_not(None),
            *_visible_to(user),
        )
        .values(completed_at=None, completed_by_id=None, version=FollowUpTask.version + 1)
        .returning(FollowUpTask.id)
    ).scalar_one_or_none()
    if reopened is None:
        raise _conflict_or_missing(db, task_id, user, None, NOT_DONE_MESSAGE)
    db.commit()
    logger.info("Tarea de seguimiento reabierta: id=%s por user_id=%s", task_id, user.id)
    return _read_one(db, task_id)


@router.put(
    "/follow-ups/{task_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "Tarea no encontrada"},
        409: {"description": "Ya está hecha o cambió antes (versión distinta)"},
        422: {"description": "Datos no válidos"},
    },
)
def update_follow_up(
    task_id: int,
    body: FollowUpUpdate,
    user: User = Depends(require_roles(*ANY_CONTACT_ROLES)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FollowUpOut:
    """Edita o reasigna una tarea pendiente (T25). Solo se comprueba lo que cambia: una tarea vencida
    se puede reasignar sin moverle la fecha, y corregir una errata no falla si el responsable ya no
    podría asignarse."""
    task = db.get(FollowUpTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TASK_NOT_FOUND_MESSAGE)
    if body.due_on != task.due_on:
        _check_due_on(body.due_on, _today(now))
    if body.assigned_to_id != task.assigned_to_id:
        _check_assignee(db, task.contact_id, body.assigned_to_id)
    updated = db.execute(
        update(FollowUpTask)
        .where(FollowUpTask.id == task_id, FollowUpTask.version == body.version, FollowUpTask.completed_at.is_(None))
        .values(**body.model_dump(exclude={"version"}), version=FollowUpTask.version + 1)
        .returning(FollowUpTask.id)
    ).scalar_one_or_none()
    if updated is None:
        raise _conflict_or_missing(db, task_id, user, EDIT_DONE_MESSAGE, None)
    db.commit()
    logger.info("Tarea de seguimiento editada: id=%s por user_id=%s", task_id, user.id)
    return _read_one(db, task_id)


@router.get("/contacts/{contact_id}/follow-ups", responses={404: {"description": "Contacto no encontrado"}})
def list_follow_ups(
    contact_id: int,
    user: User = Depends(require_roles(*STAFF)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FollowUpList:
    """Las tareas de un contacto: primero las pendientes y después las hechas, cada grupo de la fecha
    más cercana a la más lejana.

    El profesional solo ve las suyas, y sin citas con el contacto, 404 como en la ficha (T20): no
    se revela que existe. El cliente, 403.
    """
    if db.get(Contact, contact_id) is None or (
        user.role == Role.PROFESSIONAL and not has_appointment_with(db, contact_id, user.id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    conditions = [FollowUpTask.contact_id == contact_id, *_visible_to(user)]
    total = db.scalar(select(func.count()).select_from(FollowUpTask).where(*conditions))
    rows = db.execute(
        _select_tasks()
        .where(*conditions)
        .order_by(FollowUpTask.completed_at.is_not(None), FollowUpTask.due_on, FollowUpTask.id)
        .limit(LIST_LIMIT)
    )
    return FollowUpList(today=_today(now), total=total, items=[_out(*row) for row in rows])


@router.get("/contacts/{contact_id}/follow-up-assignees", responses={404: {"description": "Contacto no encontrado"}})
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
    "/contacts/{contact_id}/follow-ups",
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
    _check_due_on(body.due_on, _today(now))
    _check_assignee(db, contact_id, body.assigned_to_id)
    task = FollowUpTask(contact_id=contact_id, created_by_id=user.id, **body.model_dump())
    db.add(task)
    db.commit()
    logger.info("Tarea de seguimiento creada: id=%s contacto=%s por user_id=%s", task.id, contact_id, user.id)
    return _read_one(db, task.id)
