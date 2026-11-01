"""Infraestructura de pruebas con PostgreSQL real (T08).

Las pruebas que piden el fixture `db` usan la base crm_demo_test, dentro del mismo
contenedor de Docker que la BD de desarrollo, nunca crm_demo. Al empezar se crea si
no existe y se migra a la última versión. Cada prueba corre dentro de una transacción
que se deshace al terminar, así que no deja datos.

Si PostgreSQL no está disponible (Docker cerrado, sin .env), esas pruebas se saltan
con un aviso y las demás se ejecutan igual.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.auth import login_limiter
from app.config import get_settings
from app.db import get_db
from app.main import app

TEST_DB_SUFFIX = "_test"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _test_url() -> URL:
    url = get_settings().database_url
    return url.set(database=f"{url.database}{TEST_DB_SUFFIX}")


def _create_test_database(admin_url: URL, name: str) -> None:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name})
            if not exists:
                # El nombre sale de la configuración propia, no de datos externos.
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    try:
        url = _test_url()
    except Exception as exc:  # sin .env o configuración incompleta
        pytest.skip(f"Sin configuración de BD para las pruebas: {type(exc).__name__}")
    # Salvaguarda fuera del try: si fallara, debe parar las pruebas, no saltarlas.
    assert url.database.endswith(TEST_DB_SUFFIX), "las pruebas nunca usan la BD de desarrollo"
    try:
        _create_test_database(get_settings().database_url, url.database)
    except Exception as exc:  # Docker cerrado, credenciales...
        pytest.skip(f"PostgreSQL de pruebas no disponible: {type(exc).__name__}")

    engine = create_engine(url, connect_args={"connect_timeout": 3})
    with engine.begin() as conn:
        # Sin alembic.ini: su configuración de logging silenciaría los loggers de la API.
        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS_DIR))
        config.attributes["connection"] = conn
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """Sesión sobre crm_demo_test; todo lo que haga la prueba (incluidos commits) se deshace."""
    connection = test_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides[get_db] = _bd_de_desarrollo_prohibida
        session.close()
        outer.rollback()
        connection.close()


def _bd_de_desarrollo_prohibida() -> Iterator[Session]:
    raise RuntimeError("Esta prueba usa la BD sin el fixture `db`: pídelo para usar crm_demo_test")
    yield  # pragma: no cover


@pytest.fixture(autouse=True)
def proteger_bd_de_desarrollo() -> Iterator[None]:
    # Sin el fixture `db`, ninguna ruta puede llegar a crm_demo (la BD de desarrollo).
    app.dependency_overrides[get_db] = _bd_de_desarrollo_prohibida
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def limpiar_limitador_de_login() -> Iterator[None]:
    # El limitador es global del proceso: cada prueba empieza sin fallos acumulados.
    login_limiter.clear()
    yield
    login_limiter.clear()
