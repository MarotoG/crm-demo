"""Servicios de la clínica (T15): alta uno a uno, lista, edición y desactivación, con las personas
que realizan cada uno.

Los gestionan administración y recepción (decisión del alumno). El profesional ve solo los
servicios activos que tiene asignados; el cliente, ninguno (403). Un servicio no se borra
nunca: se desactiva, y deja de ofrecerse para citas nuevas sin perder el historial.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_csrf, require_roles
from app.db import get_db
from app.errors import field_error, user_message
from app.models import Role, Service, ServiceStaff, User
from app.validators import check_duration, normalize_service_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["servicios"])

# Quién puede realizar un servicio (decisión T15): cualquier cuenta interna activa. El jefe o la
# recepcionista pueden ser también profesionales cualificados.
STAFF_ROLES = (Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)
# Más que suficiente para una clínica pequeña o mediana; evita listas desmesuradas.
MAX_STAFF = 50

NOT_FOUND_MESSAGE = "Servicio no encontrado"
NAME_TAKEN_MESSAGE = "Ya existe un servicio con ese nombre (puede estar desactivado: edítalo y reactívalo)"
VERSION_CONFLICT_MESSAGE = "Otra persona ha cambiado este servicio antes de que guardaras"
NEEDS_STAFF_MESSAGE = "Un servicio activo necesita al menos una persona que lo realice"
STAFF_NOT_VALID_MESSAGE = "Solo se pueden asignar cuentas internas activas (administración, recepción o profesional)"


class ServiceCreate(BaseModel):
    # extra="forbid": el navegador no puede fijar el id, la versión ni el estado al crear.
    model_config = ConfigDict(extra="forbid")

    name: str
    duration_minutes: int
    staff_ids: Annotated[list[StrictInt], Field(max_length=MAX_STAFF)]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return user_message(normalize_service_name)(value)

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def _duration(cls, value: object) -> int:
        # Solo un entero de verdad: ni «60», ni 60.5, ni true.
        if not isinstance(value, int) or isinstance(value, bool):
            raise PydanticCustomError("dato_no_valido", "La duración debe ser un número entero de minutos")
        return user_message(check_duration)(value)

    @field_validator("staff_ids")
    @classmethod
    def _staff(cls, value: list[int]) -> list[int]:
        # La misma persona marcada dos veces cuenta una sola.
        return sorted(set(value))


class ServiceUpdate(ServiceCreate):
    """Edición: el servicio entero (PUT), con si está activo y la versión que se leyó."""

    active: StrictBool
    version: int = Field(ge=1)


class StaffOut(BaseModel):
    id: int
    email: str
    role: str
    active: bool


class ServiceOut(BaseModel):
    id: int
    name: str
    duration_minutes: int
    active: bool
    version: int
    # Quién lo realiza, por email. Puede incluir a alguien desactivado después de asignarlo.
    staff: list[StaffOut]


def _staff_out(user: User) -> StaffOut:
    return StaffOut(id=user.id, email=user.email, role=user.role, active=user.active)


def _out(db: Session, services: list[Service]) -> list[ServiceOut]:
    """Los servicios con sus personas, en una sola consulta para todas (no una por servicio)."""
    staff: dict[int, list[StaffOut]] = {s.id: [] for s in services}
    rows = db.execute(
        select(ServiceStaff.service_id, User)
        .join(User, User.id == ServiceStaff.user_id)
        .where(ServiceStaff.service_id.in_(staff))
        .order_by(User.email)
    )
    for service_id, user in rows:
        staff[service_id].append(_staff_out(user))
    return [
        ServiceOut(id=s.id, name=s.name, duration_minutes=s.duration_minutes, active=s.active, version=s.version,
                   staff=staff[s.id])
        for s in services
    ]


def _all_eligible(db: Session, user_ids: set[int]) -> bool:
    found = db.scalar(
        select(func.count()).where(User.id.in_(user_ids), User.active.is_(True), User.role.in_(STAFF_ROLES))
    )
    return found == len(user_ids)


def _name_taken_or_raise(error: IntegrityError) -> HTTPException:
    """409 si ha saltado el índice del nombre; cualquier otro error de integridad sigue su curso."""
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint == "uq_services_name":
        return HTTPException(status.HTTP_409_CONFLICT, NAME_TAKEN_MESSAGE)
    raise error


@router.get("")
def list_services(
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION, Role.PROFESSIONAL)),
    db: Session = Depends(get_db),
) -> list[ServiceOut]:
    """Todos, primero los activos y por nombre. El profesional, solo sus servicios activos."""
    query = select(Service).order_by(Service.active.desc(), func.lower(Service.name), Service.id)
    if user.role == Role.PROFESSIONAL:
        mine = select(ServiceStaff.service_id).where(ServiceStaff.user_id == user.id)
        query = query.where(Service.active.is_(True), Service.id.in_(mine))
    return _out(db, list(db.scalars(query)))


@router.get("/staff")
def list_staff(
    _user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> list[StaffOut]:
    """Quién se puede asignar: las cuentas internas activas. Va antes de /{service_id}."""
    users = db.scalars(select(User).where(User.active.is_(True), User.role.in_(STAFF_ROLES)).order_by(User.email))
    return [_staff_out(u) for u in users]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={409: {"description": "Ya existe un servicio con ese nombre"}},
)
def create_service(
    body: ServiceCreate,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> ServiceOut:
    if not body.staff_ids:
        raise field_error("staff_ids", NEEDS_STAFF_MESSAGE)
    if not _all_eligible(db, set(body.staff_ids)):
        raise field_error("staff_ids", STAFF_NOT_VALID_MESSAGE)
    service = Service(name=body.name, duration_minutes=body.duration_minutes)
    db.add(service)
    try:
        # El índice único del nombre decide: dos altas iguales a la vez no pasan las dos.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise _name_taken_or_raise(error) from None
    db.add_all(ServiceStaff(service_id=service.id, user_id=user_id) for user_id in body.staff_ids)
    db.commit()
    logger.info("Servicio creado: id=%s por user_id=%s", service.id, user.id)
    return _out(db, [service])[0]


@router.put(
    "/{service_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "Servicio no encontrado"},
        409: {"description": "Otra persona guardó antes (versión distinta) o ya existe otro con ese nombre"},
    },
)
def update_service(
    service_id: int,
    body: ServiceUpdate,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> ServiceOut:
    """Editar, desactivar o reactivar: siempre el servicio entero con la versión leída."""
    if db.get(Service, service_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    if body.active and not body.staff_ids:
        raise field_error("staff_ids", NEEDS_STAFF_MESSAGE)
    # Como el responsable de un contacto (T14), solo se comprueba a quien se añade: guardar sin
    # tocar las personas no falla aunque alguna cuenta se haya desactivado después.
    current = set(db.scalars(select(ServiceStaff.user_id).where(ServiceStaff.service_id == service_id)))
    added = set(body.staff_ids) - current
    if added and not _all_eligible(db, added):
        raise field_error("staff_ids", STAFF_NOT_VALID_MESSAGE)
    # Bloqueo optimista en una sola sentencia, como en los contactos (T13). Si actualiza, la fila
    # queda bloqueada hasta el commit: otra edición del mismo servicio espera y recibe 409. Como
    # cualquier cambio sube la versión, las personas leídas arriba son las de esta versión.
    statement = (
        update(Service)
        .where(Service.id == service_id, Service.version == body.version)
        .values(name=body.name, duration_minutes=body.duration_minutes, active=body.active,
                version=Service.version + 1)
        .returning(Service.id)
    )
    try:
        updated = db.execute(statement).scalar_one_or_none()
    except IntegrityError as error:
        db.rollback()
        raise _name_taken_or_raise(error) from None
    if updated is None:
        db.rollback()
        if db.get(Service, service_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
        raise HTTPException(status.HTTP_409_CONFLICT, VERSION_CONFLICT_MESSAGE)
    db.execute(
        delete(ServiceStaff).where(ServiceStaff.service_id == service_id, ServiceStaff.user_id.not_in(body.staff_ids))
    )
    db.add_all(ServiceStaff(service_id=service_id, user_id=user_id) for user_id in added)
    db.commit()
    service = db.get(Service, service_id, populate_existing=True)
    logger.info("Servicio editado: id=%s por user_id=%s, versión %s", service.id, user.id, service.version)
    return _out(db, [service])[0]
