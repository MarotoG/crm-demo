"""Usuario de BD con el que se conecta la API en producción (T28): trabaja con los datos y nada más.

Uso, después de las migraciones y conectado como dueño de la BD:
    python -m app.db_roles

Es idempotente: crea el usuario si falta, le aplica la contraseña de CRM_APP_DB_PASSWORD y vuelve a
dar los permisos, de modo que cada tabla nueva de una migración los recibe. Puede leer y escribir en
las tablas, pero no cambiar su estructura ni tocar las versiones de las migraciones, y en la auditoría
solo puede añadir y leer: no puede modificar ni borrar eventos. Quien administre la BD, sí.
"""

import sys

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Connection, text

from app.config import ENV_FILE
from app.db import get_engine


class AppRoleSettings(BaseSettings):
    """CRM_APP_DB_USER y CRM_APP_DB_PASSWORD."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="CRM_APP_DB_", extra="ignore", hide_input_in_errors=True)

    user: str = "crm_app"
    password: SecretStr


def apply_app_role(conn: Connection, role: str, password: str) -> None:
    """Crea o actualiza el usuario y fija sus permisos, dentro de la transacción de `conn`."""
    # La contraseña sale de aquí ya convertida en un verificador SCRAM: PostgreSQL nunca la recibe en
    # claro, así que tampoco podría aparecer en su log si la sentencia fallara.
    verifier = conn.connection.driver_connection.pgconn.encrypt_password(
        password.encode(), role.encode(), b"scram-sha-256"
    ).decode()
    name = conn.dialect.identifier_preparer.quote(role)
    exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})
    verb = "ALTER" if exists else "CREATE"
    conn.exec_driver_sql(f"{verb} ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{verifier}'")
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {name}"))
    conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {name}"))
    conn.execute(text(f"REVOKE ALL ON alembic_version FROM {name}"))
    conn.execute(text(f"REVOKE UPDATE, DELETE ON audit_events FROM {name}"))


def main() -> int:
    try:
        settings = AppRoleSettings()
    except ValueError:
        print("Falta CRM_APP_DB_PASSWORD.", file=sys.stderr)
        return 1
    with get_engine().begin() as conn:
        apply_app_role(conn, settings.user, settings.password.get_secret_value())
    print(f"Permisos aplicados al usuario {settings.user}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
