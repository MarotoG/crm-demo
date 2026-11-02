"""Administración de usuarios (T09): por ahora solo la lista, y solo para el administrador."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import Role, User

router = APIRouter(prefix="/api/users", tags=["usuarios"])


class UserAdminOut(BaseModel):
    """Lo que ve el administrador de cada cuenta: nunca el hash."""

    id: int
    email: str
    role: str
    active: bool


@router.get("")
def list_users(
    _admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> list[UserAdminOut]:
    users = db.scalars(select(User).order_by(User.id))
    return [UserAdminOut(id=u.id, email=u.email, role=u.role, active=u.active) for u in users]
