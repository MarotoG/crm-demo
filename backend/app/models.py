"""Modelos de SQLAlchemy. Alembic compara estos modelos con la BD para generar migraciones."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, MetaData, String, func, text, true
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


class UserSession(Base):
    """Sesión de login guardada en BD (T08): la «pulsera con lista».

    La cookie lleva un token aleatorio; aquí solo se guarda su hash SHA-256, de modo
    que quien lea esta tabla no puede usar las sesiones. revoked_at lo usará el logout (T09).
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContactSource(StrEnum):
    """De dónde llegó el contacto (lista fija, decisión T11): permite contar por canal."""

    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    GOOGLE = "google"
    WEBSITE = "website"
    REFERRAL = "referral"
    WALK_IN = "walk_in"
    OTHER = "other"


class ContactStatus(StrEnum):
    """Estado comercial (T03): Nuevo → Contactado → Cita agendada → Cliente; Perdido desde cualquiera.

    T11 solo crea contactos en «new»; las transiciones llegan en T14.
    """

    NEW = "new"
    CONTACTED = "contacted"
    SCHEDULED = "scheduled"
    CLIENT = "client"
    LOST = "lost"


def _in_list(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


def _name_normalized(column: str) -> str:
    # Sin espacios en los extremos ni repetidos, y no vacío.
    return rf"{column} = btrim(regexp_replace({column}, '\s+', ' ', 'g')) AND {column} <> ''"


def _name_ascii(column: str) -> str:
    # Empieza por letra; después letras sin tilde, espacio, punto, apóstrofo ('' en SQL) o guion.
    return f"{column} ~ '^[A-Za-z][A-Za-z .''-]*$'"


class Contact(Base):
    """Ficha de una persona: lead y después cliente, sin duplicarla (T11).

    Sin datos clínicos (alergias, fecha de nacimiento, historia) ni notas libres.
    La BD repite las reglas de la API para que nadie las salte escribiendo directamente.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="email_or_phone"),
        CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
        # E.164: «+», prefijo de país sin 0 inicial y de 8 a 15 cifras en total.
        CheckConstraint(r"phone ~ '^\+[1-9][0-9]{7,14}$'", name="phone_e164"),
        CheckConstraint(_name_normalized("first_name"), name="first_name_normalized"),
        CheckConstraint(_name_normalized("last_name"), name="last_name_normalized"),
        # Sin tildes (T12b): la misma lista cerrada que app/validators.py.
        CheckConstraint(_name_ascii("first_name"), name="first_name_ascii"),
        CheckConstraint(_name_ascii("last_name"), name="last_name_ascii"),
        CheckConstraint("email ~ '^[!-~]+$'", name="email_ascii"),
        CheckConstraint(_in_list("source", ContactSource), name="source_valid"),
        CheckConstraint(_in_list("status", ContactStatus), name="status_valid"),
        # Duplicados (decisión T11): el email o el teléfono pueden repetirse (una familia),
        # pero no junto con el mismo nombre y apellidos, sin distinguir mayúsculas. Al ser
        # índices únicos de PostgreSQL, dos altas simultáneas no pueden pasar las dos.
        Index(
            "uq_contacts_name_email",
            func.lower(text("first_name")),
            func.lower(text("last_name")),
            text("email"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_contacts_name_phone",
            func.lower(text("first_name")),
            func.lower(text("last_name")),
            text("phone"),
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=ContactStatus.NEW, server_default=ContactStatus.NEW.value)
    # Si se borrara la cuenta de quien lo creó, el contacto se conserva.
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
