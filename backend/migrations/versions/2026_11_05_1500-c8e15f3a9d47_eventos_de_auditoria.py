"""eventos de auditoría (T26)

Crea audit_events. Escrita a mano: autogenerate no compara las restricciones CHECK (T15). Las mismas
reglas están en app/models.py. Deshacerla pierde todos los eventos registrados.

Revision ID: c8e15f3a9d47
Revises: a6d27c5e81f3
Create Date: 2026-11-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e15f3a9d47'
down_revision: Union[str, Sequence[str], None] = 'a6d27c5e81f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIONS = (
    'login_succeeded', 'login_failed', 'logout',
    'contact_viewed', 'contact_created', 'contact_updated', 'contact_status_changed',
    'service_created', 'service_updated',
    'appointment_created', 'appointment_rescheduled', 'appointment_cancelled',
    'appointment_attendance_marked', 'appointment_note_edited',
    'invitation_created', 'invitation_accepted',
    'follow_up_created', 'follow_up_updated', 'follow_up_completed', 'follow_up_reopened',
)
TARGETS = ('contact', 'service', 'appointment', 'follow_up', 'user')


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('target_type', sa.String(length=20), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('changed_fields', sa.String(length=200), nullable=True),
        sa.Column('from_status', sa.String(length=20), nullable=True),
        sa.Column('to_status', sa.String(length=20), nullable=True),
        sa.CheckConstraint(_in_list('action', ACTIONS), name=op.f('ck_audit_events_action_valid')),
        sa.CheckConstraint(_in_list('target_type', TARGETS), name=op.f('ck_audit_events_target_type_valid')),
        sa.CheckConstraint('(target_type IS NULL) = (target_id IS NULL)', name=op.f('ck_audit_events_target_complete')),
        sa.CheckConstraint("changed_fields ~ '^[a-z_]+(, [a-z_]+)*$'", name=op.f('ck_audit_events_changed_fields_names')),
        sa.CheckConstraint("from_status ~ '^[a-z_]+$'", name=op.f('ck_audit_events_from_status_name')),
        sa.CheckConstraint("to_status ~ '^[a-z_]+$'", name=op.f('ck_audit_events_to_status_name')),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_events_actor_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events')),
    )
    op.create_index(op.f('ix_audit_events_actor_id'), 'audit_events', ['actor_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_audit_events_actor_id'), table_name='audit_events')
    op.drop_table('audit_events')
