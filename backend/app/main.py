"""Punto de entrada de la API de crm-demo.

Arranque en desarrollo (desde backend/):
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI, Response, status

from app.db import check_database

logger = logging.getLogger(__name__)

app = FastAPI(title="crm-demo API", version="0.1.0")


@app.get("/api/health", tags=["sistema"])
def health() -> dict[str, str]:
    """Indica que el proceso de la API está vivo.

    No consulta la base de datos a propósito: si PostgreSQL cae, la API
    sigue respondiendo aquí y el fallo se ve en /api/health/db.
    """
    return {"status": "ok"}


@app.get("/api/health/db", tags=["sistema"])
def health_db(response: Response) -> dict[str, str]:
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
