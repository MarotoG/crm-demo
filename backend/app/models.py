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

    Todo contacto nace en «new». Las transiciones a mano están en app/contacts_routes.py (T14);
    «scheduled» lo pone crear una cita (T16) y «client» lo pondrá marcar Realizada la primera.
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
        CheckConstraint("version >= 1", name="version_positive"),
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
    # Quién hizo el último cambio (T13); el historial completo llegará con la auditoría.
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Bloqueo optimista (T13): cada edición la sube en 1; quien edita envía la que leyó y,
    # si ya no coincide, otra persona guardó antes (409).
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    # Responsable (T14): quien lleva el contacto en la clínica (recepción o admin); por
    # defecto quien lo crea. Puede quedar sin responsable; si se borrara su cuenta, también.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class Service(Base):
    """Servicio que ofrece la clínica (p. ej. «Facial cleansing», 60 min).

    Primera tabla del CRM (T05). Desde T15 la gestionan administración y recepción: nombre,
    duración, quién lo realiza y si está activo. No se borra nunca: desactivado deja de
    ofrecerse para citas nuevas sin perder el historial. Las citas guardarán su propia duración.
    """

    __tablename__ = "services"
    __table_args__ = (
        # Duración (decisión T15): múltiplos de 5 minutos, hasta 4 horas.
        CheckConstraint(
            "duration_minutes BETWEEN 5 AND 240 AND duration_minutes % 5 = 0", name="duration_minutes_valid"
        ),
        CheckConstraint(_name_normalized("name"), name="name_normalized"),
        # La misma lista cerrada que app/validators.py (sin tildes, como los contactos).
        CheckConstraint("name ~ '^[A-Za-z0-9][A-Za-z0-9 .,''&+/()-]*$'", name="name_ascii"),
        CheckConstraint("version >= 1", name="version_positive"),
        # Dos servicios no se llaman igual, sin distinguir mayúsculas (tampoco con uno desactivado).
        Index("uq_services_name", func.lower(text("name")), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    duration_minutes: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Bloqueo optimista, como en los contactos (T13): admin y recepción pueden editar a la vez.
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class ServiceStaff(Base):
    """Quién realiza cada servicio (T15): una o varias cuentas internas por servicio.

    Al crear una cita (T16) solo se podrá elegir a una de estas personas. Que sean cuentas
    internas activas lo comprueba la API; si se borrara una cuenta, deja de figurar.
    """

    __tablename__ = "service_staff"

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)


class AppointmentStatus(StrEnum):
    """Estados de una cita (T03): Programada, Realizada, No presentado, Cancelada.

    Toda cita nace «scheduled» (T16). Solo «cancelled» liberará la franja (T17); marcar
    «completed» la primera cita pasará el contacto a Cliente (llegará con la asistencia).
    """

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class Appointment(Base):
    """Cita de un contacto para un servicio con una de las personas que lo realizan (T16).

    Guarda su propia duración, copiada del servicio al crearla: cambiar después el servicio no
    reescribe las citas ya dadas. Inicio y fin son instantes (timestamptz); la zona de la
    clínica solo se usa para leerlos y escribirlos. Sin notas libres por ahora (decisión T16).
    """

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(_in_list("status", AppointmentStatus), name="status_valid"),
        # La misma regla que los servicios (T15): la duración copiada siempre la cumple.
        CheckConstraint(
            "duration_minutes BETWEEN 5 AND 240 AND duration_minutes % 5 = 0", name="duration_minutes_valid"
        ),
        # El fin no es un dato aparte: es el inicio más la duración (y por tanto posterior).
        CheckConstraint("ends_at = starts_at + duration_minutes * interval '1 minute'", name="ends_at_consistent"),
        CheckConstraint("version >= 1", name="version_positive"),
        # La agenda de cada persona por fecha (T18) y, en T17, la regla de solapamientos.
        Index("ix_appointments_staff_id_starts_at", "staff_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Sin ON DELETE: contactos, servicios y cuentas no se borran (se desactivan o pasan a
    # Perdido); si alguien lo intentara con citas, la BD lo impide y el historial se conserva.
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    # Quién la realiza: una de las personas del servicio al crearla. Puede ser admin, recepción o
    # profesional (T15), por eso no se llama professional_id como en el modelo de T03.
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int]
    status: Mapped[str] = mapped_column(
        String(20), default=AppointmentStatus.SCHEDULED, server_default=AppointmentStatus.SCHEDULED.value
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Bloqueo optimista desde el principio, para reprogramar y cancelar (T19) como en T13.
    version: Mapped[int] = mapped_column(default=1, server_default="1")
