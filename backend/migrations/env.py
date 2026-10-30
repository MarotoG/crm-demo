from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# crm-demo: metadatos de los modelos, para que --autogenerate compare modelos y BD.
target_metadata = Base.metadata

# crm-demo: la URL sale del .env (vía app.config), nunca de alembic.ini.
database_url = get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Genera el SQL sin conectarse (alembic upgrade head --sql).
    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Se conecta a PostgreSQL y aplica las migraciones en una transacción.
    """
    connectable = create_engine(database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
