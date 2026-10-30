"""Punto de entrada de la API de crm-demo.

Arranque en desarrollo (desde backend/):
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload
"""

from fastapi import FastAPI

app = FastAPI(title="crm-demo API", version="0.1.0")


@app.get("/api/health", tags=["sistema"])
def health() -> dict[str, str]:
    """Indica que el proceso de la API está vivo.

    No consulta la base de datos (todavía no existe, T05). Más adelante
    servirá como comprobación de salud para Compose y el proxy.
    """
    return {"status": "ok"}
