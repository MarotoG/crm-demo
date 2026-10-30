"""Modelos de SQLAlchemy. Alembic compara estos modelos con la BD para generar migraciones."""

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
