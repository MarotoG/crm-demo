"""personas y reglas de los servicios (T15)

Quién realiza cada servicio (tabla service_staff), versión para el bloqueo optimista, nombre
único sin distinguir mayúsculas y las reglas de nombre y duración también en la BD.

Las restricciones CHECK se añaden a mano: autogenerate no las compara. Los dos servicios de
demo de T05 («Limpieza facial (demo)», 60; «Consulta inicial (demo)», 30) ya las cumplen.

Revision ID: ab6bf3465c84
Revises: 8de7aa393dac
Create Date: 2026-11-03 01:51:27.331743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab6bf3465c84'
down_revision: Union[str, Sequence[str], None] = '8de7aa393dac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('service_staff',
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], name=op.f('fk_service_staff_service_id_services'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_service_staff_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('service_id', 'user_id', name=op.f('pk_service_staff'))
    )
    op.create_index(op.f('ix_service_staff_user_id'), 'service_staff', ['user_id'], unique=False)
    op.add_column('services', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.create_index('uq_services_name', 'services', [sa.literal_column('lower(name)')], unique=True)
    # Añadido a mano: las mismas reglas que app/models.py.
    op.drop_constraint(op.f('ck_services_duration_minutes_positive'), 'services', type_='check')
    op.create_check_constraint(
        op.f('ck_services_duration_minutes_valid'), 'services',
        'duration_minutes BETWEEN 5 AND 240 AND duration_minutes % 5 = 0',
    )
    op.create_check_constraint(
        op.f('ck_services_name_normalized'), 'services',
        r"name = btrim(regexp_replace(name, '\s+', ' ', 'g')) AND name <> ''",
    )
    op.create_check_constraint(
        op.f('ck_services_name_ascii'), 'services', "name ~ '^[A-Za-z0-9][A-Za-z0-9 .,''&+/()-]*$'"
    )
    op.create_check_constraint(op.f('ck_services_version_positive'), 'services', 'version >= 1')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_services_version_positive'), 'services', type_='check')
    op.drop_constraint(op.f('ck_services_name_ascii'), 'services', type_='check')
    op.drop_constraint(op.f('ck_services_name_normalized'), 'services', type_='check')
    op.drop_constraint(op.f('ck_services_duration_minutes_valid'), 'services', type_='check')
    op.create_check_constraint(
        op.f('ck_services_duration_minutes_positive'), 'services', 'duration_minutes > 0'
    )
    op.drop_index('uq_services_name', table_name='services')
    op.drop_column('services', 'version')
    op.drop_index(op.f('ix_service_staff_user_id'), table_name='service_staff')
    op.drop_table('service_staff')
