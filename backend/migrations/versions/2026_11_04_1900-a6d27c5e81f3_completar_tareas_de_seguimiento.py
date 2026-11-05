"""completar y editar tareas de seguimiento (T25)

Añade quién marcó la tarea y cuándo, la versión para el bloqueo optimista y un índice por
responsable para el panel de pendientes. Las tareas existentes quedan pendientes y en la versión 1.

Escrita a mano: autogenerate no compara las restricciones CHECK (T15). Las mismas reglas están en
app/models.py. Deshacerla pierde qué tareas estaban hechas: volverían a parecer pendientes.

Revision ID: a6d27c5e81f3
Revises: f4b19d7e3c58
Create Date: 2026-11-04 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6d27c5e81f3'
down_revision: Union[str, Sequence[str], None] = 'f4b19d7e3c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('follow_up_tasks', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('follow_up_tasks', sa.Column('completed_by_id', sa.Integer(), nullable=True))
    op.add_column('follow_up_tasks', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.create_foreign_key(
        op.f('fk_follow_up_tasks_completed_by_id_users'), 'follow_up_tasks', 'users',
        ['completed_by_id'], ['id'], ondelete='SET NULL',
    )
    op.create_check_constraint(op.f('ck_follow_up_tasks_version_positive'), 'follow_up_tasks', 'version >= 1')
    op.create_check_constraint(
        op.f('ck_follow_up_tasks_completed_by_with_time'), 'follow_up_tasks',
        'completed_by_id IS NULL OR completed_at IS NOT NULL',
    )
    op.create_index(op.f('ix_follow_up_tasks_assigned_to_id'), 'follow_up_tasks', ['assigned_to_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_follow_up_tasks_assigned_to_id'), table_name='follow_up_tasks')
    op.drop_constraint(op.f('ck_follow_up_tasks_completed_by_with_time'), 'follow_up_tasks', type_='check')
    op.drop_constraint(op.f('ck_follow_up_tasks_version_positive'), 'follow_up_tasks', type_='check')
    op.drop_constraint(op.f('fk_follow_up_tasks_completed_by_id_users'), 'follow_up_tasks', type_='foreignkey')
    op.drop_column('follow_up_tasks', 'version')
    op.drop_column('follow_up_tasks', 'completed_by_id')
    op.drop_column('follow_up_tasks', 'completed_at')
