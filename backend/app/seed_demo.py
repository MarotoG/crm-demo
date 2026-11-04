"""Crea o actualiza las cuentas de demo, una por rol (T07).

Uso, desde backend/ y con la BD migrada:
    .venv\\Scripts\\python.exe -m app.seed_demo

Las contraseñas no están en el código: se leen de CRM_DEMO_PASSWORD_<ROL> en el
.env de la raíz (no versionado). Es idempotente: crea las cuentas que falten y, en
las existentes, aplica la contraseña actual del .env, el rol y las reactiva. La cuenta de
cliente queda vinculada a un contacto ficticio, que se crea si falta (T21).
No muestra nunca las contraseñas ni sus hashes.
"""

import sys

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ENV_FILE
from app.db import get_engine
from app.models import Contact, ContactSource, Role, User
from app.security import MIN_PASSWORD_LENGTH, hash_password, normalize_email

# Dominio reservado para ejemplos (RFC 2606): nunca pertenecerá a nadie real.
DEMO_EMAILS = {
    Role.ADMIN: "admin@demo.example.com",
    Role.RECEPTION: "recepcion@demo.example.com",
    Role.PROFESSIONAL: "profesional@demo.example.com",
    Role.CLIENT: "cliente@demo.example.com",
}


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
    contact_id = session.scalar(
        select(Contact.id).where(Contact.first_name == "Demo", Contact.last_name == "Cliente", Contact.email == email)
    )
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
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
