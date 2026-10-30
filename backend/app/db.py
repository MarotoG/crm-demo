"""Conexión a PostgreSQL con SQLAlchemy (síncrono)."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # Un único Engine por proceso; gestiona el pool de conexiones.
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,  # descarta conexiones muertas (p. ej. tras reiniciar el contenedor)
        connect_args={"connect_timeout": 3},  # que /api/health/db no se quede colgado
    )


def check_database() -> None:
    """Lanza una excepción si PostgreSQL no responde a una consulta trivial."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
