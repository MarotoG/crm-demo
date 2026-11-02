"""Contactos: alta (T11) y lista con búsqueda (T12), para administración y recepción.

El profesional verá solo los contactos con alguna cita con él cuando existan las citas;
hasta entonces recibe 403, igual que el cliente.
"""

import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import ColumnElement, func, or_, select
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


class ContactOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    source: str
    status: str
    created_at: datetime


class ContactList(BaseModel):
    """Una página de resultados: `total` cuenta todos los que cumplen la búsqueda."""

    total: int
    items: list[ContactOut]


def _search_condition(q: str) -> ColumnElement[bool]:
    """Coincidencia parcial en nombre y apellidos (en cualquier orden), email o teléfono.

    Sin distinguir mayúsculas ni tildes (unaccent, migración dc66ba7eb339). El texto va como
    parámetro, nunca pegado al SQL; % y _ se escapan para que se busquen literalmente.
    """
    escaped = re.sub(r"([\\%_])", r"\\\1", q)
    pattern = func.unaccent(f"%{escaped}%")
    conditions = [
        func.unaccent(Contact.first_name + " " + Contact.last_name).ilike(pattern, escape="\\"),
        func.unaccent(Contact.last_name + " " + Contact.first_name).ilike(pattern, escape="\\"),
        func.unaccent(Contact.email).ilike(pattern, escape="\\"),
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
    # Espacios de más fuera, como al guardar. La tilde suelta («e» + tilde) ya la quita unaccent.
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
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint in DUPLICATE_MESSAGES:
            raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_MESSAGES[constraint]) from None
        raise
    db.refresh(contact)
    logger.info("Contacto creado: id=%s por user_id=%s", contact.id, user.id)
    return ContactOut.model_validate(contact, from_attributes=True)
