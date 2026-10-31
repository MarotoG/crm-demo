"""Modelos de SQLAlchemy. Alembic compara estos modelos con la BD para generar migraciones."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, MetaData, String, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nombres de restricciones predecibles, para que las migraciones sean estables.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Service(Base):
    """Servicio que ofrece la clínica (p. ej. «Limpieza facial», 60 min).

    Primera tabla del CRM (T05): sin relaciones; las citas la referenciarán.
    """

    __tablename__ = "services"
    __table_args__ = (CheckConstraint("duration_minutes > 0", name="duration_minutes_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    duration_minutes: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True, server_default=true())


class Role(StrEnum):
    """Los cuatro roles del CRM (especificaciones, sección 5)."""

    ADMIN = "admin"
    RECEPTION = "reception"
    PROFESSIONAL = "professional"
    CLIENT = "client"


_ROLES_SQL = ", ".join(f"'{role.value}'" for role in Role)


class User(Base):
    """Cuenta de acceso de personal o de cliente (T07).

    El vínculo único con el contacto del cliente se añadirá cuando exista la tabla
    contacts; las cuentas de cliente reales se crearán por invitación (T21).
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({_ROLES_SQL})", name="role_valid"),
        # La BD también exige el email ya normalizado: dos mayúsculas distintas no
        # pueden colarse como cuentas diferentes aunque alguien salte la API.
        CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # Hash Argon2id en formato PHC ($argon2id$v=19$m=...); nunca la contraseña.
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True, server_default=true())
