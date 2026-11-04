"""Invitación al portal y cuenta de cliente (T21).

Recorrido: admin o recepción generan desde la ficha un enlace para un contacto y lo envían a mano
(WhatsApp). El cliente lo abre, elige email y contraseña, y nace su cuenta, siempre de rol cliente
y vinculada a ese contacto: el vínculo sale de la invitación, nunca de lo que escriba el navegador.

Las dos rutas públicas no llevan sesión ni CSRF: lo que autoriza es el propio token, secreto y
aleatorio. Va en el cuerpo y no en la dirección, para que no acabe en los logs de un proxy.
"""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.appointments_routes import get_now
from app.auth import hash_token, require_csrf, require_roles
from app.db import get_db
from app.errors import user_message
from app.models import Contact, ContactStatus, PortalInvitation, Role, User
from app.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password
from app.validators import normalize_contact_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["portal"])

INVITATION_DURATION = timedelta(hours=24)  # decisión T21
MAX_TOKEN_LENGTH = 128

CONTACT_NOT_FOUND_MESSAGE = "Contacto no encontrado"
CONTACT_LOST_MESSAGE = "El contacto está «Perdido»: reábrelo antes de invitarlo"
HAS_ACCOUNT_MESSAGE = "Este contacto ya tiene cuenta en el portal"
# El mismo mensaje en todos los casos: quien tenga un enlace no averigua por qué dejó de valer.
INVALID_LINK_MESSAGE = "Este enlace no es válido o ha caducado. Pide uno nuevo a la clínica."
EMAIL_TAKEN_MESSAGE = "Ese email ya está en uso: escribe otro"
PASSWORD_LENGTH_MESSAGE = f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres"


class PortalStatus(BaseModel):
    """Lo que ve el personal en la ficha: nunca el enlace ni el email de acceso del cliente."""

    has_account: bool
    invitation_expires_at: datetime | None


class InvitationOut(BaseModel):
    """El token en claro: solo existe en esta respuesta (en la BD queda su hash)."""

    token: str
    expires_at: datetime


class InvitationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: StrictStr = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)


class InvitationAccept(InvitationToken):
    # extra="forbid": el navegador no fija el rol ni el contacto de la cuenta.
    email: str
    password: StrictStr

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return user_message(normalize_contact_email)(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
            raise PydanticCustomError("dato_no_valido", PASSWORD_LENGTH_MESSAGE)
        return value


def _lock_contact(db: Session, contact_id: int) -> Contact | None:
    return db.scalars(
        select(Contact).where(Contact.id == contact_id).with_for_update().execution_options(populate_existing=True)
    ).one_or_none()


def _has_account(db: Session, contact_id: int) -> bool:
    return db.scalar(select(select(User.id).where(User.contact_id == contact_id).exists()))


def _open_invitation_filter(contact_id: int) -> tuple:
    return (
        PortalInvitation.contact_id == contact_id,
        PortalInvitation.used_at.is_(None),
        PortalInvitation.revoked_at.is_(None),
    )


@router.get(
    "/api/contacts/{contact_id}/portal",
    responses={404: {"description": "Contacto no encontrado"}},
)
def portal_status(
    contact_id: int,
    _user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PortalStatus:
    """Si el contacto ya tiene cuenta y hasta cuándo vale el enlace abierto, si hay uno."""
    if db.get(Contact, contact_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CONTACT_NOT_FOUND_MESSAGE)
    expires_at = db.scalar(
        select(PortalInvitation.expires_at).where(
            *_open_invitation_filter(contact_id), PortalInvitation.expires_at > now
        )
    )
    return PortalStatus(has_account=_has_account(db, contact_id), invitation_expires_at=expires_at)


@router.post(
    "/api/contacts/{contact_id}/portal-invitation",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        404: {"description": "Contacto no encontrado"},
        409: {"description": "El contacto está Perdido o ya tiene cuenta"},
    },
)
def create_invitation(
    contact_id: int,
    user: User = Depends(require_roles(Role.ADMIN, Role.RECEPTION)),
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> InvitationOut:
    """Genera el enlace de un contacto, con o sin citas (decisión T21), y anula el anterior.

    El contacto queda bloqueado hasta el commit: dos invitaciones a la vez se esperan, y solo la
    última sigue abierta. Invitar no cambia la ficha: ni su estado ni su versión.
    """
    contact = _lock_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CONTACT_NOT_FOUND_MESSAGE)
    if contact.status == ContactStatus.LOST:
        raise HTTPException(status.HTTP_409_CONFLICT, CONTACT_LOST_MESSAGE)
    if _has_account(db, contact_id):
        raise HTTPException(status.HTTP_409_CONFLICT, HAS_ACCOUNT_MESSAGE)
    db.execute(update(PortalInvitation).where(*_open_invitation_filter(contact_id)).values(revoked_at=now))
    token = secrets.token_urlsafe(32)
    expires_at = now + INVITATION_DURATION
    db.add(
        PortalInvitation(token_hash=hash_token(token), contact_id=contact_id, created_by_id=user.id, expires_at=expires_at)
    )
    db.commit()
    logger.info("Invitación al portal: contacto=%s por user_id=%s", contact_id, user.id)
    return InvitationOut(token=token, expires_at=expires_at)


def _valid_invitation(db: Session, token: str, now: datetime) -> PortalInvitation:
    """La invitación del token y su contacto, bloqueados en este orden; si no vale, 410.

    Con el bloqueo, dos usos a la vez del mismo enlace se esperan y el segundo ya lo ve gastado.
    """
    invalid = HTTPException(status.HTTP_410_GONE, INVALID_LINK_MESSAGE)
    token_hash = hash_token(token)
    contact_id = db.scalar(select(PortalInvitation.contact_id).where(PortalInvitation.token_hash == token_hash))
    if contact_id is None:
        raise invalid
    contact = _lock_contact(db, contact_id)
    invitation = db.scalars(
        select(PortalInvitation)
        .where(PortalInvitation.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if (
        invitation.used_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= now
        or contact.status == ContactStatus.LOST
    ):
        raise invalid
    return invitation


@router.post(
    "/api/portal-invitations/check",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={410: {"description": "El enlace no es válido, caducó o ya se usó"}},
)
def check_invitation(body: InvitationToken, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> None:
    """Pública: para decir que el enlace no vale antes de que se rellene el formulario. No revela
    datos del contacto: un enlace reenviado no descubre a quién pertenece."""
    _valid_invitation(db, body.token, now)


@router.post(
    "/api/portal-invitations/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"description": "Ese email ya está en uso"},
        410: {"description": "El enlace no es válido, caducó o ya se usó"},
        422: {"description": "Email o contraseña no válidos"},
    },
)
def accept_invitation(body: InvitationAccept, db: Session = Depends(get_db), now: datetime = Depends(get_now)) -> None:
    """Pública: crea la cuenta de cliente y gasta el enlace, las dos cosas o ninguna.

    El token se comprueba antes de calcular el hash: Argon2id es caro y sin un enlace válido no se
    gasta. Si el email está en uso, el enlace sigue valiendo para escribir otro.
    """
    invitation = _valid_invitation(db, body.token, now)
    invitation.used_at = now
    user = User(
        email=body.email, password_hash=hash_password(body.password), role=Role.CLIENT, contact_id=invitation.contact_id
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_users_email":
            raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN_MESSAGE) from None
        raise
    logger.info("Cuenta de cliente creada: user_id=%s contacto=%s", user.id, invitation.contact_id)
