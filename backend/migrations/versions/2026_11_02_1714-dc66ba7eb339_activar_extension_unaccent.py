"""activar extension unaccent

Revision ID: dc66ba7eb339
Revises: 56c932d1ef68
Create Date: 2026-11-02 17:14:38.927883

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc66ba7eb339'
down_revision: Union[str, Sequence[str], None] = '56c932d1ef68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    unaccent (T12) permite buscar «jose» y encontrar «José». Viene con PostgreSQL
    (no es una dependencia nueva) y es una extensión «de confianza»: basta con ser
    dueño de la base de datos, no superusuario.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS unaccent")
