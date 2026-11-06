"""Crea o actualiza las cuentas de demo, una por rol (T07), y datos ficticios para enseñar (T27).

Uso, desde backend/ y con la BD migrada:
    .venv\\Scripts\\python.exe -m app.seed_demo

Las contraseñas no están en el código: se leen de CRM_DEMO_PASSWORD_<ROL> en el
.env de la raíz (no versionado). Es idempotente: crea las cuentas que falten y, en
las existentes, aplica la contraseña actual del .env, el rol y las reactiva. La cuenta de
cliente queda vinculada a un contacto ficticio, que se crea si falta (T21).
No muestra nunca las contraseñas ni sus hashes.

Los datos de demo (contactos, servicios, citas y tareas) se crean una sola vez, con fechas alrededor
del día en que se ejecuta. No pasan por la API, así que no dejan eventos de auditoría.
"""

import sys
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ENV_FILE, get_settings
from app.db import get_engine
from app.models import (
    Appointment,
    AppointmentStatus,
    CancelReason,
    Contact,
    ContactSource,
    ContactStatus,
    FollowUpTask,
    Role,
    Service,
    ServiceStaff,
    User,
)
from app.security import MIN_PASSWORD_LENGTH, hash_password, normalize_email

# Dominio reservado para ejemplos (RFC 2606): nunca pertenecerá a nadie real.
DEMO_EMAILS = {
    Role.ADMIN: "admin@demo.example.com",
    Role.RECEPTION: "recepcion@demo.example.com",
    Role.PROFESSIONAL: "profesional@demo.example.com",
    Role.CLIENT: "cliente@demo.example.com",
}

# Nombre, duración. Si ya existe un servicio con ese nombre, se usa ese.
DEMO_SERVICES = {"facial": ("Limpieza facial", 60), "peeling": ("Peeling suave", 45), "consulta": ("Consulta inicial", 30)}

# Teléfonos 555-01XX: reservados para ficción en EE. UU. El estado cuadra con las citas de abajo.
DEMO_CONTACTS = {
    "emma": ("Emma", "Carter", "+12125550101", ContactSource.INSTAGRAM, ContactStatus.NEW, None),
    "olivia": ("Olivia", "Bennett", "+12125550102", ContactSource.GOOGLE, ContactStatus.CONTACTED, "Prefiere WhatsApp por las tardes"),
    "liam": ("Liam", "Parker", "+12125550103", ContactSource.REFERRAL, ContactStatus.SCHEDULED, None),
    "sophia": ("Sophia", "Reed", "+12125550104", ContactSource.WEBSITE, ContactStatus.CLIENT, None),
    "noah": ("Noah", "Hayes", "+12125550105", ContactSource.FACEBOOK, ContactStatus.LOST, "Ha elegido otra clinica por ahora"),
}
CLIENT_KEY = "cliente"  # el contacto de la cuenta de cliente de demo

# Contacto, servicio, días desde hoy, hora de la clínica, estado. Una Programada pasada es una cita
# sin marcar: la de Liam deja probar la asistencia y la de la cuenta de cliente, «Sin confirmar».
DEMO_APPOINTMENTS = (
    (CLIENT_KEY, "facial", -14, 11, AppointmentStatus.COMPLETED),
    (CLIENT_KEY, "consulta", -2, 12, AppointmentStatus.SCHEDULED),
    (CLIENT_KEY, "peeling", 3, 11, AppointmentStatus.SCHEDULED),
    ("sophia", "facial", -7, 16, AppointmentStatus.COMPLETED),
    ("olivia", "peeling", -10, 15, AppointmentStatus.NO_SHOW),
    ("olivia", "consulta", -3, 10, AppointmentStatus.NO_SHOW),
    ("liam", "facial", -1, 10, AppointmentStatus.SCHEDULED),
    ("liam", "consulta", 1, 12, AppointmentStatus.SCHEDULED),
    ("liam", "facial", 5, 15, AppointmentStatus.CANCELLED),
)

# Contacto, días desde hoy, descripción, ¿del profesional? (solo con contactos con cita con él), ¿hecha?
DEMO_TASKS = (
    ("emma", 0, "Llamar para presentar los servicios", False, False),
    ("olivia", -2, "Volver a llamar tras la falta a la cita", False, False),
    ("liam", 1, "Confirmar preferencias antes de la visita", True, False),
    ("sophia", -1, "Preguntar si quiere otra sesion", False, True),
    ("noah", 60, "Reintentar el contacto en dos meses", False, False),
)


class DemoPasswords(BaseSettings):
    """CRM_DEMO_PASSWORD_ADMIN, _RECEPTION, _PROFESSIONAL y _CLIENT."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_prefix="CRM_DEMO_PASSWORD_", extra="ignore"
    )

    admin: SecretStr | None = None
    reception: SecretStr | None = None
    professional: SecretStr | None = None
    client: SecretStr | None = None


def check_passwords(passwords: DemoPasswords) -> list[str]:
    """Devuelve los problemas encontrados (sin revelar valores); vacía si todo es válido."""
    problems = []
    for role in Role:
        variable = f"CRM_DEMO_PASSWORD_{role.name}"
        secret = getattr(passwords, role.value)
        if secret is None or not secret.get_secret_value():
            problems.append(f"falta {variable}")
        elif len(secret.get_secret_value()) < MIN_PASSWORD_LENGTH:
            problems.append(f"{variable} tiene menos de {MIN_PASSWORD_LENGTH} caracteres")
    return problems


def demo_contact_id(session: Session) -> int:
    """El contacto ficticio de la cuenta de cliente (T21): lo crea si falta."""
    email = DEMO_EMAILS[Role.CLIENT]
    contact_id = session.scalar(select(Contact.id).where(Contact.email == email))
    if contact_id is not None:
        return contact_id
    contact = Contact(first_name="Demo", last_name="Cliente", email=email, source=ContactSource.OTHER)
    session.add(contact)
    session.flush()
    return contact.id


def upsert_demo_users(session: Session, passwords: DemoPasswords) -> list[str]:
    """Crea o actualiza las cuentas dentro de la sesión dada; devuelve un resumen."""
    summary = []
    for role, email in DEMO_EMAILS.items():
        email = normalize_email(email)
        password_hash = hash_password(getattr(passwords, role.value).get_secret_value())
        contact_id = demo_contact_id(session) if role == Role.CLIENT else None
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            session.add(User(email=email, password_hash=password_hash, role=role, active=True, contact_id=contact_id))
            summary.append(f"creada      {email} ({role.value})")
        else:
            user.password_hash = password_hash
            user.role = role
            user.active = True
            user.contact_id = contact_id
            summary.append(f"actualizada {email} ({role.value})")
    return summary


def _demo_service(session: Session, key: str, staff: User) -> Service:
    name, minutes = DEMO_SERVICES[key]
    service = session.scalar(select(Service).where(Service.name == name))
    if service is None:
        service = Service(name=name, duration_minutes=minutes)
        session.add(service)
        session.flush()
    if session.get(ServiceStaff, (service.id, staff.id)) is None:
        session.add(ServiceStaff(service_id=service.id, user_id=staff.id))
    return service


def _free_start(session: Session, staff: User, start: datetime, minutes: int) -> datetime:
    """La primera hora libre desde `start`: la BD no deja solapar a una persona (T17), y puede que
    ya tenga citas de otras pruebas."""
    length = timedelta(minutes=minutes)
    while session.scalar(
        select(Appointment.id).where(
            Appointment.staff_id == staff.id,
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.starts_at < start + length,
            Appointment.ends_at > start,
        )
    ):
        start += timedelta(hours=1)
    return start


def _local_instant(today: date, days: int, hour: int, zone: ZoneInfo) -> datetime:
    return datetime.combine(today + timedelta(days=days), time(hour), tzinfo=zone).astimezone(UTC)


def seed_demo_data(session: Session, now: datetime | None = None) -> str:
    """Contactos en cada estado, servicios, citas y tareas ficticios, para no enseñar un CRM vacío.

    Una sola vez: si el primero de los contactos ya existe, no toca nada, y lo que alguien haya
    cambiado durante una demo se queda como está. Necesita las cuentas de demo ya creadas.
    """
    if session.scalar(select(Contact.id).where(Contact.phone == DEMO_CONTACTS["emma"][2])) is not None:
        return "datos de demo: ya estaban, no se tocan"

    now = now or datetime.now(UTC)
    zone = get_settings().clinic_zone
    today = now.astimezone(zone).date()
    reception = session.scalar(select(User).where(User.email == DEMO_EMAILS[Role.RECEPTION]))
    staff = session.scalar(select(User).where(User.email == DEMO_EMAILS[Role.PROFESSIONAL]))

    contacts: dict[str, Contact] = {}
    for key, (first, last, phone, source, status, note) in DEMO_CONTACTS.items():
        contacts[key] = Contact(
            first_name=first,
            last_name=last,
            email=f"{key}@demo.example.com",
            phone=phone,
            source=source,
            status=status,
            note=note,
            created_by_id=reception.id,
            owner_id=reception.id,
        )
    session.add_all(contacts.values())
    contacts[CLIENT_KEY] = session.get(Contact, demo_contact_id(session))
    contacts[CLIENT_KEY].status = ContactStatus.CLIENT
    session.flush()

    services = {key: _demo_service(session, key, staff) for key in DEMO_SERVICES}
    for contact_key, service_key, days, hour, status in DEMO_APPOINTMENTS:
        service = services[service_key]
        start = _local_instant(today, days, hour, zone)
        # Una cancelada no ocupa la franja: no hay que buscarle hueco.
        if status != AppointmentStatus.CANCELLED:
            start = _free_start(session, staff, start, service.duration_minutes)
        session.add(
            Appointment(
                contact_id=contacts[contact_key].id,
                service_id=service.id,
                staff_id=staff.id,
                starts_at=start,
                ends_at=start + timedelta(minutes=service.duration_minutes),
                duration_minutes=service.duration_minutes,
                status=status,
                created_by_id=reception.id,
                attended_at=start if status in (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW) else None,
                cancel_reason=CancelReason.CLINIC if status == AppointmentStatus.CANCELLED else None,
            )
        )
        session.flush()

    for contact_key, days, description, for_staff, done in DEMO_TASKS:
        session.add(
            FollowUpTask(
                contact_id=contacts[contact_key].id,
                assigned_to_id=staff.id if for_staff else reception.id,
                due_on=today + timedelta(days=days),
                description=description,
                created_by_id=reception.id,
                completed_at=now if done else None,
                completed_by_id=reception.id if done else None,
            )
        )
    return (
        f"datos de demo: {len(DEMO_CONTACTS)} contactos, {len(DEMO_SERVICES)} servicios, "
        f"{len(DEMO_APPOINTMENTS)} citas y {len(DEMO_TASKS)} tareas"
    )


def main() -> int:
    passwords = DemoPasswords()
    problems = check_passwords(passwords)
    if problems:
        # Se valida todo antes de tocar la BD: o se aplican las cuatro cuentas o ninguna.
        print("No se ha modificado la BD. Revisa el .env de la raíz:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    with Session(get_engine()) as session, session.begin():
        summary = upsert_demo_users(session, passwords)
        summary.append(seed_demo_data(session))
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
