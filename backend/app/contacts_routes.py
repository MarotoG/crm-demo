"""Contactos: alta (T11), lista con búsqueda (T12) y ficha con edición (T13), para
administración y recepción.

El profesional verá solo los contactos con alguna cita con él cuando existan las citas;
hasta entonces recibe 403, igual que el cliente.
"""

import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_csrf, require_roles
from app.db import get_db
from app.models import Contact, ContactSource, Role, User
from app.validators import normalize_contact_email, normalize_name, normalize_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["contactos"])

# Qué regla de duplicados ha saltado, según el índice único de PostgreSQL.
DUPLICATE_MESSAGES = {
    "uq_contacts_name_email": "Ya existe un contacto con ese nombre, apellidos y email",
    "uq_contacts_name_phone": "Ya existe un contacto con ese nombre, apellidos y teléfono",
}
VERSION_CONFLICT_MESSAGE = "Otra persona ha cambiado esta ficha mientras la editabas"
NOT_FOUND_MESSAGE = "Contacto no encontrado"

# Lista (decisión T12): los 20 más recientes que cumplan la búsqueda, más el total.
LIST_LIMIT = 20
MAX_SEARCH_LENGTH = 100
# Con menos cifras, buscar «1» o «55» en los teléfonos devolvería casi todo.
MIN_PHONE_DIGITS = 3


def _user_message(normalize: Callable[[str], str]) -> Callable[[str], str]:
    """Convierte el ValueError de un validador en un error de Pydantic con el mensaje tal cual."""

    def validator(value: str) -> str:
        try:
            return normalize(value)
        except ValueError as error:
            raise PydanticCustomError("dato_no_valido", str(error)) from None

    return validator


class ContactCreate(BaseModel):
    # extra="forbid": el navegador no puede fijar el estado, el autor ni las fechas.
    model_config = ConfigDict(extra="forbid")

    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    source: ContactSource

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, value: str) -> str:
        return _user_message(lambda v: normalize_name(v, "nombre"))(value)

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, value: str) -> str:
        return _user_message(lambda v: normalize_name(v, "apellido"))(value)

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        # Un campo vacío del formulario equivale a no darlo.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else _user_message(normalize_contact_email)(value)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return None if value is None else _user_message(normalize_phone)(value)

    @model_validator(mode="after")
    def _email_or_phone(self) -> "ContactCreate":
        if self.email is None and self.phone is None:
            raise PydanticCustomError("falta_contacto", "Indica al menos un email o un teléfono")
        return self


class ContactUpdate(ContactCreate):
    """Edición (T13): la ficha entera (PUT) con las mismas reglas que el alta, más la versión
    que se leyó. El estado y el responsable se cambian en T14; el autor y las fechas, nunca."""

    version: int = Field(ge=1)


class ContactOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    source: str
    status: str
    created_at: datetime


class ContactDetail(ContactOut):
    """La ficha (T13): además, la versión para editar y quién creó y cambió por última vez."""

    version: int
    updated_at: datetime
    created_by_email: str | None
    updated_by_email: str | None


def _detail(db: Session, contact: Contact) -> ContactDetail:
    def email_of(user_id: int | None) -> str | None:
        # None si no consta o si esa cuenta se borró (ON DELETE SET NULL).
        user = db.get(User, user_id) if user_id is not None else None
        return user.email if user else None

    return ContactDetail(
        **ContactOut.model_validate(contact, from_attributes=True).model_dump(),
        version=contact.version,
        updated_at=contact.updated_at,
        created_by_email=email_of(contact.created_by_id),
        updated_by_email=email_of(contact.updated_by_id),
    )


def _duplicate_or_raise(error: IntegrityError) -> HTTPException:
    """409 si ha saltado un índice de duplicados; cualquier otro error de integridad sigue su curso."""
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint in DUPLICATE_MESSAGES:
        return HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_MESSAGES[constraint])
    raise error


class ContactList(BaseModel):
    """Una página de resultados: `total` cuenta todos los que cumplen la búsqueda."""

    total: int
    items: list[ContactOut]


def _search_condition(q: str) -> ColumnElement[bool]:
    """Coincidencia parcial en nombre y apellidos (en cualquier orden), email o teléfono.

    Sin distinguir mayúsculas (ILIKE). Los datos no llevan tildes (T12b): una búsqueda con
    tilde no encuentra nada y la interfaz avisa. El texto va como parámetro, nunca pegado
    al SQL; % y _ se escapan para que se busquen literalmente.
    """
    escaped = re.sub(r"([\\%_])", r"\\\1", q)
    pattern = f"%{escaped}%"
    conditions = [
        (Contact.first_name + " " + Contact.last_name).ilike(pattern, escape="\\"),
        (Contact.last_name + " " + Contact.first_name).ilike(pattern, escape="\\"),
        Contact.email.ilike(pattern, escape="\\"),
    ]
    # Teléfono: solo las cifras, para que «(212) 555» encuentre +12125550123.
    digits = "".join(c for c in q if c.isascii() and c.isdigit())
    if len(digits) >= MIN_PHONE_DIGITS:
        conditions.append(Contact.phone.contains(digits, autoescape=True))
    return or_(*conditions)


@router.get("")
def list_contacts(
    _user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
    q: Annotated[str, Query(max_length=MAX_SEARCH_LENGTH)] = "",
) -> ContactList:
    # Espacios de más fuera, como al guardar.
    q = " ".join(q.split())
    query = select(Contact)
    if q:
        query = query.where(_search_condition(q))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    contacts = db.scalars(query.order_by(Contact.created_at.desc(), Contact.id.desc()).limit(LIST_LIMIT))
    return ContactList(total=total, items=[ContactOut.model_validate(c, from_attributes=True) for c in contacts])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={409: {"description": "Ya existe un contacto con ese nombre y el mismo email o teléfono"}},
)
def create_contact(
    body: ContactCreate,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> ContactOut:
    contact = Contact(**body.model_dump(), created_by_id=user.id)
    db.add(contact)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _duplicate_or_raise(error) from None
    db.refresh(contact)
    logger.info("Contacto creado: id=%s por user_id=%s", contact.id, user.id)
    return ContactOut.model_validate(contact, from_attributes=True)


@router.get("/{contact_id}", responses={404: {"description": "Contacto no encontrado"}})
def get_contact(
    contact_id: int,
    _user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> ContactDetail:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    return _detail(db, contact)


@router.put(
    "/{contact_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "Contacto no encontrado"},
        409: {"description": "Otra persona guardó antes (versión distinta) o la edición crea un duplicado"},
    },
)
def update_contact(
    contact_id: int,
    body: ContactUpdate,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
) -> ContactDetail:
    # Bloqueo optimista en una sola sentencia: solo se actualiza si la versión sigue siendo la
    # que leyó quien edita. Con dos ediciones a la vez, PostgreSQL bloquea la fila: la segunda
    # espera, vuelve a mirar la versión (ya subida) y no actualiza nada.
    statement = (
        update(Contact)
        .where(Contact.id == contact_id, Contact.version == body.version)
        .values(
            **body.model_dump(exclude={"version"}),
            version=Contact.version + 1,
            updated_by_id=user.id,
            updated_at=func.now(),
        )
        .returning(Contact.id)
    )
    try:
        updated = db.execute(statement).scalar_one_or_none()
    except IntegrityError as error:
        db.rollback()
        raise _duplicate_or_raise(error) from None
    if updated is None:
        db.rollback()
        if db.get(Contact, contact_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
        raise HTTPException(status.HTTP_409_CONFLICT, VERSION_CONFLICT_MESSAGE)
    db.commit()
    contact = db.get(Contact, contact_id, populate_existing=True)
    logger.info("Contacto editado: id=%s por user_id=%s, versión %s", contact.id, user.id, contact.version)
    return _detail(db, contact)
