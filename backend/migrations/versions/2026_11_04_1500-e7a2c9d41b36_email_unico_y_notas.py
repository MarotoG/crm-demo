"""email obligatorio y único por contacto, teléfono único y notas (T21b)

Una persona, un contacto (decisión T21b). Sustituye a los índices de T11, que dejaban repetir el
email o el teléfono con otro nombre. Añade la nota corta de la ficha y la de la cita.

Escrita a mano: autogenerate no compara las restricciones CHECK (T15). Las mismas reglas están en
app/models.py. Si hay contactos sin email o con el email o el teléfono repetidos, la migración falla
sin cambiar nada: hay que corregirlos antes. Deshacerla borra las notas.

Revision ID: e7a2c9d41b36
Revises: c3e8a1f5d702
Create Date: 2026-11-04 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a2c9d41b36'
down_revision: Union[str, Sequence[str], None] = 'c3e8a1f5d702'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTE_NORMALIZED = r"note = btrim(regexp_replace(note, '\s+', ' ', 'g')) AND note <> ''"
NOTE_ASCII = "note ~ '^[ -~]{1,200}$'"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('uq_contacts_name_email', table_name='contacts', postgresql_where=sa.text('email IS NOT NULL'))
    op.drop_index('uq_contacts_name_phone', table_name='contacts', postgresql_where=sa.text('phone IS NOT NULL'))
    op.drop_constraint(op.f('ck_contacts_email_or_phone'), 'contacts', type_='check')
    op.alter_column('contacts', 'email', existing_type=sa.String(length=254), nullable=False)
    op.create_unique_constraint(op.f('uq_contacts_email'), 'contacts', ['email'])
    op.create_unique_constraint(op.f('uq_contacts_phone'), 'contacts', ['phone'])
    for table in ('contacts', 'appointments'):
        op.add_column(table, sa.Column('note', sa.String(length=200), nullable=True))
        op.create_check_constraint(op.f(f'ck_{table}_note_normalized'), table, NOTE_NORMALIZED)
        op.create_check_constraint(op.f(f'ck_{table}_note_ascii'), table, NOTE_ASCII)


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('contacts', 'appointments'):
        op.drop_constraint(op.f(f'ck_{table}_note_ascii'), table, type_='check')
        op.drop_constraint(op.f(f'ck_{table}_note_normalized'), table, type_='check')
        op.drop_column(table, 'note')
    op.drop_constraint(op.f('uq_contacts_phone'), 'contacts', type_='unique')
    op.drop_constraint(op.f('uq_contacts_email'), 'contacts', type_='unique')
    op.alter_column('contacts', 'email', existing_type=sa.String(length=254), nullable=True)
    op.create_check_constraint(op.f('ck_contacts_email_or_phone'), 'contacts', 'email IS NOT NULL OR phone IS NOT NULL')
    op.create_index(
        'uq_contacts_name_email',
        'contacts',
        [sa.literal_column('lower(first_name)'), sa.literal_column('lower(last_name)'), sa.literal_column('email')],
        unique=True,
        postgresql_where=sa.text('email IS NOT NULL'),
    )
    op.create_index(
        'uq_contacts_name_phone',
        'contacts',
        [sa.literal_column('lower(first_name)'), sa.literal_column('lower(last_name)'), sa.literal_column('phone')],
        unique=True,
        postgresql_where=sa.text('phone IS NOT NULL'),
    )
