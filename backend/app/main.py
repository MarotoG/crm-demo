"""Punto de entrada de la API de crm-demo.

Arranque en desarrollo (desde backend/):
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload
"""

import logging
from collections.abc import Callable

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.auth_routes import router as auth_router
from app.db import get_database_check

logger = logging.getLogger(__name__)

app = FastAPI(title="crm-demo API", version="0.1.0")
app.include_router(auth_router)


@app.exception_handler(OperationalError)
def bd_no_disponible(request: Request, exc: OperationalError) -> JSONResponse:
    """Sin conexión con PostgreSQL en cualquier ruta: 503 sin detalles, no un 500 genérico."""
    logger.error("BD no disponible en %s %s: %s", request.method, request.url.path, type(exc.orig).__name__)
    return JSONResponse({"detail": "Servicio no disponible"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


@app.get("/api/health", tags=["sistema"])
def health() -> dict[str, str]:
    """Indica que el proceso de la API está vivo.

    No consulta la base de datos a propósito: si PostgreSQL cae, la API
    sigue respondiendo aquí y el fallo se ve en /api/health/db.
    """
    return {"status": "ok"}


@app.get("/api/health/db", tags=["sistema"])
def health_db(
    response: Response, check_database: Callable[[], None] = Depends(get_database_check)
) -> dict[str, str]:
    """Comprueba que la API puede consultar PostgreSQL."""
    try:
        check_database()
    except Exception:
        # Cualquier fallo (BD apagada, credenciales, falta .env) se registra en el
        # log del servidor; al cliente no se le dan detalles internos.
        logger.exception("Fallo en la comprobación de la base de datos")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}
