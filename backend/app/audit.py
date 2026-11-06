"""Registrar eventos de auditoría (T26).

Cada ruta llama a `record` antes de su commit: el evento y la acción se guardan en la misma
transacción, los dos o ninguno. Una acción sin rastro no llega a confirmarse, y un error después no
deja un evento de algo que no pasó.

Solo admite nombres de campos y estados, no valores: ver AuditEvent en app/models.py.
"""

from collections.abc import Iterable, Mapping

from sqlalchemy.orm import Session

from app.models import AuditAction, AuditEvent, AuditTarget, Contact, User


def record(
    db: Session,
    action: AuditAction,
    actor: User | None = None,
    target: tuple[AuditTarget, int] | None = None,
    fields: Iterable[str] = (),
    from_status: str | None = None,
    to_status: str | None = None,
) -> None:
    target_type, target_id = target if target else (None, None)
    db.add(
        AuditEvent(
            action=action,
            actor_id=actor.id if actor else None,
            target_type=target_type,
            target_id=target_id,
            changed_fields=", ".join(sorted(fields)) or None,
            from_status=from_status,
            to_status=to_status,
        )
    )


def changed_fields(current: object, new_values: Mapping[str, object]) -> list[str]:
    """Los nombres de los campos que cambian. Hay que llamarla antes del UPDATE."""
    return [name for name, value in new_values.items() if getattr(current, name) != value]


def record_contact_status(db: Session, actor: User, contact: Contact, before: str) -> None:
    """El estado del contacto que cambia como efecto de una cita. Sin cambio, no registra nada."""
    if contact.status != before:
        record(
            db,
            AuditAction.CONTACT_STATUS_CHANGED,
            actor,
            (AuditTarget.CONTACT, contact.id),
            from_status=before,
            to_status=contact.status,
        )
