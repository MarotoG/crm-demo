"""contactos sin tildes y sin unaccent

Revision ID: 81885f19fa14
Revises: dc66ba7eb339
Create Date: 2026-11-02 18:05:21.174338

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81885f19fa14'
down_revision: Union[str, Sequence[str], None] = 'dc66ba7eb339'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_ASCII = "{column} ~ '^[A-Za-z][A-Za-z .''-]*$'"
EMAIL_ASCII = "email ~ '^[!-~]+$'"


def upgrade() -> None:
    """Upgrade schema.

    T12b: el MVP no admite tildes en nombres ni emails (clínicas de EE. UU.). La BD repite
    la regla de app/validators.py y deja de necesitar unaccent (activada en dc66ba7eb339).
    Si ya hubiera filas con tildes, la migración fallaría en vez de dejarlas inconsistentes.
    """
    op.create_check_constraint(op.f("ck_contacts_first_name_ascii"), "contacts", NAME_ASCII.format(column="first_name"))
    op.create_check_constraint(op.f("ck_contacts_last_name_ascii"), "contacts", NAME_ASCII.format(column="last_name"))
    op.create_check_constraint(op.f("ck_contacts_email_ascii"), "contacts", EMAIL_ASCII)
    op.execute("DROP EXTENSION IF EXISTS unaccent")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.drop_constraint(op.f("ck_contacts_email_ascii"), "contacts", type_="check")
    op.drop_constraint(op.f("ck_contacts_last_name_ascii"), "contacts", type_="check")
    op.drop_constraint(op.f("ck_contacts_first_name_ascii"), "contacts", type_="check")
