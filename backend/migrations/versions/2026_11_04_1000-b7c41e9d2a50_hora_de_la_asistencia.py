"""hora de la asistencia (T20b)

Cuándo se marcó la asistencia de la cita (Realizada o No presentado) por primera vez. Sirve
para el plazo de corrección (decisión T20b: se puede cambiar entre Realizada y No presentado
durante 7 días desde que se marcó) y para saber cuándo se marcó. Corregirla no la cambia: si
no, cada corrección alargaría el plazo.

La CHECK obliga a que la tengan las citas marcadas y solo ellas. Escrita a mano: autogenerate
añade la columna, pero no compara las restricciones CHECK (T15). La misma regla está en
app/models.py. En crm_demo no hay citas (04/11/2026); si hubiera alguna marcada sin hora, la
migración fallaría sin cambiar nada.

Revision ID: b7c41e9d2a50
Revises: 4ef4b3b1d7a2
Create Date: 2026-11-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c41e9d2a50'
down_revision: Union[str, Sequence[str], None] = '4ef4b3b1d7a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('appointments', sa.Column('attended_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f('ck_appointments_attended_has_time'),
        'appointments',
        "(status IN ('completed', 'no_show')) = (attended_at IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_appointments_attended_has_time'), 'appointments', type_='check')
    op.drop_column('appointments', 'attended_at')
