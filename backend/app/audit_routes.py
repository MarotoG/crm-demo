"""Consulta de los eventos de auditoría (T26): solo para administración y solo lectura.

No hay rutas para cambiar ni borrar eventos, pero eso no los hace inmutables: ver AuditEvent en
app/models.py.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.auth import require_roles
from app.db import get_db
from app.models import AuditAction, AuditEvent, AuditTarget, Role, User

router = APIRouter(prefix="/api/audit-events", tags=["auditoría"])

PAGE_SIZE = 50


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    actor_email: str | None  # None en un login fallido: nadie ha demostrado quién es
    action: str
    target_type: str | None
    target_id: int | None
    target_email: str | None  # solo si el objetivo es una cuenta: su id no le dice nada a nadie
    changed_fields: list[str]
    from_status: str | None
    to_status: str | None


class AuditEventList(BaseModel):
    """Una página, del más reciente al más antiguo; `total` cuenta todos los que cumplen el filtro."""

    total: int
    page_size: int
    items: list[AuditEventOut]


@router.get("")
def list_audit_events(
    actor_id: int | None = None,
    action: AuditAction | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    _admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
) -> AuditEventList:
    conditions = []
    if actor_id is not None:
        conditions.append(AuditEvent.actor_id == actor_id)
    if action is not None:
        conditions.append(AuditEvent.action == action)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions))
    actor = aliased(User)
    target_user = aliased(User)
    rows = db.execute(
        select(AuditEvent, actor.email, target_user.email)
        .outerjoin(actor, actor.id == AuditEvent.actor_id)
        .outerjoin(
            target_user, and_(AuditEvent.target_type == AuditTarget.USER, target_user.id == AuditEvent.target_id)
        )
        .where(*conditions)
        .order_by(AuditEvent.id.desc())
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    )
    return AuditEventList(
        total=total,
        page_size=PAGE_SIZE,
        items=[
            AuditEventOut(
                id=event.id,
                occurred_at=event.occurred_at,
                actor_email=actor_email,
                action=event.action,
                target_type=event.target_type,
                target_id=event.target_id,
                target_email=target_email,
                changed_fields=event.changed_fields.split(", ") if event.changed_fields else [],
                from_status=event.from_status,
                to_status=event.to_status,
            )
            for event, actor_email, target_email in rows
        ],
    )
