"""Conexión a PostgreSQL con SQLAlchemy (síncrono)."""

from collections.abc import Callable, Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # Un único Engine por proceso; gestiona el pool de conexiones.
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,  # descarta conexiones muertas (p. ej. tras reiniciar el contenedor)
        connect_args={"connect_timeout": 3},  # que /api/health/db no se quede colgado
    )


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión de BD por petición, cerrada al terminar.

    Las rutas la reciben con Depends(get_db) en vez de crearla ellas mismas; así las
    pruebas pueden sustituirla (app.dependency_overrides) por una BD de pruebas.
    """
    with Session(get_engine()) as session:
        yield session


def check_database() -> None:
    """Lanza una excepción si PostgreSQL no responde a una consulta trivial.

    Todo ocurre aquí dentro (también leer el .env), para que /api/health/db pueda
    convertir cualquier fallo en un 503.
    """
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))


def get_database_check() -> Callable[[], None]:
    """Dependencia de /api/health/db; las pruebas la sustituyen por una que falla o no."""
    return check_database
