"""citas sin solapamientos por persona (T17)

Restricción de exclusión: la misma persona (staff_id) no puede tener dos citas cuyos intervalos
[inicio, fin) se pisen, salvo que alguna esté cancelada. La comprueba PostgreSQL en cada alta o
cambio, así que dos peticiones simultáneas no pueden guardar las dos.

Necesita btree_gist (para combinar «=» sobre un entero con «&&» sobre un rango en el mismo índice
GiST). Viene con PostgreSQL y es una extensión «de confianza»: basta con ser dueño de la base de
datos, no superusuario (como unaccent en dc66ba7eb339).

Escrita a mano: autogenerate no compara restricciones de exclusión. La misma regla está en
app/models.py. Si ya hubiera citas solapadas, la migración fallaría sin cambiar nada; en
crm_demo no hay ninguna (03/11/2026).

Revision ID: 6974f0c1a56c
Revises: 31c5cec120a4
Create Date: 2026-11-03 15:08:31.657839

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6974f0c1a56c'
down_revision: Union[str, Sequence[str], None] = '31c5cec120a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE appointments ADD CONSTRAINT ex_appointments_staff_overlap "
        "EXCLUDE USING gist (staff_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) "
        "WHERE (status <> 'cancelled')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE appointments DROP CONSTRAINT ex_appointments_staff_overlap")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
