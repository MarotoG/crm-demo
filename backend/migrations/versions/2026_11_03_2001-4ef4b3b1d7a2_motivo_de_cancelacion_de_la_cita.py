"""motivo de cancelacion de la cita (T19)

Al cancelar una cita se elige un motivo de una lista cerrada (decisión T19) y, si se quiere, un
detalle corto: una línea de hasta 200 caracteres ASCII visibles, sin tildes (como los contactos,
T12b). Las CHECK obligan a que una cita esté cancelada si y solo si tiene motivo, y a que el
detalle solo exista junto a un motivo.

Escrita a mano: autogenerate añade las columnas, pero no compara las restricciones CHECK (T15).
La misma regla está en app/models.py. En crm_demo no hay citas canceladas (03/11/2026); si las
hubiera sin motivo, la migración fallaría sin cambiar nada.

Revision ID: 4ef4b3b1d7a2
Revises: 6974f0c1a56c
Create Date: 2026-11-03 20:01:40.718301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ef4b3b1d7a2'
down_revision: Union[str, Sequence[str], None] = '6974f0c1a56c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('appointments', sa.Column('cancel_reason', sa.String(length=20), nullable=True))
    op.add_column('appointments', sa.Column('cancel_note', sa.String(length=200), nullable=True))
    op.create_check_constraint(
        op.f('ck_appointments_cancel_reason_valid'),
        'appointments',
        "cancel_reason IN ('client_request', 'clinic', 'other')",
    )
    op.create_check_constraint(
        op.f('ck_appointments_cancelled_has_reason'),
        'appointments',
        "(status = 'cancelled') = (cancel_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f('ck_appointments_cancel_note_with_reason'),
        'appointments',
        'cancel_note IS NULL OR cancel_reason IS NOT NULL',
    )
    op.create_check_constraint(
        op.f('ck_appointments_cancel_note_normalized'),
        'appointments',
        r"cancel_note = btrim(regexp_replace(cancel_note, '\s+', ' ', 'g')) AND cancel_note <> ''",
    )
    op.create_check_constraint(
        op.f('ck_appointments_cancel_note_ascii'),
        'appointments',
        "cancel_note ~ '^[ -~]{1,200}$'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_appointments_cancel_note_ascii'), 'appointments', type_='check')
    op.drop_constraint(op.f('ck_appointments_cancel_note_normalized'), 'appointments', type_='check')
    op.drop_constraint(op.f('ck_appointments_cancel_note_with_reason'), 'appointments', type_='check')
    op.drop_constraint(op.f('ck_appointments_cancelled_has_reason'), 'appointments', type_='check')
    op.drop_constraint(op.f('ck_appointments_cancel_reason_valid'), 'appointments', type_='check')
    op.drop_column('appointments', 'cancel_note')
    op.drop_column('appointments', 'cancel_reason')
