"""invitaciones al portal y vínculo de la cuenta de cliente (T21)

La tabla portal_invitations guarda los enlaces de un solo uso (solo el hash del token), con como
mucho uno abierto por contacto. users.contact_id es el vínculo explícito y único entre una cuenta
de cliente y su contacto. Es opcional en la BD: la cuenta de demo ya existe sin contacto y la
vincula app.seed_demo, y una cuenta de cliente sin vínculo no tiene citas que ver.

Escrita a mano: autogenerate no compara las restricciones CHECK (T15). Las mismas reglas están en
app/models.py. Deshacerla borra las invitaciones y deja las cuentas de cliente sin vínculo.

Revision ID: c3e8a1f5d702
Revises: b7c41e9d2a50
Create Date: 2026-11-04 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e8a1f5d702'
down_revision: Union[str, Sequence[str], None] = 'b7c41e9d2a50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('contact_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_users_contact_id_contacts'), 'users', 'contacts', ['contact_id'], ['id'])
    op.create_unique_constraint(op.f('uq_users_contact_id'), 'users', ['contact_id'])
    op.create_check_constraint(
        op.f('ck_users_contact_only_for_client'), 'users', "contact_id IS NULL OR role = 'client'"
    )
    op.create_table(
        'portal_invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('used_at IS NULL OR revoked_at IS NULL', name=op.f('ck_portal_invitations_used_or_revoked')),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name=op.f('fk_portal_invitations_contact_id_contacts')),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'], name=op.f('fk_portal_invitations_created_by_id_users'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_portal_invitations')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_portal_invitations_token_hash')),
    )
    op.create_index(
        'uq_portal_invitations_contact_open',
        'portal_invitations',
        ['contact_id'],
        unique=True,
        postgresql_where=sa.text('used_at IS NULL AND revoked_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_portal_invitations_contact_open',
        table_name='portal_invitations',
        postgresql_where=sa.text('used_at IS NULL AND revoked_at IS NULL'),
    )
    op.drop_table('portal_invitations')
    op.drop_constraint(op.f('ck_users_contact_only_for_client'), 'users', type_='check')
    op.drop_constraint(op.f('uq_users_contact_id'), 'users', type_='unique')
    op.drop_constraint(op.f('fk_users_contact_id_contacts'), 'users', type_='foreignkey')
    op.drop_column('users', 'contact_id')
