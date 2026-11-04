"""tareas de seguimiento (T24)

La tabla follow_up_tasks guarda las tareas de un contacto, con responsable y fecha prevista.

Escrita a mano: autogenerate no compara las restricciones CHECK (T15). Las mismas reglas están en
app/models.py. Deshacerla borra las tareas.

Revision ID: f4b19d7e3c58
Revises: e7a2c9d41b36
Create Date: 2026-11-04 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4b19d7e3c58'
down_revision: Union[str, Sequence[str], None] = 'e7a2c9d41b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'follow_up_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        sa.Column('assigned_to_id', sa.Integer(), nullable=False),
        sa.Column('due_on', sa.Date(), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            r"description = btrim(regexp_replace(description, '\s+', ' ', 'g')) AND description <> ''",
            name=op.f('ck_follow_up_tasks_description_normalized'),
        ),
        sa.CheckConstraint("description ~ '^[ -~]{1,200}$'", name=op.f('ck_follow_up_tasks_description_ascii')),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name=op.f('fk_follow_up_tasks_contact_id_contacts')),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], name=op.f('fk_follow_up_tasks_assigned_to_id_users')),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'], name=op.f('fk_follow_up_tasks_created_by_id_users'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_follow_up_tasks')),
    )
    op.create_index(op.f('ix_follow_up_tasks_contact_id'), 'follow_up_tasks', ['contact_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_follow_up_tasks_contact_id'), table_name='follow_up_tasks')
    op.drop_table('follow_up_tasks')
